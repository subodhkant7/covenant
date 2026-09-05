"""Tests for Covenant bounded autonomous monitoring cycle."""

import asyncio
from datetime import datetime, timezone
from pathlib import Path
import pytest

from agent_runtime.core.contracts.context import Task
from agent_runtime.core.contracts.tool import ToolRequest
from agent_runtime.core.state.enums import ApprovalState
from covenant.agents.base import AgentContext
from covenant.agents.supervisor import SupervisorAgent
from covenant.domain.enums import (
    ActionStatus,
    ActionType,
    CommitmentCategory,
    CommitmentStatus,
    ObligationDirection,
    RiskLevel,
)
from covenant.domain.models import Commitment, Party, ProposedAction
from covenant.llm.ollama_provider import DeterministicFallbackProvider
from covenant.persistence.sqlite_repo import SQLiteCommitmentRepository
from covenant.synthetic_data.store import workspace_store
from covenant.tools import initialize_tools
from covenant_runtime_bridge.bootstrap import CovenantRuntimeBootstrap


@pytest.fixture
async def supervisor_env(tmp_path: Path):
    """Provides an isolated SupervisorAgent with persistent test repository and runtime."""
    test_db = tmp_path / "test_supervisor.db"
    repo = SQLiteCommitmentRepository(db_path=test_db)
    await repo.initialize()

    workspace_store.reset()
    runtime_env = CovenantRuntimeBootstrap.assemble()
    tools = initialize_tools()
    llm = DeterministicFallbackProvider()

    supervisor = SupervisorAgent(
        llm=llm,
        tools=tools,
        commitment_repo=repo,
        event_repo=repo,
        runtime_env=runtime_env,
    )
    return supervisor, repo, runtime_env


@pytest.mark.asyncio
async def test_monitoring_cycle_discovers_new_commitment(supervisor_env):
    """Verifies that the autonomous cycle discovers commitments from workspace sources."""
    supervisor, repo, _ = supervisor_env

    res = await supervisor.run_monitoring_cycle()
    assert res.success is True

    # Atlas commitment discovered
    atlas = await repo.get_by_id("com_atlas_approval")
    assert atlas is not None
    assert atlas.title == "Meridian Global Phase 2 Deliverable Formal Sign-Off"
    assert len(atlas.evidence_references) >= 2


@pytest.mark.asyncio
async def test_monitoring_cycle_recalculates_risk(supervisor_env):
    """Verifies that risk and drift are recalculated deterministically during the cycle."""
    supervisor, repo, _ = supervisor_env

    await supervisor.run_monitoring_cycle()
    atlas = await repo.get_by_id("com_atlas_approval")
    assert atlas is not None

    # Atlas has imminent deadline / overdue and is calculated at HIGH or MEDIUM risk
    assert atlas.risk in [RiskLevel.HIGH, RiskLevel.MEDIUM]
    assert atlas.is_overdue is True or atlas.status == CommitmentStatus.AWAITING_APPROVAL


@pytest.mark.asyncio
async def test_monitoring_cycle_generates_action_proposal(supervisor_env):
    """Verifies that an operational remedy is proposed for drifted commitments."""
    supervisor, repo, _ = supervisor_env

    await supervisor.run_monitoring_cycle()
    atlas = await repo.get_by_id("com_atlas_approval")
    assert atlas is not None
    assert atlas.next_action is not None
    assert atlas.next_action.action_type == ActionType.FOLLOWUP_EMAIL
    assert "Sarah" in atlas.next_action.description or "sjenkins" in (atlas.next_action.recipient or "")


@pytest.mark.asyncio
async def test_monitoring_cycle_respects_policy(supervisor_env):
    """Verifies that PolicyAgent is invoked and evaluates rules against proposed actions."""
    supervisor, repo, _ = supervisor_env

    await supervisor.run_monitoring_cycle()
    atlas = await repo.get_by_id("com_atlas_approval")
    assert atlas is not None
    assert atlas.next_action is not None
    assert atlas.next_action.requires_human_approval is True
    assert "RULE-EXT-COMM" in (atlas.next_action.approval_reason or "")


@pytest.mark.asyncio
async def test_monitoring_cycle_does_not_bypass_human_approval(supervisor_env):
    """Verifies that commitments requiring approval halt at AWAITING_APPROVAL without side effects."""
    supervisor, repo, _ = supervisor_env

    await supervisor.run_monitoring_cycle()
    atlas = await repo.get_by_id("com_atlas_approval")
    assert atlas is not None

    # The commitment MUST halt at AWAITING_APPROVAL
    assert atlas.status == CommitmentStatus.AWAITING_APPROVAL
    assert atlas.next_action.status == ActionStatus.AWAITING_APPROVAL
    # No tool execution occurred
    assert atlas.next_action.executed_at is None


@pytest.mark.asyncio
async def test_monitoring_cycle_is_idempotent(supervisor_env):
    """Verifies that running multiple consecutive monitoring cycles does not duplicate state or actions."""
    supervisor, repo, _ = supervisor_env

    # Cycle 1
    await supervisor.run_monitoring_cycle()
    atlas_1 = await repo.get_by_id("com_atlas_approval")
    action_id_1 = atlas_1.next_action.id
    status_1 = atlas_1.status

    events_1 = await repo.list_events(commitment_id="com_atlas_approval")
    discovery_count_1 = sum(1 for e in events_1 if e.action_name == "DISCOVER_COMMITMENT")
    assert discovery_count_1 == 1

    # Cycle 2: identical workspace evidence
    await supervisor.run_monitoring_cycle()
    atlas_2 = await repo.get_by_id("com_atlas_approval")

    # Proposal ID and status remain unchanged
    assert atlas_2.next_action.id == action_id_1
    assert atlas_2.status == status_1

    # No duplicate discovery events
    events_2 = await repo.list_events(commitment_id="com_atlas_approval")
    discovery_count_2 = sum(1 for e in events_2 if e.action_name == "DISCOVER_COMMITMENT")
    assert discovery_count_2 == 1


@pytest.mark.asyncio
async def test_monitoring_cycle_does_not_clobber_advanced_state(supervisor_env):
    """Verifies that commitments in EXECUTING, VERIFYING, or RESOLVED are not clobbered back to OVERDUE."""
    supervisor, repo, _ = supervisor_env

    # 1. Run cycle to generate proposal
    await supervisor.run_monitoring_cycle()
    atlas = await repo.get_by_id("com_atlas_approval")
    assert atlas.status == CommitmentStatus.AWAITING_APPROVAL

    # 2. Simulate dispatch to VERIFYING
    atlas.status = CommitmentStatus.VERIFYING
    atlas.next_action.status = ActionStatus.COMPLETED
    atlas.next_action.executed_at = datetime.now(timezone.utc)
    await repo.save(atlas)

    # 3. Re-run monitoring cycle
    await supervisor.run_monitoring_cycle()
    reloaded = await repo.get_by_id("com_atlas_approval")

    # State must remain VERIFYING, never reverted to OVERDUE or DISCOVERED
    assert reloaded.status == CommitmentStatus.VERIFYING
    assert reloaded.next_action.status == ActionStatus.COMPLETED


@pytest.mark.asyncio
async def test_monitoring_cycle_rechecks_verifying_commitment(supervisor_env):
    """Verifies that commitments in VERIFYING are independently inspected by VerificationAgent."""
    supervisor, repo, _ = supervisor_env

    # Setup commitment in VERIFYING
    await supervisor.run_monitoring_cycle()
    atlas = await repo.get_by_id("com_atlas_approval")
    atlas.status = CommitmentStatus.VERIFYING
    atlas.next_action.status = ActionStatus.COMPLETED
    await repo.save(atlas)

    # Cycle runs verification pass, but no counterparty reply yet
    await supervisor.run_monitoring_cycle()
    reloaded = await repo.get_by_id("com_atlas_approval")

    assert reloaded.status == CommitmentStatus.VERIFYING
    assert reloaded.verification_result is not None
    assert reloaded.verification_result.is_verified is False


@pytest.mark.asyncio
async def test_monitoring_cycle_reaches_resolved_after_fresh_evidence(supervisor_env):
    """Verifies that when fresh counterparty proof arrives, the autonomous cycle resolves the commitment."""
    supervisor, repo, _ = supervisor_env

    # 1. Initialize and move to VERIFYING
    await supervisor.run_monitoring_cycle()
    atlas = await repo.get_by_id("com_atlas_approval")
    atlas.status = CommitmentStatus.VERIFYING
    atlas.next_action.status = ActionStatus.COMPLETED
    await repo.save(atlas)

    # 2. World changes: counterparty provides signed approval
    workspace_store.simulate_client_reply("com_atlas_approval", fulfilled=True)

    # 3. Next autonomous cycle automatically detects fresh evidence and resolves
    await supervisor.run_monitoring_cycle()
    final_com = await repo.get_by_id("com_atlas_approval")

    assert final_com.status == CommitmentStatus.RESOLVED
    assert final_com.resolution_timestamp is not None
    assert final_com.verification_result is not None
    assert final_com.verification_result.is_verified is True
    assert final_com.verification_result.business_outcome_verified is True


@pytest.mark.asyncio
async def test_monitoring_cycle_records_audit_events(supervisor_env):
    """Verifies that cycle start, agent operations, and cycle completion are recorded in audit telemetry."""
    supervisor, repo, _ = supervisor_env

    await supervisor.run_monitoring_cycle()
    all_events = await repo.list_events(limit=100)

    event_names = [e.action_name for e in all_events]
    assert "SUPERVISOR_CYCLE_START" in event_names
    assert "DISCOVER_COMMITMENT" in event_names
    assert "CORROBORATE_EVIDENCE" in event_names
    assert "PROPOSE_ACTION" in event_names
    assert "EVALUATE_POLICY" in event_names
    assert "SUPERVISOR_CYCLE_COMPLETE" in event_names


@pytest.mark.asyncio
async def test_monitoring_cycle_negative_verification_outcome(supervisor_env):
    """Verifies that when counterparty rejects, the autonomous cycle does NOT resolve the commitment."""
    supervisor, repo, _ = supervisor_env

    await supervisor.run_monitoring_cycle()
    atlas = await repo.get_by_id("com_atlas_approval")
    atlas.status = CommitmentStatus.VERIFYING
    atlas.next_action.status = ActionStatus.COMPLETED
    await repo.save(atlas)

    # Counterparty rejects fulfillment
    workspace_store.simulate_client_reply("com_atlas_approval", fulfilled=False)

    await supervisor.run_monitoring_cycle()
    reloaded = await repo.get_by_id("com_atlas_approval")

    # MUST NOT be RESOLVED
    assert reloaded.status != CommitmentStatus.RESOLVED
    assert reloaded.status in [CommitmentStatus.VERIFYING, CommitmentStatus.FAILED]
    assert reloaded.verification_result.is_verified is False


@pytest.mark.asyncio
async def test_monitoring_cycle_concurrent_execution_safety(supervisor_env):
    """Verifies that concurrent monitoring cycles execute safely without race conditions or corrupt state."""
    supervisor, repo, _ = supervisor_env

    # Run two monitoring cycles concurrently
    results = await asyncio.gather(
        supervisor.run_monitoring_cycle(),
        supervisor.run_monitoring_cycle(),
        return_exceptions=True,
    )

    for r in results:
        assert not isinstance(r, Exception)
        assert r.success is True

    atlas = await repo.get_by_id("com_atlas_approval")
    assert atlas is not None
    assert atlas.status == CommitmentStatus.AWAITING_APPROVAL
    assert atlas.next_action is not None
    assert atlas.next_action.status == ActionStatus.AWAITING_APPROVAL
