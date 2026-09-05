"""Tests for Evidence-Driven Decision Intelligence, Semantic Correctness, and Demo Integrity in Covenant UI & Trace API."""

from datetime import datetime, timezone
from pathlib import Path
import re
import pytest
import httpx
from fastapi import FastAPI

from covenant.api.routes import (
    router,
    llm as default_llm,
    tools as default_tools,
)
from covenant.agents.base import AgentContext
from covenant.agents.evidence import EvidenceAgent
from covenant.agents.supervisor import SupervisorAgent
from covenant.agents.verification import VerificationAgent
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
    """Seed Project Atlas commitment with multi-source evidence synthesis, corroboration, and evidence gap."""
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
                claim="Formal sign-off SLA breached; Phase 3 engineering kickoff blocked on client approval.",
                is_fact=False,
                relevance="HIGH",
                confidence=0.92,
            ),
        ],
        conflicts=[],  # Corroborating sources must NOT be mislabeled as contradictions
        corroborations=[
            "PRJ-ATLAS and INBOX_SCAN independently corroborate that Phase 2 was submitted and formal sign-off remains unreceived."
        ],
        evidence_gaps=[
            "Formal written sign-off email from Sarah Jenkins (promised for Sep 5 at 5 PM EST per EML-102) is absent from inbox records."
        ],
        confidence=0.96,
        is_blocking_downstream=True,
        recommended_risk=RiskLevel.HIGH,
        rationale="Project records and inbox scan corroborate deliverable submission on Sep 3 with absence of promised sign-off by Sep 5. Downstream Phase 3 engineering kickoff is blocked.",
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
    containing synthesized findings, factual claims, corroborations, and evidence gaps.
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

    assert any("PRJ" in f["source_id"] for f in facts)
    assert any("INBOX" in f["source_id"] for f in facts)
    assert any("DERIVED" in inf["source_id"] for inf in inferences)


@pytest.mark.asyncio
async def test_corroboration_and_evidence_gaps_distinguished_from_contradiction_in_trace(api_client):
    """
    Verifies that compatible sources (PRJ-ATLAS awaiting sign-off + INBOX_SCAN empty) are categorized
    as corroboration and evidence gap rather than falsely labeled as a contradiction.
    """
    client, repo, runtime_env, supervisor = api_client
    await _seed_atlas_with_evidence_intelligence(repo)

    resp = await client.get("/api/commitments/com_atlas_approval/trace")
    assert resp.status_code == 200
    data = resp.json()

    assessment = data.get("evidence_assessment")
    assert assessment is not None

    # Corroboration captured
    corroborations = assessment.get("corroborations", [])
    assert len(corroborations) >= 1
    assert "corroborate" in corroborations[0].lower()

    # Evidence gap captured
    gaps = assessment.get("evidence_gaps", [])
    assert len(gaps) >= 1
    assert "absent" in gaps[0].lower() or "missing" in gaps[0].lower()

    # Compatible records are NOT mislabeled as contradictions
    conflicts = assessment.get("conflicts", [])
    assert len(conflicts) == 0


@pytest.mark.asyncio
async def test_genuine_contradiction_preserved_in_trace(api_client):
    """
    Verifies that genuine contradictions (e.g. promised repair complete vs invoice held with machine error)
    are strictly captured as contradictions.
    """
    client, repo, runtime_env, supervisor = api_client

    apex_assessment = EvidenceAssessment(
        finding="Repair incomplete past Sep 2 commitment date; fabrication workshop remains blocked.",
        conflicts=[
            EvidenceConflict(
                source_a="EML-201",
                source_b="INV-APEX-992",
                description="Repair completion promised for Sep 2, but invoice held and machine telemetry indicates unresolved error E-402.",
                conflict_type="STATUS_CONTRADICTION",
                severity=RiskLevel.HIGH,
            )
        ],
        is_blocking_downstream=True,
        recommended_risk=RiskLevel.HIGH,
    )
    apex_com = Commitment(
        id="com_apex_repair",
        title="Apex Industrial CNC Laser Head Calibration & Repair",
        description="Marcus Vance guaranteed laser head calibration complete by Sep 2.",
        promisor=Party(name="Marcus Vance", organization="Apex Industrial Repairs", role="PROMISOR"),
        promisee=Party(name="Alex North", organization="Northstar Studio", role="PROMISEE"),
        status=CommitmentStatus.OVERDUE,
        risk=RiskLevel.HIGH,
        evidence_assessment=apex_assessment,
    )
    await repo.save(apex_com)

    resp = await client.get("/api/commitments/com_apex_repair/trace")
    assert resp.status_code == 200
    data = resp.json()

    assessment = data.get("evidence_assessment")
    assert assessment is not None
    conflicts = assessment.get("conflicts", [])
    assert len(conflicts) == 1
    assert conflicts[0]["conflict_type"] == "STATUS_CONTRADICTION"
    assert "error" in conflicts[0]["description"].lower() or "invoice" in conflicts[0]["description"].lower()


@pytest.mark.asyncio
async def test_atlas_risk_and_downstream_blocking_consistent_across_surfaces(api_client):
    """
    Ensures Atlas risk is HIGH and downstream blocking state is consistently represented
    across commitment API, decision trace API, and decisions surface.
    """
    client, repo, runtime_env, supervisor = api_client
    await _seed_atlas_with_evidence_intelligence(repo)

    # 1. Commitment API
    com_resp = await client.get("/api/commitments/com_atlas_approval")
    assert com_resp.status_code == 200
    com_data = com_resp.json()
    assert com_data["risk"] == "HIGH"
    assert com_data["evidence_assessment"]["is_blocking_downstream"] is True

    # 2. Trace API
    trace_resp = await client.get("/api/commitments/com_atlas_approval/trace")
    assert trace_resp.status_code == 200
    trace_data = trace_resp.json()
    assert trace_data["current_risk"] == "HIGH"
    assert trace_data["risk"]["risk_level"] == "HIGH"
    # Must NOT claim "No downstream dependencies blocked" when evidence assessment proves downstream work is blocked
    assert "No downstream dependencies blocked" not in trace_data["risk"]["blocking_impact"]
    assert "Phase 3" in trace_data["risk"]["blocking_impact"] or "blocked" in trace_data["risk"]["blocking_impact"].lower()

    # 3. Decision Surface
    dec_resp = await client.get("/api/decisions")
    assert dec_resp.status_code == 200
    decisions = dec_resp.json()
    atlas_dec = next((d for d in decisions if d["commitment_id"] == "com_atlas_approval"), None)
    assert atlas_dec is not None
    assert atlas_dec["risk"] == "HIGH"


def test_decision_trace_heading_is_not_misleadingly_verified():
    """
    Regression test: Ensures UI code does not claim all 10 sequence stages are 'Verified'.
    Labels sequence accurately as 'Decision Stages' or 'Lifecycle Sequence'.
    """
    detail_path = Path(__file__).resolve().parent.parent / "frontend" / "src" / "components" / "CommitmentDetail.jsx"
    assert detail_path.exists()
    content = detail_path.read_text()

    # Must NOT contain "10 Verified Stages"
    assert "10 Verified Stages" not in content
    # Must contain accurate label
    assert "Decision Stages" in content or "Lifecycle Stages" in content


@pytest.mark.asyncio
async def test_verification_attempt_telemetry_numbering(tmp_path):
    """
    Verifies that autonomous verification monitoring cycles emit attempt numbers
    to clearly show structured monitoring attempts rather than runaway duplicate events.
    """
    db_path = tmp_path / "test_telemetry.db"
    isolated_repo = SQLiteCommitmentRepository(db_path)
    await isolated_repo.initialize()

    from covenant.tools import initialize_tools
    tools = initialize_tools()
    com = Commitment(
        id="com_verif_telemetry",
        title="Telemetry Verification Test",
        description="Testing verification attempt count",
        promisor=Party(name="Test Promisor"),
        promisee=Party(name="Alex North"),
        status=CommitmentStatus.VERIFYING,
        risk=RiskLevel.HIGH,
    )
    await isolated_repo.save(com)

    v_agent = VerificationAgent(tools=tools, commitment_repo=isolated_repo, event_repo=isolated_repo)
    ctx = AgentContext(session_id="verif_cycle_1", target_commitment_id="com_verif_telemetry")

    # Pass 1: Attempt #1
    await v_agent.run(ctx)
    events_1 = await isolated_repo.list_events(commitment_id="com_verif_telemetry")
    v_events_1 = [e for e in events_1 if e.action_name == "VERIFY_RESOLUTION"]
    assert len(v_events_1) == 1
    assert "check #1" in v_events_1[0].summary.lower()
    assert v_events_1[0].metadata.get("attempt_number") == 1

    # Pass 2: Attempt #2
    await v_agent.run(ctx)
    events_2 = await isolated_repo.list_events(commitment_id="com_verif_telemetry")
    v_events_2 = [e for e in events_2 if e.action_name == "VERIFY_RESOLUTION"]
    assert len(v_events_2) == 2
    # list_events returns in DESC order: index 0 is newest (attempt 2), index 1 is oldest (attempt 1)
    assert "check #2" in v_events_2[0].summary.lower()
    assert v_events_2[0].metadata.get("attempt_number") == 2
    assert "check #1" in v_events_2[1].summary.lower()
    assert v_events_2[1].metadata.get("attempt_number") == 1


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
