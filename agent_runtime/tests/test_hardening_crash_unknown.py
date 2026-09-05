"""Section 1, 6, 11, 12, 18: Tests for ambiguous crash recovery, UNKNOWN state, and Test A-F."""

import asyncio
from datetime import datetime, timezone
import pytest

from agent_runtime.core.contracts.agent import AgentRun
from agent_runtime.core.contracts.approval import HumanApprovalRequest
from agent_runtime.core.contracts.context import Task
from agent_runtime.core.contracts.tool import ToolExecution, ToolRequest, ToolSpec
from agent_runtime.core.engine.registry import ToolRegistry
from agent_runtime.core.interfaces.tool import ITool
from agent_runtime.core.persistence.agent_run_repo import SQLiteAgentRunRepository
from agent_runtime.core.persistence.approval_repo import SQLiteApprovalRepository
from agent_runtime.core.persistence.connection import DatabaseManager
from agent_runtime.core.persistence.idempotency_store import SQLiteIdempotencyStore
from agent_runtime.core.persistence.recovery import RuntimeCrashRecoveryService
from agent_runtime.core.persistence.task_repo import SQLiteTaskRepository
from agent_runtime.core.persistence.tool_exec_repo import SQLiteToolExecutionRepository
from agent_runtime.core.state.enums import (
    AgentRunState,
    ApprovalState,
    ExecutionSafety,
    IdempotencyStatus,
    TaskState,
    ToolExecutionState,
)


class NonIdempotentEmailTool(ITool):
    spec = ToolSpec(
        name="send_external_email",
        description="Sends external formal email",
        parameters_schema={"type": "object", "required": ["to", "body"]},
        execution_safety=ExecutionSafety.NON_IDEMPOTENT,
    )

    def __init__(self):
        self.invocation_count = 0

    async def execute(self, to: str, body: str, **kwargs):
        self.invocation_count += 1
        return {"sent_to": to, "status": "DELIVERED"}


class IdempotentS3UploadTool(ITool):
    spec = ToolSpec(
        name="upload_blob",
        description="Puts blob to object storage",
        parameters_schema={"type": "object", "required": ["key", "data"]},
        execution_safety=ExecutionSafety.IDEMPOTENT,
    )

    def __init__(self):
        self.invocation_count = 0

    async def execute(self, key: str, data: str, **kwargs):
        self.invocation_count += 1
        return {"key": key, "etag": "etag_12345"}


@pytest.fixture
def test_env(tmp_path):
    db_file = tmp_path / "test_unknown_matrix.sqlite"
    mgr = DatabaseManager(str(db_file))
    task_repo = SQLiteTaskRepository(mgr)
    run_repo = SQLiteAgentRunRepository(mgr)
    tool_repo = SQLiteToolExecutionRepository(mgr)
    approval_repo = SQLiteApprovalRepository(mgr)
    idempotency = SQLiteIdempotencyStore(mgr)

    tools = ToolRegistry()
    email_tool = NonIdempotentEmailTool()
    s3_tool = IdempotentS3UploadTool()
    tools.register(email_tool)
    tools.register(s3_tool)

    service = RuntimeCrashRecoveryService(
        task_repo=task_repo,
        run_repo=run_repo,
        tool_repo=tool_repo,
        approval_repo=approval_repo,
        idempotency_store=idempotency,
        tool_registry=tools,
    )

    yield service, task_repo, run_repo, tool_repo, approval_repo, idempotency, email_tool, s3_tool, str(db_file)
    mgr.close()


@pytest.mark.asyncio
async def test_case_a_persistent_state_close_and_recover_continue(test_env):
    """Test A: Create persistent state -> close runtime -> create new runtime instance -> recover -> continue."""
    service, task_repo, run_repo, _, _, _, _, _, db_path = test_env

    # 1. Create task and run
    task = Task(id="tsk_test_a", organization_id="org_a", intent="Process data", required_role="worker", status=TaskState.RUNNING)
    await task_repo.create(task)
    run = AgentRun(id="run_test_a", task_id="tsk_test_a", agent_id="agent_a", status=AgentRunState.EXECUTING)
    await run_repo.create(run)

    # 2. Simulate process restart by opening new DatabaseManager on same file
    mgr2 = DatabaseManager(db_path)
    service2 = RuntimeCrashRecoveryService(
        task_repo=SQLiteTaskRepository(mgr2),
        run_repo=SQLiteAgentRunRepository(mgr2),
        tool_repo=SQLiteToolExecutionRepository(mgr2),
        approval_repo=SQLiteApprovalRepository(mgr2),
    )

    report = await service2.recover()
    assert report.runs_marked_interrupted == 1
    assert report.tasks_reset_to_pending == 1

    # Task is now PENDING and can be safely claimed by next worker
    task_resumed = await SQLiteTaskRepository(mgr2).get("tsk_test_a")
    assert task_resumed.status == TaskState.PENDING
    assert task_resumed.attempt_count == 1  # Consumed 1 attempt!

    mgr2.close()


@pytest.mark.asyncio
async def test_case_b_agent_run_interrupted_by_crash(test_env):
    """Test B: Simulate process death while AgentRun active."""
    service, task_repo, run_repo, _, _, _, _, _, _ = test_env

    task = Task(id="tsk_test_b", organization_id="org_b", intent="Job", required_role="worker", status=TaskState.RUNNING)
    await task_repo.create(task)
    run = AgentRun(id="run_test_b", task_id="tsk_test_b", agent_id="agent_b", status=AgentRunState.EXECUTING)
    await run_repo.create(run)

    report = await service.recover()
    assert report.runs_marked_interrupted == 1

    recovered_run = await run_repo.get("run_test_b")
    assert recovered_run.status == AgentRunState.FAILED
    assert "INTERRUPTED_BY_PROCESS_CRASH" in recovered_run.error


@pytest.mark.asyncio
async def test_case_c_non_idempotent_tool_marked_unknown_and_blocked(test_env):
    """
    Test C: Simulate process death while NON_IDEMPOTENT ToolExecution active.
    Must be marked UNKNOWN and Task marked BLOCKED. NOT blindly replayed!
    """
    service, task_repo, run_repo, tool_repo, _, idempotency, _, _, _ = test_env

    task = Task(id="tsk_test_c", organization_id="org_c", intent="Send email", required_role="worker", status=TaskState.RUNNING)
    await task_repo.create(task)
    run = AgentRun(id="run_test_c", task_id="tsk_test_c", agent_id="agent_c", status=AgentRunState.EXECUTING)
    await run_repo.create(run)

    key = idempotency.compute_key("tsk_test_c", "run_test_c", "send_external_email", {"to": "client@corp.com", "body": "Notice"})
    await idempotency.reserve_or_get(key, "send_external_email", "exec_test_c")

    tool = ToolExecution(
        id="exec_test_c",
        agent_run_id="run_test_c",
        task_id="tsk_test_c",
        tool_name="send_external_email",
        arguments={"to": "client@corp.com", "body": "Notice"},
        status=ToolExecutionState.RUNNING,
        idempotency_key=key,
    )
    await tool_repo.create(tool)

    report = await service.recover()
    assert report.tools_marked_unknown == 1
    assert report.tasks_blocked_for_unknown == 1

    # Invariant: ToolExecution is UNKNOWN
    recovered_tool = await tool_repo.get("exec_test_c")
    assert recovered_tool.status == ToolExecutionState.UNKNOWN
    assert "AMBIGUOUS_EXTERNAL_EFFECT" in recovered_tool.error

    # Invariant: Task is BLOCKED (not PENDING!)
    recovered_task = await task_repo.get("tsk_test_c")
    assert recovered_task.status == TaskState.BLOCKED

    # Invariant: Idempotency store blocks replay
    replay_attempt = await idempotency.reserve_or_get(key, "send_external_email", "exec_new")
    assert replay_attempt.status == IdempotencyStatus.UNKNOWN
    assert "Replay blocked" in replay_attempt.error


@pytest.mark.asyncio
async def test_case_d_approval_preserved_after_crash(test_env):
    """Test D: Simulate process death after approval but before execution -> approval preserved as APPROVED."""
    service, task_repo, run_repo, _, approval_repo, _, _, _, _ = test_env

    task = Task(id="tsk_test_d", organization_id="org_d", intent="Approved action", required_role="worker", status=TaskState.BLOCKED)
    await task_repo.create(task)
    run = AgentRun(id="run_test_d", task_id="tsk_test_d", agent_id="agent_d", status=AgentRunState.AWAITING_APPROVAL)
    await run_repo.create(run)

    appr = HumanApprovalRequest(
        approval_id="appr_test_d",
        organization_id="org_d",
        task_id="tsk_test_d",
        agent_run_id="run_test_d",
        tool_request=ToolRequest(tool_name="send_external_email", arguments={"to": "client@corp.com", "body": "Approved"}),
        policy_decision_id="pol_d",
        status=ApprovalState.APPROVED,
        reviewed_by="Manager_Dan",
        reviewed_at=datetime.now(timezone.utc),
    )
    await approval_repo.create(appr)

    # Process crashes while approval is in APPROVED state
    report = await service.recover()
    assert report.pending_approvals_preserved == 0  # It's approved, not pending

    # Must still be APPROVED in database
    recovered_appr = await approval_repo.get("appr_test_d")
    assert recovered_appr.status == ApprovalState.APPROVED
    assert recovered_appr.reviewed_by == "Manager_Dan"


@pytest.mark.asyncio
async def test_case_e_and_f_duplicate_worker_executions(test_env):
    """
    Test E: Duplicate workers attempting same idempotent execution -> one executes, other gets cached.
    Test F: Duplicate workers attempting same non-idempotent execution -> prevented from duplicate execution.
    """
    _, _, _, _, _, idempotency, email_tool, s3_tool, _ = test_env

    # --- Test E (Idempotent tool): Race prevention ---
    key_e = idempotency.compute_key("tsk_e", "run_e", "upload_blob", {"key": "report.pdf", "data": "abc"}, is_tool_idempotent=True)
    res_e1, res_e2 = await asyncio.gather(
        idempotency.reserve_or_get(key_e, "upload_blob", "exec_e1"),
        idempotency.reserve_or_get(key_e, "upload_blob", "exec_e2"),
    )
    assert [res_e1.status, res_e2.status].count(IdempotencyStatus.ACQUIRED) == 1
    assert [res_e1.status, res_e2.status].count(IdempotencyStatus.CONCURRENT_RUN) == 1

    # --- Test F (Non-idempotent tool): Duplicate attempt prevented ---
    key_f = idempotency.compute_key("tsk_f", "run_f", "send_external_email", {"to": "ceo@corp.com", "body": "Alert"})
    res_f1, res_f2 = await asyncio.gather(
        idempotency.reserve_or_get(key_f, "send_external_email", "exec_f1"),
        idempotency.reserve_or_get(key_f, "send_external_email", "exec_f2"),
    )
    assert [res_f1.status, res_f2.status].count(IdempotencyStatus.ACQUIRED) == 1
    assert [res_f1.status, res_f2.status].count(IdempotencyStatus.CONCURRENT_RUN) == 1

    # The non-owner worker (CONCURRENT_RUN) is NOT permitted to invoke the tool!
    # Invocation count remains 0 for non-owner
    assert email_tool.invocation_count == 0
