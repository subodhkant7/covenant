"""Tests for Evidence-Driven Decision Intelligence in Covenant UI & Trace API."""

from datetime import datetime, timezone
from pathlib import Path
import pytest
import httpx
from fastapi import FastAPI

from covenant.api.routes import (
    router,
    llm as default_llm,
    tools as default_tools,
)
from covenant.agents.evidence import EvidenceAgent
from covenant.agents.supervisor import SupervisorAgent
from covenant.domain.enums import (
    ActionStatus,
    ActionType,
    CommitmentStatus,
    EvidenceSourceType,
    ObligationDirection,
    RiskLevel,
)
from covenant.domain.models import (
    Commitment,
    EvidenceAssessment,
    EvidenceClaim,
    EvidenceConflict,
    EvidenceReference,
    Party,
    ProposedAction,
    VerificationResult,
    utc_now,
)
from covenant.persistence.sqlite_repo import SQLiteCommitmentRepository
from covenant.state_machine.exceptions import InvalidStateTransitionError
from covenant.state_machine.machine import CommitmentStateMachine
from covenant.synthetic_data.store import workspace_store
from covenant_runtime_bridge.bootstrap import CovenantRuntimeBootstrap


@pytest.fixture
async def api_client(tmp_path: Path):
    """Provides an HTTP client connected to an isolated test FastAPI application with initialized DB."""
    test_db = tmp_path / "test_ui_intel.db"
    test_repo = SQLiteCommitmentRepository(db_path=test_db)
    await test_repo.initialize()

    workspace_store.reset()
    test_runtime_env = CovenantRuntimeBootstrap.assemble()

    test_supervisor = SupervisorAgent(
        llm=default_llm,
        tools=default_tools,
        commitment_repo=test_repo,
        event_repo=test_repo,
        runtime_env=test_runtime_env,
    )

    import covenant.api.routes as routes_mod
    orig_repo = routes_mod.repo
    orig_supervisor = routes_mod.supervisor
    orig_runtime_env = routes_mod.runtime_env

    routes_mod.repo = test_repo
    routes_mod.supervisor = test_supervisor
    routes_mod.runtime_env = test_runtime_env

    app = FastAPI()
    app.include_router(router)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client, test_repo, test_runtime_env, test_supervisor

    routes_mod.repo = orig_repo
    routes_mod.supervisor = orig_supervisor
    routes_mod.runtime_env = orig_runtime_env


async def _seed_atlas_with_evidence_intelligence(test_repo):
    """Seed Project Atlas commitment with multi-source evidence synthesis."""
    ev1 = EvidenceReference(
        id="ev_atlas_01",
        commitment_id="com_atlas_approval",
        source_type=EvidenceSourceType.PROJECT,

        source_id="PRJ-ATLAS",
        title="Project Atlas - Phase 2 Deliverable",
        snippet="Phase 2 deliverables submitted Sep 3. Awaiting client formal sign-off. Phase 3 kickoff blocked.",
        confidence=0.98,
        timestamp=datetime(2026, 9, 3, 14, 0, tzinfo=timezone.utc),
    )
    ev2 = EvidenceReference(
        id="ev_atlas_02",
        commitment_id="com_atlas_approval",
        source_type=EvidenceSourceType.EMAIL,
        source_id="INBOX_SCAN",
        title="Meridian Communications Scan",
        snippet="No formal approval email received from Sarah Jenkins after Sep 5 deadline.",
        confidence=0.95,
        timestamp=datetime(2026, 9, 6, 9, 0, tzinfo=timezone.utc),
    )

    action = ProposedAction(
        id="act_atlas_approval",
        commitment_id="com_atlas_approval",
        action_type=ActionType.FOLLOWUP_EMAIL,
        description="Follow up with Meridian Global regarding Phase 2 formal signoff per Section 4.2.",
        recipient="sjenkins@meridianglobal.com",
        subject="Follow-up: Project Atlas Phase 2 Formal Approval",
        payload={"tool": "send_followup", "body": "Hi Sarah, Following up on Phase 2 deliverables."},
        status=ActionStatus.AWAITING_APPROVAL,
        requires_human_approval=True,
        approval_reason="RULE-EXT-COMM: Outbound messages to external clients require approval.",
        risk=RiskLevel.HIGH,
    )

    assessment = EvidenceAssessment(
        finding="Client approval overdue by timeline; Phase 3 frontend implementation blocked.",
        factual_claims=[
            EvidenceClaim(
                source_id="PRJ-ATLAS",
                claim="Phase 2 deliverable formally submitted on Sep 3; Phase 3 kickoff blocked pending client sign-off.",
                is_fact=True,
                relevance="HIGH",
                confidence=0.98,
            ),
            EvidenceClaim(
                source_id="INBOX_SCAN",
                claim="Zero formal approval confirmation or email received from Meridian Global after Sep 5, 2026 deadline.",
                is_fact=True,
                relevance="HIGH",
                confidence=0.95,
            ),
            EvidenceClaim(
                source_id="DERIVED_ANALYSIS",
                claim="Downstream engineering kickoff for Phase 3 is obstructed; counterparty sign-off SLA is breached.",
                is_fact=False,
                relevance="MEDIUM",
                confidence=0.89,
            ),
        ],
        conflicts=[
            EvidenceConflict(
                source_a="PRJ-ATLAS",
                source_b="INBOX_SCAN",
                description="Project Atlas milestone submitted awaiting formal sign-off (blocking Phase 3), but communication records show zero sign-off received after Sep 5 deadline.",
                conflict_type="STATUS_CONTRADICTION",
                severity=RiskLevel.HIGH,
            )
        ],
        confidence=0.96,
        is_blocking_downstream=True,
        recommended_risk=RiskLevel.HIGH,
        rationale="Project records verify deliverable submission on Sep 3, while communications scan confirms absence of promised formal approval by Sep 5.",
    )

    com = Commitment(
        id="com_atlas_approval",
        title="Meridian Global Phase 2 Formal Sign-Off",
        description="Meridian Global (Sarah Jenkins) committed to formal sign-off for Phase 2 deliverables by Sep 5, 2026.",
        promisor=Party(name="Sarah Jenkins", email="sjenkins@meridianglobal.com", organization="Meridian Global"),
        promisee=Party(name="Alex North", email="alex@northstarstudio.com", organization="Northstar Studio"),
        status=CommitmentStatus.AWAITING_APPROVAL,
        risk=RiskLevel.HIGH,
        confidence=0.96,
        due_date=datetime(2026, 9, 5, 17, 0, tzinfo=timezone.utc),
        obligation_direction=ObligationDirection.THEY_OWE_US,
        evidence_references=[ev1, ev2],
        evidence_assessment=assessment,
        next_action=action,
        required_human_approval=True,
        dependencies=["com_atlas_phase3"],
    )
    await test_repo.save(com)
    return com


@pytest.mark.asyncio
async def test_atlas_decision_trace_contains_evidence_intelligence(api_client):
    """
    Asserts that GET /api/commitments/{id}/trace returns structured evidence_assessment
    containing synthesized findings, factual claims, and conflict detection.
    """
    client, repo, runtime_env, supervisor = api_client
    await _seed_atlas_with_evidence_intelligence(repo)

    resp = await client.get("/api/commitments/com_atlas_approval/trace")
    assert resp.status_code == 200
    data = resp.json()

    assert "evidence_assessment" in data
    assessment = data["evidence_assessment"]
    assert assessment is not None
    assert "finding" in assessment
    assert len(assessment["finding"]) > 0
    assert assessment["confidence"] >= 0.85
    assert assessment["is_blocking_downstream"] is True


@pytest.mark.asyncio
async def test_factual_claims_distinguished_from_inferences_in_trace(api_client):
    """
    Verifies that the trace API distinguishes documentary records (is_fact=True)
    from analytical deductions (is_fact=False).
    """
    client, repo, runtime_env, supervisor = api_client
    await _seed_atlas_with_evidence_intelligence(repo)

    resp = await client.get("/api/commitments/com_atlas_approval/trace")
    assert resp.status_code == 200
    data = resp.json()

    assessment = data.get("evidence_assessment")
    assert assessment is not None
    claims = assessment.get("factual_claims", [])
    assert len(claims) >= 2

    facts = [c for c in claims if c.get("is_fact") is True]
    inferences = [c for c in claims if c.get("is_fact") is False]

    assert len(facts) >= 2, "Must contain documentary facts from project tracker and inbox"
    assert len(inferences) >= 1, "Must contain derived analytical inference"

    # Verify fact cites a primary documentary source
    assert any("PRJ" in f["source_id"] for f in facts)
    assert any("INBOX" in f["source_id"] for f in facts)
    # Verify inference is marked as non-factual deduction
    assert any("DERIVED" in inf["source_id"] for inf in inferences)


@pytest.mark.asyncio
async def test_conflict_information_preserved_in_trace(api_client):
    """
    Verifies that cross-source contradictions (e.g. project tracker expecting sign-off vs inbox scan empty)
    are captured, typed, and returned in the trace.
    """
    client, repo, runtime_env, supervisor = api_client
    await _seed_atlas_with_evidence_intelligence(repo)

    resp = await client.get("/api/commitments/com_atlas_approval/trace")
    assert resp.status_code == 200
    data = resp.json()

    assessment = data.get("evidence_assessment")
    assert assessment is not None
    conflicts = assessment.get("conflicts", [])
    assert len(conflicts) >= 1, "Atlas scenario must detect cross-source tension"

    conflict = conflicts[0]
    assert "PRJ-ATLAS" in (conflict["source_a"] + conflict["source_b"])
    assert "INBOX" in (conflict["source_a"] + conflict["source_b"])
    assert conflict["conflict_type"] == "STATUS_CONTRADICTION"
    assert "deadline" in conflict["description"].lower() or "sign-off" in conflict["description"].lower()


@pytest.mark.asyncio
async def test_verification_evidence_distinguishable_from_execution_evidence(api_client):
    """
    Verifies that execution evidence (action dispatch) is fundamentally distinct
    from post-dispatch counterparty fulfillment verification.
    """
    client, repo, runtime_env, supervisor = api_client
    com = await _seed_atlas_with_evidence_intelligence(repo)

    # Move commitment to VERIFYING with executed tool
    com.status = CommitmentStatus.VERIFYING
    com.next_action.status = ActionStatus.COMPLETED
    com.next_action.executed_at = utc_now()
    com.verification_result = VerificationResult(
        commitment_id=com.id,
        is_verified=True,
        rationale="Signed approval document verified from Sarah Jenkins.",
        evidence_ids=["ev_fresh_reply_01"],
    )
    fresh_ev = EvidenceReference(
        id="ev_fresh_reply_01",
        commitment_id=com.id,
        source_type=EvidenceSourceType.EMAIL,
        source_id="EML-ATLAS-REPLY-01",
        title="Meridian Formal Sign-Off Attachment",
        snippet="Signed Phase 2 deliverable approval PDF received.",
        confidence=0.99,
    )
    com.evidence_references.append(fresh_ev)
    await repo.save(com)

    # Fetch trace
    trace_resp = await client.get("/api/commitments/com_atlas_approval/trace")
    assert trace_resp.status_code == 200
    trace = trace_resp.json()

    # 1. Execution block represents runtime action dispatch
    execution = trace["execution"]
    assert execution["status"] == "COMPLETED"

    # 2. Verification block represents independent outcome proof
    verification = trace["verification"]
    assert verification["gate_result"] == "PASSED"
    assert "VerificationGate" in verification["authority"]
    assert len(verification["fresh_evidence"]) >= 1

    # Fresh verification evidence is distinct from execution dispatch
    fresh_source_ids = [fe["source_id"] for fe in verification["fresh_evidence"]]
    assert any("EML-ATLAS-REPLY" in sid or "REPLY" in sid for sid in fresh_source_ids)


@pytest.mark.asyncio
async def test_frontend_cannot_mutate_protected_state(tmp_path):
    """
    Authority boundary: UI clients cannot illegally mark commitments RESOLVED
    or bypass state machine guards.
    """
    db_path = tmp_path / "authority_test.db"
    repo = SQLiteCommitmentRepository(db_path)
    await repo.initialize()

    c = Commitment(
        id="com_ui_security_01",
        title="Unverified Task",
        description="Attempt to resolve without verification.",
        promisor=Party(name="Vendor"),
        promisee=Party(name="Client"),
        status=CommitmentStatus.DISCOVERED,
        risk=RiskLevel.MEDIUM,
    )
    await repo.save(c)

    # State machine strictly forbids jumping from DISCOVERED -> RESOLVED
    with pytest.raises(InvalidStateTransitionError):
        CommitmentStateMachine.transition(
            commitment=c,
            target_state=CommitmentStatus.RESOLVED,
            agent_name="FrontendUI",
            reason="User clicked resolve without VerificationGate.",
        )
