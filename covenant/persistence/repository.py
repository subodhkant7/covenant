"""Abstract repository interfaces for Covenant persistence."""

from abc import ABC, abstractmethod
from typing import List, Optional

from covenant.domain.enums import CommitmentStatus, ObligationDirection, RiskLevel
from covenant.domain.models import AgentEvent, Commitment


class AbstractCommitmentRepository(ABC):
    """Abstract interface for Commitment entity persistence."""

    @abstractmethod
    async def initialize(self) -> None:
        """Initialize storage tables or schemas."""
        pass

    @abstractmethod
    async def save(self, commitment: Commitment) -> Commitment:
        """Create or update a commitment."""
        pass

    @abstractmethod
    async def get_by_id(self, commitment_id: str) -> Optional[Commitment]:
        """Fetch a single commitment by ID."""
        pass

    @abstractmethod
    async def list_all(
        self,
        status: Optional[CommitmentStatus] = None,
        direction: Optional[ObligationDirection] = None,
        risk: Optional[RiskLevel] = None,
        search_query: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Commitment]:
        """Query commitments with optional filtering."""
        pass

    @abstractmethod
    async def delete(self, commitment_id: str) -> bool:
        """Delete a commitment by ID."""
        pass

    @abstractmethod
    async def count(
        self,
        status: Optional[CommitmentStatus] = None,
        direction: Optional[ObligationDirection] = None,
    ) -> int:
        """Count commitments matching criteria."""
        pass


class AbstractEventRepository(ABC):
    """Abstract interface for observability and audit trail persistence."""

    @abstractmethod
    async def record_event(self, event: AgentEvent) -> AgentEvent:
        """Persist an agent event."""
        pass

    @abstractmethod
    async def list_events(
        self,
        commitment_id: Optional[str] = None,
        agent_name: Optional[str] = None,
        limit: int = 100,
    ) -> List[AgentEvent]:
        """Fetch recent events in reverse chronological order."""
        pass
