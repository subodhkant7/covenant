"""Tests for deterministic crash recovery semantics with UNKNOWN outcomes and reconciliation."""

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
from agent_runtime.core.persistence.recovery import RuntimeCrashRecoveryService
from agent_runtime.core.persistence.task_repo import SQLiteTaskRepository
from agent_runtime.core.persistence.tool_exec_repo import SQLiteToolExecutionRepository
from agent_runtime.core.state.enums import (
    AgentRunState,
    ApprovalState,
    ExecutionSafety,
    TaskState,
    ToolExecutionState,
)


class FakeReadOnlyTool(ITool):
    spec = ToolSpec(
        name="read_metrics",
        description="Reads metrics",
        execution_safety=ExecutionSafety.READ_ONLY,
    )

    async def execute(self, **kwargs):
        return {"ok": True}


class FakeMutatingNonIdempotentTool(ITool):
    spec = ToolSpec(
        name="send_external_payment",
        description="Charges money via payment gateway",
        execution_safety=ExecutionSafety.NON_IDEMPOTENT,
    )

    async def execute(self, **kwargs):
        return {"charged": True}


@pytest.fixture
def recovery_setup(tmp_path):
    db_file = tmp_path / "test_recovery.sqlite"
    mgr = DatabaseManager(str(db_file))
    task_repo = SQLiteTaskRepository(mgr)
    run_repo = SQLiteAgentRunRepository(mgr)
    tool_repo = SQLiteToolExecutionRepository(mgr)
    approval_repo = SQLiteApprovalRepository(mgr)

    tool_reg = ToolRegistry()
    tool_reg.register(FakeReadOnlyTool())
    tool_reg.register(FakeMutatingNonIdempotentTool())

    service = RuntimeCrashRecoveryService(
        task_repo=task_repo,
        run_repo=run_repo,
        tool_repo=tool_repo,
        approval_repo=approval_repo,
        tool_registry=tool_reg,
    )
    yield service, task_repo, run_repo, tool_repo, approval_repo
    mgr.close()


@pytest.mark.asyncio
async def test_crash_recovery_with_read_only_and_unknown_semantics(recovery_setup):
    service, task_repo, run_repo, tool_repo, approval_repo = recovery_setup

    # Task 1: Interrupted while executing READ_ONLY tool
    task_1 = Task(id="tsk_ro", organization_id="org_rec", intent="Check metrics", required_role="worker", status=TaskState.RUNNING)
    await task_repo.create(task_1)
    run_1 = AgentRun(id="run_ro", task_id="tsk_ro", agent_id="agent_1", status=AgentRunState.EXECUTING)
    await run_repo.create(run_1)
    tool_ro = ToolExecution(
        id="exec_ro",
        agent_run_id="run_ro",
        task_id="tsk_ro",
        tool_name="read_metrics",
        status=ToolExecutionState.RUNNING,
    )
    await tool_repo.create(tool_ro)

    # Task 2: Interrupted while executing NON_IDEMPOTENT tool (e.g. payment)
    task_2 = Task(id="tsk_mut", organization_id="org_rec", intent="Charge customer", required_role="worker", status=TaskState.RUNNING)
    await task_repo.create(task_2)
    run_2 = AgentRun(id="run_mut", task_id="tsk_mut", agent_id="agent_2", status=AgentRunState.EXECUTING)
    await run_repo.create(run_2)
    tool_mut = ToolExecution(
        id="exec_mut",
        agent_run_id="run_mut",
        task_id="tsk_mut",
        tool_name="send_external_payment",
        status=ToolExecutionState.RUNNING,
    )
    await tool_repo.create(tool_mut)

    # Pending Approval on Task 3
    task_3 = Task(id="tsk_appr", organization_id="org_rec", intent="Approve action", required_role="worker", status=TaskState.BLOCKED)
    await task_repo.create(task_3)
    run_3 = AgentRun(id="run_appr", task_id="tsk_appr", agent_id="agent_3", status=AgentRunState.AWAITING_APPROVAL)
    await run_repo.create(run_3)
    appr = HumanApprovalRequest(
        approval_id="appr_pending_01",
        organization_id="org_rec",
        task_id="tsk_appr",
        agent_run_id="run_appr",
        tool_request=ToolRequest(tool_name="some_tool", arguments={}),
        policy_decision_id="pol_1",
        status=ApprovalState.PENDING,
    )
    await approval_repo.create(appr)

    # Run Crash Recovery
    report = await service.recover()

    # Assertions on Recovery Report
    assert report.tools_marked_orphaned == 1     # read_metrics marked FAILED (safe to retry)
    assert report.tools_marked_unknown == 1      # send_external_payment marked UNKNOWN (cannot blindly retry)
    assert report.tasks_reset_to_pending == 1    # tsk_ro reset to PENDING
    assert report.tasks_blocked_for_unknown == 1 # tsk_mut BLOCKED for manual review/verification
    assert report.pending_approvals_preserved == 1

    # Inspect Task 1 (read-only): Reset to PENDING so another worker can claim it
    rec_task_1 = await task_repo.get("tsk_ro")
    assert rec_task_1.status == TaskState.PENDING
    assert rec_task_1.assigned_agent_id is None
    assert rec_task_1.attempt_count == 1

    # Inspect Task 2 (non-idempotent side effect): BLOCKED because tool outcome is UNKNOWN
    rec_task_2 = await task_repo.get("tsk_mut")
    assert rec_task_2.status == TaskState.BLOCKED
    rec_tool_mut = await tool_repo.get("exec_mut")
    assert rec_tool_mut.status == ToolExecutionState.UNKNOWN
    assert "AMBIGUOUS_EXTERNAL_EFFECT" in rec_tool_mut.error

    # Inspect Task 3 (approval): Still PENDING and task still BLOCKED
    rec_appr = await approval_repo.get("appr_pending_01")
    assert rec_appr.status == ApprovalState.PENDING

    # Test Reconciliation of UNKNOWN tool execution
    # External verification proves that the payment DID execute
    reconciled = await service.reconcile_unknown_execution(
        execution_id="exec_mut",
        verified_outcome=True,
        rationale="Stripe dashboard confirms charge ch_992 succeeded.",
    )
    assert reconciled.status == ToolExecutionState.SUCCEEDED
    assert reconciled.result["reconciled"] is True

    # Task 2 unblocks from BLOCKED to RUNNING
    unblocked_task_2 = await task_repo.get("tsk_mut")
    assert unblocked_task_2.status == TaskState.RUNNING
