"""Failure, crash, timeout, and recovery tests for ExternalAgentAdapter."""

import asyncio
import pytest
from typing import Any, Dict, List, Optional

from agent_runtime.adapters.external_agent import (
    ExternalAgentAdapter,
    ExternalAgentRequest,
    ExternalAgentResponse,
    ExternalAgentResponseType,
    ExternalAgentToolProposal,
    IExternalAgent,
    IExternalAgentTransport,
)
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
from agent_runtime.core.contracts.tool import ToolRequest, ToolSpec
from agent_runtime.core.engine.execution import ExecutionEngine
from agent_runtime.core.engine.idempotency import IdempotencyStore
from agent_runtime.core.engine.registry import ToolRegistry
from agent_runtime.core.engine.run_executor import AgentRunExecutor
from agent_runtime.core.interfaces.tool import ITool
from agent_runtime.core.policy.engine import DefaultPolicyEngine
from agent_runtime.core.state.enums import AgentRunState, ApprovalState, ExecutionSafety, ScopeType, TaskState
from agent_runtime.core.telemetry.sink import InMemoryEventSink


class SideEffectCounterTool(ITool):
    spec = ToolSpec(
        name="apply_payment_credit",
        description="Applies payment credit",
        parameters_schema={"type": "object", "required": ["account_id", "amount"]},
        has_side_effects=True,
        execution_safety=ExecutionSafety.IDEMPOTENT,
    )

    def __init__(self):
        self.execution_count = 0

    async def execute(self, account_id: str, amount: float, **kwargs):
        self.execution_count += 1
        return {"applied": True, "account": account_id, "amount": amount, "exec_count": self.execution_count}


class TimeoutExternalAgent(IExternalAgent):
    """Simulates an external agent that hangs or times out."""

    async def decide(self, request: ExternalAgentRequest) -> ExternalAgentResponse:
        await asyncio.sleep(2.0)  # Sleeps longer than configured adapter timeout
        return ExternalAgentResponse(
            response_type=ExternalAgentResponseType.COMPLETE,
            completion_summary="Too late",
        )


class CrashingExternalAgent(IExternalAgent):
    """Simulates an external process or subagent that crashes with an unhandled exception."""

    def __init__(self, crash_on_turn: int = 1):
        self.crash_on_turn = crash_on_turn
        self.turn = 0

    async def decide(self, request: ExternalAgentRequest) -> ExternalAgentResponse:
        self.turn += 1
        if self.turn == self.crash_on_turn:
            raise ConnectionResetError("Underlying external reasoning connection terminated abruptly!")
        return ExternalAgentResponse(
            response_type=ExternalAgentResponseType.TOOL_PROPOSAL,
            tool_proposal=ExternalAgentToolProposal(
                tool_name="apply_payment_credit",
                arguments={"account_id": "ACC-100", "amount": 500.0},
            ),
        )


class ReconnectingExternalAgent(IExternalAgent):
    """Simulates an external agent that crashed on turn 1, but reconnects and replays turn 1."""

    def __init__(self):
        self.turn = 0

    async def decide(self, request: ExternalAgentRequest) -> ExternalAgentResponse:
        self.turn += 1
        if len(request.history) == 0:
            return ExternalAgentResponse(
                response_type=ExternalAgentResponseType.TOOL_PROPOSAL,
                tool_proposal=ExternalAgentToolProposal(
                    tool_name="apply_payment_credit",
                    arguments={"account_id": "ACC-100", "amount": 500.0},
                    rationale="Credit refund attempt 1",
                ),
            )
        else:
            obs = request.history[-1].observation
            return ExternalAgentResponse(
                response_type=ExternalAgentResponseType.COMPLETE,
                completion_summary=f"Reconnected and saw observation success={obs.success if obs else False}",
                output_payload={"result": obs.data if obs else None},
            )


@pytest.fixture
def failure_environment():
    tools = ToolRegistry()
    counter_tool = SideEffectCounterTool()
    tools.register(counter_tool)

    perms = ToolPermissionMatrix()
    perms.grant("org_fail", "agent.crash_tester", ["apply_payment_credit"])

    policy = DefaultPolicyEngine()  # Allows read-only, side-effect requires approval unless rule allows
    # Add a permissive rule for apply_payment_credit for idempotency testing
    class AllowPaymentPolicy(DefaultPolicyEngine):
        def evaluate(self, context):
            from agent_runtime.core.contracts.policy import PolicyDecision
            from agent_runtime.core.state.enums import PolicyDecisionType
            return PolicyDecision(tool_request_id=context.tool_request.request_id, decision=PolicyDecisionType.ALLOW, rationale="Allowed for test")

    sink = InMemoryEventSink()
    idemp_store = IdempotencyStore()
    engine = ExecutionEngine(
        tool_registry=tools,
        permissions=perms,
        policy_engine=AllowPaymentPolicy(),
        event_sink=sink,
        idempotency_store=idemp_store,
    )
    executor = AgentRunExecutor(engine, sink)
    return tools, counter_tool, perms, engine, executor, sink, idemp_store


@pytest.mark.asyncio
async def test_external_agent_timeout_handling(failure_environment):
    """Section 22: Verify external agent timeout fails closed and emits telemetry."""
    tools, counter_tool, perms, engine, executor, sink, idemp = failure_environment

    agent_def = AgentDefinition(id="agent.crash_tester", name="Timeout Tester")
    # Configure strict 0.2s timeout
    adapter = ExternalAgentAdapter(
        agent_def,
        external_agent=TimeoutExternalAgent(),
        event_sink=sink,
        timeout=0.2,
    )

    task = Task(id="tsk_timeout_01", organization_id="org_fail", intent="Timeout test", required_role="tester")
    ctx = TaskContext(
        task_id=task.id,
        organization_id=task.organization_id,
        intent=task.intent,
        required_role=task.required_role,
        scope=TaskScope(),
        available_tools=tools.list_specs(),
        max_turns=3,
    )

    run, history, appr = await executor.execute_run(task, adapter, ctx)

    # Invariant: Run status is FAILED, not hung
    assert run.status == AgentRunState.FAILED
    assert "timed out" in run.error.lower()
    assert appr is None

    # Invariant: EXTERNAL_AGENT_TIMEOUT event was recorded
    events = await sink.list_events(task_id=task.id)
    timeout_events = [e for e in events if e.event_type == EventType.EXTERNAL_AGENT_TIMEOUT]
    assert len(timeout_events) == 1


@pytest.mark.asyncio
async def test_external_agent_crash_exception_handling(failure_environment):
    """Section 22: Verify unhandled external process crash fails closed cleanly."""
    tools, counter_tool, perms, engine, executor, sink, idemp = failure_environment

    agent_def = AgentDefinition(id="agent.crash_tester", name="Crash Tester")
    adapter = ExternalAgentAdapter(
        agent_def,
        external_agent=CrashingExternalAgent(crash_on_turn=1),
        event_sink=sink,
    )

    task = Task(id="tsk_crash_01", organization_id="org_fail", intent="Crash test", required_role="tester")
    ctx = TaskContext(
        task_id=task.id,
        organization_id=task.organization_id,
        intent=task.intent,
        required_role=task.required_role,
        scope=TaskScope(),
        available_tools=tools.list_specs(),
        max_turns=3,
    )

    run, history, appr = await executor.execute_run(task, adapter, ctx)

    assert run.status == AgentRunState.FAILED
    assert "terminated abruptly" in run.error
    assert appr is None

    # Invariant: EXTERNAL_AGENT_REJECTED event recorded
    events = await sink.list_events(task_id=task.id)
    rejected_events = [e for e in events if e.event_type == EventType.EXTERNAL_AGENT_REJECTED]
    assert len(rejected_events) == 1


@pytest.mark.asyncio
async def test_idempotency_preservation_across_external_agent_reconnect(failure_environment):
    """Section 22: Invariant: An external agent crash and retry must not cause duplicate side effects.
    Runtime idempotency cache returns cached result without executing tool a second time.
    """
    tools, counter_tool, perms, engine, executor, sink, idemp = failure_environment

    agent_def = AgentDefinition(id="agent.crash_tester", name="Crash Tester")
    task = Task(id="tsk_idemp_01", organization_id="org_fail", intent="Idempotency test", required_role="tester")
    ctx = TaskContext(
        task_id=task.id,
        organization_id=task.organization_id,
        intent=task.intent,
        required_role=task.required_role,
        scope=TaskScope(),
        available_tools=tools.list_specs(),
        max_turns=3,
    )

    # 1. First execution: agent successfully dispatches tool, then completes
    adapter_1 = ExternalAgentAdapter(agent_def, external_agent=ReconnectingExternalAgent(), event_sink=sink)
    run_1, history_1, _ = await executor.execute_run(task, adapter_1, ctx)
    assert run_1.status == AgentRunState.COMPLETED
    assert counter_tool.execution_count == 1

    # 2. Reconnection / retry with same task and idempotent arguments:
    # A reconnected agent dispatches the exact same ToolRequest
    adapter_2 = ExternalAgentAdapter(agent_def, external_agent=ReconnectingExternalAgent(), event_sink=sink)
    task_retry = Task(id=task.id, organization_id="org_fail", intent="Idempotency test", required_role="tester", attempt_count=1)
    run_2, history_2, _ = await executor.execute_run(task_retry, adapter_2, ctx)

    assert run_2.status == AgentRunState.COMPLETED
    # Invariant: tool execute() was NOT called again! execution_count remains 1!
    assert counter_tool.execution_count == 1
    # Observation received by reconnected agent was the cached result
    assert history_2.turns[0].observation.success is True
