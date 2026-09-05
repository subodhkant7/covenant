"""Finite lifecycle states and enums for the runtime kernel."""

from enum import Enum


class TaskState(str, Enum):
    """Lifecycle states of a Task."""
    PENDING = "PENDING"
    ROUTED = "ROUTED"
    RUNNING = "RUNNING"
    BLOCKED = "BLOCKED"
    VERIFYING = "VERIFYING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class AgentRunState(str, Enum):
    """Lifecycle states of an AgentRun attempt."""
    INITIALIZING = "INITIALIZING"
    EXECUTING = "EXECUTING"
    AWAITING_TOOL = "AWAITING_TOOL"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    TIMED_OUT = "TIMED_OUT"
    CANCELLED = "CANCELLED"


class ToolExecutionState(str, Enum):
    """Lifecycle states of an individual ToolExecution."""
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"  # Ambiguous outcome after crash or connection loss
    TIMED_OUT = "TIMED_OUT"
    CANCELLED = "CANCELLED"


class ExecutionSafety(str, Enum):
    """Execution delivery and retry guarantee semantics for tools."""
    READ_ONLY = "READ_ONLY"            # Safe to retry; no external side-effects
    IDEMPOTENT = "IDEMPOTENT"          # Side-effects occur, but retry produces identical outcome
    NON_IDEMPOTENT = "NON_IDEMPOTENT"  # Side-effects occur; retry may duplicate effect (crashed -> UNKNOWN)


class IdempotencyStatus(str, Enum):
    """Reservation status in the idempotency store."""
    ACQUIRED = "ACQUIRED"              # Worker owns the reservation and may execute
    CACHED = "CACHED"                  # Prior execution succeeded; cached observation available
    CONCURRENT_RUN = "CONCURRENT_RUN"  # Another worker is actively executing this key
    UNKNOWN = "UNKNOWN"                # Prior execution outcome was ambiguous; replay blocked


class ApprovalState(str, Enum):
    """Lifecycle states of a HumanApprovalRequest."""
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"
    EXECUTED = "EXECUTED"


class PolicyDecisionType(str, Enum):
    """Output categories from policy evaluation."""
    ALLOW = "ALLOW"
    DENY = "DENY"
    REQUIRE_HUMAN_APPROVAL = "REQUIRE_HUMAN_APPROVAL"


class ScopeType(str, Enum):
    """Target scope categorization for a Task."""
    UNSCOPED = "UNSCOPED"
    ORGANIZATION = "ORGANIZATION"
    ENTITY = "ENTITY"
    MULTI_ENTITY = "MULTI_ENTITY"


class StepCondition(str, Enum):
    """Execution conditions for DAG workflow steps."""
    ALL_SUCCESS = "ALL_SUCCESS"
    ANY_SUCCESS = "ANY_SUCCESS"
    ALWAYS = "ALWAYS"
