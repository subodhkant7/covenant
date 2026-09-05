"""Tool specifications, requests, executions, and observations."""

from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import uuid4
from pydantic import BaseModel, ConfigDict, Field, model_validator

from agent_runtime.core.state.enums import ExecutionSafety, ToolExecutionState


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ToolSpec(BaseModel):
    """Specification of a registered tool capability."""
    model_config = ConfigDict(frozen=True)

    name: str
    description: str
    parameters_schema: Dict[str, Any] = Field(default_factory=dict)
    has_side_effects: bool = False
    is_idempotent: bool = False
    execution_safety: ExecutionSafety = ExecutionSafety.READ_ONLY
    default_risk_level: str = "LOW"  # "LOW", "MEDIUM", "HIGH", "CRITICAL"

    @model_validator(mode="before")
    @classmethod
    def harmonize_safety_guarantees(cls, values: Any) -> Any:
        if isinstance(values, dict):
            # If execution_safety was explicitly supplied, derive booleans
            if "execution_safety" in values:
                safety = values["execution_safety"]
                if isinstance(safety, str):
                    safety = ExecutionSafety(safety)
                values["has_side_effects"] = (safety != ExecutionSafety.READ_ONLY)
                values["is_idempotent"] = (safety in (ExecutionSafety.READ_ONLY, ExecutionSafety.IDEMPOTENT))
            else:
                # Derive execution_safety from legacy boolean flags
                has_side = values.get("has_side_effects", False)
                is_idemp = values.get("is_idempotent", False)
                if not has_side:
                    values["execution_safety"] = ExecutionSafety.READ_ONLY
                elif is_idemp:
                    values["execution_safety"] = ExecutionSafety.IDEMPOTENT
                else:
                    values["execution_safety"] = ExecutionSafety.NON_IDEMPOTENT
        return values


class ToolRequest(BaseModel):
    """An agent's request to invoke a capability."""
    request_id: str = Field(default_factory=lambda: f"req_{uuid4().hex[:8]}")
    tool_name: str
    arguments: Dict[str, Any] = Field(default_factory=dict)
    rationale: str = ""


class ToolExecution(BaseModel):
    """Authoritative record of a concrete tool execution attempt."""
    id: str = Field(default_factory=lambda: f"exec_{uuid4().hex[:8]}")
    agent_run_id: str
    task_id: str
    tool_name: str
    arguments: Dict[str, Any] = Field(default_factory=dict)
    status: ToolExecutionState = ToolExecutionState.QUEUED
    result: Any = None
    error: Optional[str] = None
    idempotency_key: Optional[str] = None
    started_at: datetime = Field(default_factory=utc_now)
    completed_at: Optional[datetime] = None


class Observation(BaseModel):
    """Sanitized, agent-visible projection of a tool execution outcome."""
    observation_id: str = Field(default_factory=lambda: f"obs_{uuid4().hex[:8]}")
    execution_id: str
    tool_name: str
    success: bool
    data: Any = None
    error: Optional[str] = None
    is_terminal_failure: bool = False
    truncated: bool = False
