"""In-memory event sink for audit and test observability."""

import asyncio
from typing import List, Optional
from agent_runtime.core.contracts.event import Event
from agent_runtime.core.interfaces.telemetry import IEventSink


class InMemoryEventSink(IEventSink):
    """Thread-safe in-memory event sink."""

    def __init__(self):
        self._events: List[Event] = []
        self._lock = asyncio.Lock()

    async def record(self, event: Event) -> None:
        async with self._lock:
            self._events.append(event)

    async def list_events(
        self,
        task_id: Optional[str] = None,
        trace_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[Event]:
        async with self._lock:
            filtered = self._events
            if task_id:
                filtered = [e for e in filtered if e.task_id == task_id]
            if trace_id:
                filtered = [e for e in filtered if e.trace_id == trace_id]
            return list(filtered[-limit:])

    def clear(self) -> None:
        self._events.clear()

    @property
    def events(self) -> List[Event]:
        return list(self._events)
