"""SQLiteTaskRepository: Durable task storage with atomic claiming and state transitions."""

from datetime import datetime, timezone
import json
from typing import Any, Dict, List, Optional
import sqlite3

from agent_runtime.core.contracts.context import Task, TaskScope
from agent_runtime.core.persistence.connection import DatabaseManager
from agent_runtime.core.persistence.interfaces import ITaskRepository
from agent_runtime.core.state.enums import TaskState


def _serialize_task(task: Task) -> Dict[str, Any]:
    return {
        "id": task.id,
        "organization_id": task.organization_id,
        "intent": task.intent,
        "required_role": task.required_role,
        "scope_json": json.dumps(task.scope.model_dump(mode="json")),
        "input_payload_json": json.dumps(task.input_payload),
        "workflow_run_id": task.workflow_run_id,
        "parent_task_id": task.parent_task_id,
        "priority": task.priority,
        "deadline": task.deadline.isoformat() if task.deadline else None,
        "status": task.status.value,
        "assigned_agent_id": task.assigned_agent_id,
        "attempt_count": task.attempt_count,
        "max_retries": task.max_retries,
        "requires_verification": 1 if task.requires_verification else 0,
        "created_at": task.created_at.isoformat(),
        "updated_at": task.updated_at.isoformat(),
    }


def _deserialize_task(row: sqlite3.Row) -> Task:
    scope_data = json.loads(row["scope_json"])
    return Task(
        id=row["id"],
        organization_id=row["organization_id"],
        intent=row["intent"],
        required_role=row["required_role"],
        scope=TaskScope(**scope_data),
        input_payload=json.loads(row["input_payload_json"]),
        workflow_run_id=row["workflow_run_id"],
        parent_task_id=row["parent_task_id"],
        priority=row["priority"],
        deadline=datetime.fromisoformat(row["deadline"]) if row["deadline"] else None,
        status=TaskState(row["status"]),
        assigned_agent_id=row["assigned_agent_id"],
        attempt_count=row["attempt_count"],
        max_retries=row["max_retries"],
        requires_verification=bool(row["requires_verification"]),
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )


class SQLiteTaskRepository(ITaskRepository):
    """SQLite implementation of Task persistence."""

    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager

    async def create(self, task: Task) -> Task:
        def _insert():
            data = _serialize_task(task)
            query = """
            INSERT INTO tasks (
                id, organization_id, intent, required_role, scope_json,
                input_payload_json, workflow_run_id, parent_task_id, priority,
                deadline, status, assigned_agent_id, attempt_count, max_retries,
                requires_verification, created_at, updated_at
            ) VALUES (
                :id, :organization_id, :intent, :required_role, :scope_json,
                :input_payload_json, :workflow_run_id, :parent_task_id, :priority,
                :deadline, :status, :assigned_agent_id, :attempt_count, :max_retries,
                :requires_verification, :created_at, :updated_at
            )
            """
            with self.db.get_connection() as conn:
                conn.execute(query, data)
                conn.commit()
            return task

        return await self.db.run_async(_insert)

    async def get(self, task_id: str) -> Optional[Task]:
        def _get():
            with self.db.get_connection() as conn:
                cursor = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
                row = cursor.fetchone()
                return _deserialize_task(row) if row else None

        return await self.db.run_async(_get)

    async def update(self, task: Task) -> None:
        def _update():
            data = _serialize_task(task)
            query = """
            UPDATE tasks SET
                organization_id = :organization_id,
                intent = :intent,
                required_role = :required_role,
                scope_json = :scope_json,
                input_payload_json = :input_payload_json,
                workflow_run_id = :workflow_run_id,
                parent_task_id = :parent_task_id,
                priority = :priority,
                deadline = :deadline,
                status = :status,
                assigned_agent_id = :assigned_agent_id,
                attempt_count = :attempt_count,
                max_retries = :max_retries,
                requires_verification = :requires_verification,
                updated_at = :updated_at
            WHERE id = :id
            """
            with self.db.get_connection() as conn:
                conn.execute(query, data)
                conn.commit()

        await self.db.run_async(_update)

    async def atomic_claim(self, task_id: str, agent_id: str) -> bool:
        """
        Atomically claims task if and only if status == 'PENDING'.
        Transitions to 'ROUTED'.
        """
        now = datetime.now(timezone.utc).isoformat()

        def _claim():
            query = """
            UPDATE tasks
            SET status = 'ROUTED', assigned_agent_id = ?, updated_at = ?
            WHERE id = ? AND status = 'PENDING'
            """
            with self.db.get_connection() as conn:
                cursor = conn.execute(query, (agent_id, now, task_id))
                conn.commit()
                return cursor.rowcount == 1

        return await self.db.run_async(_claim)

    async def atomic_transition(
        self,
        task_id: str,
        expected_status: TaskState,
        new_status: TaskState,
    ) -> bool:
        """
        Atomically transitions status only if current status matches expected_status.
        """
        now = datetime.now(timezone.utc).isoformat()

        def _transition():
            query = """
            UPDATE tasks
            SET status = ?, updated_at = ?
            WHERE id = ? AND status = ?
            """
            with self.db.get_connection() as conn:
                cursor = conn.execute(query, (new_status.value, now, task_id, expected_status.value))
                conn.commit()
                return cursor.rowcount == 1

        return await self.db.run_async(_transition)

    async def list_by_status(
        self,
        status: TaskState,
        organization_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[Task]:
        def _list():
            query = "SELECT * FROM tasks WHERE status = ?"
            params: List[Any] = [status.value]
            if organization_id:
                query += " AND organization_id = ?"
                params.append(organization_id)
            query += " ORDER BY priority DESC, created_at ASC LIMIT ?"
            params.append(limit)

            with self.db.get_connection() as conn:
                cursor = conn.execute(query, params)
                return [_deserialize_task(r) for r in cursor.fetchall()]

        return await self.db.run_async(_list)

    async def list_interrupted(self) -> List[Task]:
        def _list():
            query = "SELECT * FROM tasks WHERE status IN ('ROUTED', 'RUNNING', 'VERIFYING')"
            with self.db.get_connection() as conn:
                cursor = conn.execute(query)
                return [_deserialize_task(r) for r in cursor.fetchall()]

        return await self.db.run_async(_list)
