"""Tests for hardened lifecycle invariants, temporal verification freshness, and evidence grounding."""

import pytest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from covenant.domain.models import (
    Commitment,
    Party,
    ProposedAction,
    VerificationResult,
    EvidenceReference,
    utc_now,
)
from covenant.domain.enums import (
    CommitmentStatus,
    RiskLevel,
    ActionType,
    ActionStatus,
    EvidenceSourceType,
    ObligationDirection,
)
from covenant.agents.evidence import EvidenceAgent
from covenant.agents.verification import VerificationAgent
from covenant.agents.base import AgentContext
from covenant.persistence.sqlite_repo import SQLiteCommitmentRepository
from covenant.state_machine.machine import CommitmentStateMachine
from covenant.state_machine.exceptions import GuardConditionFailedError, InvalidStateTransitionError
from covenant.synthetic_data.store import workspace_store
from covenant.tools.action_tools import VerifyCommitmentTool
from covenant.tools import initialize_tools


@pytest.fixture(autouse=True)
def clean_workspace_store():
    workspace_store.reset()
    yield
    workspace_store.reset()


@pytest.mark.asyncio
async def test_temporal_freshness_rejects_stale_pre_execution_evidence():
    """
    Ensures that VerifyCommitmentTool strictly rejects candidate evidence artifacts
    whose timestamp pre-dates the remedy action's executed_at timestamp.
    """
    tool = VerifyCommitmentTool()

    # Clear emails and set up a stale approval email from 2 hours ago
    now = utc_now()
    stale_time = (now - timedelta(hours=2)).isoformat()
    exec_time = (now - timedelta(minutes=30)).isoformat()

    old_emails = list(workspace_store.emails)
    try:
        workspace_store.emails = [
            {
                "id": "EML-STALE-999",
                "date": stale_time,
                "from": "Sarah Jenkins <sjenkins@meridianglobal.com>",
                "to": ["alex@northstarstudio.com"],
                "subject": "Old Phase 1 note",
                "body": "We formally approve the earlier draft.",
                "attachments": ["Signed_Atlas_Phase2_Signoff.pdf"],
            }
        ]

        # Execute verification with executed_at = 30 minutes ago
        res = await tool.execute(commitment_id="com_atlas_approval", executed_at=exec_time)
        assert res.success is True
        data = res.data
        # Must NOT be verified because evidence pre-dates execution!
        assert data["is_verified"] is False
        assert "stale evidence" in data["rationale"].lower()
        assert len(data["evidence_ids"]) == 0

        # Now simulate a fresh reply arriving after execution
        fresh_time = (now - timedelta(minutes=5)).isoformat()
        workspace_store.emails.append({
            "id": "EML-FRESH-1000",
            "date": fresh_time,
            "from": "Sarah Jenkins <sjenkins@meridianglobal.com>",
            "to": ["alex@northstarstudio.com"],
            "subject": "Formal Signoff Phase 2",
            "body": "We formally approve the Phase 2 deliverables.",
            "attachments": ["Signed_Atlas_Phase2_Signoff.pdf"],
        })

        fresh_res = await tool.execute(commitment_id="com_atlas_approval", executed_at=exec_time)
        assert fresh_res.success is True
        fresh_data = fresh_res.data
        assert fresh_data["is_verified"] is True
        assert "EML-FRESH-1000" in fresh_data["evidence_ids"]
    finally:
        workspace_store.emails = old_emails


@pytest.mark.asyncio
async def test_negative_path_counterparty_rejection_blocks_resolution(tmp_path):
    """
    Ensures that when a counterparty explicitly rejects or disputes deliverables,
    the commitment transitions to FAILED or remains unverified, and NEVER enters RESOLVED.
    """
    db_path = tmp_path / "neg_path.db"
    repo = SQLiteCommitmentRepository(db_path)
    await repo.initialize()

    tools = initialize_tools()
    v_agent = VerificationAgent(tools=tools, commitment_repo=repo, event_repo=repo)

    # Create commitment in VERIFYING state
    action = ProposedAction(
        commitment_id="com_atlas_neg",
        action_type=ActionType.FOLLOWUP_EMAIL,
        description="Follow-up email",
        status=ActionStatus.COMPLETED,
        executed_at=utc_now() - timedelta(minutes=10),
    )
    com = Commitment(
        id="com_atlas_neg",
        title="Atlas Negative Path Test",
        description="Testing rejection handling",
        promisor=Party(name="Sarah Jenkins", email="sjenkins@meridianglobal.com"),
        promisee=Party(name="Alex North"),
        status=CommitmentStatus.VERIFYING,
        risk=RiskLevel.HIGH,
        next_action=action,
    )
    await repo.save(com)

    # Simulate counterparty rejection email in workspace
    old_emails = list(workspace_store.emails)
    try:
        workspace_store.emails = [
            {
                "id": "EML-REJECT-001",
                "date": utc_now().isoformat(),
                "from": "Sarah Jenkins <sjenkins@meridianglobal.com>",
                "to": ["alex@northstarstudio.com"],
                "subject": "Re: Follow-up",
                "body": "Alex, we cannot approve this milestone. The QA tests failed and we reject the deliverable.",
                "attachments": [],
            }
        ]

        ctx = AgentContext(session_id="cycle_neg", target_commitment_id=com.id)
        await v_agent.run(ctx)

        updated = await repo.get_by_id(com.id)
        assert updated is not None
        # Must NOT be resolved!
        assert updated.status != CommitmentStatus.RESOLVED
        assert updated.status == CommitmentStatus.FAILED
        assert updated.verification_result is not None
        assert updated.verification_result.is_verified is False
        assert "rejected" in updated.verification_result.rationale.lower() or "cannot approve" in updated.verification_result.rationale.lower()
    finally:
        workspace_store.emails = old_emails


@pytest.mark.asyncio
async def test_empty_evidence_produces_explicit_uncertainty_and_gap():
    """
    Ensures EvidenceAgent does not fabricate high confidence when zero evidence sources
    are gathered, and produces an explicit EVIDENCE_GAP.
    """
    agent = EvidenceAgent()

    com = Commitment(
        id="com_empty_evidence",
        title="Uncorroborated Client Promise",
        description="Testing uncertainty on zero documentary sources",
        promisor=Party(name="Unknown Client"),
        promisee=Party(name="Alex North"),
        status=CommitmentStatus.ACTIVE,
        risk=RiskLevel.LOW,
    )

    # Synthesize with empty evidence list
    assessment = await agent.synthesize_evidence(commitment=com, gathered_evidence=[])

    # Confidence must be low (explicit uncertainty)
    assert assessment.confidence < 0.50
    assert assessment.confidence == 0.35
    # Evidence gaps must be captured
    assert len(assessment.evidence_gaps) >= 1
    assert "no documentary records" in assessment.evidence_gaps[0].lower()
    assert "complete documentary evidence gap" in assessment.finding.lower()
    # Must contain factual scan vs analytical inference claims
    facts = [c for c in assessment.factual_claims if c.is_fact]
    inferences = [c for c in assessment.factual_claims if not c.is_fact]
    assert len(facts) >= 1
    assert len(inferences) >= 1


@pytest.mark.asyncio
async def test_multi_source_status_contradiction_detection():
    """
    Ensures generic evidence synthesis detects mutually incompatible status claims across
    disparate sources and raises a STATUS_CONTRADICTION conflict.
    """
    agent = EvidenceAgent()

    com = Commitment(
        id="com_generic_conflict",
        title="Vendor Component Delivery",
        description="Testing dynamic conflict detection",
        promisor=Party(name="Vendor X"),
        promisee=Party(name="Alex North"),
        status=CommitmentStatus.INVESTIGATING,
        risk=RiskLevel.MEDIUM,
    )

    ev1 = EvidenceReference(
        source_type=EvidenceSourceType.EMAIL,
        source_id="EML-VEND-1",
        title="Delivery Notice",
        snippet="Component shipment delivered and complete yesterday.",
    )
    ev2 = EvidenceReference(
        source_type=EvidenceSourceType.PROJECT,
        source_id="PRJ-LOG-2",
        title="Warehouse Receiving",
        snippet="Shipment pending customs hold; calibration error unresolved.",
    )

    assessment = await agent.synthesize_evidence(commitment=com, gathered_evidence=[ev1, ev2])

    # Conflicting signals must be caught as a contradiction
    assert len(assessment.conflicts) == 1
    conflict = assessment.conflicts[0]
    assert conflict.conflict_type == "STATUS_CONTRADICTION"
    assert conflict.source_a == "EML-VEND-1"
    assert conflict.source_b == "PRJ-LOG-2"
    # Confidence should be penalized due to conflict
    assert assessment.confidence <= 0.70


def test_guard_resolved_enforces_verified_proof_and_evidence_ids():
    """
    Ensures CommitmentStateMachine._guard_resolved prevents transition to RESOLVED
    if verification result is missing, unverified, or lacks evidence IDs.
    """
    com = Commitment(
        id="com_guard_test",
        title="Guard Test Commitment",
        description="Testing _guard_resolved invariants",
        promisor=Party(name="Vendor"),
        promisee=Party(name="Northstar"),
        status=CommitmentStatus.VERIFYING,
    )

    # 1. No verification result
    with pytest.raises(GuardConditionFailedError) as exc:
        CommitmentStateMachine.transition(
            commitment=com,
            target_state=CommitmentStatus.RESOLVED,
            agent_name="Test",
            reason="Attempt resolution",
        )
    assert "No verification result recorded" in str(exc.value)

    # 2. Verification result with is_verified = False
    com.verification_result = VerificationResult(
        commitment_id=com.id,
        action_succeeded=True,
        business_outcome_verified=False,
        is_verified=False,
        rationale="Awaiting counterparty reply",
        evidence_ids=[],
    )
    with pytest.raises(GuardConditionFailedError) as exc:
        CommitmentStateMachine.transition(
            commitment=com,
            target_state=CommitmentStatus.RESOLVED,
            agent_name="Test",
            reason="Attempt resolution",
        )
    assert "Cannot resolve commitment without verified outcome" in str(exc.value)

    # 3. Verification result with is_verified = True but empty evidence_ids
    com.verification_result.is_verified = True
    com.verification_result.business_outcome_verified = True
    com.verification_result.evidence_ids = []
    with pytest.raises(GuardConditionFailedError) as exc:
        CommitmentStateMachine.transition(
            commitment=com,
            target_state=CommitmentStatus.RESOLVED,
            agent_name="Test",
            reason="Attempt resolution",
        )
    assert "without corroborating evidence IDs" in str(exc.value)

    # 4. Valid verification result with non-empty evidence IDs succeeds
    com.verification_result.evidence_ids = ["EML-SIGNED-DOC-1"]
    resolved = CommitmentStateMachine.transition(
        commitment=com,
        target_state=CommitmentStatus.RESOLVED,
        agent_name="Test",
        reason="Outcome verified with proof",
    )
    assert resolved.status == CommitmentStatus.RESOLVED
    assert resolved.resolution_timestamp is not None


def test_escalated_cannot_transition_directly_to_resolved():
    """
    Ensures ESCALATED commitments cannot bypass verification to enter RESOLVED directly.
    """
    com = Commitment(
        id="com_escalated_test",
        title="Escalated Test Commitment",
        description="Testing state machine graph",
        promisor=Party(name="Vendor"),
        promisee=Party(name="Northstar"),
        status=CommitmentStatus.ESCALATED,
    )
    with pytest.raises(InvalidStateTransitionError):
        CommitmentStateMachine.transition(
            commitment=com,
            target_state=CommitmentStatus.RESOLVED,
            agent_name="Test",
            reason="Illegal bypass",
        )


@pytest.mark.asyncio
async def test_sqlite_persistence_restart_preserves_obligation_direction_and_state(tmp_path):
    """
    Ensures SQLiteCommitmentRepository preserves obligation_direction (e.g. WE_OWE_THEM),
    evidence assessment, and verification results across database restart/reloads.
    """
    db_file = tmp_path / "restart_test.db"

    # Session 1: Create and save commitment with WE_OWE_THEM
    repo1 = SQLiteCommitmentRepository(db_file)
    await repo1.initialize()

    com = Commitment(
        id="com_persist_restart",
        title="Deliverable Owed to Client",
        description="Northstar owes deliverable to Client",
        obligation_direction=ObligationDirection.WE_OWE_THEM,
        promisor=Party(name="Alex North", organization="Northstar Studio"),
        promisee=Party(name="Sarah Jenkins", organization="Meridian Global"),
        status=CommitmentStatus.ACTIVE,
        risk=RiskLevel.MEDIUM,
        tags=["design", "milestone"],
    )
    await repo1.save(com)

    # Session 2: Fresh repository instance representing application restart
    repo2 = SQLiteCommitmentRepository(db_file)
    await repo2.initialize()

    loaded = await repo2.get_by_id("com_persist_restart")
    assert loaded is not None
    assert loaded.id == "com_persist_restart"
    # Invariant check: obligation_direction must NOT reset to default THEY_OWE_US!
    assert loaded.obligation_direction == ObligationDirection.WE_OWE_THEM
    assert loaded.promisor.name == "Alex North"
    assert loaded.promisee.name == "Sarah Jenkins"


@pytest.mark.asyncio
async def test_atlas_full_positive_path_lifecycle(tmp_path):
    """
    Phase 9 Scenario Validation: Full Atlas Positive Path
    DISCOVERED -> CORROBORATED/GAP -> HIGH RISK -> REMEDIATION PROPOSAL ->
    POLICY APPROVAL REQUIRED -> APPROVED -> DISPATCHED/VERIFYING ->
    FRESH COUNTERPARTY EVIDENCE (T > T_exec) -> VERIFICATION GATE -> RESOLVED (VERIFIED)
    """
    from covenant.agents.supervisor import SupervisorAgent
    from covenant.orchestration.background_monitor import BackgroundMonitor

    db_file = tmp_path / "atlas_pos.db"
    repo = SQLiteCommitmentRepository(db_file)
    await repo.initialize()

    supervisor = SupervisorAgent(
        commitment_repo=repo,
        event_repo=repo,
    )

    # 1. Discover & establish initial Atlas obligation
    ctx = AgentContext(session_id="atlas_pos_init")
    await supervisor.run(ctx)

    atlas = await repo.get_by_id("com_atlas_approval")
    assert atlas is not None
    assert atlas.risk == RiskLevel.HIGH
    assert atlas.evidence_assessment is not None
    assert atlas.evidence_assessment.is_blocking_downstream is True
    assert len(atlas.evidence_assessment.corroborations) >= 1
    assert len(atlas.evidence_assessment.evidence_gaps) >= 1
    assert atlas.status == CommitmentStatus.AWAITING_APPROVAL
    assert atlas.next_action is not None
    assert atlas.next_action.requires_human_approval is True

    # 2. Human approval and runtime execution dispatch
    atlas.next_action.status = ActionStatus.APPROVED
    atlas.next_action.decided_at = utc_now()
    CommitmentStateMachine.transition(
        commitment=atlas,
        target_state=CommitmentStatus.EXECUTING,
        agent_name="HumanUser",
        reason="Human approved follow-up email",
    )
    atlas.next_action.status = ActionStatus.COMPLETED
    atlas.next_action.executed_at = utc_now()
    CommitmentStateMachine.transition(
        commitment=atlas,
        target_state=CommitmentStatus.VERIFYING,
        agent_name="System",
        reason="Action dispatched; awaiting counterparty verification",
    )
    await repo.save(atlas)

    # 3. Before fresh reply arrives, verification check must NOT resolve
    verif_res_1 = await supervisor.verify_commitment("com_atlas_approval")
    assert verif_res_1.data["is_verified"] is False
    atlas_verifying = await repo.get_by_id("com_atlas_approval")
    assert atlas_verifying.status == CommitmentStatus.VERIFYING

    # 4. Simulate fresh external counterparty reply (T_proof > T_exec)
    workspace_store.simulate_client_reply("com_atlas_approval", fulfilled=True)

    # 5. VerificationGate evaluates fresh proof -> transitions to RESOLVED
    verif_res_2 = await supervisor.verify_commitment("com_atlas_approval")
    assert verif_res_2.data["is_verified"] is True
    assert len(verif_res_2.data["evidence_ids"]) >= 1

    final_atlas = await repo.get_by_id("com_atlas_approval")
    assert final_atlas.status == CommitmentStatus.RESOLVED
    assert final_atlas.resolution_timestamp is not None
    assert final_atlas.verification_result.is_verified is True


@pytest.mark.asyncio
async def test_atlas_execution_without_fulfillment_never_resolves(tmp_path):
    """
    Phase 9 Scenario Validation: Negative Path
    Execution succeeds, but fulfillment evidence does not arrive.
    The commitment MUST remain in VERIFYING (or FAILED if rejected), and NEVER RESOLVED.
    """
    from covenant.agents.supervisor import SupervisorAgent

    db_file = tmp_path / "atlas_neg_timeout.db"
    repo = SQLiteCommitmentRepository(db_file)
    await repo.initialize()

    supervisor = SupervisorAgent(
        commitment_repo=repo,
        event_repo=repo,
    )

    ctx = AgentContext(session_id="atlas_neg_init")
    await supervisor.run(ctx)

    atlas = await repo.get_by_id("com_atlas_approval")
    assert atlas is not None

    # Simulate approval and dispatch
    atlas.next_action.status = ActionStatus.APPROVED
    atlas.next_action.decided_at = utc_now()
    CommitmentStateMachine.transition(atlas, CommitmentStatus.EXECUTING, "HumanUser", "Approved")
    atlas.next_action.status = ActionStatus.COMPLETED
    atlas.next_action.executed_at = utc_now()
    CommitmentStateMachine.transition(atlas, CommitmentStatus.VERIFYING, "System", "Dispatched")
    await repo.save(atlas)

    # Run verification multiple times with NO reply arriving
    for i in range(3):
        res = await supervisor.verify_commitment("com_atlas_approval")
        assert res.data["is_verified"] is False

    reloaded = await repo.get_by_id("com_atlas_approval")
    assert reloaded.status == CommitmentStatus.VERIFYING
    assert reloaded.status != CommitmentStatus.RESOLVED

