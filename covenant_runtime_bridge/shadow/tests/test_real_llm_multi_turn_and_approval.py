"""Sections 4 & 5: Real-Ollama Multi-Turn Reasoning & Human Approval Resumption Soak Tests."""

import asyncio
import pytest

from agent_runtime.adapters.model_agent import ModelDrivenAgent
from agent_runtime.adapters.ollama_model import OllamaModelProvider
from agent_runtime.core.contracts.agent import AgentDefinition
from agent_runtime.core.contracts.context import Task, TaskContext
from agent_runtime.core.engine.execution import ExecutionEngine
from agent_runtime.core.engine.run_executor import AgentRunExecutor
from agent_runtime.core.state.enums import ApprovalState, AgentRunState
from agent_runtime.core.telemetry.sink import InMemoryEventSink

from covenant.synthetic_data.store import workspace_store
from covenant_runtime_bridge.bootstrap import CovenantRuntimeBootstrap
from covenant_runtime_bridge.shadow.isolation import (
    ExternalSideEffectGuard,
    clone_workspace_store,
    scoped_workspace_store,
)


@pytest.fixture
def real_ollama_provider():
    p = OllamaModelProvider(
        base_url="http://localhost:11434",
        model="qwen2.5-coder:3b-instruct-q4_K_M",
        timeout=15.0,
    )
    return p


@pytest.mark.asyncio
@pytest.mark.parametrize("run_idx", range(10))
async def test_real_ollama_multi_turn_runs(real_ollama_provider, run_idx):
    """
    SECTION 4: 10 Real Ollama multi-turn executions.
    Turn 0: Inspect evidence.
    Turn 1: Review observation & select next tool.
    Turn 2: Synthesize outcome.
    Observations from one tool are actually supplied to next model turn.
    """
    if not await real_ollama_provider.is_available():
        pytest.skip("Local Ollama server is offline.")

    bridge_env = CovenantRuntimeBootstrap.assemble()
    sink = InMemoryEventSink()
    engine = ExecutionEngine(bridge_env.tools, bridge_env.permissions, bridge_env.policy, sink)
    executor = AgentRunExecutor(engine, sink)

    agent_def = AgentDefinition(
        id=f"cov.real_mt_{run_idx}",
        name=f"MultiTurn Agent {run_idx}",
        supported_roles=["covenant.resolver"],
    )
    bridge_env.permissions.grant("org_covenant_northstar", agent_def.id, ["get_project_status", "search_email"])

    system_prompt = (
        "You are an investigation agent. Emit exactly ONE tool call at a time.\n"
        "Step 1: Check project status with get_project_status for project PRJ-ATLAS.\n"
        "Step 2: Check emails with search_email for Meridian.\n"
        "Step 3: Conclude with summary."
    )
    agent = ModelDrivenAgent(agent_def, real_ollama_provider, system_prompt=system_prompt)

    task = Task(
        id=f"tsk_mt_soak_{run_idx}",
        organization_id="org_covenant_northstar",
        intent="Multi-turn evidence corroboration",
        required_role="covenant.resolver",
    )
    ctx = TaskContext(
        task_id=task.id,
        organization_id=task.organization_id,
        intent=task.intent,
        required_role=task.required_role,
        scope=task.scope,
        available_tools=bridge_env.tools.list_specs(),
        input_data={"project_id": "PRJ-ATLAS"},
        max_turns=3,
    )

    store = clone_workspace_store(workspace_store)
    with ExternalSideEffectGuard(), scoped_workspace_store(store):
        run, history, _ = await executor.execute_run(task, agent, ctx)

    # Invariant: Multi-turn loop executed through kernel
    assert run is not None
    assert len(history.turns) >= 2
    # Verify that tool observation was captured
    assert history.turns[0].observation is not None


@pytest.mark.asyncio
@pytest.mark.parametrize("run_idx", range(5))
async def test_real_ollama_approval_resumption_runs(real_ollama_provider, run_idx):
    """
    SECTION 5: 5 Real Ollama approval resumption executions.
    Turn 0: Real LLM requests side-effect.
    Runtime policy halts execution for human approval.
    Approval supplied.
    Turn 1: Real LLM receives resumed context and executes next action / synthesis.
    ExecutionEngine governs both turns.
    """
    if not await real_ollama_provider.is_available():
        pytest.skip("Local Ollama server is offline.")

    bridge_env = CovenantRuntimeBootstrap.assemble()
    sink = InMemoryEventSink()
    engine = ExecutionEngine(bridge_env.tools, bridge_env.permissions, bridge_env.policy, sink)
    executor = AgentRunExecutor(engine, sink)

    agent_def = AgentDefinition(
        id=f"cov.real_appr_{run_idx}",
        name=f"Approval Agent {run_idx}",
        supported_roles=["covenant.resolver"],
    )
    bridge_env.permissions.grant("org_covenant_northstar", agent_def.id, ["send_followup"])

    system_prompt = (
        "You are an operations agent. Invoke tool send_followup with recipient_email alex@northstar.com, "
        "subject Follow-up, body Please review."
    )
    agent = ModelDrivenAgent(agent_def, real_ollama_provider, system_prompt=system_prompt)

    task = Task(
        id=f"tsk_appr_soak_{run_idx}",
        organization_id="org_covenant_northstar",
        intent="Approval gated dispatch",
        required_role="covenant.resolver",
    )
    ctx = TaskContext(
        task_id=task.id,
        organization_id=task.organization_id,
        intent=task.intent,
        required_role=task.required_role,
        scope=task.scope,
        available_tools=bridge_env.tools.list_specs(),
        input_data={"commitment_id": "com_atlas"},
        max_turns=3,
    )

    store = clone_workspace_store(workspace_store)
    with ExternalSideEffectGuard(), scoped_workspace_store(store):
        # Turn 0: Gated by policy
        run, history, appr = await executor.execute_run(task, agent, ctx)
        assert appr is not None
        assert appr.status == ApprovalState.PENDING
        assert appr.tool_request.tool_name == "send_followup"

        # Supply approval
        appr.status = ApprovalState.APPROVED
        appr.reviewed_by = f"HumanAuditor_{run_idx}"

        # Resumed turn from real LLM
        run2, history2, _ = await executor.execute_run(
            task=task,
            agent=agent,
            context=ctx,
            run=run,
            history=history,
            approval_resume=appr,
        )

        assert run2.status in (AgentRunState.COMPLETED, AgentRunState.EXECUTING, AgentRunState.FAILED, AgentRunState.AWAITING_APPROVAL)
        assert len(history2.turns) >= 2
        # Verify resumed turn executed successfully
        resumed_turn = history2.turns[1]
        assert resumed_turn.observation is not None
        assert resumed_turn.observation.success is True
