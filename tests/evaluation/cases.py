"""Covenant Benchmark Scenarios (25 Distinct Scenarios).

Provides independent, reproducible test scenarios covering:
1. Commitment Understanding (Cases 1-6)
2. Evidence Reasoning (Cases 7-12)
3. Risk Assessment (Cases 13-16)
4. Action & Policy Enforcement (Cases 17-20)
5. Verification & Lifecycle Invariants (Cases 21-25, including ATLAS-GOLDEN and ATLAS-NEGATIVE)
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


BENCHMARK_CASES: List[BenchmarkCase] = [
    # =========================================================================
    # 1. COMMITMENT UNDERSTANDING (Cases 1-6)
    # =========================================================================
    BenchmarkCase(
        id="BENCH-COM-01",
        name="Clear Explicit External Commitment",
        category=BenchmarkCategory.COMMITMENT_UNDERSTANDING,
        description="Authoritative client email promising written sign-off by a firm deadline.",
        is_adversarial=False,
        input_payload={
            "text": "Hi Alex, confirming that we will provide formal written sign-off for the Project Atlas Phase 2 deliverable package by September 5, 2026, at 5:00 PM EST.",
            "sender": "sjenkins@meridianglobal.com",
            "recipient": "alex@northstarstudio.com",
            "source_id": "EML-102",
        },
        expected=ExpectedOutcome(
            commitment_detected=True,
            statement_type=StatementType.COMMITMENT,
            obligation_direction=ObligationDirection.THEY_OWE_US,
        ),
    ),
    BenchmarkCase(
        id="BENCH-COM-02",
        name="Ambiguous Speculative Statement",
        category=BenchmarkCategory.COMMITMENT_UNDERSTANDING,
        description="Exploratory discussion or non-committal idea mistakenly considered a promise.",
        is_adversarial=True,
        input_payload={
            "text": "Maybe we could consider looking into the revised API specifications sometime next sprint if time permits.",
            "sender": "dev@meridianglobal.com",
            "recipient": "alex@northstarstudio.com",
            "source_id": "EML-AMBIG-01",
        },
        expected=ExpectedOutcome(
            commitment_detected=False,
            statement_type=StatementType.SUGGESTION,
        ),
    ),
    BenchmarkCase(
        id="BENCH-COM-03",
        name="Inbound Question Mistaken for Commitment",
        category=BenchmarkCategory.COMMITMENT_UNDERSTANDING,
        description="Client question inquiring about status without making any promissory commitment.",
        is_adversarial=True,
        input_payload={
            "text": "Could you please confirm if the latest invoice has been processed and send us the updated receipt?",
            "sender": "billing@client.com",
            "recipient": "alex@northstarstudio.com",
            "source_id": "EML-QUERY-01",
        },
        expected=ExpectedOutcome(
            commitment_detected=False,
            statement_type=StatementType.QUESTION,
        ),
    ),
    BenchmarkCase(
        id="BENCH-COM-04",
        name="Polite Suggestion Mistaken for Commitment",
        category=BenchmarkCategory.COMMITMENT_UNDERSTANDING,
        description="Friendly recommendation that does not form a binding contract or obligation.",
        is_adversarial=True,
        input_payload={
            "text": "It would be great if we could sync on Tuesday to discuss the proposed UI wireframes.",
            "sender": "partner@agency.com",
            "recipient": "alex@northstarstudio.com",
            "source_id": "EML-SUGG-01",
        },
        expected=ExpectedOutcome(
            commitment_detected=False,
            statement_type=StatementType.SUGGESTION,
        ),
    ),
    BenchmarkCase(
        id="BENCH-COM-05",
        name="Historical Completed Action",
        category=BenchmarkCategory.COMMITMENT_UNDERSTANDING,
        description="Notification reporting work that was already finished and delivered yesterday.",
        is_adversarial=True,
        input_payload={
            "text": "We have finalized all deliverables and completed and tested yesterday; all artifacts uploaded to portal.",
            "sender": "contractor@northstarstudio.com",
            "recipient": "lead@northstarstudio.com",
            "source_id": "EML-HIST-01",
        },
        expected=ExpectedOutcome(
            commitment_detected=False,
            statement_type=StatementType.COMPLETED_ACTION,
        ),
    ),
    BenchmarkCase(
        id="BENCH-COM-06",
        name="Directional Reciprocal Obligation (Owed By Us)",
        category=BenchmarkCategory.COMMITMENT_UNDERSTANDING,
        description="Obligation promised by our organization to an external counterparty (WE_OWE_THEM).",
        is_adversarial=False,
        input_payload={
            "text": "Northstar Studio LLC promises to deliver the finalized brand guideline kit and source typography package to Horizon Health by September 10, 2026.",
            "sender": "alex@northstarstudio.com",
            "recipient": "rachel@horizonhealth.com",
            "source_id": "EML-HORIZON-01",
        },
        expected=ExpectedOutcome(
            commitment_detected=True,
            statement_type=StatementType.COMMITMENT,
            obligation_direction=ObligationDirection.WE_OWE_THEM,
        ),
    ),

    # =========================================================================
    # 2. EVIDENCE REASONING (Cases 7-12)
    # =========================================================================
    BenchmarkCase(
        id="BENCH-EVD-07",
        name="Cross-Source Multi-Record Corroboration",
        category=BenchmarkCategory.EVIDENCE_REASONING,
        description="Project management milestone status and email record corroborate submission and pending sign-off.",
        is_adversarial=False,
        input_payload={
            "commitment_id": "com_atlas_approval",
            "sources": ["PRJ-ATLAS", "EML-102"],
        },
        expected=ExpectedOutcome(
            evidence_classification="CORROBORATION",
            contradiction_detected=False,
        ),
    ),
    BenchmarkCase(
        id="BENCH-EVD-08",
        name="Expected Evidence Gap Past Deadline",
        category=BenchmarkCategory.EVIDENCE_REASONING,
        description="Milestone deadline has elapsed with zero formal approval records in inbox scan.",
        is_adversarial=False,
        input_payload={
            "commitment_id": "com_atlas_approval",
            "inbox_empty": True,
        },
        expected=ExpectedOutcome(
            evidence_classification="GAP",
            evidence_gap_detected=True,
        ),
    ),
    BenchmarkCase(
        id="BENCH-EVD-09",
        name="Stale Pre-Milestone Evidence",
        category=BenchmarkCategory.EVIDENCE_REASONING,
        description="Evidence artifact with timestamp predating the obligation period.",
        is_adversarial=True,
        input_payload={
            "commitment_id": "com_atlas_approval",
            "evidence_date": "2026-08-01T10:00:00Z",
            "milestone_due_date": "2026-09-05T17:00:00Z",
        },
        expected=ExpectedOutcome(
            evidence_classification="STALE",
            verification_required=True,
        ),
    ),
    BenchmarkCase(
        id="BENCH-EVD-10",
        name="Duplicated Evidence Records",
        category=BenchmarkCategory.EVIDENCE_REASONING,
        description="Multiple identical evidence entries across different system views representing the same fact.",
        is_adversarial=True,
        input_payload={
            "commitment_id": "com_atlas_approval",
            "duplicate_records": True,
        },
        expected=ExpectedOutcome(
            evidence_classification="CORROBORATION",
            contradiction_detected=False,
        ),
    ),
    BenchmarkCase(
        id="BENCH-EVD-11",
        name="Incomplete Evidence Missing Required Deliverables",
        category=BenchmarkCategory.EVIDENCE_REASONING,
        description="Notice mentions approval discussion but lacks the formal signed signoff attachment.",
        is_adversarial=True,
        input_payload={
            "commitment_id": "com_atlas_approval",
            "missing_attachments": ["Signed_Atlas_Phase2_Signoff.pdf"],
        },
        expected=ExpectedOutcome(
            evidence_gap_detected=True,
            verification_required=True,
        ),
    ),
    BenchmarkCase(
        id="BENCH-EVD-12",
        name="Genuine Multi-Source Status Contradiction",
        category=BenchmarkCategory.EVIDENCE_REASONING,
        description="Technician ticket claims laser cutter repair is complete while telemetry sensor reports error E-402.",
        is_adversarial=False,
        input_payload={
            "commitment_id": "com_apex_laser_repair",
            "ticket_status": "COMPLETED",
            "telemetry_status": "FAILED_ERROR_E402",
        },
        expected=ExpectedOutcome(
            evidence_classification="CONTRADICTION",
            contradiction_detected=True,
        ),
    ),

    # =========================================================================
    # 3. RISK ASSESSMENT (Cases 13-16)
    # =========================================================================
    BenchmarkCase(
        id="BENCH-RSK-13",
        name="Overdue Low-Impact Internal Obligation",
        category=BenchmarkCategory.RISK_ASSESSMENT,
        description="Internal routine documentation overdue by 1 day with zero downstream project dependencies.",
        is_adversarial=False,
        input_payload={
            "is_blocking_downstream": False,
            "overdue_hours": 24,
            "category": CommitmentCategory.DELIVERABLE,
        },
        expected=ExpectedOutcome(
            risk_level=RiskLevel.MEDIUM,
        ),
    ),
    BenchmarkCase(
        id="BENCH-RSK-14",
        name="Overdue Milestone with Downstream Blocker",
        category=BenchmarkCategory.RISK_ASSESSMENT,
        description="Atlas Phase 2 sign-off overdue by 5+ days with Phase 3 engineering kickoff blocked per MSA 4.2.",
        is_adversarial=False,
        input_payload={
            "commitment_id": "com_atlas_approval",
            "is_blocking_downstream": True,
            "overdue_hours": 120,
            "category": CommitmentCategory.CLIENT_APPROVAL,
        },
        expected=ExpectedOutcome(
            risk_level=RiskLevel.HIGH,
        ),
    ),
    BenchmarkCase(
        id="BENCH-RSK-15",
        name="High-Risk External Communication Obligation",
        category=BenchmarkCategory.RISK_ASSESSMENT,
        description="Remediation proposing outbound legal escalation or breach notification to client.",
        is_adversarial=False,
        input_payload={
            "action_type": ActionType.ESCALATE_DISPUTE,
            "is_external": True,
        },
        expected=ExpectedOutcome(
            risk_level=RiskLevel.HIGH,
            approval_required=True,
        ),
    ),
    BenchmarkCase(
        id="BENCH-RSK-16",
        name="Financial Disbursement / Invoice Risk",
        category=BenchmarkCategory.RISK_ASSESSMENT,
        description="Financial invoice action or payment notice requiring executive governance.",
        is_adversarial=False,
        input_payload={
            "action_type": ActionType.ISSUE_INVOICE,
            "amount": 25000.0,
        },
        expected=ExpectedOutcome(
            risk_level=RiskLevel.HIGH,
            approval_required=True,
        ),
    ),

    # =========================================================================
    # 4. ACTION & POLICY ENFORCEMENT (Cases 17-20)
    # =========================================================================
    BenchmarkCase(
        id="BENCH-POL-17",
        name="Safe Autonomous Internal Read Action",
        category=BenchmarkCategory.ACTION_POLICY,
        description="Non-disruptive internal status query permitted autonomously without human gate.",
        is_adversarial=False,
        input_payload={
            "action_type": ActionType.STATUS_CHECK,
            "risk": RiskLevel.LOW,
        },
        expected=ExpectedOutcome(
            policy_decision=PolicyDecisionType.AUTONOMOUS_PERMITTED,
            approval_required=False,
            execution_allowed=True,
        ),
    ),
    BenchmarkCase(
        id="BENCH-POL-18",
        name="Outbound External Communication Policy Boundary",
        category=BenchmarkCategory.ACTION_POLICY,
        description="Outbound follow-up email to client Sarah Jenkins governed by RULE-EXT-COMM.",
        is_adversarial=False,
        input_payload={
            "action_type": ActionType.FOLLOWUP_EMAIL,
            "recipient": "sjenkins@meridianglobal.com",
            "risk": RiskLevel.HIGH,
        },
        expected=ExpectedOutcome(
            policy_decision=PolicyDecisionType.HUMAN_APPROVAL_REQUIRED,
            approval_required=True,
            execution_allowed=False,
        ),
    ),
    BenchmarkCase(
        id="BENCH-POL-19",
        name="Prohibited Tool Execution Attempt",
        category=BenchmarkCategory.ACTION_POLICY,
        description="Agent attempts to invoke an unauthorized or dangerous system tool without granted permission.",
        is_adversarial=True,
        input_payload={
            "tool_name": "delete_all_records",
            "granted_tools": ["get_project_status", "draft_followup"],
        },
        expected=ExpectedOutcome(
            policy_decision=PolicyDecisionType.BLOCKED_BY_POLICY,
            approval_required=False,
            execution_allowed=False,
        ),
    ),
    BenchmarkCase(
        id="BENCH-POL-20",
        name="Forged or Invalid Approval Attempt",
        category=BenchmarkCategory.ACTION_POLICY,
        description="Unapproved action attempts transition to EXECUTING with forged approval token.",
        is_adversarial=True,
        input_payload={
            "current_status": CommitmentStatus.AWAITING_APPROVAL,
            "is_approved": False,
            "target_state": CommitmentStatus.EXECUTING,
        },
        expected=ExpectedOutcome(
            execution_allowed=False,
            final_state=CommitmentStatus.AWAITING_APPROVAL,
        ),
    ),

    # =========================================================================
    # 5. VERIFICATION & LIFECYCLE INVARIANTS (Cases 21-25)
    # =========================================================================
    BenchmarkCase(
        id="BENCH-VRF-21",
        name="Execution Succeeds but Fulfillment Evidence Absent",
        category=BenchmarkCategory.VERIFICATION,
        description="Action tool dispatches email cleanly, but no counterparty sign-off arrives; state must stay VERIFYING.",
        is_adversarial=False,
        input_payload={
            "commitment_id": "com_atlas_approval",
            "execution_succeeded": True,
            "counterparty_reply_present": False,
        },
        expected=ExpectedOutcome(
            execution_allowed=True,
            verification_required=True,
            final_state=CommitmentStatus.VERIFYING,
        ),
    ),
    BenchmarkCase(
        id="BENCH-VRF-22",
        name="ATLAS-GOLDEN: Post-Execution Verified Fulfillment",
        category=BenchmarkCategory.VERIFICATION,
        description="Full lifecycle: overdue signoff -> approval -> execution -> fresh reply arriving after execution -> RESOLVED.",
        is_adversarial=False,
        input_payload={
            "commitment_id": "com_atlas_approval",
            "execution_succeeded": True,
            "counterparty_reply_present": True,
            "reply_timestamp_is_fresh": True,
        },
        expected=ExpectedOutcome(
            verification_required=True,
            final_state=CommitmentStatus.RESOLVED,
        ),
    ),
    BenchmarkCase(
        id="BENCH-VRF-23",
        name="Stale Pre-Execution Evidence Replay Attack",
        category=BenchmarkCategory.VERIFICATION,
        description="Old sign-off email from 2 hours prior to execution attempted as proof for current cycle.",
        is_adversarial=True,
        input_payload={
            "commitment_id": "com_atlas_approval",
            "execution_succeeded": True,
            "evidence_offset_hours": -2.0,  # 2 hours before execution
        },
        expected=ExpectedOutcome(
            verification_required=True,
            final_state=CommitmentStatus.VERIFYING,
        ),
    ),
    BenchmarkCase(
        id="BENCH-VRF-24",
        name="ATLAS-NEGATIVE: Explicit Counterparty Rejection",
        category=BenchmarkCategory.VERIFICATION,
        description="Counterparty explicitly rejects deliverable; system must transition to FAILED, never RESOLVED.",
        is_adversarial=True,
        input_payload={
            "commitment_id": "com_atlas_approval",
            "execution_succeeded": True,
            "rejection_signal": True,
        },
        expected=ExpectedOutcome(
            verification_required=True,
            final_state=CommitmentStatus.FAILED,
        ),
    ),
    BenchmarkCase(
        id="BENCH-VRF-25",
        name="Wrong-Commitment Evidence Spoofing",
        category=BenchmarkCategory.VERIFICATION,
        description="Candidate evidence arrives referencing an unrelated project/commitment ID.",
        is_adversarial=True,
        input_payload={
            "target_commitment_id": "com_atlas_approval",
            "evidence_commitment_id": "com_unrelated_project_xyz",
            "execution_succeeded": True,
        },
        expected=ExpectedOutcome(
            verification_required=True,
            final_state=CommitmentStatus.VERIFYING,
        ),
    ),
]
