"""Multi-turn, multi-entity, and realistic Covenant scenario tests for ExternalAgentAdapter."""

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
from agent_runtime.core.contracts.context import Task, TaskContext, TaskScope
from agent_runtime.core.contracts.event import EventType
from agent_runtime.core.contracts.tool import ToolRequest, ToolSpec
from agent_runtime.core.contracts.verification import Evidence, VerificationRequest, VerificationResult
from agent_runtime.core.engine.execution import ExecutionEngine
from agent_runtime.core.engine.registry import ToolRegistry
from agent_runtime.core.engine.run_executor import AgentRunExecutor
from agent_runtime.core.interfaces.tool import ITool
from agent_runtime.core.interfaces.verification import IVerifier
from agent_runtime.core.policy.engine import DefaultPolicyEngine
from agent_runtime.core.state.enums import AgentRunState, ApprovalState, ScopeType, TaskState
from agent_runtime.core.telemetry.sink import InMemoryEventSink
from agent_runtime.core.verification.gate import VerificationGate

from covenant.domain.enums import CommitmentCategory, CommitmentStatus, RiskLevel
from covenant.domain.models import Commitment, Party
from covenant.synthetic_data.store import workspace_store
from covenant_runtime_bridge.bootstrap import CovenantRuntimeBootstrap
from covenant_runtime_bridge.shadow.isolation import (
    ExternalSideEffectGuard,
    scoped_workspace_store,
    clone_workspace_store,
)


class MultiTurnInvestigatorAgent(IExternalAgent):
    """Simulates a multi-turn reasoning agent executing a real 3-turn sequence:
    Turn 0: requests get_project_status
    Turn 1: inspects observation, requests search_email
    Turn 2: receives email observation, synthesizes and concludes with completion.
    """

    def __init__(self):
        self.received_turns: List[ExternalAgentRequest] = []

    async def decide(self, request: ExternalAgentRequest) -> ExternalAgentResponse:
        self.received_turns.append(request)

        if len(request.history) == 0:
            # Turn 0: Propose get_project_status
            return ExternalAgentResponse(
                response_type=ExternalAgentResponseType.TOOL_PROPOSAL,
                tool_proposal=ExternalAgentToolProposal(
                    tool_name="get_project_status",
                    arguments={"project_id": "PRJ-ATLAS"},
                    rationale="Step 1: Check Atlas milestone status",
                ),
                rationale="Checking project status first.",
            )

        elif len(request.history) == 1:
            # Turn 1: Inspect turn 0 observation and propose search_email
            last_obs = request.history[-1].observation
            assert last_obs is not None
            assert last_obs.tool_name == "get_project_status"
            assert last_obs.success is True

            return ExternalAgentResponse(
                response_type=ExternalAgentResponseType.TOOL_PROPOSAL,
                tool_proposal=ExternalAgentToolProposal(
                    tool_name="search_email",
                    arguments={"query": "Atlas deliverable sign-off"},
                    rationale="Step 2: Search communication trail for sign-off evidence",
                ),
                rationale="Status verified. Now searching emails for sign-off evidence.",
            )

        else:
            # Turn 2: Synthesize final conclusions
            obs_emails = request.history[-1].observation
            assert obs_emails is not None
            assert obs_emails.tool_name == "search_email"

            return ExternalAgentResponse(
                response_type=ExternalAgentResponseType.COMPLETE,
                completion_summary="Investigation complete: Atlas is overdue and awaiting Sarah's sign-off.",
                output_payload={
                    "project_id": "PRJ-ATLAS",
                    "status": "BLOCKED",
                    "next_action": "draft_followup",
                },
                rationale="All evidence collected. Concluding task.",
            )


class MultiEntityEvaluatorAgent(IExternalAgent):
    """External agent that processes a multi-entity scope."""

    def __init__(self):
        self.scope_received = None
        self.turns = 0

    async def decide(self, request: ExternalAgentRequest) -> ExternalAgentResponse:
        self.scope_received = request.task.scope
        self.turns += 1

        entity_ids = self.scope_received.get("entity_ids", [])
        if self.turns <= len(entity_ids):
            target = entity_ids[self.turns - 1]
            return ExternalAgentResponse(
                response_type=ExternalAgentResponseType.TOOL_PROPOSAL,
                tool_proposal=ExternalAgentToolProposal(
                    tool_name="verify_commitment",
                    arguments={"commitment_id": target},
                    rationale=f"Verifying commitment for entity {target}",
                ),
            )
        return ExternalAgentResponse(
            response_type=ExternalAgentResponseType.COMPLETE,
            completion_summary=f"Evaluated all {len(entity_ids)} entities.",
            output_payload={"evaluated_entities": entity_ids},
        )


class CorroboratedVerifier(IVerifier):
    async def verify(self, request: VerificationRequest, context: Dict[str, Any]) -> VerificationResult:
        return VerificationResult(
            task_id=request.task_id,
            verified=True,
            rationale="Outcome independently confirmed in system logs.",
            evidence=[
                Evidence(
                    source_type="SYSTEM_AUDIT",
                    source_id="covenant_audit_01",
                    summary="Milestone review verified",
                    collected_by="CorroboratedVerifier",
                )
            ],
            verified_by="CorroboratedVerifier",
        )


@pytest.fixture(autouse=True)
def reset_covenant_world():
    workspace_store.reset()
    yield
    workspace_store.reset()


@pytest.mark.asyncio
async def test_realistic_multi_turn_protocol():
    """Section 9: Realistic multi-turn sequence:
    Turn 0: get_project_status
    Turn 1: search_email
    Turn 2: Complete
    Verifies that runtime exclusively owns history, state, observations, and telemetry.
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
        id="covenant.external_investigator",
        name="External Investigator",
        supported_roles=["covenant.investigator"],
    )
    # Grant permissions to the external agent
    bridge_env.permissions.grant("org_covenant_northstar", agent_def.id, ["get_project_status", "search_email"])

    ext_worker = MultiTurnInvestigatorAgent()
    adapter = ExternalAgentAdapter(agent_def, external_agent=ext_worker, event_sink=sink)

    task = Task(
        id="tsk_multi_turn_01",
        organization_id="org_covenant_northstar",
        intent="Investigate Atlas deliverable delays",
        required_role="covenant.investigator",
        requires_verification=True,
    )
    ctx = TaskContext(
        task_id=task.id,
        organization_id=task.organization_id,
        intent=task.intent,
        required_role=task.required_role,
        scope=TaskScope(scope_type=ScopeType.ENTITY, entity_type="project", entity_ids=["PRJ-ATLAS"]),
        available_tools=bridge_env.tools.list_specs(),
        input_data={"project_id": "PRJ-ATLAS"},
        max_turns=5,
    )

    run, history, appr = await executor.execute_run(task, agent=adapter, context=ctx)

    # 1. Verify Run State
    assert run.status == AgentRunState.COMPLETED
    assert run.turn_count == 3
    assert "Atlas is overdue" in run.completion_summary
    assert appr is None

    # 2. Verify History & Turns
    assert len(history.turns) == 3
    # Turn 0: get_project_status
    assert history.turns[0].turn_index == 1
    assert history.turns[0].request.tool_name == "get_project_status"
    assert history.turns[0].observation.success is True
    # Turn 1: search_email
    assert history.turns[1].turn_index == 2
    assert history.turns[1].request.tool_name == "search_email"
    assert history.turns[1].observation.success is True
    # Turn 2: Complete
    assert history.turns[2].turn_index == 3
    assert history.turns[2].request is None

    # 3. Verify Telemetry Records
    events = await sink.list_events(task_id=task.id)
    req_events = [e for e in events if e.event_type == EventType.EXTERNAL_AGENT_REQUESTED]
    resp_events = [e for e in events if e.event_type == EventType.EXTERNAL_AGENT_RESPONDED]
    tool_events = [e for e in events if e.event_type == EventType.TOOL_EXECUTION_COMPLETED]

    assert len(req_events) == 3
    assert len(resp_events) == 3
    assert len(tool_events) == 2

    # 4. Verify Independent VerificationGate
    gate = VerificationGate(sink)
    verif = await gate.verify_task(
        task=task,
        verifier=CorroboratedVerifier(),
        expected_outcome="Investigation corroborated",
    )
    assert verif.verified is True
    assert len(verif.evidence) == 1


@pytest.mark.asyncio
async def test_multi_entity_scope_delivered_to_external_agent():
    """Section 21: TaskScope(MULTI_ENTITY) delivered through external agent protocol.
    Runtime continues to enforce authorization/policy per ToolRequest.
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
        id="covenant.external_multi_evaluator",
        name="External Multi Evaluator",
        supported_roles=["covenant.investigator"],
    )
    bridge_env.permissions.grant("org_covenant_northstar", agent_def.id, ["verify_commitment"])

    ext_worker = MultiEntityEvaluatorAgent()
    adapter = ExternalAgentAdapter(agent_def, external_agent=ext_worker, event_sink=sink)

    entity_ids = ["com_atlas_approval", "com_apex_repair"]
    multi_task = Task(
        id="tsk_multi_entity_01",
        organization_id="org_covenant_northstar",
        intent="Batch investigate commitments",
        required_role="covenant.investigator",
        scope=TaskScope(
            scope_type=ScopeType.MULTI_ENTITY,
            entity_type="covenant.commitment",
            entity_ids=entity_ids,
            filter_criteria={"status": "OVERDUE"},
        ),
    )
    ctx = TaskContext(
        task_id=multi_task.id,
        organization_id=multi_task.organization_id,
        intent=multi_task.intent,
        required_role=multi_task.required_role,
        scope=multi_task.scope,
        available_tools=bridge_env.tools.list_specs(),
        input_data={"commitment_ids": entity_ids},
        max_turns=6,
    )

    run, history, _ = await executor.execute_run(multi_task, adapter, ctx)

    assert run.status == AgentRunState.COMPLETED
    assert ext_worker.scope_received is not None
    assert ext_worker.scope_received["scope_type"] == "MULTI_ENTITY"
    assert ext_worker.scope_received["entity_ids"] == entity_ids
    assert run.output_payload["evaluated_entities"] == entity_ids


@pytest.mark.asyncio
async def test_real_covenant_scenario_shadow_isolation():
    """Section 19 & 20: Real Covenant workflow executed inside shadow isolated sandbox:
    investigate -> formulate action -> policy -> approval -> execution -> verification.
    Guarantees no production mutation and no external side effects.
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
        id="covenant.external_resolver",
        name="External Resolver",
        supported_roles=["covenant.resolver"],
    )
    bridge_env.permissions.grant("org_covenant_northstar", agent_def.id, ["get_project_status", "send_followup"])

    class RealCovenantAgent(IExternalAgent):
        def __init__(self):
            self.turn = 0

        async def decide(self, request: ExternalAgentRequest) -> ExternalAgentResponse:
            self.turn += 1
            if self.turn == 1:
                # Step 1: Investigate project status
                return ExternalAgentResponse(
                    response_type=ExternalAgentResponseType.TOOL_PROPOSAL,
                    tool_proposal=ExternalAgentToolProposal(
                        tool_name="get_project_status",
                        arguments={"project_id": "PRJ-ATLAS"},
                    ),
                    rationale="Looking up project status for PRJ-ATLAS.",
                )
            elif self.turn == 2:
                # Step 2: Formulate action requiring approval
                return ExternalAgentResponse(
                    response_type=ExternalAgentResponseType.TOOL_PROPOSAL,
                    tool_proposal=ExternalAgentToolProposal(
                        tool_name="send_followup",
                        arguments={
                            "commitment_id": "com_atlas_approval",
                            "recipient_email": "sjenkins@meridianglobal.com",
                            "subject": "Atlas Phase 2 Deliverable Formal Sign-Off",
                            "body": "Sarah, please provide formal sign-off for Phase 2 deliverable.",
                        },
                    ),
                    rationale="Status inspected. Proposing client follow-up.",
                )
            else:
                # Step 3: Conclude after approved tool execution
                return ExternalAgentResponse(
                    response_type=ExternalAgentResponseType.COMPLETE,
                    completion_summary="Follow-up sent successfully under human supervision.",
                    output_payload={"status": "RESOLVED"},
                )

    adapter = ExternalAgentAdapter(agent_def, external_agent=RealCovenantAgent(), event_sink=sink)

    task = Task(
        id="tsk_real_cov_01",
        organization_id="org_covenant_northstar",
        intent="Resolve overdue sign-off",
        required_role="covenant.resolver",
        requires_verification=True,
    )
    ctx = TaskContext(
        task_id=task.id,
        organization_id=task.organization_id,
        intent=task.intent,
        required_role=task.required_role,
        scope=TaskScope(scope_type=ScopeType.ENTITY, entity_id="com_atlas_approval"),
        available_tools=bridge_env.tools.list_specs(),
        max_turns=5,
    )

    store = clone_workspace_store(workspace_store)
    with ExternalSideEffectGuard(), scoped_workspace_store(store):
        # Phase 1: Investigation turn 1 succeeds, action turn 2 halts for human approval
        run, history, appr = await executor.execute_run(task, adapter, ctx)
        assert run.status == AgentRunState.AWAITING_APPROVAL
        assert appr is not None
        assert appr.tool_request.tool_name == "send_followup"

        # Phase 2: Authoritative human approval granted
        appr.status = ApprovalState.APPROVED
        appr.reviewed_by = "lead_ops@northstar.com"

        # Phase 3: Resume run with approved request
        resumed_run, resumed_history, final_appr = await executor.execute_run(
            task, adapter, ctx, run=run, history=history, approval_resume=appr
        )
        assert resumed_run.status == AgentRunState.COMPLETED
        assert final_appr is None
        assert "Follow-up sent" in resumed_run.completion_summary

        # Phase 4: VerificationGate evaluates outcome
        gate = VerificationGate(sink)
        verif = await gate.verify_task(
            task=task,
            verifier=CorroboratedVerifier(),
            expected_outcome="Client follow-up confirmed in communication audit",
        )
        assert verif.verified is True
