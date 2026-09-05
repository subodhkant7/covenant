"""Section 7, 8, 16: Tests for sensitive credential redaction across events, executions, and observations."""

import pytest

from agent_runtime.core.authorization.matrix import ToolPermissionMatrix
from agent_runtime.core.contracts.agent import AgentRun
from agent_runtime.core.contracts.context import Task
from agent_runtime.core.contracts.event import EventType
from agent_runtime.core.contracts.tool import ToolRequest, ToolSpec
from agent_runtime.core.engine.execution import ExecutionEngine
from agent_runtime.core.engine.registry import ToolRegistry
from agent_runtime.core.interfaces.tool import ITool
from agent_runtime.core.persistence.agent_run_repo import SQLiteAgentRunRepository
from agent_runtime.core.persistence.connection import DatabaseManager
from agent_runtime.core.persistence.task_repo import SQLiteTaskRepository
from agent_runtime.core.persistence.tool_exec_repo import SQLiteToolExecutionRepository
from agent_runtime.core.policy.engine import DefaultPolicyEngine
from agent_runtime.core.telemetry.sqlite_sink import SQLiteEventSink


class FakeApiKeyTool(ITool):
    spec = ToolSpec(
        name="authenticate_external_api",
        description="Authenticates against external vendor",
        parameters_schema={"type": "object", "required": ["api_key", "service_name"]},
        has_side_effects=False,
    )

    async def execute(self, api_key: str, service_name: str, **kwargs):
        # Emits a token back in response
        return {
            "authenticated": True,
            "session_token": "Bearer secret_session_token_xyz98765",
            "service": service_name,
        }


@pytest.fixture
def secure_setup(tmp_path):
    db_file = tmp_path / "test_secure.sqlite"
    mgr = DatabaseManager(str(db_file))
    task_repo = SQLiteTaskRepository(mgr)
    run_repo = SQLiteAgentRunRepository(mgr)
    tool_repo = SQLiteToolExecutionRepository(mgr)
    event_sink = SQLiteEventSink(mgr)

    tools = ToolRegistry()
    tools.register(FakeApiKeyTool())

    perms = ToolPermissionMatrix()
    perms.grant("org_sec", "sec_agent", ["authenticate_external_api"])

    engine = ExecutionEngine(
        tool_registry=tools,
        permissions=perms,
        policy_engine=DefaultPolicyEngine(),
        event_sink=event_sink,
        tool_execution_repo=tool_repo,
    )
    yield engine, task_repo, run_repo, tool_repo, event_sink
    mgr.close()


@pytest.mark.asyncio
async def test_secret_redaction_in_arguments_executions_events_and_observations(secure_setup):
    """
    Verifies that raw secrets passed in tool arguments:
    1. Are NOT in ToolExecution.arguments_json
    2. Are NOT in ToolExecution.result_json
    3. Are NOT in Event.payload_json
    4. Are NOT in Observation.data
    """
    engine, task_repo, run_repo, tool_repo, event_sink = secure_setup
    task = Task(id="tsk_sec_01", organization_id="org_sec", intent="Auth vendor", required_role="sec")
    await task_repo.create(task)
    run = AgentRun(id="run_sec_01", task_id="tsk_sec_01", agent_id="sec_agent")
    await run_repo.create(run)

    raw_secret_key = "sk-live-super-secret-production-key-999"
    req = ToolRequest(
        tool_name="authenticate_external_api",
        arguments={"api_key": raw_secret_key, "service_name": "stripe_vendor"},
    )

    obs, _ = await engine.handle_tool_request(task, run, req)
    assert obs.success is True

    # 1. Observation data must be redacted
    assert "secret_session_token" not in str(obs.data)
    assert "[REDACTED_SECRET]" in str(obs.data)

    # 2. Persisted ToolExecution arguments must be redacted
    execs = await tool_repo.list_by_task("tsk_sec_01")
    assert len(execs) == 1
    persisted_exec = execs[0]
    assert raw_secret_key not in str(persisted_exec.arguments)
    assert "[REDACTED_SECRET]" in str(persisted_exec.arguments)
    assert "secret_session_token" not in str(persisted_exec.result)
    assert "[REDACTED_SECRET]" in str(persisted_exec.result)

    # 3. Persisted Events must be redacted
    events = await event_sink.list_events(task_id="tsk_sec_01")
    for event in events:
        payload_str = str(event.payload)
        assert raw_secret_key not in payload_str, f"Secret leaked in event {event.event_type}!"
        assert "secret_session_token" not in payload_str, f"Secret leaked in event {event.event_type}!"
