"""Policy evaluation context and decisions."""

from datetime import datetime, timezone
from typing import List, Optional
from uuid import uuid4
from pydantic import BaseModel, Field

from agent_runtime.core.contracts.context import TaskScope
from agent_runtime.core.contracts.tool import ToolRequest, ToolSpec
from agent_runtime.core.state.enums import PolicyDecisionType


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class PolicyEvaluationContext(BaseModel):
    """Immutable evaluation context constructed solely by the runtime."""
    organization_id: str
    task_id: str
    agent_run_id: str
    agent_id: str
    role_id: str
    tool_spec: ToolSpec
    tool_request: ToolRequest
    task_scope: TaskScope
    timestamp: datetime = Field(default_factory=utc_now)
    recent_execution_count: int = 0


class PolicyDecision(BaseModel):
    """Deterministic result of policy evaluation."""
    decision_id: str = Field(default_factory=lambda: f"pol_{uuid4().hex[:8]}")
    tool_request_id: str
    decision: PolicyDecisionType
    rationale: str = ""
    rules_triggered: List[str] = Field(default_factory=list)
    evaluated_at: datetime = Field(default_factory=utc_now)
