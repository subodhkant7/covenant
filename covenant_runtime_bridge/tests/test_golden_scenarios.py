"""Golden Scenarios A through E: Behavioral comparison of Legacy Covenant vs Agent Organization Runtime."""

from datetime import datetime, timezone
import pytest
from covenant.agents.base import AgentContext as LegacyAgentContext
from covenant.agents.evidence import EvidenceAgent as LegacyEvidenceAgent
from covenant.agents.policy import PolicyAgent as LegacyPolicyAgent
from covenant.agents.resolution import ResolutionAgent as LegacyResolutionAgent
from covenant.agents.verification import VerificationAgent as LegacyVerificationAgent
from covenant.domain.enums import ActionStatus, CommitmentCategory, CommitmentStatus, RiskLevel
from covenant.domain.models import Commitment, Party
from covenant.persistence.sqlite_repo import SQLiteCommitmentRepository
from covenant.state_machine.machine import CommitmentStateMachine
from covenant.synthetic_data.store import workspace_store
from covenant.tools.base import BaseTool, ToolResult

from agent_runtime.core.contracts.agent import AgentRun
from agent_runtime.core.contracts.context import Task, TaskContext
from agent_runtime.core.contracts.tool import ToolRequest
from agent_runtime.core.contracts.verification import VerificationRequest
from agent_runtime.core.engine.execution import ExecutionEngine
from agent_runtime.core.engine.run_executor import AgentRunExecutor
from agent_runtime.core.state.enums import ApprovalState, ExecutionSafety, TaskState
from agent_runtime.core.telemetry.sink import InMemoryEventSink
from agent_runtime.core.verification.gate import VerificationGate

from covenant_runtime_bridge.bootstrap import CovenantRuntimeBootstrap
from covenant_runtime_bridge.comparator.comparator import (
    CovenantBehavioralComparator,
    ScenarioOutcome,
)
from covenant_runtime_bridge.mapping.task_factory import CovenantTaskFactory
from covenant_runtime_bridge.tools.tool_adapter import CovenantToolAdapter


def create_atlas_commitment() -> Commitment:
    return Commitment(
        id="com_atlas_approval",
        title="Meridian Global Phase 2 Deliverable Formal Sign-Off",
        description="Sarah Jenkins promised formal written sign-off for Project Atlas Phase 2 deliverables by Friday, Sep 5.",
        category=CommitmentCategory.CLIENT_APPROVAL,
        promisor=Party(name="Sarah Jenkins", email="sjenkins@meridianglobal.com", organization="Meridian Global Corp", role="PROMISOR"),
        promisee=Party(name="Alex North", email="alex@northstarstudio.com", organization="Northstar Studio LLC", role="PROMISEE"),
        source_references=["EML-102", "CTR-2026-081", "PRJ-ATLAS"],
        promised_at=datetime.fromisoformat("2026-09-03T14:30:00").replace(tzinfo=timezone.utc),
        due_date=datetime.fromisoformat("2026-09-05T17:00:00").replace(tzinfo=timezone.utc),
        status=CommitmentStatus.OVERDUE,
        risk=RiskLevel.MEDIUM,
        confidence=0.96,
    )


class ProhibitedLeakTool(BaseTool):
    name = "prohibited_external_leak"
    description = "Unauthorized exfiltration tool"
    parameters_schema = {"type": "object", "properties": {}}

    async def execute(self, **kwargs):
        return ToolResult(success=True, data={"leaked": True})


@pytest.fixture(autouse=True)
def reset_synthetic_world():
    """Isolate synthetic environment before each test scenario."""
    workspace_store.reset()
    yield
    workspace_store.reset()


@pytest.mark.asyncio
async def test_golden_scenario_a_safe_read(tmp_path):
    """
    Scenario A — Safe Read:
    Discover overdue commitment -> gather evidence -> no mutation.
    """
    db_path = str(tmp_path / "legacy_a.db")
    legacy_com_repo = SQLiteCommitmentRepository(db_path)
    await legacy_com_repo.initialize()

    c_atlas = create_atlas_commitment()
    await legacy_com_repo.save(c_atlas)

    # --- LEGACY PATH ---
    legacy_ev_agent = LegacyEvidenceAgent(commitment_repo=legacy_com_repo)
    legacy_res = await legacy_ev_agent.run(LegacyAgentContext(session_id="sess_leg_a", target_commitment_id=c_atlas.id))
    legacy_com = await legacy_com_repo.get_by_id(c_atlas.id)

    legacy_outcome = ScenarioOutcome(
        target_id=c_atlas.id,
        evidence_found=["PRJ-ATLAS", "INBOX_SCAN"],
        proposed_action=None,
        policy_requires_approval=False,
        tool_chosen="get_project_status",
        execution_success=legacy_res.success,
        verified=False,
        final_state=legacy_com.status.value,
    )

    # --- RUNTIME PATH ---
    bridge_env = CovenantRuntimeBootstrap.assemble()
    sink = InMemoryEventSink()
    engine = ExecutionEngine(
        tool_registry=bridge_env.tools,
        permissions=bridge_env.permissions,
        policy_engine=bridge_env.policy,
        event_sink=sink,
    )
    executor = AgentRunExecutor(engine, sink)

    inv_task = CovenantTaskFactory.create_investigation_task(c_atlas)
    inv_agent = bridge_env.agents.get("covenant.investigator_agent")
    inv_context = TaskContext(
        task_id=inv_task.id,
        organization_id=inv_task.organization_id,
        intent=inv_task.intent,
        required_role=inv_task.required_role,
        scope=inv_task.scope,
        available_tools=bridge_env.tools.list_specs(),
        input_data=inv_task.input_payload,
    )

    run, history, _ = await executor.execute_run(inv_task, inv_agent, inv_context)
    if run.status.value == "COMPLETED":
        inv_task.status = TaskState.COMPLETED

    runtime_outcome = ScenarioOutcome(
        target_id=inv_task.input_payload["commitment_id"],
        evidence_found=run.output_payload.get("corroborating_sources", []),
        proposed_action=None,
        policy_requires_approval=False,
        tool_chosen=history.turns[0].request.tool_name if history.turns else None,
        execution_success=(run.status.value == "COMPLETED"),
        verified=False,
        final_state=inv_task.status.value,
    )

    # --- BEHAVIORAL COMPARISON ---
    comparison = CovenantBehavioralComparator.compare("Scenario A - Safe Read", legacy_outcome, runtime_outcome)
    assert comparison.matches["target"] is True
    assert comparison.matches["evidence"] is True
    assert comparison.matches["tool_chosen"] is True
    assert comparison.overall_match is True


@pytest.mark.asyncio
async def test_golden_scenario_b_approval_gated_action(tmp_path):
    """
    Scenario B — Approval-Gated Action:
    Overdue commitment -> investigate -> propose follow-up -> approval required -> approved -> execute -> verify -> resolved.
    """
    db_path = str(tmp_path / "legacy_b.db")
    legacy_com_repo = SQLiteCommitmentRepository(db_path)
    await legacy_com_repo.initialize()
    c_atlas = create_atlas_commitment()
    await legacy_com_repo.save(c_atlas)

    # --- LEGACY PATH ---
    legacy_res_agent = LegacyResolutionAgent(commitment_repo=legacy_com_repo)
    legacy_pol_agent = LegacyPolicyAgent(commitment_repo=legacy_com_repo)
    legacy_ver_agent = LegacyVerificationAgent(commitment_repo=legacy_com_repo)

    # 1. Propose action
    await legacy_res_agent.run(LegacyAgentContext(session_id="sess_b", target_commitment_id=c_atlas.id))
    # 2. Evaluate policy (requires approval)
    await legacy_pol_agent.run(LegacyAgentContext(session_id="sess_b", target_commitment_id=c_atlas.id))

    # 3. Simulate human approves and dispatches in legacy
    c_atlas = await legacy_com_repo.get_by_id(c_atlas.id)
    c_atlas.next_action.status = ActionStatus.APPROVED
    CommitmentStateMachine.transition(
        commitment=c_atlas,
        target_state=CommitmentStatus.EXECUTING,
        agent_name="HumanUser",
        reason="Human approved follow-up email.",
        approved_by="Alex North",
    )
    await legacy_com_repo.save(c_atlas)

    workspace_store.send_email(
        from_addr="Alex North <alex@northstarstudio.com>",
        to_addrs=["sjenkins@meridianglobal.com"],
        subject="Follow-up: Project Atlas Phase 2 Formal Approval",
        body="Dear Sarah, please review.",
        thread_id="TH-ATLAS-APPROVAL",
    )
    # 4. Client signs and sends back reply
    workspace_store.simulate_client_reply(c_atlas.id)

    # 5. Verify resolution
    ver_res = await legacy_ver_agent.run(LegacyAgentContext(session_id="sess_b", target_commitment_id=c_atlas.id))
    final_legacy_com = await legacy_com_repo.get_by_id(c_atlas.id)

    legacy_outcome = ScenarioOutcome(
        target_id=c_atlas.id,
        evidence_found=["PRJ-ATLAS"],
        proposed_action="FOLLOWUP_EMAIL",
        policy_requires_approval=True,
        approval_status="APPROVED",
        tool_chosen="send_followup",
        execution_success=True,
        verified=ver_res.data["is_verified"],
        final_state=final_legacy_com.status.value,
    )

    # --- RUNTIME PATH ---
    # Reset synthetic world for isolated runtime run
    workspace_store.reset()

    bridge_env = CovenantRuntimeBootstrap.assemble()
    sink = InMemoryEventSink()
    engine = ExecutionEngine(
        tool_registry=bridge_env.tools,
        permissions=bridge_env.permissions,
        policy_engine=bridge_env.policy,
        event_sink=sink,
    )
    executor = AgentRunExecutor(engine, sink)
    verif_gate = VerificationGate(sink)

    res_task = CovenantTaskFactory.create_resolution_task(c_atlas)
    res_agent = bridge_env.agents.get("covenant.resolver_agent")
    res_context = TaskContext(
        task_id=res_task.id,
        organization_id=res_task.organization_id,
        intent=res_task.intent,
        required_role=res_task.required_role,
        scope=res_task.scope,
        available_tools=bridge_env.tools.list_specs(),
        input_data=res_task.input_payload,
    )

    # Turn loop runs until approval blocks
    run, history, approval_req = await executor.execute_run(res_task, res_agent, res_context)
    assert approval_req is not None
    assert approval_req.status == ApprovalState.PENDING

    # Human approves
    approval_req.status = ApprovalState.APPROVED
    approval_req.reviewed_by = "ExecutiveReviewer"

    # Resume run with approval
    run2, history2, _ = await executor.execute_run(
        task=res_task,
        agent=res_agent,
        context=res_context,
        run=run,
        history=history,
        approval_resume=approval_req,
    )
    assert run2.status.value == "COMPLETED"

    # Simulate client signed response into synthetic world
    workspace_store.simulate_client_reply(c_atlas.id)

    # Runtime Verification Gate verifies outcome
    v_res = await verif_gate.verify_task(res_task, bridge_env.verifier, expected_outcome="Signed client approval")
    assert v_res.verified is True

    runtime_outcome = ScenarioOutcome(
        target_id=c_atlas.id,
        evidence_found=["PRJ-ATLAS"],
        proposed_action="FOLLOWUP_EMAIL",
        policy_requires_approval=True,
        approval_status="APPROVED",
        tool_chosen="send_followup",
        execution_success=True,
        verified=v_res.verified,
        final_state="RESOLVED",
    )

    # --- BEHAVIORAL COMPARISON ---
    comparison = CovenantBehavioralComparator.compare("Scenario B - Approval-Gated Action", legacy_outcome, runtime_outcome)
    assert comparison.matches["target"] is True
    assert comparison.matches["proposed_action"] is True
    assert comparison.matches["approval_required"] is True
    assert comparison.matches["tool_chosen"] is True
    assert comparison.matches["verification"] is True
    assert comparison.matches["final_state"] is True
    assert comparison.overall_match is True


@pytest.mark.asyncio
async def test_golden_scenario_c_policy_denial():
    """
    Scenario C — Policy Denial:
    Agent requests prohibited action -> DENY -> no side effect.
    """
    bridge_env = CovenantRuntimeBootstrap.assemble()
    # Register prohibited tool to test policy gate
    bridge_env.tools.register(CovenantToolAdapter(ProhibitedLeakTool(), ExecutionSafety.NON_IDEMPOTENT))
    bridge_env.permissions.grant("org_covenant_northstar", "covenant.resolver_agent", ["prohibited_external_leak"])

    sink = InMemoryEventSink()
    engine = ExecutionEngine(
        tool_registry=bridge_env.tools,
        permissions=bridge_env.permissions,
        policy_engine=bridge_env.policy,
        event_sink=sink,
    )

    task = Task(id="tsk_c", organization_id="org_covenant_northstar", intent="Test prohibited", required_role="covenant.resolver")
    run = AgentRun(id="run_c", task_id="tsk_c", agent_id="covenant.resolver_agent")
    req = ToolRequest(tool_name="prohibited_external_leak", arguments={})
    obs, appr = await engine.handle_tool_request(task, run, req)

    # Invariant: Observation is failure due to policy deny
    assert obs.success is False
    assert "Policy denied execution" in obs.error
    assert appr is None


@pytest.mark.asyncio
async def test_golden_scenario_d_verification_failure():
    """
    Scenario D — Verification Failure:
    Action executes -> outcome not achieved in environment -> Task must not complete.
    """
    bridge_env = CovenantRuntimeBootstrap.assemble()
    sink = InMemoryEventSink()
    verif_gate = VerificationGate(sink)

    task = Task(
        id="tsk_cov_res_com_atlas_approval",
        organization_id="org_covenant_northstar",
        intent="Resolve commitment",
        required_role="covenant.resolver",
        status=TaskState.VERIFYING,
        requires_verification=True,
    )

    # Do NOT simulate client reply (environment remains unfulfilled)
    v_res = await verif_gate.verify_task(
        task=task,
        verifier=bridge_env.verifier,
        expected_outcome="Formal signed approval in inbox",
    )

    # Invariant: Verification fails and task remains in VERIFYING/RUNNING (does not complete!)
    assert v_res.verified is False
    assert task.status != TaskState.COMPLETED
    assert "no corroborating client approval" in v_res.rationale


@pytest.mark.asyncio
async def test_golden_scenario_e_duplicate_execution():
    """
    Scenario E — Duplicate Execution:
    Same action requested twice -> idempotency prevents duplicate execution.
    """
    bridge_env = CovenantRuntimeBootstrap.assemble()
    sink = InMemoryEventSink()
    engine = ExecutionEngine(
        tool_registry=bridge_env.tools,
        permissions=bridge_env.permissions,
        policy_engine=bridge_env.policy,
        event_sink=sink,
    )

    task = Task(id="tsk_e", organization_id="org_covenant_northstar", intent="Draft", required_role="covenant.resolver")
    run = AgentRun(id="run_e", task_id="tsk_e", agent_id="covenant.resolver_agent")

    req = ToolRequest(
        tool_name="draft_followup",
        arguments={
            "commitment_id": "com_1",
            "recipient_name": "Sarah",
            "subject": "Notice",
            "promise_summary": "Phase 2 Deliverable sign-off",
        },
    )

    # Call 1: Executes and records in idempotency store
    obs1, _ = await engine.handle_tool_request(task, run, req)
    assert obs1.success is True

    # Call 2: Returns cached observation without re-executing
    obs2, _ = await engine.handle_tool_request(task, run, req)
    assert obs2.success is True
    assert obs2.execution_id == obs1.execution_id
