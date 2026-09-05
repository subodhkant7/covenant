"""Minimal workflow structural contracts."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from agent_runtime.core.state.enums import StepCondition


class WorkflowStep(BaseModel):
    """Step specification in a declarative workflow DAG."""
    step_id: str
    intent: str
    required_role: str
    depends_on: List[str] = Field(default_factory=list)
    condition: StepCondition = StepCondition.ALL_SUCCESS
    timeout_seconds: int = 300


class WorkflowDefinition(BaseModel):
    """Declarative DAG definition."""
    id: str
    name: str
    version: str = "1.0.0"
    steps: List[WorkflowStep] = Field(default_factory=list)


class WorkflowRun(BaseModel):
    """Active instance of a workflow DAG execution."""
    id: str
    workflow_definition_id: str
    organization_id: str
    status: str = "RUNNING"
    completed_steps: List[str] = Field(default_factory=list)
    step_outputs: Dict[str, Any] = Field(default_factory=dict)
