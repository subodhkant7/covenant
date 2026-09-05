"""Tests for Model-Driven Runtime Execution & Model Governance."""

import pytest

from agent_runtime.core.contracts.agent import (
    AgentDefinition,
    AgentRun,
    AgentRunHistory,
    AgentStepComplete,
    AgentStepResult,
    AgentStepToolRequest,
)
from agent_runtime.core.contracts.context import Task, TaskContext
from agent_runtime.core.contracts.tool import ToolRequest
from agent_runtime.core.engine.execution import ExecutionEngine
from agent_runtime.core.engine.run_executor import AgentRunExecutor
from agent_runtime.core.interfaces.agent import IAgent
from agent_runtime.core.interfaces.model import (
    IModelProvider,
    ModelMessage,
    ModelRequest,
    ModelResponse,
    ModelToolCall,
)
from agent_runtime.core.state.enums import ApprovalState, TaskState
from agent_runtime.core.telemetry.sink import InMemoryEventSink

from covenant_runtime_bridge.bootstrap import CovenantRuntimeBootstrap


class FakeDeterministicModelProvider(IModelProvider):
    """Deterministic model provider used for governance verification."""

    def __init__(self, canned_response: ModelResponse):
        self.canned_response = canned_response

    async def generate(self, request: ModelRequest) -> ModelResponse:
        return self.canned_response


class ModelDrivenAgent(IAgent):
    """Agent that consults an IModelProvider to formulate tool requests."""

    def __init__(self, model_provider: IModelProvider):
        self.model_provider = model_provider
        self.definition = AgentDefinition(
            id="covenant.model_driven_agent",
            name="Model Driven Agent",
            supported_roles=["covenant.resolver"],
        )

    async def step(self, context: TaskContext, history: AgentRunHistory) -> AgentStepResult:
        if history.turn_count >= 1:
            return AgentStepComplete(thought="Done", summary="Execution concluded")

        # Consult model provider
        req = ModelRequest(
            messages=[ModelMessage(role="user", content=context.intent)],
            available_tools=context.available_tools,
        )
        resp = await self.model_provider.generate(req)
        if resp.tool_calls:
            tc = resp.tool_calls[0]
            return AgentStepToolRequest(
                thought=f"Model proposed tool {tc.tool_name}",
                request=ToolRequest(
                    tool_name=tc.tool_name,
                    arguments=tc.arguments,
                    rationale="Proposed by LLM",
                ),
            )
        return AgentStepComplete(thought="No action proposed", summary="Model output empty")


@pytest.mark.asyncio
async def test_valid_model_proposal_executes_governed():
    """Valid tool call from model executes through ExecutionEngine governance."""
    canned = ModelResponse(
        tool_calls=[
            ModelToolCall(
                call_id="call_1",
                tool_name="draft_followup",
                arguments={
                    "commitment_id": "com_atlas_approval",
                    "recipient_name": "Sarah",
                    "subject": "Follow-up",
                    "promise_summary": "Phase 2 Sign-off",
                },
            )
        ]
    )
    agent = ModelDrivenAgent(FakeDeterministicModelProvider(canned))
    bridge_env = CovenantRuntimeBootstrap.assemble()
    bridge_env.agents.register(agent)
    bridge_env.permissions.grant("org_covenant_northstar", agent.definition.id, ["draft_followup"])

    sink = InMemoryEventSink()
    engine = ExecutionEngine(
        tool_registry=bridge_env.tools,
        permissions=bridge_env.permissions,
        policy_engine=bridge_env.policy,
        event_sink=sink,
    )
    executor = AgentRunExecutor(engine, sink)

    task = Task(id="tsk_md_1", organization_id="org_covenant_northstar", intent="Followup", required_role="covenant.resolver")
    ctx = TaskContext(
        task_id=task.id,
        organization_id=task.organization_id,
        intent=task.intent,
        required_role=task.required_role,
        scope=task.scope,
        available_tools=bridge_env.tools.list_specs(),
    )

    run, history, _ = await executor.execute_run(task, agent, ctx)
    assert run.status.value == "COMPLETED"
    assert len(history.turns) >= 1
    assert history.turns[0].observation.success is True


@pytest.mark.asyncio
async def test_model_proposing_unauthorized_tool_is_rejected():
    """Model proposing tool not granted in permission matrix is rejected by runtime."""
    canned = ModelResponse(
        tool_calls=[
            ModelToolCall(
                call_id="call_unauth",
                tool_name="create_escalation",  # Agent does NOT have grant for this
                arguments={"commitment_id": "com_1", "title": "Dispute", "rationale": "High"},
            )
        ]
    )
    agent = ModelDrivenAgent(FakeDeterministicModelProvider(canned))
    bridge_env = CovenantRuntimeBootstrap.assemble()
    bridge_env.agents.register(agent)
    # Explicitly do NOT grant create_escalation to this agent!

    sink = InMemoryEventSink()
    engine = ExecutionEngine(
        tool_registry=bridge_env.tools,
        permissions=bridge_env.permissions,
        policy_engine=bridge_env.policy,
        event_sink=sink,
    )
    executor = AgentRunExecutor(engine, sink)

    task = Task(id="tsk_md_unauth", organization_id="org_covenant_northstar", intent="Escalate", required_role="covenant.resolver")
    ctx = TaskContext(
        task_id=task.id,
        organization_id=task.organization_id,
        intent=task.intent,
        required_role=task.required_role,
        scope=task.scope,
        available_tools=bridge_env.tools.list_specs(),
    )

    run, history, _ = await executor.execute_run(task, agent, ctx)
    obs = history.turns[0].observation
    assert obs.success is False
    assert "Permission denied" in obs.error


@pytest.mark.asyncio
async def test_model_proposing_malformed_arguments_is_rejected():
    """Model hallucinating invalid schema parameters is rejected by schema validator."""
    canned = ModelResponse(
        tool_calls=[
            ModelToolCall(
                call_id="call_malformed",
                tool_name="draft_followup",
                arguments={"completely_wrong_key": 42},  # Missing required fields!
            )
        ]
    )
    agent = ModelDrivenAgent(FakeDeterministicModelProvider(canned))
    bridge_env = CovenantRuntimeBootstrap.assemble()
    bridge_env.agents.register(agent)
    bridge_env.permissions.grant("org_covenant_northstar", agent.definition.id, ["draft_followup"])

    sink = InMemoryEventSink()
    engine = ExecutionEngine(
        tool_registry=bridge_env.tools,
        permissions=bridge_env.permissions,
        policy_engine=bridge_env.policy,
        event_sink=sink,
    )
    executor = AgentRunExecutor(engine, sink)

    task = Task(id="tsk_md_bad_args", organization_id="org_covenant_northstar", intent="Draft", required_role="covenant.resolver")
    ctx = TaskContext(
        task_id=task.id,
        organization_id=task.organization_id,
        intent=task.intent,
        required_role=task.required_role,
        scope=task.scope,
        available_tools=bridge_env.tools.list_specs(),
    )

    run, history, _ = await executor.execute_run(task, agent, ctx)
    obs = history.turns[0].observation
    assert obs.success is False
    assert "Missing required fields" in obs.error
