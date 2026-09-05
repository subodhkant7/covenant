"""Unit and integration tests for ExternalAgentAdapter and protocol boundary."""

import pytest
from typing import Any, Dict, List

from agent_runtime.adapters.external_agent import (
    ExternalAgentAdapter,
    ExternalAgentRequest,
    ExternalAgentResponse,
    ExternalAgentResponseType,
    ExternalAgentToolProposal,
    IExternalAgent,
    IExternalAgentTransport,
    InProcessExternalAgentTransport,
)
from agent_runtime.core.authorization.matrix import ToolPermissionMatrix
from agent_runtime.core.contracts.agent import (
    AgentDefinition,
    AgentRunHistory,
    AgentStepComplete,
    AgentStepFailure,
    AgentStepToolRequest,
)
from agent_runtime.core.contracts.context import Task, TaskContext, TaskScope
from agent_runtime.core.contracts.event import EventType
from agent_runtime.core.contracts.tool import ToolRequest, ToolSpec
from agent_runtime.core.engine.execution import ExecutionEngine
from agent_runtime.core.engine.registry import ToolRegistry
from agent_runtime.core.engine.run_executor import AgentRunExecutor
from agent_runtime.core.interfaces.agent import IAgent
from agent_runtime.core.interfaces.tool import ITool
from agent_runtime.core.policy.engine import DefaultPolicyEngine
from agent_runtime.core.state.enums import AgentRunState, ScopeType
from agent_runtime.core.telemetry.sink import InMemoryEventSink


class SimpleAddTool(ITool):
    spec = ToolSpec(
        name="add_numbers",
        description="Calculates sum of a and b",
        parameters_schema={"type": "object", "required": ["a", "b"]},
        has_side_effects=False,
    )

    async def execute(self, a: int, b: int, **kwargs):
        return {"sum": a + b}


class ExternalTestAgent(IExternalAgent):
    """Deterministic scripted external agent used to prove the adapter contract."""

    def __init__(self, script: List[ExternalAgentResponse]):
        self.script = list(script)
        self.call_count = 0
        self.received_requests: List[ExternalAgentRequest] = []

    async def decide(self, request: ExternalAgentRequest) -> ExternalAgentResponse:
        self.received_requests.append(request)
        if self.call_count < len(self.script):
            resp = self.script[self.call_count]
            self.call_count += 1
            return resp
        return ExternalAgentResponse(
            response_type=ExternalAgentResponseType.COMPLETE,
            completion_summary="Default scripted completion",
        )


class AlternativeProviderMockAgent(IExternalAgent):
    """Represents a distinct external model/provider (e.g. Anthropic, OpenAI, custom IPC)."""

    def __init__(self):
        self.turns_handled = 0

    async def decide(self, request: ExternalAgentRequest) -> ExternalAgentResponse:
        self.turns_handled += 1
        if self.turns_handled == 1:
            return ExternalAgentResponse(
                response_type=ExternalAgentResponseType.TOOL_PROPOSAL,
                tool_proposal=ExternalAgentToolProposal(
                    tool_name="add_numbers",
                    arguments={"a": 20, "b": 22},
                    rationale="Summing via alternative provider reasoning",
                ),
                rationale="I must add 20 and 22 to solve the task.",
            )
        else:
            last_turn = request.history[-1]
            sum_val = last_turn.observation.data["sum"] if last_turn.observation else 0
            return ExternalAgentResponse(
                response_type=ExternalAgentResponseType.COMPLETE,
                completion_summary=f"Alternative provider finished: sum is {sum_val}",
                output_payload={"result": sum_val},
            )


@pytest.fixture
def base_test_environment():
    tools = ToolRegistry()
    tools.register(SimpleAddTool())

    perms = ToolPermissionMatrix()
    perms.grant("org_test", "agent.external_tester", ["add_numbers"])
    perms.grant("org_test", "agent.alternative_tester", ["add_numbers"])

    policy = DefaultPolicyEngine()
    sink = InMemoryEventSink()
    engine = ExecutionEngine(tools, perms, policy, sink)
    executor = AgentRunExecutor(engine, sink)
    return tools, perms, policy, sink, engine, executor


@pytest.mark.asyncio
async def test_external_agent_step_tool_request(base_test_environment):
    tools, perms, policy, sink, engine, executor = base_test_environment

    agent_def = AgentDefinition(id="agent.external_tester", name="External Tester")
    script = [
        ExternalAgentResponse(
            response_type=ExternalAgentResponseType.TOOL_PROPOSAL,
            tool_proposal=ExternalAgentToolProposal(
                tool_name="add_numbers",
                arguments={"a": 10, "b": 25},
                rationale="Proposing calculation",
            ),
            rationale="Calculating 10 + 25",
        )
    ]
    ext_agent = ExternalTestAgent(script)
    adapter = ExternalAgentAdapter(agent_def, external_agent=ext_agent, event_sink=sink)

    assert isinstance(adapter, IAgent)

    task = Task(id="tsk_01", organization_id="org_test", intent="Add numbers", required_role="calc")
    ctx = TaskContext(
        task_id=task.id,
        organization_id="org_test",
        intent=task.intent,
        required_role=task.required_role,
        scope=TaskScope(scope_type=ScopeType.UNSCOPED),
        available_tools=tools.list_specs(),
        input_data={"x": 1},
    )
    history = AgentRunHistory(run_id="run_01", task_id=task.id)

    step_res = await adapter.step(ctx, history)

    assert isinstance(step_res, AgentStepToolRequest)
    assert step_res.request.tool_name == "add_numbers"
    assert step_res.request.arguments == {"a": 10, "b": 25}
    assert step_res.request.rationale == "Proposing calculation"

    # Verify facts delivered in request contain zero execution handles
    assert len(ext_agent.received_requests) == 1
    req = ext_agent.received_requests[0]
    assert req.task.task_id == "tsk_01"
    assert req.task.intent == "Add numbers"
    assert req.current_turn == 1
    assert len(req.allowed_tools) == 1
    assert req.allowed_tools[0].name == "add_numbers"
    # Invariant: no database handles or execution engine in request
    assert not hasattr(req, "engine")
    assert not hasattr(req, "tools")


@pytest.mark.asyncio
async def test_external_agent_step_complete(base_test_environment):
    tools, perms, policy, sink, engine, executor = base_test_environment

    agent_def = AgentDefinition(id="agent.external_tester", name="External Tester")
    script = [
        ExternalAgentResponse(
            response_type=ExternalAgentResponseType.COMPLETE,
            completion_summary="Calculation completed successfully",
            output_payload={"final": 42},
            rationale="I am done",
        )
    ]
    ext_agent = ExternalTestAgent(script)
    adapter = ExternalAgentAdapter(agent_def, external_agent=ext_agent, event_sink=sink)

    ctx = TaskContext(
        task_id="tsk_comp",
        organization_id="org_test",
        intent="Finish",
        required_role="worker",
        scope=TaskScope(),
    )
    history = AgentRunHistory(run_id="run_comp", task_id="tsk_comp")

    step_res = await adapter.step(ctx, history)
    assert isinstance(step_res, AgentStepComplete)
    assert step_res.summary == "Calculation completed successfully"
    assert step_res.output_payload == {"final": 42}


@pytest.mark.asyncio
async def test_external_agent_step_failure(base_test_environment):
    tools, perms, policy, sink, engine, executor = base_test_environment

    agent_def = AgentDefinition(id="agent.external_tester", name="External Tester")
    script = [
        ExternalAgentResponse(
            response_type=ExternalAgentResponseType.FAILURE,
            error_message="Model reasoning perplexity exceeded threshold",
            rationale="Cannot proceed",
        )
    ]
    ext_agent = ExternalTestAgent(script)
    adapter = ExternalAgentAdapter(agent_def, external_agent=ext_agent, event_sink=sink)

    ctx = TaskContext(
        task_id="tsk_fail",
        organization_id="org_test",
        intent="Fail test",
        required_role="worker",
        scope=TaskScope(),
    )
    history = AgentRunHistory(run_id="run_fail", task_id="tsk_fail")

    step_res = await adapter.step(ctx, history)
    assert isinstance(step_res, AgentStepFailure)
    assert "perplexity exceeded threshold" in step_res.error_message


@pytest.mark.asyncio
async def test_model_agnosticism_interchangeable_providers(base_test_environment):
    """Section 15: Prove model agnosticism.
    The same runtime task executes with ExternalTestAgent and AlternativeProviderMockAgent
    with ZERO modifications to ExecutionEngine, Policy, or Task model.
    """
    tools, perms, policy, sink, engine, executor = base_test_environment

    # Provider 1: ExternalTestAgent
    agent_def_1 = AgentDefinition(id="agent.external_tester", name="External Script")
    script_1 = [
        ExternalAgentResponse(
            response_type=ExternalAgentResponseType.TOOL_PROPOSAL,
            tool_proposal=ExternalAgentToolProposal(tool_name="add_numbers", arguments={"a": 20, "b": 22}),
        ),
        ExternalAgentResponse(
            response_type=ExternalAgentResponseType.COMPLETE,
            completion_summary="Scripted provider finished: sum is 42",
            output_payload={"result": 42},
        ),
    ]
    agent_1 = ExternalAgentAdapter(agent_def_1, external_agent=ExternalTestAgent(script_1), event_sink=sink)

    task_1 = Task(id="tsk_agnostic_1", organization_id="org_test", intent="Add 20 and 22", required_role="calc")
    ctx_1 = TaskContext(
        task_id=task_1.id,
        organization_id=task_1.organization_id,
        intent=task_1.intent,
        required_role=task_1.required_role,
        scope=TaskScope(),
        available_tools=tools.list_specs(),
    )
    run_1, hist_1, _ = await executor.execute_run(task_1, agent_1, ctx_1)
    assert run_1.status == AgentRunState.COMPLETED
    assert run_1.output_payload["result"] == 42
    assert hist_1.turn_count == 2

    # Provider 2: AlternativeProviderMockAgent
    agent_def_2 = AgentDefinition(id="agent.alternative_tester", name="Alternative Provider")
    agent_2 = ExternalAgentAdapter(agent_def_2, external_agent=AlternativeProviderMockAgent(), event_sink=sink)

    task_2 = Task(id="tsk_agnostic_2", organization_id="org_test", intent="Add 20 and 22", required_role="calc")
    ctx_2 = TaskContext(
        task_id=task_2.id,
        organization_id=task_2.organization_id,
        intent=task_2.intent,
        required_role=task_2.required_role,
        scope=TaskScope(),
        available_tools=tools.list_specs(),
    )
    run_2, hist_2, _ = await executor.execute_run(task_2, agent_2, ctx_2)
    assert run_2.status == AgentRunState.COMPLETED
    assert run_2.output_payload["result"] == 42
    assert hist_2.turn_count == 2

    # Verify telemetry events for both providers
    events_1 = await sink.list_events(task_id=task_1.id)
    assert any(e.event_type == EventType.EXTERNAL_AGENT_REQUESTED for e in events_1)
    assert any(e.event_type == EventType.EXTERNAL_AGENT_RESPONDED for e in events_1)

    events_2 = await sink.list_events(task_id=task_2.id)
    assert any(e.event_type == EventType.EXTERNAL_AGENT_REQUESTED for e in events_2)
    assert any(e.event_type == EventType.EXTERNAL_AGENT_RESPONDED for e in events_2)
