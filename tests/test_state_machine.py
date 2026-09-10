"""Tests for the Deterministic Commitment State Machine."""

import pytest
from covenant.domain.enums import ActionStatus, ActionType, CommitmentStatus, RiskLevel
from covenant.domain.models import Commitment, Party, ProposedAction, VerificationResult
from covenant.state_machine.exceptions import GuardConditionFailedError, InvalidStateTransitionError
from covenant.state_machine.machine import CommitmentStateMachine


@pytest.fixture
def base_commitment() -> Commitment:
    return Commitment(
        id="test_com_01",
        title="Test Deliverable Approval",
        description="Client signoff",
        promisor=Party(name="Client Rep", organization="Acme"),
        promisee=Party(name="Alex North", organization="Northstar Studio"),
        status=CommitmentStatus.DISCOVERED,
    )


def test_legal_linear_transitions(base_commitment: Commitment):
    # DISCOVERED -> ACTIVE
    CommitmentStateMachine.transition(base_commitment, CommitmentStatus.ACTIVE, "TestAgent", "Activated")
    assert base_commitment.status == CommitmentStatus.ACTIVE

    # ACTIVE -> OVERDUE
    CommitmentStateMachine.transition(base_commitment, CommitmentStatus.OVERDUE, "TestAgent", "Deadline missed")
    assert base_commitment.status == CommitmentStatus.OVERDUE

    # OVERDUE -> INVESTIGATING
    CommitmentStateMachine.transition(base_commitment, CommitmentStatus.INVESTIGATING, "EvidenceAgent", "Checking inbox")
    assert base_commitment.status == CommitmentStatus.INVESTIGATING

    # INVESTIGATING -> ACTION_READY
    CommitmentStateMachine.transition(base_commitment, CommitmentStatus.ACTION_READY, "ResolutionAgent", "Draft prepared")
    assert base_commitment.status == CommitmentStatus.ACTION_READY


def test_illegal_transitions(base_commitment: Commitment):
    # Cannot jump from DISCOVERED straight to RESOLVED
    with pytest.raises(InvalidStateTransitionError):
        CommitmentStateMachine.transition(base_commitment, CommitmentStatus.RESOLVED, "TestAgent", "Invalid jump")


def test_guard_awaiting_approval_requires_next_action(base_commitment: Commitment):
    base_commitment.status = CommitmentStatus.ACTION_READY
    base_commitment.next_action = None

    with pytest.raises(GuardConditionFailedError):
        CommitmentStateMachine.transition(
            base_commitment,
            CommitmentStatus.AWAITING_APPROVAL,
            "PolicyAgent",
            "Missing action guard check",
        )


def test_guard_executing_requires_approval(base_commitment: Commitment):
    base_commitment.status = CommitmentStatus.ACTION_READY
    base_commitment.next_action = ProposedAction(
        commitment_id=base_commitment.id,
        action_type=ActionType.FOLLOWUP_EMAIL,
        description="Follow-up email",
        status=ActionStatus.PROPOSED,
        requires_human_approval=True,
    )

    # Transition to AWAITING_APPROVAL
    CommitmentStateMachine.transition(
        base_commitment,
        CommitmentStatus.AWAITING_APPROVAL,
        "PolicyAgent",
        "Awaiting human approval",
    )

    # Attempt transition to EXECUTING before approval -> should fail guard
    with pytest.raises(GuardConditionFailedError):
        CommitmentStateMachine.transition(
            base_commitment,
            CommitmentStatus.EXECUTING,
            "System",
            "Executing without approval",
        )

    # Approve action -> transition should now succeed
    base_commitment.next_action.status = ActionStatus.APPROVED
    CommitmentStateMachine.transition(
        base_commitment,
        CommitmentStatus.EXECUTING,
        "System",
        "Approved execution",
        approved_by="User",
    )
    assert base_commitment.status == CommitmentStatus.EXECUTING


def test_guard_resolved_verification_failure(base_commitment: Commitment):
    base_commitment.status = CommitmentStatus.VERIFYING
    base_commitment.verification_result = VerificationResult(
        commitment_id=base_commitment.id,
        is_verified=False,
        rationale="Client has not signed off yet.",
    )

    with pytest.raises(GuardConditionFailedError):
        CommitmentStateMachine.transition(
            base_commitment,
            CommitmentStatus.RESOLVED,
            "VerificationAgent",
            "Should fail verification guard",
        )

    # Mark verified -> now transition to RESOLVED succeeds
    base_commitment.verification_result.is_verified = True
    base_commitment.verification_result.evidence_ids = ["EML-SIGNOFF-01"]
    CommitmentStateMachine.transition(
        base_commitment,
        CommitmentStatus.RESOLVED,
        "VerificationAgent",
        "Verified signoff received",
    )
    assert base_commitment.status == CommitmentStatus.RESOLVED
    assert base_commitment.resolution_timestamp is not None
