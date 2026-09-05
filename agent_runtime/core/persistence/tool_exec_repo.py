"""SQLiteToolExecutionRepository: Durable ToolExecution lifecycle storage."""

from datetime import datetime
import json
from typing import Any, Dict, List, Optional
import sqlite3

from agent_runtime.core.contracts.tool import ToolExecution
from agent_runtime.core.persistence.connection import DatabaseManager
from agent_runtime.core.persistence.interfaces import IToolExecutionRepository
from agent_runtime.core.state.enums import ToolExecutionState


def _serialize_exec(execution: ToolExecution) -> Dict[str, Any]:
    return {
        "id": execution.id,
        "agent_run_id": execution.agent_run_id,
        "task_id": execution.task_id,
        "tool_name": execution.tool_name,
        "arguments_json": json.dumps(execution.arguments),
        "status": execution.status.value,
        "result_json": json.dumps(execution.result) if execution.result is not None else None,
        "error": execution.error,
        "idempotency_key": execution.idempotency_key,
        "started_at": execution.started_at.isoformat(),
        "completed_at": execution.completed_at.isoformat() if execution.completed_at else None,
    }


def _deserialize_exec(row: sqlite3.Row) -> ToolExecution:
    return ToolExecution(
        id=row["id"],
        agent_run_id=row["agent_run_id"],
        task_id=row["task_id"],
        tool_name=row["tool_name"],
        arguments=json.loads(row["arguments_json"]),
        status=ToolExecutionState(row["status"]),
        result=json.loads(row["result_json"]) if row["result_json"] is not None else None,
        error=row["error"],
        idempotency_key=row["idempotency_key"],
        started_at=datetime.fromisoformat(row["started_at"]),
        completed_at=datetime.fromisoformat(row["completed_at"]) if row["completed_at"] else None,
    )


class SQLiteToolExecutionRepository(IToolExecutionRepository):
    """SQLite implementation of ToolExecution persistence."""

    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager

    async def create(self, execution: ToolExecution) -> ToolExecution:
        def _insert():
            data = _serialize_exec(execution)
            query = """
            INSERT INTO tool_executions (
                id, agent_run_id, task_id, tool_name, arguments_json,
                status, result_json, error, idempotency_key, started_at, completed_at
            ) VALUES (
                :id, :agent_run_id, :task_id, :tool_name, :arguments_json,
                :status, :result_json, :error, :idempotency_key, :started_at, :completed_at
            )
            """
            with self.db.get_connection() as conn:
                conn.execute(query, data)
                conn.commit()
            return execution

        return await self.db.run_async(_insert)

    async def get(self, execution_id: str) -> Optional[ToolExecution]:
        def _get():
            with self.db.get_connection() as conn:
                cursor = conn.execute("SELECT * FROM tool_executions WHERE id = ?", (execution_id,))
                row = cursor.fetchone()
                return _deserialize_exec(row) if row else None

        return await self.db.run_async(_get)

    async def update(self, execution: ToolExecution) -> None:
        def _update():
            data = _serialize_exec(execution)
            query = """
            UPDATE tool_executions SET
                status = :status,
                result_json = :result_json,
                error = :error,
                completed_at = :completed_at
            WHERE id = :id
            """
            with self.db.get_connection() as conn:
                conn.execute(query, data)
                conn.commit()

        await self.db.run_async(_update)

    async def list_by_run(self, agent_run_id: str) -> List[ToolExecution]:
        def _list():
            with self.db.get_connection() as conn:
                cursor = conn.execute("SELECT * FROM tool_executions WHERE agent_run_id = ? ORDER BY started_at ASC", (agent_run_id,))
                return [_deserialize_exec(r) for r in cursor.fetchall()]

        return await self.db.run_async(_list)

    async def list_by_task(self, task_id: str) -> List[ToolExecution]:
        def _list():
            with self.db.get_connection() as conn:
                cursor = conn.execute("SELECT * FROM tool_executions WHERE task_id = ? ORDER BY started_at ASC", (task_id,))
                return [_deserialize_exec(r) for r in cursor.fetchall()]

        return await self.db.run_async(_list)

    async def list_active(self) -> List[ToolExecution]:
        def _list():
            query = "SELECT * FROM tool_executions WHERE status IN ('QUEUED', 'RUNNING')"
            with self.db.get_connection() as conn:
                cursor = conn.execute(query)
                return [_deserialize_exec(r) for r in cursor.fetchall()]

        return await self.db.run_async(_list)
