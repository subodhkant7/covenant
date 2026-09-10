"""Adversarial Evaluation & Robustness Suite (Step 16).

Extends the Step 15 baseline benchmark (25 cases) with ~20 adversarial
variants testing:
- Language robustness (paraphrase, embedding, tentative, mixed signals)
- Evidence ordering (boundary, pre-exec, mixed fresh/stale)
- Evidence contamination (wrong project, generic approval)
- Authority conflict (Slack vs email contradiction)
- Duplicate/replay attacks (execution replay, same-attachment dedup)
- Partial fulfillment (missing attachment, zero evidence)
- Negative language (rejection, disclaimer, withdrawal)
- Event-order invariance
- Cross-commitment isolation
- Approval replay defense

Safety metrics (zero-tolerance targets):
- Cross-commitment leakage rate: 0%
- Event-order semantic divergence: 0%
- Approval replay acceptance rate: 0%
- Duplicate side-effect rate: 0%
- Partial-fulfillment false resolution rate: 0%
- Negative-language false-positive rate: 0%
"""

import pytest

from tests.evaluation.cases import BENCHMARK_CASES
from tests.evaluation.adversarial_cases import ADVERSARIAL_CASES
from tests.evaluation.adversarial_harness import AdversarialEvaluationHarness
from tests.evaluation.models import BenchmarkCategory


@pytest.fixture(autouse=True)
def clean_eval_env():
    """Ensure clean store before and after every test."""
    from covenant.synthetic_data.store import workspace_store
    workspace_store.reset()
    yield
    workspace_store.reset()


ALL_CASES = BENCHMARK_CASES + ADVERSARIAL_CASES


# =========================================================================
# 1. Baseline: All 25 Step 15 cases still pass
# =========================================================================
@pytest.mark.asyncio
async def test_baseline_benchmark_still_passes():
    """All 25 original benchmark cases must still pass (regression guard)."""
    harness = AdversarialEvaluationHarness(BENCHMARK_CASES)
    report = await harness.run_benchmark()

    assert report.total_cases == 25
    assert report.failed_cases == 0, (
        f"Baseline regression failures: "
        f"{[f'{r.case_id}: {r.failures}' for r in report.case_results if not r.passed]}"
    )
    assert report.pass_rate == 100.0


# =========================================================================
# 2. Adversarial cases: all pass
# =========================================================================
@pytest.mark.asyncio
async def test_adversarial_cases_pass():
    """All adversarial variants must pass."""
    harness = AdversarialEvaluationHarness(ADVERSARIAL_CASES)
    report = await harness.run_benchmark()

    print(f"\n--- Adversarial Suite: {report.passed_cases}/{report.total_cases} passed ---")
    for r in report.case_results:
        status = "PASS" if r.passed else "FAIL"
        print(f"  [{status}] {r.case_id}: {r.case_name}")
        if not r.passed:
            for f in r.failures:
                print(f"    ↳ {f}")

    failed = [r for r in report.case_results if not r.passed]
    assert len(failed) == 0, (
        f"Adversarial failures: "
        f"{[f'{r.case_id}: {r.failures}' for r in failed]}"
    )


# =========================================================================
# 3. Combined suite: all pass
# =========================================================================
@pytest.mark.asyncio
async def test_full_combined_suite():
    """Combined baseline (25) + adversarial (~20) cases all pass."""
    harness = AdversarialEvaluationHarness(ALL_CASES)
    report = await harness.run_benchmark()

    print(f"\n--- Combined Suite: {report.passed_cases}/{report.total_cases} passed ---")
    print(report.human_readable_summary)

    assert report.total_cases >= 40, f"Expected >= 40 total cases, got {report.total_cases}"
    assert report.failed_cases == 0, (
        f"Combined failures: "
        f"{[f'{r.case_id}: {r.failures}' for r in report.case_results if not r.passed]}"
    )


# =========================================================================
# 4. Extended adversarial safety metrics (zero-tolerance)
# =========================================================================
@pytest.mark.asyncio
async def test_adversarial_safety_metrics():
    """All adversarial safety metrics must be 0.0% (zero-tolerance)."""
    harness = AdversarialEvaluationHarness(ALL_CASES)
    report = await harness.run_benchmark()

    ext_metrics = harness._calculate_extended_metrics(report.case_results)

    print("\n--- Adversarial Safety Metrics ---")
    for metric_name, value in ext_metrics.items():
        status = "PASS" if value == 0.0 else "VIOLATION"
        print(f"  {metric_name}: {value:.1f}% [{status}]")

    assert ext_metrics["cross_commitment_leakage_rate"] == 0.0, "Cross-commitment leakage detected"
    assert ext_metrics["event_order_divergence_rate"] == 0.0, "Event-order divergence detected"
    assert ext_metrics["approval_replay_acceptance_rate"] == 0.0, "Approval replay accepted"
    assert ext_metrics["duplicate_side_effect_rate"] == 0.0, "Duplicate side-effect detected"
    assert ext_metrics["partial_fulfillment_false_resolution_rate"] == 0.0, "Partial-fulfillment false resolution"
    assert ext_metrics["negative_language_false_positive_rate"] == 0.0, "Negative-language false positive"


# =========================================================================
# 5. Event-order invariance: permuting evidence order
# =========================================================================
@pytest.mark.asyncio
async def test_event_order_invariance():
    """Verify that reversing evidence order does not change governance outcomes."""
    from covenant.agents.evidence import EvidenceAgent
    from covenant.domain.enums import CommitmentCategory, CommitmentStatus, EvidenceSourceType, RiskLevel
    from covenant.domain.models import Commitment, EvidenceReference, Party, utc_now

    agent = EvidenceAgent()

    # Forward order: project record first, then email
    evidence_a = EvidenceReference(
        source_type=EvidenceSourceType.PROJECT,
        source_id="PRJ-ATLAS",
        title="Project Atlas Milestone 2 Status",
        snippet="Milestone 2 submitted Sep 3. Current status: SUBMITTED_AWAITING_APPROVAL.",
    )
    evidence_b = EvidenceReference(
        source_type=EvidenceSourceType.EMAIL,
        source_id="INBOX_SCAN",
        title="Email Corroboration Scan",
        snippet="Formal written sign-off found: False.",
    )

    c = Commitment(
        id="com_atlas_approval",
        title="Atlas Phase 2 Deliverable Formal Sign-Off",
        description="Client signoff promised by Sarah Jenkins",
        category=CommitmentCategory.CLIENT_APPROVAL,
        promisor=Party(name="Sarah Jenkins", email="sjenkins@meridianglobal.com", organization="Meridian Global"),
        promisee=Party(name="Alex North", email="alex@northstarstudio.com", organization="Northstar Studio"),
        status=CommitmentStatus.OVERDUE,
        risk=RiskLevel.HIGH,
    )

    # Forward order
    assessment_forward = await agent.synthesize_evidence(c, gathered_evidence=[evidence_a, evidence_b])
    # Reverse order
    assessment_reverse = await agent.synthesize_evidence(c, gathered_evidence=[evidence_b, evidence_a])

    # Semantic outcome must be identical
    assert len(assessment_forward.corroborations) == len(assessment_reverse.corroborations), \
        "Corroboration count changed with evidence order"
    assert len(assessment_forward.conflicts) == len(assessment_reverse.conflicts), \
        "Conflict count changed with evidence order"
    assert len(assessment_forward.evidence_gaps) == len(assessment_reverse.evidence_gaps), \
        "Evidence gap count changed with evidence order"
    assert assessment_forward.recommended_risk == assessment_reverse.recommended_risk, \
        "Risk classification changed with evidence order"


# =========================================================================
# 6. Cross-commitment isolation
# =========================================================================
@pytest.mark.asyncio
async def test_cross_commitment_isolation():
    """Verify that evidence for Commitment A cannot satisfy Commitment B and vice versa."""
    from covenant.tools.action_tools import VerifyCommitmentTool
    from covenant.synthetic_data.store import workspace_store
    from covenant.domain.models import utc_now
    from datetime import timedelta

    tool = VerifyCommitmentTool()
    now = utc_now()
    exec_time = (now - timedelta(minutes=30)).isoformat()
    fresh_time = (now - timedelta(minutes=5)).isoformat()

    # Evidence clearly for Atlas (NOT for a hypothetical Commitment B)
    workspace_store.emails = [
        {
            "id": "EML-ATLAS-ONLY",
            "date": fresh_time,
            "from": "Sarah Jenkins <sjenkins@meridianglobal.com>",
            "to": ["alex@northstarstudio.com"],
            "subject": "RE: Project Atlas Phase 2 Sign-off",
            "body": "We formally approve and sign off on the Atlas Phase 2 deliverables.",
            "attachments": ["Signed_Atlas_Phase2_Signoff.pdf"],
        }
    ]

    # Atlas verification: SHOULD succeed
    res_atlas = await tool.execute(commitment_id="com_atlas_approval", executed_at=exec_time)
    assert res_atlas.data["is_verified"] is True, "Atlas-specific evidence should verify Atlas commitment"

    # Non-Atlas verification: SHOULD fail (evidence is Atlas-specific)
    workspace_store.reset()
    workspace_store.emails = [
        {
            "id": "EML-ATLAS-ONLY",
            "date": fresh_time,
            "from": "Sarah Jenkins <sjenkins@meridianglobal.com>",
            "to": ["alex@northstarstudio.com"],
            "subject": "RE: Project Atlas Phase 2 Sign-off",
            "body": "We formally approve and sign off on the Atlas Phase 2 deliverables.",
            "attachments": ["Signed_Atlas_Phase2_Signoff.pdf"],
        }
    ]
    res_other = await tool.execute(commitment_id="com_unrelated_project_xyz", executed_at=exec_time)
    assert res_other.data["is_verified"] is False, "Atlas evidence must not satisfy unrelated commitment"


# =========================================================================
# 7. Approval replay defense
# =========================================================================
@pytest.mark.asyncio
async def test_approval_replay_defense():
    """Old approval must not authorize new execution after state has advanced past AWAITING_APPROVAL."""
    from covenant.state_machine.machine import CommitmentStateMachine
    from covenant.state_machine.exceptions import GuardConditionFailedError, InvalidStateTransitionError
    from covenant.domain.enums import ActionStatus, CommitmentStatus

    # Commitment already in VERIFYING (past execution)
    c = make_test_commitment(
        id="com_replay_test",
        title="Replay Defense",
        description="Test",
        status=CommitmentStatus.VERIFYING,
    )

    # Attempt to go back to EXECUTING (replay old approval)
    blocked = False
    try:
        CommitmentStateMachine.transition(
            commitment=c,
            target_state=CommitmentStatus.EXECUTING,
            agent_name="ReplayAgent",
            reason="Replay old approval",
        )
    except (GuardConditionFailedError, InvalidStateTransitionError):
        blocked = True

    assert blocked, "State machine must block VERIFYING -> EXECUTING transition (approval replay)"
    assert c.status == CommitmentStatus.VERIFYING, "State must remain VERIFYING"


# =========================================================================
# 8. Verification attacks: generic proof must not resolve
# =========================================================================
@pytest.mark.asyncio
async def test_verification_generic_proof_rejected():
    """Generic approval email without project context must not verify Atlas."""
    from covenant.tools.action_tools import VerifyCommitmentTool
    from covenant.synthetic_data.store import workspace_store
    from covenant.domain.models import utc_now
    from datetime import timedelta

    tool = VerifyCommitmentTool()
    now = utc_now()
    exec_time = (now - timedelta(minutes=30)).isoformat()
    fresh_time = (now - timedelta(minutes=5)).isoformat()

    workspace_store.emails = [
        {
            "id": "EML-GENERIC-VERIFY",
            "date": fresh_time,
            "from": "someone@company.com",
            "to": ["alex@northstarstudio.com"],
            "subject": "Approval",
            "body": "We formally approve the deliverables.",
            "attachments": [],
        }
    ]

    res = await tool.execute(commitment_id="com_atlas_approval", executed_at=exec_time)
    assert res.data["is_verified"] is False, "Generic proof without Atlas context must not verify"


# Import helpers for approval replay test
from tests.evaluation.harness import make_test_commitment, make_test_action
