"""Deterministic state transition engines for Task, AgentRun, ToolExecution, and Approval."""

from typing import Dict, Generic, Optional, Set, TypeVar
from agent_runtime.core.state.enums import (
    ApprovalState,
    AgentRunState,
    TaskState,
    ToolExecutionState,
)
from agent_runtime.core.state.exceptions import InvalidStateTransitionError

S = TypeVar("S")


class DeterministicTransitionValidator(Generic[S]):
    """Generic transition graph validator."""

    def __init__(self, entity_name: str, legal_transitions: Dict[S, Set[S]]):
        self.entity_name = entity_name
        self.legal_transitions = legal_transitions

    def can_transition(self, current: S, target: S) -> bool:
        if current == target:
            return True
        allowed = self.legal_transitions.get(current, set())
        return target in allowed

    def validate_transition(self, current: S, target: S, reason: str = "") -> None:
        if not self.can_transition(current, target):
            raise InvalidStateTransitionError(
                current_state=str(current),
                target_state=str(target),
                entity_type=self.entity_name,
                reason=reason,
            )


# Task State Machine Transitions
TASK_TRANSITIONS: Dict[TaskState, Set[TaskState]] = {
    TaskState.PENDING: {TaskState.ROUTED, TaskState.CANCELLED},
    TaskState.ROUTED: {TaskState.RUNNING, TaskState.PENDING, TaskState.CANCELLED, TaskState.FAILED},
    TaskState.RUNNING: {
        TaskState.BLOCKED,
        TaskState.VERIFYING,
        TaskState.COMPLETED,
        TaskState.FAILED,
        TaskState.CANCELLED,
        TaskState.PENDING,  # Crash recovery reset
    },
    TaskState.BLOCKED: {TaskState.RUNNING, TaskState.VERIFYING, TaskState.FAILED, TaskState.CANCELLED},
    TaskState.VERIFYING: {
        TaskState.COMPLETED,
        TaskState.RUNNING,
        TaskState.BLOCKED,
        TaskState.FAILED,
        TaskState.CANCELLED,
        TaskState.PENDING,
    },
    TaskState.COMPLETED: set(),
    TaskState.FAILED: set(),
    TaskState.CANCELLED: set(),
}

# AgentRun State Machine Transitions
AGENT_RUN_TRANSITIONS: Dict[AgentRunState, Set[AgentRunState]] = {
    AgentRunState.INITIALIZING: {AgentRunState.EXECUTING, AgentRunState.FAILED, AgentRunState.CANCELLED},
    AgentRunState.EXECUTING: {
        AgentRunState.AWAITING_TOOL,
        AgentRunState.AWAITING_APPROVAL,
        AgentRunState.COMPLETED,
        AgentRunState.FAILED,
        AgentRunState.TIMED_OUT,
        AgentRunState.CANCELLED,
    },
    AgentRunState.AWAITING_TOOL: {
        AgentRunState.EXECUTING,
        AgentRunState.FAILED,
        AgentRunState.TIMED_OUT,
        AgentRunState.CANCELLED,
    },
    AgentRunState.AWAITING_APPROVAL: {
        AgentRunState.EXECUTING,
        AgentRunState.FAILED,
        AgentRunState.TIMED_OUT,
        AgentRunState.CANCELLED,
    },
    AgentRunState.COMPLETED: set(),
    AgentRunState.FAILED: set(),
    AgentRunState.TIMED_OUT: set(),
    AgentRunState.CANCELLED: set(),
}

# ToolExecution State Machine Transitions (includes UNKNOWN)
TOOL_EXECUTION_TRANSITIONS: Dict[ToolExecutionState, Set[ToolExecutionState]] = {
    ToolExecutionState.QUEUED: {ToolExecutionState.RUNNING, ToolExecutionState.FAILED, ToolExecutionState.CANCELLED},
    ToolExecutionState.RUNNING: {
        ToolExecutionState.SUCCEEDED,
        ToolExecutionState.FAILED,
        ToolExecutionState.UNKNOWN,
        ToolExecutionState.TIMED_OUT,
        ToolExecutionState.CANCELLED,
    },
    ToolExecutionState.UNKNOWN: {
        ToolExecutionState.SUCCEEDED,  # External verification corroborated completion
        ToolExecutionState.FAILED,     # External verification corroborated non-execution
    },
    ToolExecutionState.SUCCEEDED: set(),
    ToolExecutionState.FAILED: set(),
    ToolExecutionState.TIMED_OUT: set(),
    ToolExecutionState.CANCELLED: set(),
}

# Approval State Machine Transitions
APPROVAL_TRANSITIONS: Dict[ApprovalState, Set[ApprovalState]] = {
    ApprovalState.PENDING: {
        ApprovalState.APPROVED,
        ApprovalState.REJECTED,
        ApprovalState.EXPIRED,
        ApprovalState.CANCELLED,
    },
    ApprovalState.APPROVED: {ApprovalState.EXECUTED, ApprovalState.REJECTED, ApprovalState.CANCELLED},
    ApprovalState.REJECTED: set(),
    ApprovalState.EXPIRED: set(),
    ApprovalState.CANCELLED: set(),
    ApprovalState.EXECUTED: set(),
}

task_validator = DeterministicTransitionValidator("Task", TASK_TRANSITIONS)
agent_run_validator = DeterministicTransitionValidator("AgentRun", AGENT_RUN_TRANSITIONS)
tool_execution_validator = DeterministicTransitionValidator("ToolExecution", TOOL_EXECUTION_TRANSITIONS)
approval_validator = DeterministicTransitionValidator("Approval", APPROVAL_TRANSITIONS)
