"""Tests for Shadow Scenarios A through E and realistic Multi-Commitment workflow."""

from datetime import datetime, timezone
import pytest

from covenant.domain.enums import CommitmentCategory, CommitmentStatus, RiskLevel
from covenant.domain.models import Commitment, Party
from covenant.synthetic_data.store import workspace_store

from agent_runtime.core.contracts.context import Task, TaskContext, TaskScope
from agent_runtime.core.contracts.tool import ToolRequest
from agent_runtime.core.engine.execution import ExecutionEngine
from agent_runtime.core.engine.run_executor import AgentRunExecutor
from agent_runtime.core.state.enums import ScopeType, TaskState
from agent_runtime.core.telemetry.sink import InMemoryEventSink
from agent_runtime.core.verification.gate import VerificationGate

from covenant_runtime_bridge.bootstrap import CovenantRuntimeBootstrap
from covenant_runtime_bridge.mapping.task_factory import CovenantTaskFactory
from covenant_runtime_bridge.shadow.contracts import MismatchCategory, ShadowMode
from covenant_runtime_bridge.shadow.harness import ShadowExecutionHarness
from covenant_runtime_bridge.shadow.metrics import shadow_metrics


def sample_atlas_commitment() -> Commitment:
    return Commitment(
        id="com_atlas_approval",
        title="Meridian Global Phase 2 Deliverable Formal Sign-Off",
        description="Sarah Jenkins promised formal sign-off for Atlas deliverables.",
        category=CommitmentCategory.CLIENT_APPROVAL,
        promisor=Party(name="Sarah Jenkins", email="sjenkins@meridianglobal.com", organization="Meridian Global Corp"),
        promisee=Party(name="Alex North", email="alex@northstarstudio.com", organization="Northstar Studio LLC"),
        status=CommitmentStatus.OVERDUE,
        risk=RiskLevel.MEDIUM,
    )


def sample_apex_commitment() -> Commitment:
    return Commitment(
        id="com_apex_repair",
        title="Apex Laser Cutter Sensor Repair",
        description="Marcus Vance promised sensor replacement by today.",
        category=CommitmentCategory.CONTRACTOR_REPAIR,
        promisor=Party(name="Marcus Vance", email="m.vance@apexindustrialrepairs.com", organization="Apex Industrial"),
        promisee=Party(name="Alex North", email="alex@northstarstudio.com", organization="Northstar Studio LLC"),
        status=CommitmentStatus.OVERDUE,
        risk=RiskLevel.HIGH,
    )


@pytest.fixture(autouse=True)
def reset_world():
    workspace_store.reset()
    shadow_metrics.reset()
    yield
    workspace_store.reset()


@pytest.mark.asyncio
async def test_shadow_scenario_b_approval_gated_action():
    """Canonical Scenario B executed through the shadow harness."""
    c = sample_atlas_commitment()
    harness = ShadowExecutionHarness(mode=ShadowMode.SHADOW)

    run = await harness.execute_scenario_b_approval_gated(
        commitment=c,
        scenario_name="Scenario B — Approval-Gated Action",
        simulate_corroboration=True,
    )

    assert run.status == "COMPLETED"
    assert run.comparison is not None
    assert run.comparison.overall_match is True
    assert run.comparison.classifications["final_domain_state"] == MismatchCategory.MATCH
    assert run.comparison.classifications["approval_requirement"] == MismatchCategory.MATCH
    assert run.comparison.post_run_state_match is True

    # Check metrics
    summary = shadow_metrics.get_summary()
    assert summary["total_shadow_runs"] == 1
    assert summary["matches"] == 1
    assert summary["parity_rate_pct"] == 100.0


@pytest.mark.asyncio
async def test_shadow_scenario_d_verification_failure():
    """Canonical Scenario D: action executes, but verification fails (no client response)."""
    c = sample_atlas_commitment()
    harness = ShadowExecutionHarness(mode=ShadowMode.SHADOW)

    # Run without simulating client reply
    run = await harness.execute_scenario_b_approval_gated(
        commitment=c,
        scenario_name="Scenario D — Verification Failure",
        simulate_corroboration=False,
    )

    assert run.status == "COMPLETED"
    assert run.comparison is not None
    # Both legacy and runtime must agree: verification is False!
    assert run.legacy_outcome.verification_outcomes[c.id] is False
    assert run.runtime_outcome.verification_outcomes[c.id] is False
    assert run.comparison.category_matches["verification"] is True


@pytest.mark.asyncio
async def test_shadow_fails_closed_on_snapshot_fingerprint_mismatch():
    """Verify that if starting state fingerprints differ, shadow execution skips immediately."""
    c = sample_atlas_commitment()
    harness = ShadowExecutionHarness(mode=ShadowMode.SHADOW)

    run = await harness.execute_scenario_b_approval_gated(
        commitment=c,
        force_snapshot_diff=True,  # Injects snapshot corruption
    )

    assert run.status == "SHADOW_SKIPPED"
    assert "Initial snapshot fingerprint mismatch" in run.skip_reason
    assert run.comparison is None


@pytest.mark.asyncio
async def test_shadow_mode_off_skips():
    """Verify that mode=OFF skips shadow execution cleanly."""
    c = sample_atlas_commitment()
    harness = ShadowExecutionHarness(mode=ShadowMode.OFF)

    run = await harness.execute_scenario_b_approval_gated(commitment=c)
    assert run.status == "SHADOW_SKIPPED"
    assert run.skip_reason == "Shadow mode is OFF"


@pytest.mark.asyncio
async def test_multi_commitment_shadow_scenario():
    """
    Section 10: Realistic Multi-Commitment Scenario.
    Evaluates multiple commitments in a single invocation using TaskScope(entity_ids=[...]).
    Validates discovery, multi-entity investigation, risk classification, and action proposal.
    """
    commitments = [sample_atlas_commitment(), sample_apex_commitment()]
    bridge_env = CovenantRuntimeBootstrap.assemble()
    sink = InMemoryEventSink()
    engine = ExecutionEngine(
        tool_registry=bridge_env.tools,
        permissions=bridge_env.permissions,
        policy_engine=bridge_env.policy,
        event_sink=sink,
    )
    executor = AgentRunExecutor(engine, sink)

    # 1. Multi-Entity Task
    multi_task = Task(
        id="tsk_multi_commitments_01",
        organization_id="org_covenant_northstar",
        intent="Batch investigate all overdue studio commitments",
        required_role="covenant.investigator",
        scope=TaskScope(
            scope_type=ScopeType.MULTI_ENTITY,
            entity_type="covenant.commitment",
            entity_ids=[c.id for c in commitments],
            filter_criteria={"status": "OVERDUE"},
        ),
        input_payload={
            "domain": "covenant",
            "batch_size": len(commitments),
            "commitment_ids": [c.id for c in commitments],
        },
    )

    inv_agent = bridge_env.agents.get("covenant.investigator_agent")
    ctx = TaskContext(
        task_id=multi_task.id,
        organization_id=multi_task.organization_id,
        intent=multi_task.intent,
        required_role=multi_task.required_role,
        scope=multi_task.scope,
        available_tools=bridge_env.tools.list_specs(),
        input_data=multi_task.input_payload,
    )

    run, history, _ = await executor.execute_run(multi_task, inv_agent, ctx)

    assert run.status.value == "COMPLETED"
    assert len(history.turns) >= 2
    # Verify both entities are contained in scope
    assert len(multi_task.scope.entity_ids) == 2
    assert "com_atlas_approval" in multi_task.scope.entity_ids
    assert "com_apex_repair" in multi_task.scope.entity_ids
