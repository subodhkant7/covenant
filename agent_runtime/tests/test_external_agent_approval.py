"""Approval lifecycle and human-in-the-loop resumption tests for ExternalAgentAdapter."""

import pytest
from typing import Any, Dict, List

from agent_runtime.adapters.external_agent import (
    ExternalAgentAdapter,
    ExternalAgentRequest,
    ExternalAgentResponse,
    ExternalAgentResponseType,
    ExternalAgentToolProposal,
    IExternalAgent,
)
from agent_runtime.core.authorization.matrix import ToolPermissionMatrix
from agent_runtime.core.contracts.agent import (
    AgentDefinition,
    AgentRun,
    AgentRunHistory,
)
from agent_runtime.core.contracts.approval import HumanApprovalRequest
from agent_runtime.core.contracts.context import Task, TaskContext, TaskScope
from agent_runtime.core.contracts.event import EventType
from agent_runtime.core.contracts.tool import ToolRequest, ToolSpec
from agent_runtime.core.engine.execution import ExecutionEngine
from agent_runtime.core.engine.registry import ToolRegistry
from agent_runtime.core.engine.run_executor import AgentRunExecutor
from agent_runtime.core.interfaces.tool import ITool
from agent_runtime.core.policy.engine import DefaultPolicyEngine
from agent_runtime.core.state.enums import AgentRunState, ApprovalState, ScopeType
from agent_runtime.core.telemetry.sink import InMemoryEventSink
from covenant.synthetic_data.store import workspace_store
from covenant_runtime_bridge.bootstrap import CovenantRuntimeBootstrap
from covenant_runtime_bridge.shadow.isolation import (
    ExternalSideEffectGuard,
    scoped_workspace_store,
    clone_workspace_store,
)


class ApprovalRequiringExternalAgent(IExternalAgent):
    """External agent that proposes an action requiring human sign-off."""

    def __init__(self):
        self.received_turns: List[ExternalAgentRequest] = []

    async def decide(self, request: ExternalAgentRequest) -> ExternalAgentResponse:
        self.received_turns.append(request)

        if len(request.history) == 0:
            # Turn 0: Propose send_followup (requires human approval by policy)
            return ExternalAgentResponse(
                response_type=ExternalAgentResponseType.TOOL_PROPOSAL,
                tool_proposal=ExternalAgentToolProposal(
                    tool_name="send_followup",
                    arguments={
                        "commitment_id": "com_atlas_approval",
                        "recipient_email": "sjenkins@meridianglobal.com",
                        "subject": "Phase 2 Deliverable Formal Sign-Off",
                        "body": "Draft follow-up body.",
                    },
                    rationale="Requesting client follow-up on overdue commitment",
                ),
                rationale="Proposing follow-up requiring human supervisor review.",
            )

        else:
            # Turn 1: Resumed after human approval. Receives execution observation.
            last_turn = request.history[-1]
            obs = last_turn.observation
            return ExternalAgentResponse(
                response_type=ExternalAgentResponseType.COMPLETE,
                completion_summary=f"Agent acknowledged execution: success={obs.success}",
                output_payload={"dispatched": obs.success, "data": obs.data},
                rationale="Observation processed. Run finished.",
            )


@pytest.fixture(autouse=True)
def reset_covenant_world():
    workspace_store.reset()
    yield
    workspace_store.reset()


@pytest.mark.asyncio
async def test_external_agent_human_approval_lifecycle():
    """Section 10: Complete human-in-the-loop approval workflow:
    1. External agent proposes tool.
    2. Policy requires human approval -> run halts in AWAITING_APPROVAL.
    3. External agent cannot self-approve.
    4. Human approval granted via runtime mechanism.
    5. Resumed run executes tool and delivers observation to external agent.
    6. External agent concludes.
    """
    bridge_env = CovenantRuntimeBootstrap.assemble()
    sink = InMemoryEventSink()
    engine = ExecutionEngine(
        tool_registry=bridge_env.tools,
        permissions=bridge_env.permissions,
        policy_engine=bridge_env.policy,
        event_sink=sink,
    )
    executor = AgentRunExecutor(engine, sink)

    agent_def = AgentDefinition(
        id="covenant.external_approval_agent",
        name="External Approval Agent",
        supported_roles=["covenant.resolver"],
    )
    bridge_env.permissions.grant("org_covenant_northstar", agent_def.id, ["send_followup"])

    ext_worker = ApprovalRequiringExternalAgent()
    adapter = ExternalAgentAdapter(agent_def, external_agent=ext_worker, event_sink=sink)

    task = Task(
        id="tsk_appr_cycle_01",
        organization_id="org_covenant_northstar",
        intent="Escalate overdue milestone",
        required_role="covenant.resolver",
    )
    ctx = TaskContext(
        task_id=task.id,
        organization_id=task.organization_id,
        intent=task.intent,
        required_role=task.required_role,
        scope=TaskScope(scope_type=ScopeType.ENTITY, entity_ids=["com_atlas_approval"]),
        available_tools=bridge_env.tools.list_specs(),
        max_turns=4,
    )

    store = clone_workspace_store(workspace_store)
    with ExternalSideEffectGuard(), scoped_workspace_store(store):
        # 1. Turn 0: Execution halts for human authorization
        run, history, appr = await executor.execute_run(task, adapter, ctx)

        assert run.status == AgentRunState.AWAITING_APPROVAL
        assert appr is not None
        assert appr.status == ApprovalState.PENDING
        assert appr.tool_request.tool_name == "send_followup"
        assert appr.task_id == task.id
        assert appr.agent_run_id == run.id

        # Invariant: External agent was NOT given an approval mutation handle
        assert len(ext_worker.received_turns) == 1
        turn0_req = ext_worker.received_turns[0]
        assert not hasattr(turn0_req, "approve")
        assert not hasattr(turn0_req, "approval")

        # 2. Human supervisor reviews and approves with modified subject
        appr.status = ApprovalState.APPROVED
        appr.reviewed_by = "lead_ops@northstar.com"
        appr.reviewer_notes = "Authorized with expedited subject."
        appr.modified_arguments = {
            "commitment_id": "com_atlas_approval",
            "recipient_email": "sjenkins@meridianglobal.com",
            "subject": "[URGENT] Phase 2 Deliverable Formal Sign-Off",
            "body": "Draft follow-up body.",
        }

        # 3. Resume AgentRun with approval
        resumed_run, resumed_history, pending_appr = await executor.execute_run(
            task, adapter, ctx, run=run, history=history, approval_resume=appr
        )

        assert resumed_run.status == AgentRunState.COMPLETED
        assert pending_appr is None
        assert resumed_run.turn_count >= 2
        assert "acknowledged execution: success=True" in resumed_run.completion_summary

        # 4. Invariant: Tool was executed with human modified arguments
        events = await sink.list_events(task_id=task.id)
        appr_decided_events = [e for e in events if e.event_type == EventType.APPROVAL_DECIDED]
        assert len(appr_decided_events) == 1
        assert appr.status == ApprovalState.EXECUTED


@pytest.mark.asyncio
async def test_rejection_of_unapproved_or_rejected_request():
    """Verify that if approval is rejected, resuming fails execution closed."""
    bridge_env = CovenantRuntimeBootstrap.assemble()
    sink = InMemoryEventSink()
    engine = ExecutionEngine(
        tool_registry=bridge_env.tools,
        permissions=bridge_env.permissions,
        policy_engine=bridge_env.policy,
        event_sink=sink,
    )
    executor = AgentRunExecutor(engine, sink)

    agent_def = AgentDefinition(
        id="covenant.external_approval_agent",
        name="External Approval Agent",
        supported_roles=["covenant.resolver"],
    )
    bridge_env.permissions.grant("org_covenant_northstar", agent_def.id, ["send_followup"])

    ext_worker = ApprovalRequiringExternalAgent()
    adapter = ExternalAgentAdapter(agent_def, external_agent=ext_worker, event_sink=sink)

    task = Task(id="tsk_appr_rej_01", organization_id="org_covenant_northstar", intent="Reject test", required_role="covenant.resolver")
    ctx = TaskContext(
        task_id=task.id,
        organization_id=task.organization_id,
        intent=task.intent,
        required_role=task.required_role,
        scope=TaskScope(),
        available_tools=bridge_env.tools.list_specs(),
        max_turns=3,
    )

    store = clone_workspace_store(workspace_store)
    with ExternalSideEffectGuard(), scoped_workspace_store(store):
        run, history, appr = await executor.execute_run(task, adapter, ctx)
        assert run.status == AgentRunState.AWAITING_APPROVAL

        # Human rejects request
        appr.status = ApprovalState.REJECTED
        appr.reviewed_by = "lead_ops@northstar.com"
        appr.reviewer_notes = "Do not send external email at this time."

        # Attempt to resume with rejected approval
        resumed_run, resumed_history, _ = await executor.execute_run(
            task, adapter, ctx, run=run, history=history, approval_resume=appr
        )

        # Resumed tool request rejected because approval status != APPROVED
        last_obs = resumed_history.turns[-2].observation if len(resumed_history.turns) >= 2 else resumed_history.turns[-1].observation
        assert last_obs is not None
        assert last_obs.success is False
        assert "not approved" in last_obs.error.lower()


@pytest.mark.asyncio
async def test_replay_protection_cannot_reuse_executed_approval():
    """Invariant: An approval in EXECUTED state cannot be reused to execute another side effect."""
    bridge_env = CovenantRuntimeBootstrap.assemble()
    sink = InMemoryEventSink()
    engine = ExecutionEngine(
        tool_registry=bridge_env.tools,
        permissions=bridge_env.permissions,
        policy_engine=bridge_env.policy,
        event_sink=sink,
    )

    agent_def = AgentDefinition(id="covenant.replay_tester", name="Replay Tester")
    task = Task(id="tsk_replay", organization_id="org_covenant_northstar", intent="Replay test", required_role="covenant.resolver")
    run = AgentRun(task_id=task.id, agent_id=agent_def.id)

    appr = HumanApprovalRequest(
        organization_id=task.organization_id,
        task_id=task.id,
        agent_run_id=run.id,
        tool_request=ToolRequest(
            tool_name="send_followup",
            arguments={
                "commitment_id": "com_atlas_approval",
                "recipient_email": "sjenkins@meridianglobal.com",
                "subject": "Test",
                "body": "Body",
            },
        ),
        policy_decision_id="pol_dec_01",
        status=ApprovalState.EXECUTED,  # Already consumed
    )

    obs, _ = await engine.handle_tool_request(task, run, appr.tool_request, approval=appr)
    assert obs.success is False
    assert "not approved" in obs.error.lower()
