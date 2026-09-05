"""Base Agent Abstraction for Covenant."""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field

from covenant.domain.models import AgentEvent, Commitment, utc_now
from covenant.llm.provider import AbstractModelProvider
from covenant.persistence.repository import AbstractCommitmentRepository, AbstractEventRepository
from covenant.tools.base import ToolRegistry, global_tool_registry


class AgentContext(BaseModel):
    """Execution context passed through the agent network."""
    model_config = ConfigDict(arbitrary_types_allowed=True)

    session_id: str
    target_commitment_id: Optional[str] = None
    parameters: Dict[str, Any] = Field(default_factory=dict)


class AgentResult(BaseModel):
    """Output summary of an agent execution step."""
    agent_name: str
    success: bool
    summary: str
    data: Dict[str, Any] = Field(default_factory=dict)
    events: List[AgentEvent] = Field(default_factory=list)


class BaseAgent(ABC):
    """Abstract specialist agent class."""
    name: str
    description: str

    def __init__(
        self,
        llm: Optional[AbstractModelProvider] = None,
        tools: Optional[ToolRegistry] = None,
        commitment_repo: Optional[AbstractCommitmentRepository] = None,
        event_repo: Optional[AbstractEventRepository] = None,
    ):
        self.llm = llm
        self.tools = tools or global_tool_registry
        self.commitment_repo = commitment_repo
        self.event_repo = event_repo

    async def emit_event(
        self,
        action_name: str,
        summary: str,
        commitment_id: Optional[str] = None,
        tool_name: Optional[str] = None,
        inputs_summary: Optional[str] = None,
        result_summary: Optional[str] = None,
        previous_state: Any = None,
        new_state: Any = None,
        rationale: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> AgentEvent:
        """Create and persist an observability event."""
        event = AgentEvent(
            commitment_id=commitment_id,
            agent_name=self.name,
            tool_name=tool_name,
            action_name=action_name,
            summary=summary,
            inputs_summary=inputs_summary,
            result_summary=result_summary,
            previous_state=previous_state,
            new_state=new_state,
            rationale=rationale,
            metadata=metadata or {},
        )
        if self.event_repo:
            await self.event_repo.record_event(event)
        return event

    @abstractmethod
    async def run(self, context: AgentContext) -> AgentResult:
        """Execute agent's specific responsibility."""
        pass
