"""SQLiteAgentRunRepository: Durable AgentRun storage."""

from datetime import datetime
import json
from typing import Any, Dict, List, Optional
import sqlite3

from agent_runtime.core.contracts.agent import AgentRun
from agent_runtime.core.persistence.connection import DatabaseManager
from agent_runtime.core.persistence.interfaces import IAgentRunRepository
from agent_runtime.core.state.enums import AgentRunState


def _serialize_run(run: AgentRun) -> Dict[str, Any]:
    return {
        "id": run.id,
        "task_id": run.task_id,
        "agent_id": run.agent_id,
        "attempt_number": run.attempt_number,
        "status": run.status.value,
        "turn_count": run.turn_count,
        "started_at": run.started_at.isoformat(),
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "error": run.error,
        "output_payload_json": json.dumps(run.output_payload) if run.output_payload else None,
        "completion_summary": run.completion_summary,
    }


def _deserialize_run(row: sqlite3.Row) -> AgentRun:
    return AgentRun(
        id=row["id"],
        task_id=row["task_id"],
        agent_id=row["agent_id"],
        attempt_number=row["attempt_number"],
        status=AgentRunState(row["status"]),
        turn_count=row["turn_count"],
        started_at=datetime.fromisoformat(row["started_at"]),
        completed_at=datetime.fromisoformat(row["completed_at"]) if row["completed_at"] else None,
        error=row["error"],
        output_payload=json.loads(row["output_payload_json"]) if row["output_payload_json"] else None,
        completion_summary=row["completion_summary"],
    )


class SQLiteAgentRunRepository(IAgentRunRepository):
    """SQLite implementation of AgentRun persistence."""

    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager

    async def create(self, run: AgentRun) -> AgentRun:
        def _insert():
            data = _serialize_run(run)
            query = """
            INSERT INTO agent_runs (
                id, task_id, agent_id, attempt_number, status, turn_count,
                started_at, completed_at, error, output_payload_json, completion_summary
            ) VALUES (
                :id, :task_id, :agent_id, :attempt_number, :status, :turn_count,
                :started_at, :completed_at, :error, :output_payload_json, :completion_summary
            )
            """
            with self.db.get_connection() as conn:
                conn.execute(query, data)
                conn.commit()
            return run

        return await self.db.run_async(_insert)

    async def get(self, run_id: str) -> Optional[AgentRun]:
        def _get():
            with self.db.get_connection() as conn:
                cursor = conn.execute("SELECT * FROM agent_runs WHERE id = ?", (run_id,))
                row = cursor.fetchone()
                return _deserialize_run(row) if row else None

        return await self.db.run_async(_get)

    async def update(self, run: AgentRun) -> None:
        def _update():
            data = _serialize_run(run)
            query = """
            UPDATE agent_runs SET
                status = :status,
                turn_count = :turn_count,
                completed_at = :completed_at,
                error = :error,
                output_payload_json = :output_payload_json,
                completion_summary = :completion_summary
            WHERE id = :id
            """
            with self.db.get_connection() as conn:
                conn.execute(query, data)
                conn.commit()

        await self.db.run_async(_update)

    async def list_by_task(self, task_id: str) -> List[AgentRun]:
        def _list():
            with self.db.get_connection() as conn:
                cursor = conn.execute("SELECT * FROM agent_runs WHERE task_id = ? ORDER BY attempt_number ASC", (task_id,))
                return [_deserialize_run(r) for r in cursor.fetchall()]

        return await self.db.run_async(_list)

    async def list_active(self) -> List[AgentRun]:
        def _list():
            query = "SELECT * FROM agent_runs WHERE status IN ('INITIALIZING', 'EXECUTING', 'AWAITING_TOOL', 'AWAITING_APPROVAL')"
            with self.db.get_connection() as conn:
                cursor = conn.execute(query)
                return [_deserialize_run(r) for r in cursor.fetchall()]

        return await self.db.run_async(_list)
