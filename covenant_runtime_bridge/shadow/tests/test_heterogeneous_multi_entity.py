"""Tests for genuine Multi-Entity TaskScope execution with heterogeneous outcomes."""

import pytest

from agent_runtime.core.contracts.context import Task, TaskContext, TaskScope
from agent_runtime.core.engine.execution import ExecutionEngine
from agent_runtime.core.engine.run_executor import AgentRunExecutor
from agent_runtime.core.state.enums import ScopeType, TaskState
from agent_runtime.core.telemetry.sink import InMemoryEventSink

from covenant_runtime_bridge.bootstrap import CovenantRuntimeBootstrap


@pytest.mark.asyncio
async def test_genuine_multi_entity_task_scope_execution():
    """
    SECTION 8 PROOF:
    Verify one Task with TaskScope(MULTI_ENTITY) processing multiple heterogeneous entities.
    Proves the runtime does not decompose into single entity tasks unless intended.
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

    entity_ids = ["com_atlas_approval", "com_apex_repair", "com_vendor_parts"]
    multi_task = Task(
        id="tsk_multi_portfolio_eval",
        organization_id="org_covenant_northstar",
        intent="Cross-portfolio drift corroboration",
        required_role="covenant.investigator",
        scope=TaskScope(
            scope_type=ScopeType.MULTI_ENTITY,
            entity_type="covenant.commitment",
            entity_ids=entity_ids,
            filter_criteria={"portfolio": "Q3_ACTIVE"},
        ),
        input_payload={"batch_eval": True, "entity_count": 3},
    )

    agent = bridge_env.agents.get("covenant.investigator_agent")
    ctx = TaskContext(
        task_id=multi_task.id,
        organization_id=multi_task.organization_id,
        intent=multi_task.intent,
        required_role=multi_task.required_role,
        scope=multi_task.scope,
        available_tools=bridge_env.tools.list_specs(),
        input_data=multi_task.input_payload,
    )

    run, history, _ = await executor.execute_run(multi_task, agent, ctx)

    assert run.status.value == "COMPLETED"
    payload = run.output_payload
    assert payload["scope_type"] == "MULTI_ENTITY"
    assert payload["total_entities_evaluated"] == 3
    assert set(payload["findings"].keys()) == set(entity_ids)

    # Invariant: History has multiple turns for the multiple entities
    assert len(history.turns) >= 2
    turn_tools = [t.request.tool_name for t in history.turns if t.request]
    assert "get_project_status" in turn_tools
    assert "search_email" in turn_tools
