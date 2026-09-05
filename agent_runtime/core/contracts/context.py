"""Organization, Task, and Context contracts."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4
from pydantic import BaseModel, ConfigDict, Field

from agent_runtime.core.contracts.tool import ToolSpec
from agent_runtime.core.state.enums import ScopeType, TaskState


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class OrganizationContext(BaseModel):
    """Organization scope and configuration."""
    organization_id: str
    name: str
    settings: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class Role(BaseModel):
    """Functional role definition required by tasks."""
    id: str
    name: str
    description: str = ""
    required_capabilities: List[str] = Field(default_factory=list)


class TaskScope(BaseModel):
    """Scope definition decoupling tasks from single domain entities."""
    scope_type: ScopeType = ScopeType.UNSCOPED
    entity_type: Optional[str] = None
    entity_ids: List[str] = Field(default_factory=list)
    filter_criteria: Dict[str, Any] = Field(default_factory=dict)


class Task(BaseModel):
    """Universal atomic unit of work."""
    id: str = Field(default_factory=lambda: f"tsk_{uuid4().hex[:8]}")
    organization_id: str
    intent: str
    required_role: str
    scope: TaskScope = Field(default_factory=TaskScope)
    input_payload: Dict[str, Any] = Field(default_factory=dict)
    workflow_run_id: Optional[str] = None
    parent_task_id: Optional[str] = None
    priority: int = 0
    deadline: Optional[datetime] = None
    status: TaskState = TaskState.PENDING
    assigned_agent_id: Optional[str] = None
    attempt_count: int = 0
    max_retries: int = 3
    requires_verification: bool = False
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class TaskContext(BaseModel):
    """Immutable base context parcel delivered to an Agent."""
    model_config = ConfigDict(frozen=True)

    task_id: str
    organization_id: str
    intent: str
    required_role: str
    scope: TaskScope
    input_data: Dict[str, Any] = Field(default_factory=dict)
    prior_step_outputs: Dict[str, Any] = Field(default_factory=dict)
    available_tools: List[ToolSpec] = Field(default_factory=list)
    deadline: Optional[datetime] = None
    max_turns: int = 10
