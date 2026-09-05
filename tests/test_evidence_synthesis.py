"""Tests for EvidenceAgent multi-source synthesis and conflict detection (Step 10).

Verifies that EvidenceAgent:
1. Synthesizes cross-source evidence into structured claims and conflicts.
2. Accurately distinguishes documentary facts from analytical inferences.
3. Detects tensions (e.g. project milestone awaiting approval vs no sign-off in inbox).
4. Maintains raw evidence provenance and emits auditable conflict events.
5. Operates within strict authority boundaries (cannot self-resolve commitments).
"""

from datetime import datetime, timezone
from pathlib import Path
import pytest

from covenant.agents.base import AgentContext
from covenant.agents.evidence import EvidenceAgent
from covenant.domain.enums import CommitmentStatus, EvidenceSourceType, RiskLevel
from covenant.domain.models import (
    Commitment,
    EvidenceAssessment,
    EvidenceClaim,
    EvidenceConflict,
    EvidenceReference,
    Party,
)
from covenant.llm.ollama_provider import DeterministicFallbackProvider
from covenant.llm.provider import ChatMessage
from covenant.persistence.sqlite_repo import SQLiteCommitmentRepository
from covenant.synthetic_data.store import workspace_store
from covenant.tools import initialize_tools


@pytest.fixture
def clean_workspace():
    workspace_store.reset()
    yield workspace_store
    workspace_store.reset()


@pytest.fixture
async def isolated_repo(tmp_path: Path):
    db_file = tmp_path / "test_evidence.db"
    repo = SQLiteCommitmentRepository(db_path=db_file)
    await repo.initialize()
    return repo


@pytest.fixture
def tools():
    return initialize_tools()


@pytest.fixture
def evidence_agent(tools, isolated_repo):
    return EvidenceAgent(tools=tools, commitment_repo=isolated_repo, event_repo=isolated_repo)


@pytest.mark.asyncio
async def test_atlas_evidence_synthesis_and_corroboration(clean_workspace, isolated_repo, evidence_agent):
    """Verify that EvidenceAgent synthesizes Atlas evidence, corroborates records, detects evidence gaps, and avoids false contradictions."""
    # Seed Atlas commitment
    atlas_com = Commitment(
        id="com_atlas_approval",
        title="Meridian Global Phase 2 Deliverable Formal Sign-Off",
        description="Sarah Jenkins promised formal written sign-off by Friday, Sep 5.",
        promisor=Party(name="Sarah Jenkins", organization="Meridian Global Corp", role="PROMISOR"),
        promisee=Party(name="Alex North", organization="Northstar Studio", role="PROMISEE"),
        due_date=datetime(2026, 9, 5, 17, 0, tzinfo=timezone.utc),
        status=CommitmentStatus.ACTIVE,
        evidence_references=[
            EvidenceReference(
                source_type=EvidenceSourceType.EMAIL,
                source_id="EML-102",
                title="Promise Email",
                snippet="We will provide formal sign-off by Sep 5.",
            )
        ],
    )
    await isolated_repo.save(atlas_com)

    context = AgentContext(
        session_id="sess_atlas_evidence",
        target_commitment_id="com_atlas_approval",
        parameters={"effective_time": "2026-09-06T12:00:00Z"},
    )

    result = await evidence_agent.run(context)
    assert result.success is True

    # Retrieve updated commitment
    updated = await isolated_repo.get_by_id("com_atlas_approval")
    assert updated is not None
    assert updated.evidence_assessment is not None
    assert updated.risk == RiskLevel.HIGH

    assessment: EvidenceAssessment = updated.evidence_assessment
    assert "overdue" in assessment.finding.lower()
    assert assessment.is_blocking_downstream is True
    assert assessment.confidence >= 0.90

    # Verify factual claims vs inferences
    assert len(assessment.factual_claims) >= 3
    prj_claim = next((c for c in assessment.factual_claims if c.source_id == "PRJ-ATLAS"), None)
    assert prj_claim is not None
    assert prj_claim.is_fact is True
    assert "Milestone 2" in prj_claim.claim

    # Verify semantic correctness: Corroboration and Evidence Gap, NOT false contradiction
    assert len(assessment.corroborations) >= 1
    assert "corroborate" in assessment.corroborations[0].lower()
    assert len(assessment.evidence_gaps) >= 1
    assert "absent" in assessment.evidence_gaps[0].lower() or "missing" in assessment.evidence_gaps[0].lower()
    assert assessment.conflicts == []  # PRJ-ATLAS and INBOX_SCAN agree sign-off is pending

    # Verify audit events recorded
    events = await isolated_repo.list_events(commitment_id="com_atlas_approval")
    synth_events = [e for e in events if e.action_name == "SYNTHESIZE_EVIDENCE"]
    assert len(synth_events) >= 1


@pytest.mark.asyncio
async def test_apex_evidence_synthesis_genuine_contradiction(clean_workspace, isolated_repo, evidence_agent):
    """Verify that genuine contradictory evidence (promised complete vs held invoice / machine error) is captured as a contradiction."""
    apex_com = Commitment(
        id="com_apex_repair",
        title="Apex Industrial CNC Laser Head Calibration & Repair",
        description="Marcus Vance guaranteed laser head calibration complete by Sep 2.",
        promisor=Party(name="Marcus Vance", organization="Apex Industrial Repairs", role="PROMISOR"),
        promisee=Party(name="Alex North", organization="Northstar Studio", role="PROMISEE"),
        due_date=datetime(2026, 9, 2, 18, 0, tzinfo=timezone.utc),
        status=CommitmentStatus.ACTIVE,
        evidence_references=[
            EvidenceReference(
                source_type=EvidenceSourceType.EMAIL,
                source_id="EML-201",
                title="Repair Promise",
                snippet="Repair 100% complete and tested by Sep 2 EOD.",
            )
        ],
    )
    await isolated_repo.save(apex_com)

    context = AgentContext(
        session_id="sess_apex_evidence",
        target_commitment_id="com_apex_repair",
    )
    result = await evidence_agent.run(context)
    assert result.success is True

    updated = await isolated_repo.get_by_id("com_apex_repair")
    assert updated is not None
    assert updated.evidence_assessment is not None
    assert len(updated.evidence_assessment.conflicts) >= 1

    conflict = updated.evidence_assessment.conflicts[0]
    assert conflict.source_a == "EML-201"
    assert conflict.source_b == "INV-APEX-992"
    assert conflict.conflict_type == "STATUS_CONTRADICTION"
    assert conflict.severity == RiskLevel.HIGH

    events = await isolated_repo.list_events(commitment_id="com_apex_repair")
    conflict_events = [e for e in events if e.action_name == "EVIDENCE_CONFLICT_DETECTED"]
    assert len(conflict_events) >= 1


@pytest.mark.asyncio
async def test_distinguish_factual_claims_vs_inference(evidence_agent):
    """Verify that documentary records are tagged as facts and analytical claims as inferences."""
    commitment = Commitment(
        id="com_test_claims",
        title="Test Commitment",
        description="Testing claim classification",
        promisor=Party(name="Test Partner", role="PROMISOR"),
        promisee=Party(name="Alex North", role="PROMISEE"),
    )
    gathered = [
        EvidenceReference(
            source_type=EvidenceSourceType.PROJECT,
            source_id="PRJ-ATLAS",
            title="Project Milestone",
            snippet="Milestone 2 submitted Sep 3. Current status: SUBMITTED_AWAITING_APPROVAL.",
        ),
        EvidenceReference(
            source_type=EvidenceSourceType.EMAIL,
            source_id="EML-102",
            title="Confirmation Email",
            snippet="Sign-off promised by Sep 5.",
        ),
    ]
    assessment = await evidence_agent.synthesize_evidence(commitment, gathered)
    factual = [c for c in assessment.factual_claims if c.is_fact]
    inferred = [c for c in assessment.factual_claims if not c.is_fact]

    assert len(factual) >= 2
    assert all(f.source_id in ["PRJ-ATLAS", "EML-102", "INBOX_SCAN", "DOC-001"] for f in factual)
    if inferred:
        assert any("DERIVED" in inf.source_id or not inf.is_fact for inf in inferred)


@pytest.mark.asyncio
async def test_ambiguous_or_insufficient_evidence(evidence_agent):
    """Verify synthesis gracefully handles non-conflicting, insufficient evidence."""
    commitment = Commitment(
        id="com_minimal",
        title="Minimal Commitment",
        description="No blocking issues present",
        promisor=Party(name="Generic Vendor", role="PROMISOR"),
        promisee=Party(name="Alex North", role="PROMISEE"),
    )
    gathered = [
        EvidenceReference(
            source_type=EvidenceSourceType.EMAIL,
            source_id="DOC-999",
            title="General Note",
            snippet="Project scope overview document provided for review.",
            confidence=0.85,
        )
    ]
    assessment = await evidence_agent.synthesize_evidence(commitment, gathered)
    assert assessment.conflicts == []
    assert assessment.is_blocking_downstream is False
    assert assessment.recommended_risk == RiskLevel.LOW


@pytest.mark.asyncio
async def test_evidence_agent_cannot_self_resolve(isolated_repo, evidence_agent):
    """Authority regression: EvidenceAgent cannot transition commitment to RESOLVED."""
    com = Commitment(
        id="com_authority_check",
        title="Fulfillable Commitment",
        description="Testing authority boundary",
        promisor=Party(name="Partner", role="PROMISOR"),
        promisee=Party(name="Alex North", role="PROMISEE"),
        status=CommitmentStatus.ACTIVE,
    )
    await isolated_repo.save(com)

    context = AgentContext(
        session_id="sess_authority",
        target_commitment_id="com_authority_check",
    )
    await evidence_agent.run(context)

    updated = await isolated_repo.get_by_id("com_authority_check")
    assert updated is not None
    # State cannot be RESOLVED; EvidenceAgent has no authority to close/resolve commitments
    assert updated.status != CommitmentStatus.RESOLVED


@pytest.mark.asyncio
async def test_evidence_agent_fallback_provider():
    """Verify that DeterministicFallbackProvider generates valid structured EvidenceAssessment."""
    provider = DeterministicFallbackProvider()
    response = await provider.chat(
        [ChatMessage(role="user", content="Synthesize evidence for Atlas commitment with PRJ-ATLAS and EML-102.")],
        json_mode=True,
    )
    assert response is not None
    import json
    data = json.loads(response.content)
    assessment = EvidenceAssessment.model_validate(data)
    assert assessment.finding != ""
    assert len(assessment.factual_claims) > 0
    assert assessment.confidence >= 0.85
