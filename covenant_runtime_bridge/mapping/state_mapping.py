"""Domain state mapping: Covenant CommitmentStatus <-> Generic Runtime TaskState."""

from typing import Dict
from covenant.domain.enums import CommitmentStatus
from agent_runtime.core.state.enums import TaskState

# Unidirectional mapping from Covenant domain status to runtime TaskState
COMMITMENT_TO_TASK_STATE: Dict[CommitmentStatus, TaskState] = {
    CommitmentStatus.DISCOVERED: TaskState.PENDING,
    CommitmentStatus.ACTIVE: TaskState.PENDING,
    CommitmentStatus.WAITING: TaskState.PENDING,
    CommitmentStatus.DUE: TaskState.PENDING,
    CommitmentStatus.OVERDUE: TaskState.PENDING,
    CommitmentStatus.INVESTIGATING: TaskState.RUNNING,
    CommitmentStatus.ACTION_READY: TaskState.RUNNING,
    CommitmentStatus.AWAITING_APPROVAL: TaskState.BLOCKED,
    CommitmentStatus.EXECUTING: TaskState.RUNNING,
    CommitmentStatus.VERIFYING: TaskState.VERIFYING,
    CommitmentStatus.RESOLVED: TaskState.COMPLETED,
    CommitmentStatus.BLOCKED: TaskState.BLOCKED,
    CommitmentStatus.REJECTED: TaskState.FAILED,
    CommitmentStatus.CANCELLED: TaskState.CANCELLED,
    CommitmentStatus.FAILED: TaskState.FAILED,
    CommitmentStatus.ESCALATED: TaskState.BLOCKED,
}


def map_commitment_status_to_task_state(status: CommitmentStatus) -> TaskState:
    """Translates a domain commitment status to a generic runtime TaskState."""
    return COMMITMENT_TO_TASK_STATE.get(status, TaskState.PENDING)


def derive_commitment_status_from_task(
    task_state: TaskState,
    current_status: CommitmentStatus,
) -> CommitmentStatus:
    """
    Derives the appropriate updated domain CommitmentStatus based on Task progression.
    Preserves domain nuance without letting runtime overwrite domain rules.
    """
    if task_state == TaskState.COMPLETED:
        return CommitmentStatus.RESOLVED
    elif task_state == TaskState.BLOCKED:
        return CommitmentStatus.AWAITING_APPROVAL
    elif task_state == TaskState.VERIFYING:
        return CommitmentStatus.VERIFYING
    elif task_state == TaskState.FAILED:
        return CommitmentStatus.FAILED
    elif task_state == TaskState.CANCELLED:
        return CommitmentStatus.CANCELLED
    elif task_state == TaskState.RUNNING:
        if current_status in (CommitmentStatus.OVERDUE, CommitmentStatus.DUE, CommitmentStatus.DISCOVERED):
            return CommitmentStatus.INVESTIGATING
        return current_status
    return current_status
