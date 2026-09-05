"""Tests for Bedrock-Ready Strands Model Provider in Covenant."""

import os
from unittest.mock import AsyncMock, patch
import pytest
from strands.models.bedrock import BedrockModel

from covenant.agents.base import AgentContext
from covenant.agents.commitment import CommitmentAgent
from covenant.agents.evidence import EvidenceAgent
from covenant.agents.policy import PolicyAgent
from covenant.agents.resolution import ResolutionAgent
from covenant.agents.strands_runtime import (
    CovenantStrandsAgentRunner,
    LocalDeterministicStrandsModel,
    OllamaStrandsModel,
)
from covenant.agents.supervisor import SupervisorAgent
from covenant.agents.verification import VerificationAgent
from covenant.domain.enums import (
    ActionStatus,
    ActionType,
    CommitmentStatus,
    ObligationDirection,
    PolicyDecisionType,
    RiskLevel,
)
from covenant.domain.models import Commitment, Party, ProposedAction
from covenant.llm import (
    BedrockModelProvider,
    ChatMessage,
    DeterministicFallbackProvider,
    OllamaModelProvider,
    get_model_provider,
    get_strands_model,
)
from covenant.persistence.sqlite_repo import SQLiteCommitmentRepository

from covenant.state_machine.exceptions import InvalidStateTransitionError
from covenant.state_machine.machine import CommitmentStateMachine


def test_deterministic_provider_remains_default():
    """Default provider must be deterministic and offline-safe without environment overrides."""
    provider = get_model_provider()
    assert isinstance(provider, DeterministicFallbackProvider)
    assert provider.model_name == "deterministic-local"

    strands_model = get_strands_model()
    assert isinstance(strands_model, LocalDeterministicStrandsModel)
    assert strands_model.config["model_id"] == "covenant-local-deterministic"


def test_ollama_local_provider_selection():
    """Ollama/local provider can be explicitly selected."""
    provider = get_model_provider("ollama")
    assert isinstance(provider, OllamaModelProvider)
    assert "llama3" in provider.model_name or "ollama" in provider.model_name.lower()

    strands_model = get_strands_model("ollama")
    assert isinstance(strands_model, OllamaStrandsModel)


def test_bedrock_provider_instantiation_offline():
    """BedrockModelProvider must construct correctly offline without invoking AWS APIs."""
    bp = BedrockModelProvider(
        model_id="anthropic.claude-3-haiku-20240307-v1:0",
        region_name="us-east-1",
        temperature=0.2,
        max_tokens=1024,
    )
    assert isinstance(bp.strands_model, BedrockModel)
    assert bp.model_name == "bedrock/anthropic.claude-3-haiku-20240307-v1:0"
    assert bp.strands_model.config["model_id"] == "anthropic.claude-3-haiku-20240307-v1:0"
    assert bp.strands_model.config.get("temperature") == 0.2
    assert bp.strands_model.config.get("max_tokens") == 1024


def test_provider_selection_env_override(monkeypatch):
    """When COVENANT_MODEL_PROVIDER=bedrock is set, factory selects BedrockModel."""
    monkeypatch.setenv("COVENANT_MODEL_PROVIDER", "bedrock")
    monkeypatch.setenv("COVENANT_BEDROCK_MODEL_ID", "anthropic.claude-3-haiku-20240307-v1:0")
    monkeypatch.setenv("COVENANT_AWS_REGION", "us-east-1")

    provider = get_model_provider()
    assert isinstance(provider, BedrockModelProvider)
    assert provider.model_id == "anthropic.claude-3-haiku-20240307-v1:0"

    strands_model = get_strands_model()
    assert isinstance(strands_model, BedrockModel)
    assert strands_model.config["model_id"] == "anthropic.claude-3-haiku-20240307-v1:0"


def test_invalid_provider_fails_deterministically():
    """Unknown provider names must fail with an informative configuration error."""
    with pytest.raises(ValueError) as exc_info:
        get_model_provider("unsupported_cloud")
    assert "Invalid model provider 'unsupported_cloud'" in str(exc_info.value)
    assert "deterministic" in str(exc_info.value)

    with pytest.raises(ValueError) as exc_info:
        get_strands_model("unsupported_cloud")
    assert "Invalid model provider 'unsupported_cloud'" in str(exc_info.value)


def test_missing_bedrock_model_id_produces_clear_error(monkeypatch):
    """Attempting to initialize Bedrock without a model_id fails deterministically."""
    monkeypatch.delenv("COVENANT_BEDROCK_MODEL_ID", raising=False)

    with pytest.raises(ValueError) as exc_info:
        BedrockModelProvider(model_id=None)
    assert "Bedrock provider requires a non-empty model_id" in str(exc_info.value)


@pytest.mark.asyncio
async def test_bedrock_chat_delegation():
    """Verifies BedrockModelProvider.chat() delegates streaming to native Strands BedrockModel."""
    bp = BedrockModelProvider(model_id="anthropic.claude-3-haiku-20240307-v1:0")

    async def fake_stream(*args, **kwargs):
        yield {"contentBlockDelta": {"delta": {"text": "Deliverable "}}}
        yield {"contentBlockDelta": {"delta": {"text": "corroborated."}}}

    bp.strands_model.stream = fake_stream

    response = await bp.chat([
        ChatMessage(role="system", content="You are Covenant's analyst."),
        ChatMessage(role="user", content="Verify milestone status."),
    ])

    assert response.content == "Deliverable corroborated."
    assert "bedrock" in response.model_name


def test_all_six_agents_receive_selected_model(tmp_path):
    """All six agent roles receive the selected Bedrock model without architectural changes."""
    bp = BedrockModelProvider(model_id="anthropic.claude-3-haiku-20240307-v1:0")
    db_path = tmp_path / "test_agents.db"
    repo = SQLiteCommitmentRepository(db_path)

    sup = SupervisorAgent(
        llm=bp,
        commitment_repo=repo,
        event_repo=repo,
    )


    # 1. SupervisorAgent
    assert sup.llm is bp

    # 2. CommitmentAgent
    assert sup.commitment_agent.llm is bp
    assert isinstance(sup.commitment_agent.strands_agent.model, BedrockModel)

    # 3. EvidenceAgent
    assert sup.evidence_agent.llm is bp
    assert isinstance(sup.evidence_agent.strands_agent.model, BedrockModel)

    # 4. ResolutionAgent
    assert sup.resolution_agent.llm is bp

    # 5. PolicyAgent
    assert sup.policy_agent.llm is bp

    # 6. VerificationAgent
    assert sup.verification_agent.llm is bp

    # 7. CovenantStrandsAgentRunner receives the model
    runner = CovenantStrandsAgentRunner(
        commitment_repo=repo,
        event_repo=repo,
        model=bp.strands_model,
    )
    assert runner.supervisor_agent.model is bp.strands_model
    assert runner.evidence_agent.model is bp.strands_model
    assert runner.verification_agent.model is bp.strands_model


@pytest.mark.asyncio
async def test_bedrock_provider_cannot_bypass_governance_or_self_authorize(tmp_path):
    """
    Governance boundary: Even if Bedrock model produces text asserting 'APPROVED' or 'RESOLVED',
    the model has zero authority to mutate state. Runtime state machine and policy remain authoritative.
    """
    bp = BedrockModelProvider(model_id="anthropic.claude-3-haiku-20240307-v1:0")
    db_path = tmp_path / "gov_test.db"
    repo = SQLiteCommitmentRepository(db_path)
    await repo.initialize()

    # Create commitment in ACTION_READY state with proposed action
    c = Commitment(
        id="com_gov_bedrock_01",
        title="Test Deliverable",
        description="Delivery of formal Phase 2 sign-off report.",
        promisor=Party(name="Vendor"),
        promisee=Party(name="Client"),
        status=CommitmentStatus.ACTION_READY,
        risk=RiskLevel.HIGH,
        obligation_direction=ObligationDirection.THEY_OWE_US,
    )


    await repo.save(c)

    # 1. Model text cannot bypass state machine
    with pytest.raises(InvalidStateTransitionError):
        # Illegally attempt to skip directly from DISCOVERED to RESOLVED
        CommitmentStateMachine.transition(
            commitment=c,
            target_state=CommitmentStatus.RESOLVED,
            agent_name="BedrockModel",
            reason="Model hallucinated completion without verification.",
        )

    # 2. Policy agent deterministically requires human approval for high risk actions
    policy_agent = PolicyAgent(llm=bp, commitment_repo=repo, event_repo=repo)
    c.next_action = ProposedAction(
        id="act_gov_01",
        commitment_id=c.id,
        action_type=ActionType.FOLLOWUP_EMAIL,
        title="Send Escalation Notice",
        description="Notify client of overdue sign-off and downstream delay.",
        status=ActionStatus.PROPOSED,
        risk=RiskLevel.HIGH,
    )
    await repo.save(c)



    result = await policy_agent.run(AgentContext(session_id="s1", target_commitment_id=c.id))
    assert result.success is True
    assert result.data["decision"]["requires_human_approval"] is True

    updated_c = await repo.get_by_id(c.id)
    assert updated_c.status == CommitmentStatus.AWAITING_APPROVAL
    assert updated_c.next_action.status == ActionStatus.AWAITING_APPROVAL


