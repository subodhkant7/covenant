"""Section 33: Canonical runtime-only integration test.

Proves the complete runtime execution protocol:
Task -> Router -> AgentRun -> Agent -> ToolRequest(read) -> Auth -> Policy ->
ToolExecution -> Observation -> Agent -> ToolRequest(mutating) -> Policy ->
Human Approval -> Approval -> ToolExecution -> Observation -> AgentComplete ->
Verification -> TaskCompleted -> Events.
"""

from datetime import datetime, timezone
import pytest

from agent_runtime.core.authorization.matrix import ToolPermissionMatrix
from agent_runtime.core.contracts.agent import (
    AgentDefinition,
    AgentRunHistory,
    AgentStepComplete,
    AgentStepToolRequest,
)
from agent_runtime.core.contracts.context import Task, TaskContext, TaskScope
from agent_runtime.core.contracts.event import Event, EventType
from agent_runtime.core.contracts.tool import ToolRequest, ToolSpec
from agent_runtime.core.contracts.verification import Evidence, VerificationRequest, VerificationResult
from agent_runtime.core.engine.execution import ExecutionEngine
from agent_runtime.core.engine.registry import AgentRegistry, ToolRegistry
from agent_runtime.core.engine.router import DeterministicTaskRouter
from agent_runtime.core.engine.run_executor import AgentRunExecutor
from agent_runtime.core.interfaces.agent import IAgent
from agent_runtime.core.interfaces.tool import ITool
from agent_runtime.core.interfaces.verification import IVerifier
from agent_runtime.core.policy.engine import DefaultPolicyEngine
from agent_runtime.core.state.enums import ApprovalState, ScopeType, TaskState
from agent_runtime.core.state.machine import task_validator
from agent_runtime.core.telemetry.sink import InMemoryEventSink
from agent_runtime.core.verification.gate import VerificationGate


# 1. Fake Synthetic Tools
class QueryStatusTool(ITool):
    spec = ToolSpec(
        name="query_status",
        description="Reads current operational status",
        parameters_schema={"type": "object", "required": ["item_id"]},
        has_side_effects=False,
    )

    async def execute(self, item_id: str, **kwargs):
        return {"item_id": item_id, "status": "PENDING_RESPONSE", "days_overdue": 3}


class DispatchNoticeTool(ITool):
    spec = ToolSpec(
        name="dispatch_notice",
        description="Sends external formal notice",
        parameters_schema={"type": "object", "required": ["recipient", "message"]},
        has_side_effects=True,
    )

    async def execute(self, recipient: str, message: str, **kwargs):
        return {"sent_to": recipient, "dispatched_at": "2026-09-03T12:00:00Z", "status": "SENT"}


# 2. Fake Multi-Turn Agent
class CanonicalLifecycleAgent(IAgent):
    definition = AgentDefinition(
        id="canonical_investigator_agent",
        name="Canonical Investigator",
        supported_roles=["role_investigator"],
    )

    async def step(self, context: TaskContext, history: AgentRunHistory):
        # Turn 1: Query status (read-only)
        if history.turn_count == 0:
            return AgentStepToolRequest(
                thought="Must query item status first.",
                request=ToolRequest(tool_name="query_status", arguments={"item_id": "ITEM-101"}),
            )
        # Turn 2: Dispatch notice (mutating, side effect)
        elif history.turn_count == 1:
            return AgentStepToolRequest(
                thought="Overdue condition confirmed. Requesting external notice dispatch.",
                request=ToolRequest(
                    tool_name="dispatch_notice",
                    arguments={"recipient": "counterparty@example.com", "message": "Notice: Action required."},
                ),
            )
        # Turn 3: Conclude reasoning
        else:
            return AgentStepComplete(
                thought="Notice sent; ready for independent outcome verification.",
                summary="Investigation complete. Remedy notice dispatched.",
                output_payload={"resolved": True, "notice_sent": True},
            )


# 3. Fake Independent Verifier
class CanonicalOutcomeVerifier(IVerifier):
    async def verify(self, request: VerificationRequest, context):
        ev = Evidence(
            source_type="COUNTERPARTY_STREAM",
            source_id="ACK-992",
            summary="Signed counterparty acknowledgment received in stream",
            collected_by="CanonicalVerifier",
        )
        return VerificationResult(
            task_id=request.task_id,
            verified=True,
            rationale="Formal acknowledgment corroborated in external stream.",
            evidence=[ev],
            verified_by="CanonicalVerifier",
        )


@pytest.mark.asyncio
async def test_canonical_end_to_end_runtime_flow():
    """
    Complete end-to-end execution through the runtime kernel:
    Router -> AgentRun -> Turn 1 (read tool) -> Turn 2 (mutating tool gated by policy) ->
    Human Approval -> Resume -> Complete -> Verification Gate -> Task Completed.
    """
    # Setup kernel services
    tools = ToolRegistry()
    tools.register(QueryStatusTool())
    tools.register(DispatchNoticeTool())

    agents = AgentRegistry()
    agent = CanonicalLifecycleAgent()
    agents.register(agent)

    perms = ToolPermissionMatrix()
    perms.grant("org_canonical", "canonical_investigator_agent", ["query_status", "dispatch_notice"])

    policy = DefaultPolicyEngine()
    sink = InMemoryEventSink()
    router = DeterministicTaskRouter()
    engine = ExecutionEngine(tools, perms, policy, sink)
    run_executor = AgentRunExecutor(engine, sink)
    verif_gate = VerificationGate(sink)

    # 1. Task exists
    task = Task(
        organization_id="org_canonical",
        intent="Investigate and remediate overdue item ITEM-101",
        required_role="role_investigator",
        scope=TaskScope(scope_type=ScopeType.ENTITY, entity_type="work_item", entity_ids=["ITEM-101"]),
        requires_verification=True,
    )
    assert task.status == TaskState.PENDING
    await sink.record(
        Event(
            trace_id=f"trc_{task.id}",
            organization_id=task.organization_id,
            task_id=task.id,
            event_type=EventType.TASK_CREATED,
            summary="Task created",
        )
    )

    # 2. Router selects Agent
    candidate = await router.route(task, agents)
    assert candidate is not None
    assert candidate.id == "canonical_investigator_agent"
    task_validator.validate_transition(task.status, TaskState.ROUTED)
    task.status = TaskState.ROUTED

    # 3. Start AgentRun & Turn Loop (Phase A: runs until Human Approval blocks)
    task_validator.validate_transition(task.status, TaskState.RUNNING)
    task.status = TaskState.RUNNING

    context = TaskContext(
        task_id=task.id,
        organization_id=task.organization_id,
        intent=task.intent,
        required_role=task.required_role,
        scope=task.scope,
        available_tools=tools.list_specs(),
        max_turns=5,
    )

    run, history, approval_req = await run_executor.execute_run(task, agent, context)

    # Turn 1 executed query_status autonomously
    assert len(history.turns) == 2  # Turn 1 (query) and Turn 2 (dispatch pending)
    assert history.turns[0].observation.data["status"] == "PENDING_RESPONSE"

    # Turn 2 triggered policy REQUIRE_HUMAN_APPROVAL for dispatch_notice
    assert approval_req is not None
    assert approval_req.status == ApprovalState.PENDING
    assert approval_req.tool_request.tool_name == "dispatch_notice"

    # Task transitions to BLOCKED
    task_validator.validate_transition(task.status, TaskState.BLOCKED)
    task.status = TaskState.BLOCKED

    # 4. Human Approval Gate
    # Human inspects request, softens text, and approves
    approval_req.status = ApprovalState.APPROVED
    approval_req.reviewed_by = "LeadSupervisor"
    approval_req.reviewed_at = datetime.now(timezone.utc)
    approval_req.modified_arguments = {
        "recipient": "counterparty@example.com",
        "message": "Polite Reminder: Action required.",
    }

    # 5. Resume Turn Loop after Approval (Phase B: runs until Completion)
    task_validator.validate_transition(task.status, TaskState.RUNNING)
    task.status = TaskState.RUNNING

    run2, history2, approval_req2 = await run_executor.execute_run(
        task=task,
        agent=agent,
        context=context,
        run=run,
        history=history,
        approval_resume=approval_req,
    )

    assert approval_req2 is None
    # Approval was executed with modified arguments
    assert approval_req.status == ApprovalState.EXECUTED
    # Turn 2 executed with modified arguments
    assert history2.turns[2].observation.data["status"] == "SENT"
    # Turn 3 finished with AgentStepComplete
    assert run2.status.value == "COMPLETED"
    assert run2.output_payload["resolved"] is True

    # 6. Verification Gate
    task_validator.validate_transition(task.status, TaskState.VERIFYING)
    task.status = TaskState.VERIFYING

    verifier = CanonicalOutcomeVerifier()
    v_res = await verif_gate.verify_task(
        task=task,
        verifier=verifier,
        expected_outcome="Signed counterparty acknowledgment received",
    )
    assert v_res.verified is True
    assert len(v_res.evidence) == 1
    assert v_res.evidence[0].source_id == "ACK-992"

    # 7. Authoritative Task Completion
    task_validator.validate_transition(task.status, TaskState.COMPLETED)
    task.status = TaskState.COMPLETED

    # 8. Event Audit Integrity Check
    events = await sink.list_events(task_id=task.id)
    event_types = [e.event_type for e in events]
    assert EventType.TOOL_REQUESTED in event_types
    assert EventType.POLICY_EVALUATED in event_types
    assert EventType.APPROVAL_REQUESTED in event_types
    assert EventType.APPROVAL_DECIDED in event_types
    assert EventType.TOOL_EXECUTION_COMPLETED in event_types
    assert EventType.VERIFICATION_STARTED in event_types
    assert EventType.VERIFICATION_DONE in event_types
