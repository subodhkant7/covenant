"""Tests for Strands-powered commitment extraction in Covenant (Step 10).

Verifies that CommitmentAgent:
1. Distinguishes binding commitments from suggestions, questions, completed actions, and notices.
2. Produces valid structured CommitmentExtractionResult models.
3. Preserves raw evidence provenance without hallucinated facts.
4. Integrates with Strands Agent tools (search_email, search_contract).
5. Provides deterministic fallback when LLM is offline without altering authority boundaries.
"""

from datetime import datetime, timezone
import json
from pathlib import Path
import pytest
from covenant.agents.commitment import CommitmentAgent
from covenant.domain.enums import StatementType, ObligationDirection, CommitmentCategory
from covenant.domain.models import CommitmentExtractionResult, Party
from covenant.llm.provider import ChatMessage
from covenant.llm.ollama_provider import DeterministicFallbackProvider
from covenant.persistence.sqlite_repo import SQLiteCommitmentRepository
from covenant.synthetic_data.store import workspace_store


@pytest.fixture
async def isolated_repo(tmp_path: Path):
    """Isolated SQLite repository for testing commitment extraction and events."""
    db_file = tmp_path / "test_strands.db"
    repo = SQLiteCommitmentRepository(db_path=db_file)
    await repo.initialize()
    return repo


@pytest.fixture
def commitment_agent(isolated_repo):
    workspace_store.reset()
    return CommitmentAgent(commitment_repo=isolated_repo, event_repo=isolated_repo)


def test_strands_agent_configured(commitment_agent):
    """Verify CommitmentAgent instantiates a real Strands agent with Covenant tools."""
    assert commitment_agent.strands_agent is not None
    # Verify tools registered with the Strands agent
    tool_names = commitment_agent.strands_agent.tool_names
    assert any("search_email" in t for t in tool_names)
    assert any("search_contract" in t for t in tool_names)
    assert any("contract" in t for t in tool_names)


def test_structured_extraction_result_schema():
    """Verify CommitmentExtractionResult Pydantic schema validation."""
    result = CommitmentExtractionResult(
        is_commitment=True,
        statement_type=StatementType.COMMITMENT,
        confidence=0.95,
        rationale="Clear promisory obligation with explicit deadline.",
        promisor=Party(name="Sarah Jenkins", organization="Atlas Corp", role="PROMISOR"),
        promisee=Party(name="Alex North", organization="Northstar Studio", role="PROMISEE"),
        obligation_direction=ObligationDirection.THEY_OWE_US,
        promised_deliverable="SOC 2 Type II audit report",
        due_date=datetime(2026, 9, 5, 17, 0, 0, tzinfo=timezone.utc),
        category=CommitmentCategory.CLIENT_APPROVAL,
        source_evidence_ids=["EML-102", "CTR-001"],
    )
    assert result.is_commitment is True
    assert result.statement_type == StatementType.COMMITMENT
    assert result.confidence == 0.95
    assert result.promisor.name == "Sarah Jenkins"
    assert result.source_evidence_ids == ["EML-102", "CTR-001"]


@pytest.mark.asyncio
async def test_distinguish_statement_types(commitment_agent):
    """Verify extraction distinguishes commitments from non-commitments."""
    # 1. Clear commitment
    res_com = await commitment_agent.extract_statement(
        text="We will provide the SOC 2 Type II audit report by September 5, 2026, at 5:00 PM EST.",
        sender="sarah.jenkins@atlascorp.com",
        recipient="alex.north@covenant-client.com",
        source_id="EML-TEST-1",
    )
    assert res_com.statement_type == StatementType.COMMITMENT
    assert res_com.is_commitment is True
    assert len(res_com.promised_deliverable) > 0

    # 2. Suggestion
    res_sug = await commitment_agent.extract_statement(
        text="Maybe we should consider upgrading our staging environment next month?",
        sender="alex.north@covenant-client.com",
        recipient="frank.miller@apexpartners.com",
        source_id="EML-TEST-2",
    )
    assert res_sug.statement_type == StatementType.SUGGESTION
    assert res_sug.is_commitment is False

    # 3. Question
    res_q = await commitment_agent.extract_statement(
        text="Could you please send over the latest status update regarding the deliverables?",
        sender="alex.north@covenant-client.com",
        recipient="sarah.jenkins@atlascorp.com",
        source_id="EML-TEST-3",
    )
    assert res_q.statement_type == StatementType.QUESTION
    assert res_q.is_commitment is False

    # 4. Completed action
    res_act = await commitment_agent.extract_statement(
        text="I have already uploaded the final signed statement to the secure portal.",
        sender="rachel.cole@beaconcorp.com",
        recipient="alex.north@covenant-client.com",
        source_id="EML-TEST-4",
    )
    assert res_act.statement_type == StatementType.COMPLETED_ACTION
    assert res_act.is_commitment is False

    # 5. Non-binding statement
    res_notice = await commitment_agent.extract_statement(
        text="FYI, tracking number #TRK-9821 has been assigned for reference only.",
        sender="support@logistics.com",
        recipient="alex.north@covenant-client.com",
        source_id="EML-TEST-5",
    )
    assert res_notice.statement_type == StatementType.NON_BINDING_STATEMENT
    assert res_notice.is_commitment is False


@pytest.mark.asyncio
async def test_atlas_scenario_eml101_vs_eml102(commitment_agent):
    """Verify Atlas scenario: EML-101 inquiry is rejected; EML-102 commitment is extracted."""
    # EML-101: Alex asks for status -> Not a commitment
    res_101 = await commitment_agent.extract_statement(
        text="Sarah, please let us know the status of the SOC 2 Type II audit report.",
        sender="alex.north@covenant-client.com",
        recipient="sarah.jenkins@atlascorp.com",
        source_id="EML-101",
    )
    assert res_101.statement_type in (StatementType.QUESTION, StatementType.SUGGESTION)
    assert res_101.is_commitment is False

    # EML-102: Sarah explicitly commits -> Valid commitment corroborated by contract
    res_102 = await commitment_agent.extract_statement(
        text="Alex, confirming that per Section 4.2 of our agreement, we will provide the SOC 2 Type II audit report by September 5, 2026, at 5:00 PM EST.",
        sender="sarah.jenkins@atlascorp.com",
        recipient="alex.north@covenant-client.com",
        source_id="EML-102",
    )
    assert res_102.statement_type == StatementType.COMMITMENT
    assert res_102.is_commitment is True
    assert res_102.promisor.name == "Sarah Jenkins"
    assert res_102.obligation_direction == ObligationDirection.THEY_OWE_US
    assert "SOC 2" in res_102.promised_deliverable
    assert "EML-102" in res_102.source_evidence_ids


@pytest.mark.asyncio
async def test_we_owe_them_direction(commitment_agent):
    """Verify that outbound obligations (WE_OWE_THEM) are correctly classified."""
    res = await commitment_agent.extract_statement(
        text="Frank, We will release the final milestone payment of $45,000 by September 15, 2026, once deliverables are approved.",
        sender="alex.north@covenant-client.com",
        recipient="frank.miller@apexpartners.com",
        source_id="EML-401",
    )
    assert res.statement_type == StatementType.COMMITMENT
    assert res.is_commitment is True
    assert res.promisor.name == "Alex North"
    assert res.promisee.name == "Frank Miller"
    assert res.obligation_direction == ObligationDirection.WE_OWE_THEM
    assert "45,000" in res.promised_deliverable or "milestone payment" in res.promised_deliverable.lower()


@pytest.mark.asyncio
async def test_raw_evidence_provenance_preserved(commitment_agent):
    """Verify that extracted commitments preserve raw source evidence citations."""
    result = await commitment_agent.run()
    assert result.success is True

    commitments = await commitment_agent.commitment_repo.list_all()
    # Find the Atlas commitment
    atlas_com = next((c for c in commitments if c.id == "com_atlas_approval"), None)
    assert atlas_com is not None

    # Provenance check: source evidence exists in synthetic data
    ev_sources = [ev.source_id for ev in atlas_com.evidence_references]
    assert "EML-102" in ev_sources

    # Check that contract clause was referenced
    clause_ev = next((ev for ev in atlas_com.evidence_references if "CTR-" in ev.source_id or "Section" in ev.source_id or "clause" in ev.source_id.lower()), None)
    assert clause_ev is not None or "MSA Section 4.2" in atlas_com.description

    # Audit events verify filtering took place
    events = await commitment_agent.event_repo.list_events()
    filtered_events = [e for e in events if e.action_name == "DISCOVERY_FILTERED"]
    assert len(filtered_events) > 0
    assert any(e.metadata.get("source_id") == "EML-101" for e in filtered_events)


@pytest.mark.asyncio
async def test_fallback_provider_semantics():
    """Verify DeterministicFallbackProvider produces valid structured JSON without side effects."""
    provider = DeterministicFallbackProvider()
    response = await provider.chat(
        [ChatMessage(role="user", content="Extract commitment from EML-102: We will provide the SOC 2 report by September 5, 2026.")],
        json_mode=True,
    )
    assert response is not None
    data = json.loads(response.content)
    assert "statement_type" in data
    assert data["statement_type"] == "COMMITMENT"
    assert data["is_commitment"] is True
    assert "promised_deliverable" in data
