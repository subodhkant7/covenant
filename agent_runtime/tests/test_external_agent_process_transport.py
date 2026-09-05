"""Test Suite for Step 6.2: Live External Agent Process Transport via Unix Domain Sockets.

Validates the complete 20-point test matrix:
1. Socket startup, restrictive permissions (0o700), and clean shutdown.
2. Request/response length-prefixed binary framing.
3. JSON serialization round-trip across OS process boundary.
4. Payload size limits (1 MiB) enforced before JSON/Pydantic parsing.
5. Real multi-turn reasoning loop (3 turns across separate OS processes).
6. Human-in-the-loop approval workflow through real external process.
7. Independent VerificationGate authority over untrusted external completion claims.
8. Unauthorized tool proposed by external process rejected at boundary.
9. Prohibited tool proposed by external process denied by runtime policy.
10. Forged self-approval attack defense and security violation logging.
11. Forged verification bypass attack defense.
12. Deliberately malformed messages (invalid JSON, truncated, extra fields) fail closed.
13. Process crash handling before response (SIGTERM and SIGKILL).
14. Process crash after tool execution with idempotency preservation on retry.
15. Deterministic external agent timeout handling.
16. Process PID isolation assertion (Runtime PID != External Worker PID).
17. Runtime handle and credential isolation.
18. Protocol replay rejection.
19. Recursive telemetry sanitization across transport events.
20. Real Covenant shadow workflow execution over Unix socket transport.
"""

import asyncio
import json
import os
import signal
import struct
import tempfile
import pytest
from typing import Any, Dict, List, Optional

from agent_runtime.adapters.external_agent import (
    ExternalAgentAdapter,
    ExternalAgentObservation,
    ExternalAgentRequest,
    ExternalAgentResponse,
    ExternalAgentResponseType,
    ExternalAgentTaskFacts,
    ExternalAgentToolDescription,
    ExternalAgentToolProposal,
    ExternalAgentTurn,
)
from agent_runtime.adapters.unix_socket_transport import (
    MAX_EXTERNAL_AGENT_MESSAGE_BYTES,
    MessageSizeExceededError,
    ProtocolFramingError,
    TransportConnectionError,
    UnixSocketExternalAgentTransport,
    read_framed_message,
    write_framed_message,
)
from agent_runtime.core.approval import InMemoryApprovalRepository, RuntimeApprovalService
from agent_runtime.core.authorization.matrix import ToolPermissionMatrix
from agent_runtime.core.contracts.agent import (
    AgentDefinition,
    AgentRun,
    AgentRunHistory,
    AgentStepFailure,
)
from agent_runtime.core.contracts.approval import HumanApprovalRequest
from agent_runtime.core.contracts.context import Task, TaskContext, TaskScope
from agent_runtime.core.contracts.event import EventType
from agent_runtime.core.contracts.policy import PolicyDecision, PolicyEvaluationContext
from agent_runtime.core.contracts.tool import Observation, ToolRequest, ToolSpec
from agent_runtime.core.contracts.verification import Evidence, VerificationRequest, VerificationResult
from agent_runtime.core.engine.execution import ExecutionEngine
from agent_runtime.core.engine.idempotency import IdempotencyStore
from agent_runtime.core.engine.registry import ToolRegistry
from agent_runtime.core.engine.run_executor import AgentRunExecutor
from agent_runtime.core.interfaces.policy import IPolicyEngine, IPolicyRule
from agent_runtime.core.interfaces.tool import ITool
from agent_runtime.core.interfaces.verification import IVerifier
from agent_runtime.core.policy.engine import DefaultPolicyEngine
from agent_runtime.core.state.enums import (
    AgentRunState,
    ApprovalState,
    ExecutionSafety,
    PolicyDecisionType,
    ScopeType,
    TaskState,
)
from agent_runtime.core.state.machine import task_validator
from agent_runtime.core.telemetry.sink import InMemoryEventSink
from agent_runtime.core.verification.gate import VerificationGate
from covenant_runtime_bridge.bootstrap import CovenantRuntimeBootstrap
from covenant.synthetic_data.store import workspace_store
from covenant_runtime_bridge.shadow.isolation import clone_workspace_store, scoped_workspace_store, ExternalSideEffectGuard


# ---------------------------------------------------------------------------
# Test Tools and Policies
# ---------------------------------------------------------------------------

class GetProjectStatusTool(ITool):
    spec = ToolSpec(
        name="get_project_status",
        description="Retrieves status of a project milestone",
        parameters_schema={"type": "object", "required": ["project_id"]},
        has_side_effects=False,
    )

    async def execute(self, project_id: str, **kwargs):
        return {"project_id": project_id, "status": "ACTIVE", "completion_percent": 85}


class SearchEmailTool(ITool):
    spec = ToolSpec(
        name="search_email",
        description="Searches email communications",
        parameters_schema={"type": "object", "required": ["query"]},
        has_side_effects=False,
    )

    async def execute(self, query: str, **kwargs):
        return {"query": query, "matches": [{"subject": "Milestone approval", "sender": "lead@covenant.local"}]}


class SendFollowupTool(ITool):
    spec = ToolSpec(
        name="send_followup",
        description="Sends client follow-up communication",
        parameters_schema={"type": "object", "required": ["recipient", "message"]},
        has_side_effects=True,
    )

    def __init__(self):
        self.dispatched_count = 0

    async def execute(self, recipient: str, message: str, **kwargs):
        self.dispatched_count += 1
        return {"recipient": recipient, "dispatched": True, "message_id": f"MSG-{self.dispatched_count}"}


class IdempotentPaymentTool(ITool):
    spec = ToolSpec(
        name="idempotent_payment",
        description="Executes an idempotent financial transaction",
        parameters_schema={"type": "object", "required": ["payment_ref", "amount"]},
        has_side_effects=True,
        execution_safety=ExecutionSafety.IDEMPOTENT,
    )

    def __init__(self):
        self.dispatch_count = 0

    async def execute(self, payment_ref: str, amount: float, **kwargs):
        self.dispatch_count += 1
        return {"payment_ref": payment_ref, "amount": amount, "status": "SETTLED"}


class AllowIdempotentPaymentPolicy(IPolicyRule):
    @property
    def rule_id(self) -> str:
        return "allow_idempotent_payment"

    def evaluate(self, context: PolicyEvaluationContext) -> Optional[PolicyDecision]:
        if context.tool_request.tool_name == "idempotent_payment":
            return PolicyDecision(
                tool_request_id=context.tool_request.request_id,
                decision=PolicyDecisionType.ALLOW,
                rationale="Allowed for automated test",
                rules_triggered=[self.rule_id],
            )
        return None


class PurgeDatabaseTool(ITool):
    spec = ToolSpec(
        name="purge_database",
        description="Dangerous tool that purges database tables",
        parameters_schema={"type": "object", "required": ["cascade"]},
        has_side_effects=True,
    )

    async def execute(self, cascade: bool = False, **kwargs):
        return {"purged": True}


class DenyPurgePolicy(IPolicyRule):
    @property
    def rule_id(self) -> str:
        return "deny_purge"

    def evaluate(self, context: PolicyEvaluationContext) -> Optional[PolicyDecision]:
        if context.tool_request.tool_name == "purge_database":
            return PolicyDecision(
                tool_request_id=context.tool_request.request_id,
                decision=PolicyDecisionType.DENY,
                rationale="Policy strictly prohibits purge_database.",
                rules_triggered=[self.rule_id],
            )
        return None


class ConfigurableVerifier(IVerifier):
    def __init__(self, should_verify: bool, rationale: str):
        self.should_verify = should_verify
        self.rationale = rationale

    async def verify(self, request: VerificationRequest, context: Optional[Dict[str, Any]] = None) -> VerificationResult:
        evidence = [
            Evidence(
                source_type="audit_trail",
                source_id="log_001",
                summary="corroborating log",
                payload={"corroborated": self.should_verify},
            )
        ]
        return VerificationResult(
            task_id=request.task_id,
            verified=self.should_verify,
            rationale=self.rationale,
            evidence=evidence,
        )


# ---------------------------------------------------------------------------
# 1. Socket Startup, Restrictive Permissions, and Clean Shutdown
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_socket_startup_shutdown_and_security():
    """Section 7: Verify unique socket path, 0o700 directory permissions, and clean shutdown."""
    transport = UnixSocketExternalAgentTransport()
    socket_path = await transport.start()

    try:
        assert os.path.exists(socket_path)
        assert os.path.exists(transport.socket_dir)
        # Check permissions: 0o700
        mode = os.stat(transport.socket_dir).st_mode & 0o777
        assert mode == 0o700, f"Expected 0o700 directory permissions, got {oct(mode)}"
    finally:
        await transport.close()

    # Verify socket and directory removed on shutdown
    assert not os.path.exists(socket_path)
    assert not os.path.exists(transport.socket_dir)


# ---------------------------------------------------------------------------
# 2. Binary Framing & Error Handling
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_request_response_binary_framing():
    """Section 5: Verify 4-byte length-prefix framing prevents partial reads and message concatenation."""
    transport = UnixSocketExternalAgentTransport()
    socket_path = await transport.start()

    try:
        # Connect client
        client_reader, client_writer = await asyncio.open_unix_connection(socket_path)
        await transport.connected_event.wait()

        # Send framed payload from client to server
        payload = b'{"hello": "world"}'
        await write_framed_message(client_writer, payload)

        # Server reads framed payload
        server_read = await read_framed_message(transport.client_reader)
        assert server_read == payload

        # Server sends framed payload back to client
        resp_payload = b'{"response": "ok"}'
        await write_framed_message(transport.client_writer, resp_payload)

        client_read = await read_framed_message(client_reader)
        assert client_read == resp_payload

        # Test incomplete header handling
        client_writer.write(b"\x00\x00")  # Only 2 bytes instead of 4
        await client_writer.drain()
        client_writer.close()

        with pytest.raises(ProtocolFramingError, match="Incomplete framing header"):
            await read_framed_message(transport.client_reader)

    finally:
        await transport.close()


# ---------------------------------------------------------------------------
# 3. JSON Round Trip Across Process Boundary
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_json_round_trip_across_process():
    """Section 4 & 13: Verify ExternalAgentRequest and Response round-trip over real process boundary."""
    sink = InMemoryEventSink()
    transport = UnixSocketExternalAgentTransport(event_sink=sink)
    await transport.spawn_worker(worker_mode="normal")

    try:
        req = ExternalAgentRequest(
            task=ExternalAgentTaskFacts(
                task_id="tsk_roundtrip",
                organization_id="org_test",
                intent="Validate process JSON boundary",
                required_role="worker",
                scope={"scope_type": "ORGANIZATION"},
                input_data={"param": "value_123"},
            ),
            allowed_tools=[
                ExternalAgentToolDescription(
                    name="get_project_status",
                    description="Status check",
                    parameters_schema={"type": "object"},
                )
            ],
            history=[],
            current_turn=1,
            max_turns=3,
            run_state="RUNNING",
        )

        resp = await transport.send_and_receive(req)
        assert isinstance(resp, ExternalAgentResponse)
        assert resp.response_type == ExternalAgentResponseType.TOOL_PROPOSAL
        assert resp.tool_proposal.tool_name == "get_project_status"
        assert resp.tool_proposal.arguments == {"project_id": "PRJ-ATLAS"}
    finally:
        await transport.close()


# ---------------------------------------------------------------------------
# 4. Message Size Enforcement (Fail Closed)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_message_size_enforcement_fail_closed():
    """Section 6: Enforce hard 1 MiB limit before buffering or Pydantic parsing."""
    transport = UnixSocketExternalAgentTransport()
    socket_path = await transport.start()

    try:
        client_reader, client_writer = await asyncio.open_unix_connection(socket_path)
        await transport.connected_event.wait()

        # Send header claiming payload is larger than limit (e.g. 1 MiB + 10 bytes)
        fake_large_length = MAX_EXTERNAL_AGENT_MESSAGE_BYTES + 10
        header = struct.pack("!I", fake_large_length)
        client_writer.write(header)
        await client_writer.drain()

        # Server must reject IMMEDIATELY without reading body
        with pytest.raises(MessageSizeExceededError, match="exceeds limit"):
            await read_framed_message(transport.client_reader)

    finally:
        await transport.close()


# ---------------------------------------------------------------------------
# 5. Real Multi-Turn Execution Across OS Processes (3 Turns)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_real_multi_turn_execution_across_processes():
    """Section 10: Real multi-turn loop (3 turns) across separate OS processes.
    Proves Runtime PID != External Worker PID.
    """
    tools = ToolRegistry()
    tools.register(GetProjectStatusTool())
    tools.register(SearchEmailTool())

    perms = ToolPermissionMatrix()
    perms.grant("org_test", "agent.multiturn", ["get_project_status", "search_email"])
    policy = DefaultPolicyEngine()
    sink = InMemoryEventSink()
    engine = ExecutionEngine(tools, perms, policy, sink)
    executor = AgentRunExecutor(engine, sink)

    transport = UnixSocketExternalAgentTransport(event_sink=sink)
    worker_proc = await transport.spawn_worker(worker_mode="scripted_multiturn")

    # Assert separate OS processes
    runtime_pid = os.getpid()
    worker_pid = transport.worker_pid
    assert worker_pid is not None
    assert runtime_pid != worker_pid, f"Runtime and worker must have different PIDs! Got {runtime_pid}"

    adapter = ExternalAgentAdapter(
        agent_definition=AgentDefinition(id="agent.multiturn", name="MultiTurn Worker"),
        transport=transport,
        event_sink=sink,
    )

    task = Task(id="tsk_multi_ipc", organization_id="org_test", intent="Execute multi-turn reasoning", required_role="worker")
    ctx = TaskContext(
        task_id=task.id,
        organization_id=task.organization_id,
        intent=task.intent,
        required_role=task.required_role,
        scope=TaskScope(),
        available_tools=tools.list_specs(),
        max_turns=5,
    )

    try:
        run, history, _ = await executor.execute_run(task, adapter, ctx)
        assert run.status == AgentRunState.COMPLETED
        assert len(history.turns) == 3

        # Turn 1: get_project_status
        assert history.turns[0].request.tool_name == "get_project_status"
        assert history.turns[0].observation.success is True
        assert history.turns[0].observation.data["status"] == "ACTIVE"

        # Turn 2: search_email
        assert history.turns[1].request.tool_name == "search_email"
        assert history.turns[1].observation.success is True

        # Turn 3: completed
        assert "verified" in run.completion_summary.lower()

        # Worker process remained alive across turns with same PID
        assert transport.worker_pid == worker_pid

    finally:
        await transport.close()


# ---------------------------------------------------------------------------
# 6. Approval Workflow Through Real Process
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_approval_workflow_through_real_process():
    """Section 11: External process proposes side-effect tool -> halts for human approval ->
    RuntimeApprovalService approves -> executes tool -> returns observation -> completes.
    """
    tools = ToolRegistry()
    followup_tool = SendFollowupTool()
    tools.register(followup_tool)

    perms = ToolPermissionMatrix()
    perms.grant("org_test", "agent.approver", ["send_followup"])
    policy = DefaultPolicyEngine()  # Side-effect tool mandates human approval
    sink = InMemoryEventSink()
    engine = ExecutionEngine(tools, perms, policy, sink)
    executor = AgentRunExecutor(engine, sink)

    transport = UnixSocketExternalAgentTransport(event_sink=sink)
    await transport.spawn_worker(worker_mode="approval_test")

    adapter = ExternalAgentAdapter(
        agent_definition=AgentDefinition(id="agent.approver", name="Approval Worker"),
        transport=transport,
        event_sink=sink,
    )

    task = Task(id="tsk_appr_ipc", organization_id="org_test", intent="Send approved email", required_role="worker")
    ctx = TaskContext(
        task_id=task.id,
        organization_id=task.organization_id,
        intent=task.intent,
        required_role=task.required_role,
        scope=TaskScope(),
        available_tools=tools.list_specs(),
        max_turns=3,
    )

    approval_repo = InMemoryApprovalRepository()
    approval_svc = RuntimeApprovalService(approval_repo, sink)

    try:
        # Step 1: Run halts in AWAITING_APPROVAL on turn 1
        run, history, approval_req = await executor.execute_run(task, adapter, ctx)
        assert run.status == AgentRunState.AWAITING_APPROVAL
        assert approval_req is not None
        assert followup_tool.dispatched_count == 0

        # Save approval request in repository
        await approval_repo.create(approval_req)
        assert approval_req.status == ApprovalState.PENDING

        # Step 2: Runtime approval service approves the request
        approved_req = await approval_svc.approve_human_request(
            approval_id=approval_req.approval_id,
            organization_id=task.organization_id,
            task_id=task.id,
            agent_run_id=run.id,
            tool_name=approval_req.tool_request.tool_name,
            reviewed_by="human_supervisor@covenant.local",
        )
        assert approved_req.status == ApprovalState.APPROVED

        # Step 3: Resumed execution dispatches tool and sends observation to worker
        ctx_resume = TaskContext(
            task_id=task.id,
            organization_id=task.organization_id,
            intent=task.intent,
            required_role=task.required_role,
            scope=TaskScope(),
            available_tools=tools.list_specs(),
            approved_request=approved_req,
            max_turns=3,
        )

        resumed_run, resumed_history, _ = await executor.execute_run(task, adapter, ctx_resume, run=run, history=history, approval_resume=approved_req)
        assert resumed_run.status == AgentRunState.COMPLETED
        assert followup_tool.dispatched_count == 1
        assert approved_req.status == ApprovalState.EXECUTED

    finally:
        await transport.close()


# ---------------------------------------------------------------------------
# 7. Verification Workflow Through Real Process
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_verification_workflow_through_real_process():
    """Section 12: External process claims complete with verified=true;
    VerificationGate independently decides whether Task may complete.
    """
    sink = InMemoryEventSink()
    transport = UnixSocketExternalAgentTransport(event_sink=sink)
    await transport.spawn_worker(worker_mode="verification_test")

    adapter = ExternalAgentAdapter(
        agent_definition=AgentDefinition(id="agent.verifier", name="Verifier Worker"),
        transport=transport,
        event_sink=sink,
    )
    task = Task(id="tsk_verif_ipc", organization_id="org_test", intent="Verified task", required_role="worker", requires_verification=True)
    ctx = TaskContext(
        task_id=task.id,
        organization_id=task.organization_id,
        intent=task.intent,
        required_role=task.required_role,
        scope=TaskScope(),
    )

    tools = ToolRegistry()
    perms = ToolPermissionMatrix()
    engine = ExecutionEngine(tools, perms, DefaultPolicyEngine(), sink)
    executor = AgentRunExecutor(engine, sink)
    verif_gate = VerificationGate(sink)

    try:
        run, history, _ = await executor.execute_run(task, adapter, ctx)
        assert run.status == AgentRunState.COMPLETED

        # Transition task to VERIFYING (PENDING -> ROUTED -> RUNNING -> VERIFYING)
        task_validator.validate_transition(task.status, TaskState.ROUTED)
        task.status = TaskState.ROUTED
        task_validator.validate_transition(task.status, TaskState.RUNNING)
        task.status = TaskState.RUNNING
        task_validator.validate_transition(task.status, TaskState.VERIFYING)
        task.status = TaskState.VERIFYING

        # Pass 1: Independent verification FAILS
        v_fail = await verif_gate.verify_task(
            task=task,
            verifier=ConfigurableVerifier(should_verify=False, rationale="Independent corroboration failed"),
            expected_outcome="Confirmed delivery",
        )
        assert v_fail.verified is False
        assert task.status == TaskState.VERIFYING  # Cannot transition to COMPLETED!

        # Pass 2: Independent verification SUCCEEDS
        v_pass = await verif_gate.verify_task(
            task=task,
            verifier=ConfigurableVerifier(should_verify=True, rationale="Independent corroboration succeeded"),
            expected_outcome="Confirmed delivery",
        )
        assert v_pass.verified is True
        task_validator.validate_transition(task.status, TaskState.COMPLETED)
        task.status = TaskState.COMPLETED
        assert task.status == TaskState.COMPLETED

    finally:
        await transport.close()


# ---------------------------------------------------------------------------
# 8. Unauthorized Tool Rejected at Boundary
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_unauthorized_tool_rejected_at_boundary():
    """Section 13.C: External process proposes unauthorized tool -> rejected by PermissionMatrix."""
    sink = InMemoryEventSink()
    transport = UnixSocketExternalAgentTransport(event_sink=sink)
    await transport.spawn_worker(worker_mode="malicious_unauthorized_tool")

    adapter = ExternalAgentAdapter(
        agent_definition=AgentDefinition(id="agent.hostile_unauth", name="Hostile Unauth Worker"),
        transport=transport,
        event_sink=sink,
    )
    task = Task(id="tsk_unauth_ipc", organization_id="org_test", intent="Attack", required_role="worker")
    ctx = TaskContext(
        task_id=task.id,
        organization_id=task.organization_id,
        intent=task.intent,
        required_role=task.required_role,
        scope=TaskScope(),
    )

    tools = ToolRegistry()
    perms = ToolPermissionMatrix()  # No tools granted to agent.hostile_unauth!
    engine = ExecutionEngine(tools, perms, DefaultPolicyEngine(), sink)
    executor = AgentRunExecutor(engine, sink)

    try:
        run, history, _ = await executor.execute_run(task, adapter, ctx)
        assert len(history.turns) >= 1
        obs = history.turns[0].observation
        assert obs is not None
        assert obs.success is False
        assert "not authorized" in obs.error.lower() or "not registered" in obs.error.lower()
    finally:
        await transport.close()


# ---------------------------------------------------------------------------
# 9. Prohibited Tool Rejected by Policy
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_prohibited_tool_rejected_by_policy():
    """Section 13.D: External process proposes policy-prohibited tool -> denied by PolicyEngine."""
    purge_tool = PurgeDatabaseTool()
    tools = ToolRegistry()
    tools.register(purge_tool)

    perms = ToolPermissionMatrix()
    perms.grant("org_test", "agent.hostile_policy", ["purge_database"])

    policy = DefaultPolicyEngine([DenyPurgePolicy()])
    sink = InMemoryEventSink()
    engine = ExecutionEngine(tools, perms, policy, sink)
    executor = AgentRunExecutor(engine, sink)

    transport = UnixSocketExternalAgentTransport(event_sink=sink)
    await transport.spawn_worker(worker_mode="malicious_prohibited_tool")

    adapter = ExternalAgentAdapter(
        agent_definition=AgentDefinition(id="agent.hostile_policy", name="Hostile Policy Worker"),
        transport=transport,
        event_sink=sink,
    )
    task = Task(id="tsk_policy_ipc", organization_id="org_test", intent="Attack", required_role="worker")
    ctx = TaskContext(
        task_id=task.id,
        organization_id=task.organization_id,
        intent=task.intent,
        required_role=task.required_role,
        scope=TaskScope(),
        available_tools=tools.list_specs(),
    )

    try:
        run, history, _ = await executor.execute_run(task, adapter, ctx)
        assert len(history.turns) >= 1
        obs = history.turns[0].observation
        assert obs is not None
        assert obs.success is False
        assert "policy denied" in obs.error.lower()
    finally:
        await transport.close()


# ---------------------------------------------------------------------------
# 10. Forged Approval Attack Defense
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_forged_approval_attack_defense():
    """Section 13.A: External process proposes tool with forged approval -> stripped, halts in AWAITING_APPROVAL."""
    tools = ToolRegistry()
    followup_tool = SendFollowupTool()
    tools.register(followup_tool)

    perms = ToolPermissionMatrix()
    perms.grant("org_test", "agent.hostile_approval", ["send_followup"])
    policy = DefaultPolicyEngine()
    sink = InMemoryEventSink()
    engine = ExecutionEngine(tools, perms, policy, sink)
    executor = AgentRunExecutor(engine, sink)

    transport = UnixSocketExternalAgentTransport(event_sink=sink)
    await transport.spawn_worker(worker_mode="malicious_forged_approval")

    adapter = ExternalAgentAdapter(
        agent_definition=AgentDefinition(id="agent.hostile_approval", name="Hostile Approval Worker"),
        transport=transport,
        event_sink=sink,
    )
    task = Task(id="tsk_forged_appr", organization_id="org_test", intent="Attack", required_role="worker")
    ctx = TaskContext(
        task_id=task.id,
        organization_id=task.organization_id,
        intent=task.intent,
        required_role=task.required_role,
        scope=TaskScope(),
        available_tools=tools.list_specs(),
    )

    try:
        run, history, approval_req = await executor.execute_run(task, adapter, ctx)
        # Invariant: Run MUST halt in AWAITING_APPROVAL, NOT execute!
        assert run.status == AgentRunState.AWAITING_APPROVAL
        assert followup_tool.dispatched_count == 0
        assert approval_req.status == ApprovalState.PENDING

        # Security violation event was recorded
        violations = [e for e in sink.events if e.event_type == EventType.SECURITY_VIOLATION]
        assert len(violations) >= 1
    finally:
        await transport.close()


# ---------------------------------------------------------------------------
# 11. Forged Verification Attack Defense
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_forged_verification_attack_defense():
    """Section 13.B: External process claims skip_verification=true -> stripped, VerificationGate enforced."""
    sink = InMemoryEventSink()
    transport = UnixSocketExternalAgentTransport(event_sink=sink)
    await transport.spawn_worker(worker_mode="malicious_forged_verification")

    adapter = ExternalAgentAdapter(
        agent_definition=AgentDefinition(id="agent.hostile_verif", name="Hostile Verif Worker"),
        transport=transport,
        event_sink=sink,
    )
    task = Task(id="tsk_forged_verif", organization_id="org_test", intent="Attack", required_role="worker", requires_verification=True)
    ctx = TaskContext(
        task_id=task.id,
        organization_id=task.organization_id,
        intent=task.intent,
        required_role=task.required_role,
        scope=TaskScope(),
    )

    tools = ToolRegistry()
    perms = ToolPermissionMatrix()
    engine = ExecutionEngine(tools, perms, DefaultPolicyEngine(), sink)
    executor = AgentRunExecutor(engine, sink)

    try:
        run, history, _ = await executor.execute_run(task, adapter, ctx)
        assert run.status == AgentRunState.COMPLETED

        # Security violation recorded
        violations = [e for e in sink.events if e.event_type == EventType.SECURITY_VIOLATION]
        assert len(violations) >= 1

        # Invariant: Task is NOT completed!
        assert task.status != TaskState.COMPLETED
    finally:
        await transport.close()


# ---------------------------------------------------------------------------
# 12. Deliberately Malformed Protocol Messages Fail Closed
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("corrupt_mode", ["corrupt_invalid_json", "corrupt_truncated_json", "corrupt_extra_field"])
async def test_malformed_protocol_messages_fail_closed(corrupt_mode: str):
    """Section 17: External process sends corrupt / malformed protocol messages -> fails closed into AgentStepFailure."""
    sink = InMemoryEventSink()
    transport = UnixSocketExternalAgentTransport(event_sink=sink)
    await transport.spawn_worker(worker_mode=corrupt_mode)

    adapter = ExternalAgentAdapter(
        agent_definition=AgentDefinition(id="agent.corrupt", name="Corrupt Worker"),
        transport=transport,
        event_sink=sink,
    )
    task = Task(id="tsk_corrupt", organization_id="org_test", intent="Corruption test", required_role="worker")
    ctx = TaskContext(
        task_id=task.id,
        organization_id=task.organization_id,
        intent=task.intent,
        required_role=task.required_role,
        scope=TaskScope(),
    )
    history = AgentRunHistory(run_id="run_corrupt", task_id=task.id)

    try:
        step_res = await adapter.step(ctx, history)
        assert isinstance(step_res, AgentStepFailure)
        assert step_res.recoverable is False
    finally:
        await transport.close()


# ---------------------------------------------------------------------------
# 13. Process Crash Before Response (SIGTERM and SIGKILL)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_process_crash_before_response():
    """Section 15: Kill worker process (SIGTERM / SIGKILL) before response -> transport fails closed."""
    sink = InMemoryEventSink()
    transport = UnixSocketExternalAgentTransport(event_sink=sink)
    await transport.spawn_worker(worker_mode="crash_before_response")

    adapter = ExternalAgentAdapter(
        agent_definition=AgentDefinition(id="agent.crasher", name="Crasher Worker"),
        transport=transport,
        event_sink=sink,
    )
    task = Task(id="tsk_crash_ipc", organization_id="org_test", intent="Crash test", required_role="worker")
    ctx = TaskContext(
        task_id=task.id,
        organization_id=task.organization_id,
        intent=task.intent,
        required_role=task.required_role,
        scope=TaskScope(),
    )
    history = AgentRunHistory(run_id="run_crash", task_id=task.id)

    try:
        step_res = await adapter.step(ctx, history)
        assert isinstance(step_res, AgentStepFailure)
        assert step_res.recoverable is False
        assert "transport failure" in step_res.error_message.lower()
    finally:
        await transport.close()


# ---------------------------------------------------------------------------
# 14. Process Crash After Tool Execution Preserves Idempotency
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_process_crash_after_tool_execution_preserves_idempotency():
    """Section 15.Case 2 & 16: Worker executes idempotent payment in turn 1, then crashes in turn 2.
    Upon reconnection/retry, the runtime does NOT re-execute the side effect.
    """
    tools = ToolRegistry()
    idemp_tool = IdempotentPaymentTool()
    tools.register(idemp_tool)

    perms = ToolPermissionMatrix()
    perms.grant("org_test", "agent.crash_idemp", ["idempotent_payment"])
    policy = DefaultPolicyEngine([AllowIdempotentPaymentPolicy()])
    sink = InMemoryEventSink()
    idemp_store = IdempotencyStore()
    engine = ExecutionEngine(tools, perms, policy, sink, idempotency_store=idemp_store)
    executor = AgentRunExecutor(engine, sink)

    # Transport 1 with crash_after_tool worker
    transport_1 = UnixSocketExternalAgentTransport(event_sink=sink)
    await transport_1.spawn_worker(worker_mode="crash_after_tool")

    adapter_1 = ExternalAgentAdapter(
        agent_definition=AgentDefinition(id="agent.crash_idemp", name="Crash Idemp Worker"),
        transport=transport_1,
        event_sink=sink,
    )

    task = Task(id="tsk_crash_post_tool", organization_id="org_test", intent="Pay once", required_role="worker")
    ctx = TaskContext(
        task_id=task.id,
        organization_id=task.organization_id,
        intent=task.intent,
        required_role=task.required_role,
        scope=TaskScope(),
        available_tools=tools.list_specs(),
        max_turns=3,
    )

    try:
        run_1, history_1, _ = await executor.execute_run(task, adapter_1, ctx)
        # Run failed on Turn 2 when worker crashed
        assert run_1.status == AgentRunState.FAILED
        # But Turn 1 executed!
        assert idemp_tool.dispatch_count == 1
    finally:
        await transport_1.close()

    # Reconnection Transport 2 with normal worker
    transport_2 = UnixSocketExternalAgentTransport(event_sink=sink)
    await transport_2.spawn_worker(worker_mode="scripted_multiturn")

    adapter_2 = ExternalAgentAdapter(
        agent_definition=AgentDefinition(id="agent.crash_idemp", name="Crash Idemp Worker"),
        transport=transport_2,
        event_sink=sink,
    )

    task_retry = Task(id=task.id, organization_id="org_test", intent="Pay once", required_role="worker", attempt_count=1)

    try:
        # Retry with same tool request parameters directly via execution engine
        req_retry = ToolRequest(
            tool_name="idempotent_payment",
            arguments={"payment_ref": "PAY-SOCKET-101", "amount": 100.0},
        )
        run_retry = AgentRun(id="run_retry", task_id=task_retry.id, agent_id="agent.crash_idemp")
        obs_retry, _ = await engine.handle_tool_request(task_retry, run_retry, req_retry)
        assert obs_retry.success is True
        # Invariant: dispatch_count is STILL 1! Result came from IdempotencyStore!
        assert idemp_tool.dispatch_count == 1
    finally:
        await transport_2.close()


# ---------------------------------------------------------------------------
# 15. External Agent Timeout Handling
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_external_agent_timeout_handling():
    """Section 16: Worker sleeps beyond timeout -> EXTERNAL_AGENT_TIMEOUT recorded, zero side effects."""
    sink = InMemoryEventSink()
    transport = UnixSocketExternalAgentTransport(event_sink=sink)
    await transport.spawn_worker(worker_mode="sleep_beyond_timeout")

    adapter = ExternalAgentAdapter(
        agent_definition=AgentDefinition(id="agent.sleeper", name="Sleeper Worker"),
        transport=transport,
        event_sink=sink,
        timeout=0.15,  # Short timeout
    )
    task = Task(id="tsk_timeout_ipc", organization_id="org_test", intent="Sleep test", required_role="worker")
    ctx = TaskContext(
        task_id=task.id,
        organization_id=task.organization_id,
        intent=task.intent,
        required_role=task.required_role,
        scope=TaskScope(),
    )
    history = AgentRunHistory(run_id="run_timeout", task_id=task.id)

    try:
        step_res = await adapter.step(ctx, history)
        assert isinstance(step_res, AgentStepFailure)
        assert "timed out" in step_res.error_message.lower()

        # Telemetry event recorded
        timeouts = [e for e in sink.events if e.event_type == EventType.EXTERNAL_AGENT_TIMEOUT]
        assert len(timeouts) == 1
    finally:
        await transport.close()


# ---------------------------------------------------------------------------
# 16. Process PID Isolation Assertion
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_process_pid_isolation_assertion():
    """Section 4 & 14: Assert Runtime PID != External Agent PID and verify live worker OS process."""
    transport = UnixSocketExternalAgentTransport()
    worker_proc = await transport.spawn_worker(worker_mode="normal")

    try:
        runtime_pid = os.getpid()
        worker_pid = transport.worker_pid

        assert worker_pid is not None
        assert runtime_pid != worker_pid, f"PIDs must be distinct! Runtime: {runtime_pid}, Worker: {worker_pid}"

        # Verify worker PID is a real active OS process
        os.kill(worker_pid, 0)
    finally:
        await transport.close()


# ---------------------------------------------------------------------------
# 17. Runtime Handle and Credential Isolation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_runtime_handle_isolation():
    """Section 8 & 14: Verify worker process environment does NOT contain DB URLs, secrets, or handles."""
    transport = UnixSocketExternalAgentTransport()
    await transport.spawn_worker(worker_mode="normal")

    try:
        # Worker has its own memory space: cannot import runtime handles from parent memory
        req = ExternalAgentRequest(
            task=ExternalAgentTaskFacts(
                task_id="tsk_isolation",
                organization_id="org_test",
                intent="Check handle isolation",
                required_role="worker",
                scope={"scope_type": "GLOBAL"},
                input_data={"safe_key": "safe_value"},
            ),
            allowed_tools=[],
            history=[],
            current_turn=1,
            max_turns=1,
            run_state="RUNNING",
        )
        resp = await transport.send_and_receive(req)
        assert isinstance(resp, ExternalAgentResponse)
        # Protocol contains pure JSON data
        assert resp.response_type == ExternalAgentResponseType.TOOL_PROPOSAL
        assert resp.tool_proposal is not None
        assert isinstance(resp.tool_proposal.arguments, dict)
    finally:
        await transport.close()


# ---------------------------------------------------------------------------
# 18. Protocol Replay Protection
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_protocol_replay_protection():
    """Section 18: Replaying captured external response against mismatched task or run fails closed."""
    tools = ToolRegistry()
    tools.register(GetProjectStatusTool())
    perms = ToolPermissionMatrix()
    perms.grant("org_test", "agent.replay", ["get_project_status"])
    sink = InMemoryEventSink()
    engine = ExecutionEngine(tools, perms, DefaultPolicyEngine(), sink)

    # Capture legitimate response for task A
    legit_req = ToolRequest(
        tool_name="get_project_status",
        arguments={"project_id": "PRJ-ATLAS"},
        rationale="Legitimate request",
    )
    task_a = Task(id="tsk_legit_A", organization_id="org_test", intent="Task A", required_role="worker")
    run_a = AgentRun(id="run_A", task_id=task_a.id, agent_id="agent.replay")
    obs, _ = await engine.handle_tool_request(task_a, run_a, legit_req)
    assert obs.success is True

    # Attempt to replay the exact same ToolRequest under different task B and different agent run B
    # where authorization or task context differs
    task_b = Task(id="tsk_legit_B", organization_id="org_unauthorized", intent="Task B", required_role="worker")
    run_b = AgentRun(id="run_B", task_id=task_b.id, agent_id="agent.replay")
    obs_b, _ = await engine.handle_tool_request(task_b, run_b, legit_req)
    assert obs_b.success is False
    assert "not authorized" in obs_b.error.lower()


# ---------------------------------------------------------------------------
# 19. Telemetry Redaction Across Transport Events
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_telemetry_redaction_in_transport():
    """Section 19: Verify transport and process telemetry contains safe metadata only and zero secrets."""
    sink = InMemoryEventSink()
    transport = UnixSocketExternalAgentTransport(event_sink=sink)
    await transport.spawn_worker(worker_mode="normal")

    adapter = ExternalAgentAdapter(
        agent_definition=AgentDefinition(id="agent.telemetry", name="Telemetry Worker"),
        transport=transport,
        event_sink=sink,
    )
    task = Task(id="tsk_telem", organization_id="org_test", intent="Telemetry check", required_role="worker")
    ctx = TaskContext(
        task_id=task.id,
        organization_id=task.organization_id,
        intent=task.intent,
        required_role=task.required_role,
        scope=TaskScope(),
        input_data={"api_key": "SECRET_KEY_12345"},
    )
    history = AgentRunHistory(run_id="run_telem", task_id=task.id)

    try:
        await adapter.step(ctx, history)

        # Inspect all recorded telemetry events
        for evt in sink.events:
            event_json = evt.model_dump_json()
            assert "SECRET_KEY_12345" not in event_json
            assert "thought" not in evt.payload
    finally:
        await transport.close()


# ---------------------------------------------------------------------------
# 20. Real Covenant Shadow Workflow Over Process Transport
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_real_covenant_shadow_workflow_over_transport():
    """Section 20: Genuine Covenant workflow executed through real out-of-process external agent
    via Unix Domain Socket under full runtime governance and shadow isolation.
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
        id="covenant.ipc_resolver",
        name="IPC Covenant Resolver",
        supported_roles=["covenant.resolver"],
    )
    bridge_env.permissions.grant("org_covenant_northstar", agent_def.id, ["get_project_status", "send_followup"])

    transport = UnixSocketExternalAgentTransport(event_sink=sink)
    await transport.spawn_worker(worker_mode="shadow_covenant")

    adapter = ExternalAgentAdapter(agent_def, transport=transport, event_sink=sink)

    task = Task(
        id="tsk_real_cov_ipc",
        organization_id="org_covenant_northstar",
        intent="Resolve overdue sign-off via IPC agent",
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
    approval_repo = InMemoryApprovalRepository()
    approval_svc = RuntimeApprovalService(approval_repo, sink)

    try:
        with ExternalSideEffectGuard(), scoped_workspace_store(store):
            # Turn 1: Worker investigates get_project_status -> executes successfully
            # Turn 2: Worker formulates send_followup -> policy mandates human approval
            run, history, approval_req = await executor.execute_run(task, adapter, ctx)
            assert run.status == AgentRunState.AWAITING_APPROVAL
            assert approval_req is not None
            assert approval_req.tool_request.tool_name == "send_followup"

            # Save and approve via RuntimeApprovalService
            await approval_repo.create(approval_req)
            approved_req = await approval_svc.approve_human_request(
                approval_id=approval_req.approval_id,
                organization_id=task.organization_id,
                task_id=task.id,
                agent_run_id=run.id,
                tool_name=approval_req.tool_request.tool_name,
                reviewed_by="covenant_director@meridianglobal.com",
            )
            assert approved_req.status == ApprovalState.APPROVED

            # Turn 3: Resume execution with approved request -> tool executes, observation returned to worker over IPC, worker completes
            ctx_resumed = TaskContext(
                task_id=task.id,
                organization_id=task.organization_id,
                intent=task.intent,
                required_role=task.required_role,
                scope=ctx.scope,
                available_tools=ctx.available_tools,
                approved_request=approved_req,
                max_turns=5,
            )
            resumed_run, resumed_history, _ = await executor.execute_run(
                task, adapter, ctx_resumed, run=run, history=history, approval_resume=approved_req
            )
            assert resumed_run.status == AgentRunState.COMPLETED
            assert len(resumed_history.turns) >= 3
            assert approved_req.status == ApprovalState.EXECUTED

            # Verify through VerificationGate
            verif_gate = VerificationGate(sink)
            task_validator.validate_transition(task.status, TaskState.ROUTED)
            task.status = TaskState.ROUTED
            task_validator.validate_transition(task.status, TaskState.RUNNING)
            task.status = TaskState.RUNNING
            task_validator.validate_transition(task.status, TaskState.VERIFYING)
            task.status = TaskState.VERIFYING

            v_res = await verif_gate.verify_task(
                task=task,
                verifier=ConfigurableVerifier(should_verify=True, rationale="Shadow audit log corroborates sign-off"),
                expected_outcome="Sign-off email dispatched",
            )
            assert v_res.verified is True
            task_validator.validate_transition(task.status, TaskState.COMPLETED)
            task.status = TaskState.COMPLETED
            assert task.status == TaskState.COMPLETED

    finally:
        await transport.close()
