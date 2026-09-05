"""Tests for SQLite persistence implementations, constraints, and monotonic ordering."""

import asyncio
from datetime import datetime, timezone
import pytest
import sqlite3

from agent_runtime.core.contracts.agent import AgentRun
from agent_runtime.core.contracts.approval import HumanApprovalRequest
from agent_runtime.core.contracts.context import Task, TaskScope
from agent_runtime.core.contracts.event import Event, EventType
from agent_runtime.core.contracts.tool import Observation, ToolExecution, ToolRequest
from agent_runtime.core.persistence.agent_run_repo import SQLiteAgentRunRepository
from agent_runtime.core.persistence.approval_repo import SQLiteApprovalRepository
from agent_runtime.core.persistence.connection import DatabaseManager
from agent_runtime.core.persistence.idempotency_store import SQLiteIdempotencyStore
from agent_runtime.core.persistence.task_repo import SQLiteTaskRepository
from agent_runtime.core.persistence.tool_exec_repo import SQLiteToolExecutionRepository
from agent_runtime.core.state.enums import AgentRunState, ApprovalState, TaskState, ToolExecutionState
from agent_runtime.core.telemetry.sqlite_sink import SQLiteEventSink


@pytest.fixture
def db_manager(tmp_path):
    db_file = tmp_path / "test_runtime.sqlite"
    mgr = DatabaseManager(str(db_file))
    yield mgr
    mgr.close()


@pytest.mark.asyncio
async def test_task_repository_crud_and_duplicate_rejection(db_manager):
    repo = SQLiteTaskRepository(db_manager)
    task = Task(
        id="tsk_test_001",
        organization_id="org_alpha",
        intent="Analyze database performance",
        required_role="role_dba",
        scope=TaskScope(entity_type="database", entity_ids=["db_prod_01"]),
    )
    saved = await repo.create(task)
    assert saved.id == "tsk_test_001"

    fetched = await repo.get("tsk_test_001")
    assert fetched is not None
    assert fetched.intent == "Analyze database performance"
    assert fetched.scope.entity_ids == ["db_prod_01"]

    # Reject duplicate task ID
    with pytest.raises(sqlite3.IntegrityError):
        await repo.create(task)


@pytest.mark.asyncio
async def test_agent_run_and_foreign_key_constraint(db_manager):
    task_repo = SQLiteTaskRepository(db_manager)
    run_repo = SQLiteAgentRunRepository(db_manager)

    task = Task(id="tsk_parent_01", organization_id="org_alpha", intent="test", required_role="role_test")
    await task_repo.create(task)

    run = AgentRun(
        id="run_child_01",
        task_id="tsk_parent_01",
        agent_id="agent_alpha",
        attempt_number=1,
        status=AgentRunState.INITIALIZING,
    )
    await run_repo.create(run)

    # Reject duplicate run ID
    with pytest.raises(sqlite3.IntegrityError):
        await run_repo.create(run)

    # Foreign key constraint: reject run referencing non-existent task
    invalid_run = AgentRun(
        id="run_orphan_01",
        task_id="tsk_nonexistent_999",
        agent_id="agent_alpha",
    )
    with pytest.raises(sqlite3.IntegrityError):
        await run_repo.create(invalid_run)


@pytest.mark.asyncio
async def test_tool_execution_lifecycle_persistence(db_manager):
    task_repo = SQLiteTaskRepository(db_manager)
    run_repo = SQLiteAgentRunRepository(db_manager)
    tool_repo = SQLiteToolExecutionRepository(db_manager)

    task = Task(id="tsk_exec_01", organization_id="org_alpha", intent="test", required_role="role_test")
    await task_repo.create(task)

    run = AgentRun(id="run_001", task_id="tsk_exec_01", agent_id="agent_alpha")
    await run_repo.create(run)

    execution = ToolExecution(
        id="exec_001",
        agent_run_id="run_001",
        task_id="tsk_exec_01",
        tool_name="ping_host",
        arguments={"host": "10.0.0.1"},
        status=ToolExecutionState.RUNNING,
    )
    await tool_repo.create(execution)

    # Transition to SUCCEEDED
    execution.status = ToolExecutionState.SUCCEEDED
    execution.result = {"latency_ms": 14}
    execution.completed_at = datetime.now(timezone.utc)
    await tool_repo.update(execution)

    retrieved = await tool_repo.get("exec_001")
    assert retrieved.status == ToolExecutionState.SUCCEEDED
    assert retrieved.result["latency_ms"] == 14


@pytest.mark.asyncio
async def test_idempotency_store_sqlite(db_manager):
    store = SQLiteIdempotencyStore(db_manager)
    key = store.compute_key("tsk_1", "run_1", "charge_card", {"amount": 50})

    cached = await store.get(key)
    assert cached is None

    obs = Observation(execution_id="exec_1", tool_name="charge_card", success=True, data={"txn_id": "TX-99"})
    await store.set(key, "charge_card", "exec_1", obs)

    cached = await store.get(key)
    assert cached is not None
    assert cached.data["txn_id"] == "TX-99"

    # Setting same key again does not crash (atomic upsert)
    await store.set(key, "charge_card", "exec_1", obs)


@pytest.mark.asyncio
async def test_sqlite_event_sink_monotonic_ordering(db_manager):
    sink = SQLiteEventSink(db_manager)
    fixed_time = datetime(2026, 9, 3, 12, 0, 0, tzinfo=timezone.utc)

    # Record 5 events sharing the EXACT same timestamp
    for i in range(5):
        evt = Event(
            event_id=f"evt_order_{i}",
            trace_id="trc_order_test",
            organization_id="org_order",
            task_id="tsk_order",
            event_type=EventType.TOOL_REQUESTED,
            summary=f"Event {i}",
            timestamp=fixed_time,
        )
        await sink.record(evt)

    events = await sink.list_events(trace_id="trc_order_test")
    assert len(events) == 5
    # Must preserve exact insertion order despite identical timestamps
    for i, e in enumerate(events):
        assert e.summary == f"Event {i}"

    # Reject duplicate event_id
    duplicate_evt = Event(
        event_id="evt_order_0",
        trace_id="trc_order_test",
        organization_id="org_order",
        event_type=EventType.TASK_CREATED,
        summary="Duplicate event",
    )
    with pytest.raises(sqlite3.IntegrityError):
        await sink.record(duplicate_evt)
