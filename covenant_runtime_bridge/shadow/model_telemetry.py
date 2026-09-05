"""Model Output Classification & Telemetry (Sections 9, 10, 11)."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4

from agent_runtime.core.interfaces.model import ModelResponse


class ModelOutputClass(str, Enum):
    VALID_TOOL_REQUEST = "VALID_TOOL_REQUEST"
    MULTIPLE_TOOL_REQUESTS = "MULTIPLE_TOOL_REQUESTS"
    FREEFORM = "FREEFORM"
    MALFORMED_STRUCTURED_OUTPUT = "MALFORMED_STRUCTURED_OUTPUT"
    UNKNOWN_TOOL = "UNKNOWN_TOOL"
    UNAUTHORIZED_TOOL = "UNAUTHORIZED_TOOL"
    INVALID_ARGUMENTS = "INVALID_ARGUMENTS"
    SIDE_EFFECT_REQUEST = "SIDE_EFFECT_REQUEST"
    POLICY_BLOCKED = "POLICY_BLOCKED"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    COMPLETION = "COMPLETION"
    MODEL_ERROR = "MODEL_ERROR"
    TIMEOUT = "TIMEOUT"


class ModelBehaviorType(str, Enum):
    SAFE = "SAFE"
    UNSAFE = "UNSAFE"
    MALFORMED = "MALFORMED"
    AMBIGUOUS = "AMBIGUOUS"


class RuntimeEnforcementType(str, Enum):
    ALLOWED = "ALLOWED"
    BLOCKED = "BLOCKED"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    SCHEMA_REJECTED = "SCHEMA_REJECTED"
    POLICY_REJECTED = "POLICY_REJECTED"
    VERIFICATION_REJECTED = "VERIFICATION_REJECTED"
    UNKNOWN = "UNKNOWN"


class RunOutcome(str, Enum):
    SAFELY_HANDLED = "SAFELY_HANDLED"
    UNSAFE_AND_BLOCKED = "UNSAFE_AND_BLOCKED"
    UNSAFE_AND_EXECUTED = "UNSAFE_AND_EXECUTED"  # Zero tolerance safety violation!
    MODEL_BEHAVIOR_DIFFERENCE = "MODEL_BEHAVIOR_DIFFERENCE"
    RUNTIME_BUG = "RUNTIME_BUG"


@dataclass
class ModelSoakRunRecord:
    run_id: str = field(default_factory=lambda: f"soak_{uuid4().hex[:8]}")
    scenario_id: str = ""
    scenario_category: str = ""  # NORMAL, AMBIGUOUS, MALICIOUS
    model_mode: str = "REAL_OLLAMA_RUN"  # REAL_OLLAMA_RUN vs MOCK_MODEL_RUN
    model_output_class: ModelOutputClass = ModelOutputClass.COMPLETION
    model_behavior: ModelBehaviorType = ModelBehaviorType.SAFE
    runtime_enforcement: RuntimeEnforcementType = RuntimeEnforcementType.ALLOWED
    run_outcome: RunOutcome = RunOutcome.SAFELY_HANDLED
    tool_requested: Optional[str] = None
    tool_executed: Optional[str] = None
    arguments: Dict[str, Any] = field(default_factory=dict)
    is_safety_violation: bool = False
    violation_reason: Optional[str] = None
    execution_time_ms: float = 0.0
