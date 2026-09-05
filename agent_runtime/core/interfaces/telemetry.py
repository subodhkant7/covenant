"""Telemetry and event sink interface."""

from abc import ABC, abstractmethod
from typing import List, Optional
from agent_runtime.core.contracts.event import Event


class IEventSink(ABC):
    """Sink for immutable event audit trail."""

    @abstractmethod
    async def record(self, event: Event) -> None:
        """Appends an event to the sink."""
        pass

    @abstractmethod
    async def list_events(
        self,
        task_id: Optional[str] = None,
        trace_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[Event]:
        """Retrieves events matching filters."""
        pass
