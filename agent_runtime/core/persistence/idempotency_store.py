"""SQLiteIdempotencyStore: Durable atomic reservation and outcome caching."""

from datetime import datetime, timezone
import hashlib
import json
import sqlite3
from typing import Any, Dict, Optional

from agent_runtime.core.contracts.tool import Observation
from agent_runtime.core.persistence.connection import DatabaseManager
from agent_runtime.core.persistence.interfaces import IIdempotencyStore, IdempotencyReservation
from agent_runtime.core.state.enums import IdempotencyStatus


class SQLiteIdempotencyStore(IIdempotencyStore):
    """
    SQLite-backed idempotency store enforcing atomic reservation.
    Prevents race conditions where two workers concurrently miss cache and duplicate side effects.
    """

    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager

    def compute_key(
        self,
        task_id: str,
        agent_run_id: str,
        tool_name: str,
        arguments: Dict[str, Any],
        is_tool_idempotent: bool = False,
    ) -> str:
        serialized = json.dumps(arguments, sort_keys=True, default=str)
        if is_tool_idempotent:
            raw = f"{task_id}:{tool_name}:{serialized}"
        else:
            raw = f"{task_id}:{agent_run_id}:{tool_name}:{serialized}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    async def get(self, key: str) -> Optional[Observation]:
        def _get():
            with self.db.get_connection() as conn:
                cursor = conn.execute(
                    "SELECT observation_json, status FROM idempotency_records WHERE idempotency_key = ?",
                    (key,),
                )
                row = cursor.fetchone()
                if row and row["status"] == "SUCCEEDED" and row["observation_json"]:
                    data = json.loads(row["observation_json"])
                    return Observation(**data)
                return None

        return await self.db.run_async(_get)

    async def set(
        self,
        key: str,
        tool_name: str = "",
        execution_id: str = "",
        observation: Optional[Observation] = None,
    ) -> None:
        """Upsert convenience setter."""
        if observation is None and isinstance(tool_name, Observation):
            obs = tool_name
            t_name = obs.tool_name
            e_id = obs.execution_id
        else:
            obs = observation
            t_name = tool_name
            e_id = execution_id
        if obs:
            await self.mark_succeeded(key, e_id, obs, tool_name=t_name)

    async def reserve_or_get(
        self,
        key: str,
        tool_name: str,
        execution_id: str,
    ) -> IdempotencyReservation:
        now = datetime.now(timezone.utc).isoformat()

        def _reserve():
            with self.db.get_connection() as conn:
                try:
                    # Attempt atomic reservation insert
                    query = """
                    INSERT INTO idempotency_records (
                        idempotency_key, tool_name, execution_id, status, created_at, updated_at
                    ) VALUES (?, ?, ?, 'RESERVED', ?, ?)
                    """
                    conn.execute(query, (key, tool_name, execution_id, now, now))
                    conn.commit()
                    return IdempotencyReservation(status=IdempotencyStatus.ACQUIRED)
                except sqlite3.IntegrityError:
                    # Row already exists! Check existing state
                    cursor = conn.execute(
                        "SELECT status, observation_json, execution_id FROM idempotency_records WHERE idempotency_key = ?",
                        (key,),
                    )
                    row = cursor.fetchone()
                    if not row:
                        return IdempotencyReservation(status=IdempotencyStatus.ACQUIRED)

                    existing_status = row["status"]
                    if existing_status == "SUCCEEDED" and row["observation_json"]:
                        obs_data = json.loads(row["observation_json"])
                        return IdempotencyReservation(
                            status=IdempotencyStatus.CACHED,
                            cached_observation=Observation(**obs_data),
                        )
                    elif existing_status in ("RESERVED", "EXECUTING"):
                        return IdempotencyReservation(
                            status=IdempotencyStatus.CONCURRENT_RUN,
                            error=f"Execution already in progress by worker execution '{row['execution_id']}'.",
                        )
                    elif existing_status == "UNKNOWN":
                        return IdempotencyReservation(
                            status=IdempotencyStatus.UNKNOWN,
                            error="Prior execution outcome was ambiguous (UNKNOWN). Replay blocked until recovery.",
                        )
                    else:  # FAILED
                        # Allow retry by re-claiming the failed reservation
                        update_q = """
                        UPDATE idempotency_records
                        SET status = 'RESERVED', execution_id = ?, updated_at = ?
                        WHERE idempotency_key = ? AND status = 'FAILED'
                        """
                        up_cursor = conn.execute(update_q, (execution_id, now, key))
                        conn.commit()
                        if up_cursor.rowcount == 1:
                            return IdempotencyReservation(status=IdempotencyStatus.ACQUIRED)
                        return IdempotencyReservation(
                            status=IdempotencyStatus.CONCURRENT_RUN,
                            error="Could not acquire reservation on failed record.",
                        )

        return await self.db.run_async(_reserve)

    async def mark_succeeded(
        self,
        key: str,
        execution_id: str,
        observation: Observation,
        tool_name: str = "",
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        obs_json = json.dumps(observation.model_dump(mode="json"))
        t_name = tool_name or observation.tool_name

        def _upsert():
            with self.db.get_connection() as conn:
                query = """
                INSERT INTO idempotency_records (
                    idempotency_key, tool_name, execution_id, status, observation_json, created_at, updated_at
                ) VALUES (?, ?, ?, 'SUCCEEDED', ?, ?, ?)
                ON CONFLICT(idempotency_key) DO UPDATE SET
                    status = 'SUCCEEDED',
                    observation_json = excluded.observation_json,
                    updated_at = excluded.updated_at
                """
                conn.execute(query, (key, t_name, execution_id, obs_json, now, now))
                conn.commit()

        await self.db.run_async(_upsert)

    async def mark_failed(
        self,
        key: str,
        execution_id: str,
        observation: Optional[Observation] = None,
        tool_name: str = "",
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        obs_json = json.dumps(observation.model_dump(mode="json")) if observation else None

        def _upsert():
            with self.db.get_connection() as conn:
                query = """
                INSERT INTO idempotency_records (
                    idempotency_key, tool_name, execution_id, status, observation_json, created_at, updated_at
                ) VALUES (?, ?, ?, 'FAILED', ?, ?, ?)
                ON CONFLICT(idempotency_key) DO UPDATE SET
                    status = 'FAILED',
                    observation_json = excluded.observation_json,
                    updated_at = excluded.updated_at
                """
                conn.execute(query, (key, tool_name or "tool", execution_id, obs_json, now, now))
                conn.commit()

        await self.db.run_async(_upsert)

    async def mark_unknown(self, key: str, execution_id: str, error: str) -> None:
        now = datetime.now(timezone.utc).isoformat()

        def _update():
            with self.db.get_connection() as conn:
                conn.execute(
                    """
                    UPDATE idempotency_records
                    SET status = 'UNKNOWN', updated_at = ?
                    WHERE idempotency_key = ?
                    """,
                    (now, key),
                )
                conn.commit()

        await self.db.run_async(_update)
