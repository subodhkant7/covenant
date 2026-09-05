"""Section 3, 13, 14: Real concurrent idempotency reservation and replay defense tests."""

import asyncio
import pytest

from agent_runtime.core.contracts.context import Task
from agent_runtime.core.contracts.tool import Observation, ToolSpec
from agent_runtime.core.engine.registry import ToolRegistry
from agent_runtime.core.interfaces.tool import ITool
from agent_runtime.core.persistence.connection import DatabaseManager
from agent_runtime.core.persistence.idempotency_store import SQLiteIdempotencyStore
from agent_runtime.core.state.enums import ExecutionSafety, IdempotencyStatus


class SlowMutatingCounterTool(ITool):
    spec = ToolSpec(
        name="charge_customer_account",
        description="Debits customer balance",
        parameters_schema={"type": "object", "required": ["account_id", "amount"]},
        execution_safety=ExecutionSafety.IDEMPOTENT,
    )

    def __init__(self):
        self.invocation_count = 0
        self._lock = asyncio.Lock()

    async def execute(self, account_id: str, amount: int, **kwargs):
        async with self._lock:
            self.invocation_count += 1
        # Simulate network delay so concurrency race is guaranteed to overlap
        await asyncio.sleep(0.05)
        return {"account_id": account_id, "amount": amount, "status": "DEBITED"}


@pytest.fixture
def db_manager(tmp_path):
    db_file = tmp_path / "test_idemp_race.sqlite"
    mgr = DatabaseManager(str(db_file))
    yield mgr
    mgr.close()


@pytest.mark.asyncio
async def test_concurrent_workers_idempotency_reservation(db_manager):
    """
    Two workers simultaneously receive the exact same logical request.
    Worker A acquires the reservation and executes the external tool.
    Worker B is blocked by the reservation (CONCURRENT_RUN) and does NOT execute the tool.
    After Worker A completes, Worker C accesses the key and receives CACHED observation.
    """
    store = SQLiteIdempotencyStore(db_manager)
    tool = SlowMutatingCounterTool()

    key = store.compute_key(
        task_id="tsk_race_101",
        agent_run_id="run_common",
        tool_name="charge_customer_account",
        arguments={"account_id": "ACC-99", "amount": 250},
        is_tool_idempotent=True,
    )

    # Worker A and Worker B race to reserve
    res_a, res_b = await asyncio.gather(
        store.reserve_or_get(key, tool.spec.name, execution_id="exec_worker_A"),
        store.reserve_or_get(key, tool.spec.name, execution_id="exec_worker_B"),
    )

    # Exactly one ACQUIRED, one CONCURRENT_RUN
    statuses = [res_a.status, res_b.status]
    assert statuses.count(IdempotencyStatus.ACQUIRED) == 1
    assert statuses.count(IdempotencyStatus.CONCURRENT_RUN) == 1

    # The winning worker executes the tool
    winning_exec_id = "exec_worker_A" if res_a.status == IdempotencyStatus.ACQUIRED else "exec_worker_B"
    raw_res = await tool.execute(account_id="ACC-99", amount=250)
    obs = Observation(execution_id=winning_exec_id, tool_name=tool.spec.name, success=True, data=raw_res)

    # Worker marks reservation SUCCEEDED
    await store.mark_succeeded(key, winning_exec_id, obs)

    # Worker C arrives later with same request -> gets CACHED
    res_c = await store.reserve_or_get(key, tool.spec.name, execution_id="exec_worker_C")
    assert res_c.status == IdempotencyStatus.CACHED
    assert res_c.cached_observation is not None
    assert res_c.cached_observation.data["status"] == "DEBITED"

    # Crucial assertion: External side effect was invoked EXACTLY ONCE
    assert tool.invocation_count == 1
