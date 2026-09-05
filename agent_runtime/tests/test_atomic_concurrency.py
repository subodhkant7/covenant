"""Tests for atomic concurrency guarantees: task claiming and single-use approval consumption."""

import asyncio
import pytest

from agent_runtime.core.contracts.approval import HumanApprovalRequest
from agent_runtime.core.contracts.context import Task
from agent_runtime.core.contracts.tool import ToolRequest
from agent_runtime.core.persistence.approval_repo import SQLiteApprovalRepository
from agent_runtime.core.persistence.connection import DatabaseManager
from agent_runtime.core.persistence.task_repo import SQLiteTaskRepository
from agent_runtime.core.state.enums import ApprovalState, TaskState


@pytest.fixture
def db_manager(tmp_path):
    db_file = tmp_path / "test_concurrency.sqlite"
    mgr = DatabaseManager(str(db_file))
    yield mgr
    mgr.close()


@pytest.mark.asyncio
async def test_atomic_task_claim_race(db_manager):
    """
    Two workers simultaneously attempt to claim the same PENDING task.
    Exactly ONE worker must succeed.
    """
    repo = SQLiteTaskRepository(db_manager)
    task = Task(
        id="tsk_race_01",
        organization_id="org_race",
        intent="Process critical transaction",
        required_role="role_worker",
    )
    await repo.create(task)

    # Worker A and Worker B simultaneously attempt to claim
    async def claim_worker(worker_id: str):
        return await repo.atomic_claim("tsk_race_01", worker_id)

    results = await asyncio.gather(
        claim_worker("worker_A"),
        claim_worker("worker_B"),
    )

    # Exactly one True and one False
    assert results.count(True) == 1
    assert results.count(False) == 1

    # Task is now in ROUTED status with winning agent
    claimed_task = await repo.get("tsk_race_01")
    assert claimed_task.status == TaskState.ROUTED
    assert claimed_task.assigned_agent_id in ["worker_A", "worker_B"]


@pytest.mark.asyncio
async def test_atomic_approval_consumption_single_use(db_manager):
    """
    Two execution workers simultaneously attempt to consume the same APPROVED request.
    Exactly ONE execution must succeed; the second must be rejected (replayed).
    """
    task_repo = SQLiteTaskRepository(db_manager)
    approval_repo = SQLiteApprovalRepository(db_manager)

    task = Task(id="tsk_appr_race", organization_id="org_race", intent="test", required_role="role_test")
    await task_repo.create(task)

    appr = HumanApprovalRequest(
        approval_id="appr_single_use_01",
        organization_id="org_race",
        task_id="tsk_appr_race",
        agent_run_id="run_01",
        tool_request=ToolRequest(tool_name="transfer_funds", arguments={"amount": 1000}),
        policy_decision_id="pol_01",
        status=ApprovalState.PENDING,
    )
    await approval_repo.create(appr)

    # Human approves
    await approval_repo.atomic_approve("appr_single_use_01", reviewed_by="FinanceLead")
    fetched = await approval_repo.get("appr_single_use_01")
    assert fetched.status == ApprovalState.APPROVED

    # Two execution attempts simultaneously attempt to consume
    async def consume_attempt():
        return await approval_repo.atomic_consume("appr_single_use_01")

    consume_results = await asyncio.gather(
        consume_attempt(),
        consume_attempt(),
    )

    # Exactly one consumption succeeded
    assert consume_results.count(True) == 1
    assert consume_results.count(False) == 1

    # State is EXECUTED and can never be consumed again
    final_appr = await approval_repo.get("appr_single_use_01")
    assert final_appr.status == ApprovalState.EXECUTED

    # Third attempt also fails
    third_attempt = await approval_repo.atomic_consume("appr_single_use_01")
    assert third_attempt is False
