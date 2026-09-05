"""Tests for IdempotencyStore."""

from agent_runtime.core.contracts.tool import Observation
from agent_runtime.core.engine.idempotency import IdempotencyStore


def test_idempotency_caching():
    store = IdempotencyStore()

    key_1 = store.compute_key(
        task_id="tsk_1",
        agent_run_id="run_1",
        tool_name="fetch_status",
        arguments={"id": 42},
        is_tool_idempotent=True,
    )
    # Same arguments, different run, but tool is declared idempotent -> same key
    key_2 = store.compute_key(
        task_id="tsk_1",
        agent_run_id="run_2",
        tool_name="fetch_status",
        arguments={"id": 42},
        is_tool_idempotent=True,
    )
    assert key_1 == key_2

    obs = Observation(
        execution_id="exec_1",
        tool_name="fetch_status",
        success=True,
        data={"status": "ONLINE"},
    )
    store.set(key_1, obs)

    cached = store.get(key_2)
    assert cached is not None
    assert cached.data["status"] == "ONLINE"


def test_non_idempotent_tool_isolated_per_run():
    store = IdempotencyStore()

    # Non-idempotent tool includes agent_run_id in hash
    key_1 = store.compute_key(
        task_id="tsk_1",
        agent_run_id="run_1",
        tool_name="charge_card",
        arguments={"amount": 100},
        is_tool_idempotent=False,
    )
    key_2 = store.compute_key(
        task_id="tsk_1",
        agent_run_id="run_2",
        tool_name="charge_card",
        arguments={"amount": 100},
        is_tool_idempotent=False,
    )
    assert key_1 != key_2
