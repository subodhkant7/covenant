"""SQLiteEventSink: Durable append-only event audit trail with monotonic ordering."""

from datetime import datetime
import json
from typing import Any, Dict, List, Optional
import sqlite3

from agent_runtime.core.contracts.event import Event, EventType
from agent_runtime.core.interfaces.telemetry import IEventSink
from agent_runtime.core.persistence.connection import DatabaseManager


def _serialize_event(event: Event) -> Dict[str, Any]:
    return {
        "event_id": event.event_id,
        "trace_id": event.trace_id,
        "parent_event_id": event.parent_event_id,
        "organization_id": event.organization_id,
        "task_id": event.task_id,
        "agent_run_id": event.agent_run_id,
        "execution_id": event.execution_id,
        "event_type": event.event_type.value,
        "summary": event.summary,
        "payload_json": json.dumps(event.payload, default=str),
        "timestamp": event.timestamp.isoformat(),
    }


def _deserialize_event(row: sqlite3.Row) -> Event:
    return Event(
        event_id=row["event_id"],
        trace_id=row["trace_id"],
        parent_event_id=row["parent_event_id"],
        organization_id=row["organization_id"],
        task_id=row["task_id"],
        agent_run_id=row["agent_run_id"],
        execution_id=row["execution_id"],
        event_type=EventType(row["event_type"]),
        summary=row["summary"],
        payload=json.loads(row["payload_json"]),
        timestamp=datetime.fromisoformat(row["timestamp"]),
    )


class SQLiteEventSink(IEventSink):
    """
    SQLite-backed append-only event sink.
    Uses SQLite AUTOINCREMENT sequence_number for deterministic, monotonic chronological ordering.
    """

    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager

    async def record(self, event: Event) -> None:
        def _insert():
            data = _serialize_event(event)
            query = """
            INSERT INTO events (
                event_id, trace_id, parent_event_id, organization_id, task_id,
                agent_run_id, execution_id, event_type, summary, payload_json, timestamp
            ) VALUES (
                :event_id, :trace_id, :parent_event_id, :organization_id, :task_id,
                :agent_run_id, :execution_id, :event_type, :summary, :payload_json, :timestamp
            )
            """
            with self.db.get_connection() as conn:
                conn.execute(query, data)
                conn.commit()

        await self.db.run_async(_insert)

    async def list_events(
        self,
        task_id: Optional[str] = None,
        trace_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[Event]:
        def _list():
            query = "SELECT * FROM events WHERE 1=1"
            params: List[Any] = []
            if task_id:
                query += " AND task_id = ?"
                params.append(task_id)
            if trace_id:
                query += " AND trace_id = ?"
                params.append(trace_id)

            query += " ORDER BY sequence_number ASC LIMIT ?"
            params.append(limit)

            with self.db.get_connection() as conn:
                cursor = conn.execute(query, params)
                return [_deserialize_event(r) for r in cursor.fetchall()]

        return await self.db.run_async(_list)
