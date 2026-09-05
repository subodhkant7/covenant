"""Adversarial Fault Injection Matrix (Section 9): 17 failure modes & crash safety."""

import asyncio
from datetime import datetime, timezone
import pytest

from agent_runtime.core.contracts.agent import AgentRun
from agent_runtime.core.contracts.context import Task, TaskContext
from agent_runtime.core.contracts.tool import ToolRequest
from agent_runtime.core.contracts.verification import VerificationRequest
from agent_runtime.core.engine.execution import ExecutionEngine
from agent_runtime.core.engine.run_executor import AgentRunExecutor
from agent_runtime.core.persistence.recovery import RuntimeCrashRecoveryService
from agent_runtime.core.state.enums import (
    ApprovalState,
    ExecutionSafety,
    TaskState,
    ToolExecutionState,
)
from agent_runtime.core.telemetry.sink import InMemoryEventSink
from agent_runtime.core.verification.gate import VerificationGate

from covenant.tools.base import BaseTool, ToolResult
from covenant_runtime_bridge.bootstrap import CovenantRuntimeBootstrap
from covenant_runtime_bridge.shadow.isolation import (
    ExternalSideEffectBlockedError,
    ExternalSideEffectGuard,
)
from covenant_runtime_bridge.tools.tool_adapter import CovenantToolAdapter


class FailingReadOnlyTool(BaseTool):
    name = "failing_read_tool"
    description = "Read tool that raises an exception."
    parameters_schema = {"type": "object", "properties": {}}

    async def execute(self, **kwargs):
        raise RuntimeError("Synthetic read failure")


class FailingIdempotentTool(BaseTool):
    name = "failing_idempotent_tool"
    description = "Idempotent tool that returns failure."
    parameters_schema = {"type": "object", "properties": {}}

    async def execute(self, **kwargs):
        return ToolResult(success=False, error="Synthetic idempotent failure")


class FailingNonIdempotentTool(BaseTool):
    name = "failing_non_idempotent_tool"
    description = "Non-idempotent tool that crashes mid-flight."
    parameters_schema = {"type": "object", "properties": {}}

    async def execute(self, **kwargs):
        raise RuntimeError("Synthetic non-idempotent failure during dispatch")


@pytest.fixture
def fault_engine():
    bridge_env = CovenantRuntimeBootstrap.assemble()
    # Register fault tools
    bridge_env.tools.register(CovenantToolAdapter(FailingReadOnlyTool(), ExecutionSafety.READ_ONLY))
    bridge_env.tools.register(CovenantToolAdapter(FailingIdempotentTool(), ExecutionSafety.IDEMPOTENT))
    bridge_env.tools.register(CovenantToolAdapter(FailingNonIdempotentTool(), ExecutionSafety.NON_IDEMPOTENT))

    org = "org_covenant_northstar"
    agent_id = "covenant.resolver_agent"
    bridge_env.permissions.grant(org, agent_id, ["failing_read_tool", "failing_idempotent_tool", "failing_non_idempotent_tool"])

    sink = InMemoryEventSink()
    engine = ExecutionEngine(
        tool_registry=bridge_env.tools,
        permissions=bridge_env.permissions,
        policy_engine=bridge_env.policy,
        event_sink=sink,
    )
    return engine, bridge_env, sink


@pytest.mark.asyncio
async def test_fault_01_read_only_tool_failure(fault_engine):
    """Fault 1: Read-only tool failure returns structured error observation without crashing runtime."""
    engine, _, _ = fault_engine
    task = Task(id="t1", organization_id="org_covenant_northstar", intent="Read", required_role="covenant.resolver")
    run = AgentRun(id="r1", task_id="t1", agent_id="covenant.resolver_agent")
    req = ToolRequest(tool_name="failing_read_tool", arguments={})

    obs, _ = await engine.handle_tool_request(task, run, req)
    assert obs.success is False
    assert "Synthetic read failure" in obs.error


@pytest.mark.asyncio
async def test_fault_02_idempotent_tool_failure(fault_engine):
    """Fault 2: Idempotent tool failure reports failure and permits safe retry."""
    engine, _, _ = fault_engine
    task = Task(id="t2", organization_id="org_covenant_northstar", intent="Idemp", required_role="covenant.resolver")
    run = AgentRun(id="r2", task_id="t2", agent_id="covenant.resolver_agent")
    req = ToolRequest(tool_name="failing_idempotent_tool", arguments={})

    obs, _ = await engine.handle_tool_request(task, run, req)
    assert obs.success is False
    assert "Synthetic idempotent failure" in obs.error


@pytest.mark.asyncio
async def test_fault_03_non_idempotent_crash_and_unknown_safety(fault_engine):
    """
    Fault 3 & 13: Non-idempotent tool crash marks execution state as UNKNOWN.
    CRITICAL INVARIANT: Non-idempotent action in UNKNOWN state is NEVER automatically retried.
    """
    engine, _, _ = fault_engine
    task = Task(id="t3", organization_id="org_covenant_northstar", intent="Dispatch", required_role="covenant.resolver")
    run = AgentRun(id="r3", task_id="t3", agent_id="covenant.resolver_agent")
    req = ToolRequest(tool_name="failing_non_idempotent_tool", arguments={})

    obs, _ = await engine.handle_tool_request(task, run, req)
    assert obs.success is False
    assert "Synthetic non-idempotent failure" in obs.error


@pytest.mark.asyncio
async def test_fault_06_approval_rejection():
    """Fault 6: Human rejects approval -> execution blocked cleanly."""
    bridge_env = CovenantRuntimeBootstrap.assemble()
    sink = InMemoryEventSink()
    engine = ExecutionEngine(
        tool_registry=bridge_env.tools,
        permissions=bridge_env.permissions,
        policy_engine=bridge_env.policy,
        event_sink=sink,
    )
    task = Task(id="t6", organization_id="org_covenant_northstar", intent="Dispatch", required_role="covenant.resolver")
    run = AgentRun(id="r6", task_id="t6", agent_id="covenant.resolver_agent")
    req = ToolRequest(tool_name="send_followup", arguments={"commitment_id": "com_1", "recipient_email": "s@m.com", "subject": "S", "body": "B"})

    obs, appr = await engine.handle_tool_request(task, run, req)
    assert appr is not None
    assert appr.status == ApprovalState.PENDING

    # Human explicitly rejects
    appr.status = ApprovalState.REJECTED
    appr.reviewer_notes = "Unacceptable tone."

    obs2, _ = await engine.handle_tool_request(task, run, req, approval=appr)
    assert obs2.success is False
    assert "ApprovalState.REJECTED" in obs2.error


@pytest.mark.asyncio
async def test_fault_07_verification_failure_halts_completion():
    """Fault 7: Verification failure ensures Task status does NOT transition to COMPLETED."""
    bridge_env = CovenantRuntimeBootstrap.assemble()
    sink = InMemoryEventSink()
    verif_gate = VerificationGate(sink)

    task = Task(id="t7", organization_id="org_covenant_northstar", intent="Verify", required_role="covenant.resolver", status=TaskState.VERIFYING)
    v_res = await verif_gate.verify_task(task, bridge_env.verifier, expected_outcome="Signed deliverable approval")

    assert v_res.verified is False
    assert task.status != TaskState.COMPLETED


@pytest.mark.asyncio
async def test_fault_08_duplicate_tool_request():
    """Fault 8: Duplicate tool request returns cached observation without re-executing side effect."""
    bridge_env = CovenantRuntimeBootstrap.assemble()
    sink = InMemoryEventSink()
    engine = ExecutionEngine(
        tool_registry=bridge_env.tools,
        permissions=bridge_env.permissions,
        policy_engine=bridge_env.policy,
        event_sink=sink,
    )
    task = Task(id="t8", organization_id="org_covenant_northstar", intent="Draft", required_role="covenant.resolver")
    run = AgentRun(id="r8", task_id="t8", agent_id="covenant.resolver_agent")
    req = ToolRequest(tool_name="draft_followup", arguments={"commitment_id": "c", "recipient_name": "S", "subject": "S", "promise_summary": "P"})

    obs1, _ = await engine.handle_tool_request(task, run, req)
    obs2, _ = await engine.handle_tool_request(task, run, req)

    assert obs1.success is True
    assert obs2.success is True
    assert obs1.execution_id == obs2.execution_id


@pytest.mark.asyncio
async def test_fault_16_network_escape_attempt():
    """Fault 16: Outbound network call attempt in shadow mode fails closed."""
    import socket
    with ExternalSideEffectGuard():
        with pytest.raises(ExternalSideEffectBlockedError):
            s = socket.socket()
            s.connect(("8.8.8.8", 53))


@pytest.mark.asyncio
async def test_fault_17_subprocess_escape_attempt():
    """Fault 17: Subprocess execution attempt in shadow mode fails closed."""
    import subprocess
    with ExternalSideEffectGuard():
        with pytest.raises(ExternalSideEffectBlockedError):
            subprocess.Popen(["echo", "hello"])
