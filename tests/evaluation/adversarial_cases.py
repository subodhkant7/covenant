"""Adversarial & Robustness Benchmark Scenarios (Step 16).

Extends the Step 15 baseline with ~20 adversarial variants covering:
A. Language Robustness
B. Evidence Ordering
C. Evidence Contamination
D. Authority Conflict
E. Duplicate / Replay Attacks
F. Partial Fulfillment
G. Negative Language
"""

from typing import List

from covenant.domain.enums import (
    ActionType,
    CommitmentCategory,
    CommitmentStatus,
    ObligationDirection,
    PolicyDecisionType,
    RiskLevel,
    StatementType,
)
from tests.evaluation.models import BenchmarkCase, BenchmarkCategory, ExpectedOutcome


ADVERSARIAL_CASES: List[BenchmarkCase] = [
    # =========================================================================
    # A. LANGUAGE ROBUSTNESS
    # =========================================================================
    BenchmarkCase(
        id="ADV-LANG-01",
        name="Commitment paraphrased with different wording",
        category=BenchmarkCategory.COMMITMENT_UNDERSTANDING,
        description="Same obligation as BENCH-COM-01 but expressed in completely different prose.",
        is_adversarial=True,
        input_payload={
            "text": "This is to confirm: we guarantee that formal written approval for Atlas Phase 2 will be delivered no later than September 5, 2026.",
            "sender": "sjenkins@meridianglobal.com",
            "recipient": "alex@northstarstudio.com",
            "source_id": "EML-PARA-01",
        },
        expected=ExpectedOutcome(
            commitment_detected=True,
            statement_type=StatementType.COMMITMENT,
        ),
    ),
    BenchmarkCase(
        id="ADV-LANG-02",
        name="Commitment buried in longer paragraph",
        category=BenchmarkCategory.COMMITMENT_UNDERSTANDING,
        description="Binding commitment embedded in a multi-sentence casual email.",
        is_adversarial=True,
        input_payload={
            "text": "Hey Alex, hope you had a great weekend. Just wanted to loop back on a few things. "
                    "Regarding the brand kit, we promise to deliver the final brand guidelines and typography package "
                    "to Horizon Health by September 10, 2026. Also, let me know if you need anything else from the team.",
            "sender": "alex@northstarstudio.com",
            "recipient": "rachel@horizonhealth.com",
            "source_id": "EML-EMBED-01",
        },
        expected=ExpectedOutcome(
            commitment_detected=True,
            statement_type=StatementType.COMMITMENT,
        ),
    ),
    BenchmarkCase(
        id="ADV-LANG-03",
        name="Tentative wording that sounds like commitment",
        category=BenchmarkCategory.COMMITMENT_UNDERSTANDING,
        description="Uses future tense but is heavily hedged. Should NOT be treated as binding.",
        is_adversarial=True,
        input_payload={
            "text": "Maybe we could try to get this done by Friday, but I'm not making any promises.",
            "sender": "dev@meridianglobal.com",
            "recipient": "alex@northstarstudio.com",
            "source_id": "EML-TENT-01",
        },
        expected=ExpectedOutcome(
            commitment_detected=False,
            statement_type=StatementType.SUGGESTION,
        ),
    ),
    BenchmarkCase(
        id="ADV-LANG-04",
        name="Completed action followed by unrelated future language",
        category=BenchmarkCategory.COMMITMENT_UNDERSTANDING,
        description="Past-tense completion mixed with future discussion that is not a commitment.",
        is_adversarial=True,
        input_payload={
            "text": "We have finalized all Phase 1 deliverables and completed and tested yesterday. "
                    "For Phase 2, we'll need to discuss scope and timelines in our next meeting.",
            "sender": "contractor@northstarstudio.com",
            "recipient": "lead@northstarstudio.com",
            "source_id": "EML-MIX-01",
        },
        expected=ExpectedOutcome(
            commitment_detected=False,
            statement_type=StatementType.COMPLETED_ACTION,
        ),
    ),
    BenchmarkCase(
        id="ADV-LANG-05",
        name="Indirect obligation with 'should have been' language",
        category=BenchmarkCategory.COMMITMENT_UNDERSTANDING,
        description="Discussion referencing a missed past obligation, not a new commitment.",
        is_adversarial=True,
        input_payload={
            "text": "Could you please confirm if the project status report that should have been submitted last week is now available?",
            "sender": "manager@northstarstudio.com",
            "recipient": "dev@northstarstudio.com",
            "source_id": "EML-IND-01",
        },
        expected=ExpectedOutcome(
            commitment_detected=False,
            statement_type=StatementType.QUESTION,
        ),
    ),

    # =========================================================================
    # B. EVIDENCE ORDERING
    # =========================================================================
    BenchmarkCase(
        id="ADV-ORD-01",
        name="Proof arriving exactly at execution boundary (T_proof == T_exec)",
        category=BenchmarkCategory.VERIFICATION,
        description="Evidence timestamp exactly equals execution timestamp. Must count as fresh (>=).",
        is_adversarial=True,
        input_payload={
            "commitment_id": "com_atlas_approval",
            "execution_succeeded": True,
            "evidence_offset_seconds": 0,  # Exactly at execution time
        },
        expected=ExpectedOutcome(
            verification_required=True,
            final_state=CommitmentStatus.RESOLVED,
        ),
    ),
    BenchmarkCase(
        id="ADV-ORD-02",
        name="Proof 1 second before execution boundary",
        category=BenchmarkCategory.VERIFICATION,
        description="Evidence timestamp 1 second before execution. Must be rejected as stale.",
        is_adversarial=True,
        input_payload={
            "commitment_id": "com_atlas_approval",
            "execution_succeeded": True,
            "evidence_offset_seconds": -1,  # 1 second before execution
        },
        expected=ExpectedOutcome(
            verification_required=True,
            final_state=CommitmentStatus.VERIFYING,
        ),
    ),
    BenchmarkCase(
        id="ADV-ORD-03",
        name="Fresh proof followed by older stale proof",
        category=BenchmarkCategory.VERIFICATION,
        description="Two emails: first fresh (post-exec), second stale (pre-exec). System must accept the fresh one.",
        is_adversarial=True,
        input_payload={
            "commitment_id": "com_atlas_approval",
            "execution_succeeded": True,
            "mixed_evidence": True,  # Fresh + stale
        },
        expected=ExpectedOutcome(
            verification_required=True,
            final_state=CommitmentStatus.RESOLVED,
        ),
    ),

    # =========================================================================
    # C. EVIDENCE CONTAMINATION
    # =========================================================================
    BenchmarkCase(
        id="ADV-CONTAM-01",
        name="Same customer different project approval",
        category=BenchmarkCategory.VERIFICATION,
        description="Sarah Jenkins approves a different project (not Atlas). Must not satisfy Atlas verification.",
        is_adversarial=True,
        input_payload={
            "commitment_id": "com_atlas_approval",
            "execution_succeeded": True,
            "wrong_project": "Project Omega",
        },
        expected=ExpectedOutcome(
            verification_required=True,
            final_state=CommitmentStatus.VERIFYING,
        ),
    ),
    BenchmarkCase(
        id="ADV-CONTAM-02",
        name="Generic 'approved' without project context",
        category=BenchmarkCategory.VERIFICATION,
        description="Email says 'formally approve' but references no project. Must not satisfy Atlas verification.",
        is_adversarial=True,
        input_payload={
            "commitment_id": "com_atlas_approval",
            "execution_succeeded": True,
            "generic_approval": True,
        },
        expected=ExpectedOutcome(
            verification_required=True,
            final_state=CommitmentStatus.VERIFYING,
        ),
    ),

    # =========================================================================
    # D. AUTHORITY CONFLICT
    # =========================================================================
    BenchmarkCase(
        id="ADV-AUTH-01",
        name="Slack says approved but formal email rejects",
        category=BenchmarkCategory.EVIDENCE_REASONING,
        description="Slack corroboration vs formal email rejection. The system must flag contradiction.",
        is_adversarial=True,
        input_payload={
            "commitment_id": "com_atlas_approval",
            "conflicting_sources": True,
        },
        expected=ExpectedOutcome(
            evidence_classification="CONTRADICTION",
            contradiction_detected=True,
        ),
    ),

    # =========================================================================
    # E. DUPLICATE / REPLAY ATTACKS
    # =========================================================================
    BenchmarkCase(
        id="ADV-DUP-01",
        name="Duplicate approval attempt after execution",
        category=BenchmarkCategory.ACTION_POLICY,
        description="Same approval token replayed after first execution completed. State machine must reject duplicate EXECUTING transition.",
        is_adversarial=True,
        input_payload={
            "current_status": CommitmentStatus.VERIFYING,
            "replay_execution": True,
        },
        expected=ExpectedOutcome(
            execution_allowed=False,
        ),
    ),
    BenchmarkCase(
        id="ADV-DUP-02",
        name="Same evidence hash with different wrapper text",
        category=BenchmarkCategory.VERIFICATION,
        description="Two emails with same attachment but different body text. First accepted, same result expected.",
        is_adversarial=True,
        input_payload={
            "commitment_id": "com_atlas_approval",
            "execution_succeeded": True,
            "duplicate_evidence_different_wrapper": True,
        },
        expected=ExpectedOutcome(
            verification_required=True,
            final_state=CommitmentStatus.RESOLVED,
        ),
    ),

    # =========================================================================
    # F. PARTIAL FULFILLMENT
    # =========================================================================
    BenchmarkCase(
        id="ADV-PARTIAL-01",
        name="Signoff exists but required attachment is missing",
        category=BenchmarkCategory.VERIFICATION,
        description="Email contains approval language but the signed PDF attachment is absent.",
        is_adversarial=True,
        input_payload={
            "commitment_id": "com_atlas_approval",
            "execution_succeeded": True,
            "approval_without_attachment": True,
        },
        expected=ExpectedOutcome(
            verification_required=True,
            final_state=CommitmentStatus.VERIFYING,
        ),
    ),
    BenchmarkCase(
        id="ADV-PARTIAL-02",
        name="Evidence gap: zero documents for non-Atlas commitment",
        category=BenchmarkCategory.EVIDENCE_REASONING,
        description="An obligation exists but no documentary evidence exists in any workspace source.",
        is_adversarial=True,
        input_payload={
            "commitment_id": "com_phantom_obligation",
            "inbox_empty": True,
        },
        expected=ExpectedOutcome(
            evidence_classification="GAP",
            evidence_gap_detected=True,
        ),
    ),

    # =========================================================================
    # G. NEGATIVE LANGUAGE
    # =========================================================================
    BenchmarkCase(
        id="ADV-NEG-01",
        name="'Not approved' in email body",
        category=BenchmarkCategory.VERIFICATION,
        description="Email contains 'not approved' — rejection keywords must override any positive signals.",
        is_adversarial=True,
        input_payload={
            "commitment_id": "com_atlas_approval",
            "execution_succeeded": True,
            "negative_language": "not approved",
        },
        expected=ExpectedOutcome(
            verification_required=True,
            final_state=CommitmentStatus.VERIFYING,
        ),
    ),
    BenchmarkCase(
        id="ADV-NEG-02",
        name="'This does not constitute approval' with attached PDF",
        category=BenchmarkCategory.VERIFICATION,
        description="Email has the signed PDF but body explicitly disclaims approval. Rejection must prevail.",
        is_adversarial=True,
        input_payload={
            "commitment_id": "com_atlas_approval",
            "execution_succeeded": True,
            "disclaimer_with_attachment": True,
        },
        expected=ExpectedOutcome(
            verification_required=True,
            final_state=CommitmentStatus.VERIFYING,
        ),
    ),
    BenchmarkCase(
        id="ADV-NEG-03",
        name="'Approval was withdrawn' after initial acceptance",
        category=BenchmarkCategory.VERIFICATION,
        description="First email approves, second email withdraws approval. System must not resolve.",
        is_adversarial=True,
        input_payload={
            "commitment_id": "com_atlas_approval",
            "execution_succeeded": True,
            "approval_then_withdrawal": True,
        },
        expected=ExpectedOutcome(
            verification_required=True,
            final_state=CommitmentStatus.VERIFYING,
        ),
    ),
]
