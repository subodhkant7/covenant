"""In-memory idempotency store with atomic reservation semantics."""

import asyncio
import hashlib
import json
from typing import Any, Dict, Optional
from agent_runtime.core.contracts.tool import Observation
from agent_runtime.core.persistence.interfaces import IIdempotencyStore, IdempotencyReservation
from agent_runtime.core.state.enums import IdempotencyStatus


class IdempotencyStore(IIdempotencyStore):
    """In-memory thread/coroutine-safe idempotency store with reservation semantics."""

    def __init__(self):
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()

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

    def get(self, key: str) -> Optional[Observation]:
        """Synchronous get for backward compatibility."""
        entry = self._cache.get(key)
        if entry and entry.get("status") == IdempotencyStatus.CACHED:
            return entry.get("observation")
        return None

    def set(
        self,
        key: str,
        tool_name: str = "",
        execution_id: str = "",
        observation: Optional[Observation] = None,
    ) -> None:
        """Synchronous set for backward compatibility."""
        if observation is None and isinstance(tool_name, Observation):
            obs = tool_name
        else:
            obs = observation
        if obs:
            self._cache[key] = {
                "status": IdempotencyStatus.CACHED,
                "observation": obs,
                "execution_id": execution_id,
            }

    async def reserve_or_get(
        self,
        key: str,
        tool_name: str,
        execution_id: str,
    ) -> IdempotencyReservation:
        async with self._lock:
            entry = self._cache.get(key)
            if not entry:
                self._cache[key] = {
                    "status": IdempotencyStatus.ACQUIRED,
                    "execution_id": execution_id,
                    "observation": None,
                }
                return IdempotencyReservation(status=IdempotencyStatus.ACQUIRED)

            status = entry["status"]
            if status == IdempotencyStatus.CACHED:
                return IdempotencyReservation(
                    status=IdempotencyStatus.CACHED,
                    cached_observation=entry["observation"],
                )
            elif status == IdempotencyStatus.ACQUIRED:
                return IdempotencyReservation(
                    status=IdempotencyStatus.CONCURRENT_RUN,
                    error=f"Execution already in progress by execution '{entry['execution_id']}'.",
                )
            elif status == IdempotencyStatus.UNKNOWN:
                return IdempotencyReservation(
                    status=IdempotencyStatus.UNKNOWN,
                    error="Prior execution outcome was ambiguous. Replay blocked.",
                )
            else:
                entry["status"] = IdempotencyStatus.ACQUIRED
                entry["execution_id"] = execution_id
                return IdempotencyReservation(status=IdempotencyStatus.ACQUIRED)

    async def mark_succeeded(self, key: str, execution_id: str, observation: Observation) -> None:
        async with self._lock:
            self._cache[key] = {
                "status": IdempotencyStatus.CACHED,
                "observation": observation,
                "execution_id": execution_id,
            }

    async def mark_failed(self, key: str, execution_id: str, observation: Optional[Observation] = None) -> None:
        async with self._lock:
            self._cache[key] = {
                "status": "FAILED",
                "observation": observation,
                "execution_id": execution_id,
            }

    async def mark_unknown(self, key: str, execution_id: str, error: str) -> None:
        async with self._lock:
            self._cache[key] = {
                "status": IdempotencyStatus.UNKNOWN,
                "error": error,
                "execution_id": execution_id,
            }

    def clear(self) -> None:
        self._cache.clear()
