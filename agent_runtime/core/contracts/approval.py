"""Human approval requests and decisions."""

from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import uuid4
from pydantic import BaseModel, Field

from agent_runtime.core.contracts.tool import ToolRequest
from agent_runtime.core.state.enums import ApprovalState


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class HumanApprovalRequest(BaseModel):
    """Durable, single-use human authorization request."""
    approval_id: str = Field(default_factory=lambda: f"appr_{uuid4().hex[:8]}")
    organization_id: str
    task_id: str
    agent_run_id: str
    tool_request: ToolRequest
    policy_decision_id: str
    status: ApprovalState = ApprovalState.PENDING
    requested_at: datetime = Field(default_factory=utc_now)
    timeout_at: Optional[datetime] = None
    modified_arguments: Optional[Dict[str, Any]] = None
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    reviewer_notes: Optional[str] = None
