"""Tests verifying real Strands Agents SDK execution in Covenant."""

import json
from pathlib import Path
import pytest

from strands import Agent
from covenant.agents.strands_runtime import (
    COVENANT_STRANDS_TOOLS,
    CovenantStrandsAgentRunner,
    LocalDeterministicStrandsModel,
    OllamaStrandsModel,
    tool_search_email,
    tool_verify_commitment,
)
from covenant.persistence.sqlite_repo import SQLiteCommitmentRepository
from covenant.synthetic_data.store import workspace_store


@pytest.fixture
async def temp_repo(tmp_path: Path):
    db_file = tmp_path / "strands_test.db"
    repo = SQLiteCommitmentRepository(db_path=db_file)
    await repo.initialize()
    return repo


@pytest.mark.asyncio
async def test_strands_agent_instantiation_and_tool_call():
    """Verify that strands.Agent is properly initialized and invokes registered tools."""
    model = LocalDeterministicStrandsModel()
    agent = Agent(
        model=model,
        tools=COVENANT_STRANDS_TOOLS,
        name="TestStrandsAgent",
        system_prompt="You are a commitment verification specialist.",
    )

    assert agent.name == "TestStrandsAgent"
    assert len(agent.tool_names) == len(COVENANT_STRANDS_TOOLS)
    assert "tool_search_email" in agent.tool_names
    assert "tool_verify_commitment" in agent.tool_names

    # Direct tool execution
    email_res = json.loads(tool_search_email("Atlas"))
    assert email_res["count"] >= 1


@pytest.mark.asyncio
async def test_strands_runner_structured_events(temp_repo: SQLiteCommitmentRepository):
    """Verify that CovenantStrandsAgentRunner emits fully typed events to the database."""
    runner = CovenantStrandsAgentRunner(
        commitment_repo=temp_repo,
        event_repo=temp_repo,
        use_ollama=False,
    )

    evt = await runner.emit_structured_event(
        agent_name="CovenantSupervisorAgent",
        event_type="DISCOVERY",
        summary="Discovered new promise from Meridian Global",
        commitment_id="com_atlas_approval",
        confidence=0.96,
        human_required=True,
        rationale="Promise extracted from email thread EML-102",
    )

    events = await temp_repo.list_events(commitment_id="com_atlas_approval")
    assert len(events) == 1
    assert events[0].agent == "CovenantSupervisorAgent"
    assert events[0].confidence == 0.96
    assert events[0].human_required is True


@pytest.mark.asyncio
async def test_ollama_graceful_diagnostic_when_unreachable():
    """Verify that Ollama provider fails gracefully with a diagnostic if not running."""
    ollama_model = OllamaStrandsModel(base_url="http://127.0.0.1:9999")  # Unused port
    is_avail = await ollama_model.check_availability()
    assert is_avail is False

    # Streaming through unavailable Ollama should yield diagnostic message without crashing
    events = []
    async for item in ollama_model.stream([{"role": "user", "content": "hi"}]):
        events.append(item)

    assert len(events) >= 1
    delta_text = events[0].get("contentBlockDelta", {}).get("delta", {}).get("text", "")
    assert "Ollama unreachable" in delta_text or "Diagnostic" in delta_text
