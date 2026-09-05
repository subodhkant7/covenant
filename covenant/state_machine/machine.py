"""Deterministic State Machine for Commitment Lifecycle Management."""

from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional, Set

from covenant.domain.enums import ActionStatus, CommitmentStatus
from covenant.domain.models import ActionHistoryItem, Commitment, utc_now
from covenant.state_machine.exceptions import GuardConditionFailedError, InvalidStateTransitionError

# Definition of allowed transitions: {current_state: {allowed_next_states}}
LEGAL_TRANSITIONS: Dict[CommitmentStatus, Set[CommitmentStatus]] = {
    CommitmentStatus.DISCOVERED: {
        CommitmentStatus.ACTIVE,
        CommitmentStatus.WAITING,
        CommitmentStatus.CANCELLED,
        CommitmentStatus.REJECTED,
    },
    CommitmentStatus.ACTIVE: {
        CommitmentStatus.WAITING,
        CommitmentStatus.DUE,
        CommitmentStatus.OVERDUE,
        CommitmentStatus.INVESTIGATING,
        CommitmentStatus.VERIFYING,
        CommitmentStatus.BLOCKED,
        CommitmentStatus.CANCELLED,
    },
    CommitmentStatus.WAITING: {
        CommitmentStatus.ACTIVE,
        CommitmentStatus.DUE,
        CommitmentStatus.OVERDUE,
        CommitmentStatus.INVESTIGATING,
        CommitmentStatus.CANCELLED,
    },
    CommitmentStatus.DUE: {
        CommitmentStatus.OVERDUE,
        CommitmentStatus.INVESTIGATING,
        CommitmentStatus.ACTION_READY,
        CommitmentStatus.VERIFYING,
        CommitmentStatus.CANCELLED,
    },
    CommitmentStatus.OVERDUE: {
        CommitmentStatus.INVESTIGATING,
        CommitmentStatus.ACTION_READY,
        CommitmentStatus.ESCALATED,
        CommitmentStatus.CANCELLED,
    },
    CommitmentStatus.INVESTIGATING: {
        CommitmentStatus.ACTION_READY,
        CommitmentStatus.AWAITING_APPROVAL,
        CommitmentStatus.ACTIVE,
        CommitmentStatus.VERIFYING,
        CommitmentStatus.BLOCKED,
        CommitmentStatus.ESCALATED,
        CommitmentStatus.CANCELLED,
    },
    CommitmentStatus.ACTION_READY: {
        CommitmentStatus.AWAITING_APPROVAL,
        CommitmentStatus.EXECUTING,
        CommitmentStatus.INVESTIGATING,
        CommitmentStatus.BLOCKED,
        CommitmentStatus.CANCELLED,
    },
    CommitmentStatus.AWAITING_APPROVAL: {
        CommitmentStatus.EXECUTING,
        CommitmentStatus.REJECTED,
        CommitmentStatus.ESCALATED,
        CommitmentStatus.CANCELLED,
    },
    CommitmentStatus.EXECUTING: {
        CommitmentStatus.VERIFYING,
        CommitmentStatus.FAILED,
        CommitmentStatus.ESCALATED,
    },
    CommitmentStatus.VERIFYING: {
        CommitmentStatus.RESOLVED,
        CommitmentStatus.FAILED,
        CommitmentStatus.INVESTIGATING,
        CommitmentStatus.ACTIVE,
    },
    CommitmentStatus.BLOCKED: {
        CommitmentStatus.ACTIVE,
        CommitmentStatus.INVESTIGATING,
        CommitmentStatus.ESCALATED,
        CommitmentStatus.CANCELLED,
    },
    CommitmentStatus.ESCALATED: {
        CommitmentStatus.INVESTIGATING,
        CommitmentStatus.AWAITING_APPROVAL,
        CommitmentStatus.RESOLVED,
        CommitmentStatus.CANCELLED,
    },
    CommitmentStatus.FAILED: {
        CommitmentStatus.INVESTIGATING,
        CommitmentStatus.ACTION_READY,
        CommitmentStatus.ESCALATED,
        CommitmentStatus.CANCELLED,
    },
    # Terminal states
    CommitmentStatus.RESOLVED: {
        CommitmentStatus.INVESTIGATING,  # If reopened on dispute
    },
    CommitmentStatus.REJECTED: set(),
    CommitmentStatus.CANCELLED: set(),
}


def _guard_awaiting_approval(commitment: Commitment) -> None:
    """Ensure proposed action exists before entering AWAITING_APPROVAL."""
    if not commitment.next_action:
        raise GuardConditionFailedError("Cannot transition to AWAITING_APPROVAL without a proposed next_action.")


def _guard_executing(commitment: Commitment) -> None:
    """Ensure action approval status is valid before EXECUTING."""
    if commitment.status == CommitmentStatus.AWAITING_APPROVAL:
        if not commitment.next_action or commitment.next_action.status != ActionStatus.APPROVED:
            raise GuardConditionFailedError("Action must be APPROVED by human before entering EXECUTING state.")


def _guard_resolved(commitment: Commitment) -> None:
    """Ensure verification condition is checked before RESOLVED."""
    if not commitment.verification_result or not commitment.verification_result.is_verified:
        rationale = commitment.verification_result.rationale if commitment.verification_result else "No verification result recorded."
        raise GuardConditionFailedError(
            f"Cannot resolve commitment without verified outcome: {rationale}"
        )


STATE_GUARDS: Dict[CommitmentStatus, List[Callable[[Commitment], None]]] = {
    CommitmentStatus.AWAITING_APPROVAL: [_guard_awaiting_approval],
    CommitmentStatus.EXECUTING: [_guard_executing],
    CommitmentStatus.RESOLVED: [_guard_resolved],
}


class CommitmentStateMachine:
    """
    Deterministic validator and executor for Commitment state transitions.
    """

    @classmethod
    def get_legal_transitions(cls, current_state: CommitmentStatus) -> Set[CommitmentStatus]:
        """Return the set of legal next states for the given state."""
        return LEGAL_TRANSITIONS.get(current_state, set())

    @classmethod
    def can_transition(cls, current_state: CommitmentStatus, target_state: CommitmentStatus) -> bool:
        """Check if transition is structurally permitted in the state machine graph."""
        return target_state in LEGAL_TRANSITIONS.get(current_state, set())

    @classmethod
    def validate_transition(cls, commitment: Commitment, target_state: CommitmentStatus) -> None:
        """
        Validate whether the transition is legal and satisfies all guard conditions.
        Raises InvalidStateTransitionError or GuardConditionFailedError on violation.
        """
        current_state = commitment.status

        if not cls.can_transition(current_state, target_state):
            raise InvalidStateTransitionError(
                current_state=current_state.value,
                target_state=target_state.value,
                reason=f"Allowed next states from {current_state.value} are: {[s.value for s in cls.get_legal_transitions(current_state)]}",
            )

        # Run guards for target state
        guards = STATE_GUARDS.get(target_state, [])
        for guard in guards:
            guard(commitment)

    @classmethod
    def transition(
        cls,
        commitment: Commitment,
        target_state: CommitmentStatus,
        agent_name: str,
        reason: str,
        approved_by: Optional[str] = None,
    ) -> Commitment:
        """
        Execute state transition deterministically, append audit history, and update timestamps.
        """
        cls.validate_transition(commitment, target_state)

        old_state = commitment.status
        commitment.status = target_state

        # Update resolution timestamp on terminal resolved state
        if target_state == CommitmentStatus.RESOLVED:
            commitment.resolution_timestamp = utc_now()
        elif old_state == CommitmentStatus.RESOLVED and target_state != CommitmentStatus.RESOLVED:
            commitment.resolution_timestamp = None

        # Record action history item
        history_item = ActionHistoryItem(
            agent_name=agent_name,
            action_type=commitment.next_action.action_type if commitment.next_action else None,  # type: ignore
            summary=f"State transition: {old_state.value} -> {target_state.value}. {reason}",
            state_before=old_state,
            state_after=target_state,
            approved_by=approved_by,
        )
        commitment.action_history.append(history_item)

        return commitment
