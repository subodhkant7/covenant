"""Tests for the turn-taking AgentRunExecutor."""

import pytest

from agent_runtime.core.authorization.matrix import ToolPermissionMatrix
from agent_runtime.core.contracts.agent import (
    AgentDefinition,
    AgentRunHistory,
    AgentStepComplete,
    AgentStepFailure,
    AgentStepToolRequest,
)
from agent_runtime.core.contracts.context import Task, TaskContext, TaskScope
from agent_runtime.core.contracts.tool import ToolRequest, ToolSpec
from agent_runtime.core.engine.execution import ExecutionEngine
from agent_runtime.core.engine.registry import ToolRegistry
from agent_runtime.core.engine.run_executor import AgentRunExecutor
from agent_runtime.core.interfaces.agent import IAgent
from agent_runtime.core.interfaces.tool import ITool
from agent_runtime.core.policy.engine import DefaultPolicyEngine
from agent_runtime.core.state.enums import AgentRunState
from agent_runtime.core.telemetry.sink import InMemoryEventSink


class SimpleAddTool(ITool):
    spec = ToolSpec(
        name="add_numbers",
        description="Adds two numbers",
        parameters_schema={"type": "object", "required": ["a", "b"]},
        has_side_effects=False,
    )

    async def execute(self, a: int, b: int, **kwargs):
        return {"sum": a + b}


class MockTwoTurnAgent(IAgent):
    definition = AgentDefinition(id="mock_math_agent", name="Math Agent", supported_roles=["calculator"])

    def __init__(self):
        self.step_count = 0

    async def step(self, context: TaskContext, history: AgentRunHistory):
        self.step_count += 1
        if self.step_count == 1:
            return AgentStepToolRequest(
                thought="Need to sum numbers first.",
                request=ToolRequest(tool_name="add_numbers", arguments={"a": 5, "b": 7}),
            )
        # Turn 2: uses observation from turn 1
        last_obs = history.turns[-1].observation
        calc_sum = last_obs.data["sum"] if last_obs and last_obs.data else 0
        return AgentStepComplete(
            thought="Calculation verified.",
            summary=f"The sum is {calc_sum}",
            output_payload={"result": calc_sum},
        )


class MockLoopingAgent(IAgent):
    definition = AgentDefinition(id="mock_loop_agent", name="Loop Agent", supported_roles=["looper"])

    async def step(self, context: TaskContext, history: AgentRunHistory):
        return AgentStepToolRequest(
            thought="Looping forever...",
            request=ToolRequest(tool_name="add_numbers", arguments={"a": 1, "b": 1}),
        )


class MockCrashingAgent(IAgent):
    definition = AgentDefinition(id="mock_crash_agent", name="Crash Agent", supported_roles=["crasher"])

    async def step(self, context: TaskContext, history: AgentRunHistory):
        raise RuntimeError("Unexpected agent internal explosion!")


@pytest.fixture
def setup_executor():
    tools = ToolRegistry()
    tools.register(SimpleAddTool())

    perms = ToolPermissionMatrix()
    perms.grant("org_test", "mock_math_agent", ["add_numbers"])
    perms.grant("org_test", "mock_loop_agent", ["add_numbers"])
    perms.grant("org_test", "mock_crash_agent", ["add_numbers"])

    policy = DefaultPolicyEngine()
    sink = InMemoryEventSink()
    engine = ExecutionEngine(tools, perms, policy, sink)
    executor = AgentRunExecutor(engine, sink)
    return executor, tools


@pytest.mark.asyncio
async def test_successful_two_turn_execution(setup_executor):
    executor, tools = setup_executor
    task = Task(organization_id="org_test", intent="Compute 5 + 7", required_role="calculator")
    agent = MockTwoTurnAgent()
    context = TaskContext(
        task_id=task.id,
        organization_id="org_test",
        intent=task.intent,
        required_role="calculator",
        scope=TaskScope(),
        available_tools=tools.list_specs(),
        max_turns=5,
    )

    run, history, approval = await executor.execute_run(task, agent, context)
    assert run.status == AgentRunState.COMPLETED
    assert run.turn_count == 2
    assert run.output_payload["result"] == 12
    assert "The sum is 12" in run.completion_summary
    assert approval is None


@pytest.mark.asyncio
async def test_max_turns_timeout_safeguard(setup_executor):
    executor, tools = setup_executor
    task = Task(organization_id="org_test", intent="Loop", required_role="looper")
    agent = MockLoopingAgent()
    context = TaskContext(
        task_id=task.id,
        organization_id="org_test",
        intent=task.intent,
        required_role="looper",
        scope=TaskScope(),
        available_tools=tools.list_specs(),
        max_turns=3,  # Strict cutoff at 3 turns
    )

    run, history, approval = await executor.execute_run(task, agent, context)
    assert run.status == AgentRunState.TIMED_OUT
    assert "exceeded max turns limit" in run.error
    assert len(history.turns) == 3


@pytest.mark.asyncio
async def test_agent_exception_handling(setup_executor):
    executor, tools = setup_executor
    task = Task(organization_id="org_test", intent="Crash", required_role="crasher")
    agent = MockCrashingAgent()
    context = TaskContext(
        task_id=task.id,
        organization_id="org_test",
        intent=task.intent,
        required_role="crasher",
        scope=TaskScope(),
        available_tools=tools.list_specs(),
        max_turns=3,
    )

    run, history, approval = await executor.execute_run(task, agent, context)
    assert run.status == AgentRunState.FAILED
    assert "Agent step crashed" in run.error
    assert "internal explosion" in run.error
