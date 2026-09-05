"""Agent definitions, runs, turns, histories, and step results."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union
from uuid import uuid4
from pydantic import BaseModel, Field

from agent_runtime.core.contracts.tool import Observation, ToolRequest
from agent_runtime.core.state.enums import AgentRunState


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class AgentDefinition(BaseModel):
    """Specification of an agent's identity and qualifications."""
    id: str
    name: str
    supported_roles: List[str] = Field(default_factory=list)
    capabilities: List[str] = Field(default_factory=list)
    is_deterministic: bool = False
    model_provider_id: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class Turn(BaseModel):
    """A single reasoning turn in an AgentRun."""
    turn_index: int
    thought: Optional[str] = None
    request: Optional[ToolRequest] = None
    observation: Optional[Observation] = None
    timestamp: datetime = Field(default_factory=utc_now)


class AgentRunHistory(BaseModel):
    """Append-only transient turn history for an AgentRun."""
    run_id: str
    task_id: str
    turns: List[Turn] = Field(default_factory=list)

    @property
    def turn_count(self) -> int:
        return len(self.turns)

    def append_turn(
        self,
        thought: Optional[str] = None,
        request: Optional[ToolRequest] = None,
        observation: Optional[Observation] = None,
    ) -> Turn:
        turn = Turn(
            turn_index=len(self.turns) + 1,
            thought=thought,
            request=request,
            observation=observation,
        )
        self.turns.append(turn)
        return turn


class AgentRun(BaseModel):
    """A single bounded attempt of an assigned agent executing a task."""
    id: str = Field(default_factory=lambda: f"run_{uuid4().hex[:8]}")
    task_id: str
    agent_id: str
    attempt_number: int = 1
    status: AgentRunState = AgentRunState.INITIALIZING
    turn_count: int = 0
    started_at: datetime = Field(default_factory=utc_now)
    completed_at: Optional[datetime] = None
    error: Optional[str] = None
    output_payload: Optional[Dict[str, Any]] = None
    completion_summary: Optional[str] = None


# Discriminated step output types from agent turns
class AgentStepToolRequest(BaseModel):
    thought: Optional[str] = None
    request: ToolRequest


class AgentStepComplete(BaseModel):
    thought: Optional[str] = None
    summary: str
    output_payload: Dict[str, Any] = Field(default_factory=dict)


class AgentStepFailure(BaseModel):
    thought: Optional[str] = None
    error_message: str
    recoverable: bool = False


AgentStepResult = Union[AgentStepToolRequest, AgentStepComplete, AgentStepFailure]
