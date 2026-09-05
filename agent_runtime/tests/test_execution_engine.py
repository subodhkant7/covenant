"""Tests for ExecutionEngine authority boundary."""

import pytest

from agent_runtime.core.authorization.matrix import ToolPermissionMatrix
from agent_runtime.core.contracts.agent import AgentRun
from agent_runtime.core.contracts.approval import HumanApprovalRequest
from agent_runtime.core.contracts.context import Task
from agent_runtime.core.contracts.event import EventType
from agent_runtime.core.contracts.tool import ToolRequest, ToolSpec
from agent_runtime.core.engine.execution import ExecutionEngine
from agent_runtime.core.engine.registry import ToolRegistry
from agent_runtime.core.interfaces.tool import ITool
from agent_runtime.core.policy.engine import DefaultPolicyEngine
from agent_runtime.core.state.enums import ApprovalState
from agent_runtime.core.telemetry.sink import InMemoryEventSink


class EchoTool(ITool):
    spec = ToolSpec(
        name="echo_tool",
        description="Echoes message",
        parameters_schema={"type": "object", "required": ["message"]},
        has_side_effects=False,
    )

    async def execute(self, message: str, **kwargs):
        return {"echoed": message}


class DangerousRebootTool(ITool):
    spec = ToolSpec(
        name="reboot_server",
        description="Reboots server",
        parameters_schema={"type": "object", "required": ["server_id"]},
        has_side_effects=True,
    )

    async def execute(self, server_id: str, **kwargs):
        return {"rebooted": server_id}


@pytest.fixture
def setup_engine():
    tools = ToolRegistry()
    tools.register(EchoTool())
    tools.register(DangerousRebootTool())

    perms = ToolPermissionMatrix()
    perms.grant("org_1", "agent_1", ["echo_tool", "reboot_server"])

    policy = DefaultPolicyEngine()
    sink = InMemoryEventSink()

    engine = ExecutionEngine(
        tool_registry=tools,
        permissions=perms,
        policy_engine=policy,
        event_sink=sink,
    )
    return engine, sink


@pytest.mark.asyncio
async def test_unknown_tool_rejection(setup_engine):
    engine, sink = setup_engine
    task = Task(organization_id="org_1", intent="test", required_role="test")
    run = AgentRun(task_id=task.id, agent_id="agent_1")
    req = ToolRequest(tool_name="nonexistent_tool", arguments={})

    obs, appr = await engine.handle_tool_request(task, run, req)
    assert obs.success is False
    assert "not registered" in obs.error
    assert appr is None


@pytest.mark.asyncio
async def test_schema_validation_missing_field(setup_engine):
    engine, sink = setup_engine
    task = Task(organization_id="org_1", intent="test", required_role="test")
    run = AgentRun(task_id=task.id, agent_id="agent_1")
    # EchoTool requires 'message'
    req = ToolRequest(tool_name="echo_tool", arguments={"wrong_arg": "hi"})

    obs, appr = await engine.handle_tool_request(task, run, req)
    assert obs.success is False
    assert "Missing required fields" in obs.error


@pytest.mark.asyncio
async def test_permission_denial(setup_engine):
    engine, sink = setup_engine
    task = Task(organization_id="org_1", intent="test", required_role="test")
    # agent_2 is NOT in permission grants
    run = AgentRun(task_id=task.id, agent_id="agent_2")
    req = ToolRequest(tool_name="echo_tool", arguments={"message": "hello"})

    obs, appr = await engine.handle_tool_request(task, run, req)
    assert obs.success is False
    assert "Permission denied" in obs.error

    events = await sink.list_events(task_id=task.id)
    security_evts = [e for e in events if e.event_type == EventType.SECURITY_VIOLATION]
    assert len(security_evts) == 1


@pytest.mark.asyncio
async def test_side_effect_triggers_approval_requirement(setup_engine):
    engine, sink = setup_engine
    task = Task(organization_id="org_1", intent="test", required_role="test")
    run = AgentRun(task_id=task.id, agent_id="agent_1")
    req = ToolRequest(tool_name="reboot_server", arguments={"server_id": "srv-99"})

    obs, appr = await engine.handle_tool_request(task, run, req)
    assert obs.success is False
    assert "requires human approval" in obs.error
    assert appr is not None
    assert appr.status == ApprovalState.PENDING
    assert appr.tool_request.tool_name == "reboot_server"


@pytest.mark.asyncio
async def test_executing_with_approved_and_modified_arguments(setup_engine):
    engine, sink = setup_engine
    task = Task(organization_id="org_1", intent="test", required_role="test")
    run = AgentRun(task_id=task.id, agent_id="agent_1")
    req = ToolRequest(tool_name="reboot_server", arguments={"server_id": "srv-99"})

    # First turn creates approval request
    obs, appr = await engine.handle_tool_request(task, run, req)
    assert appr is not None

    # Reviewer approves with modified server_id
    appr.status = ApprovalState.APPROVED
    appr.reviewed_by = "LeadSRE"
    appr.modified_arguments = {"server_id": "srv-safe-101"}

    # Re-dispatch with approval override
    obs2, appr2 = await engine.handle_tool_request(task, run, req, approval=appr)
    assert obs2.success is True
    assert obs2.data["rebooted"] == "srv-safe-101"
    assert appr.status == ApprovalState.EXECUTED
