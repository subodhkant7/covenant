"""Action execution, human-in-the-loop, and independent verification tools."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from covenant.domain.enums import (
    ActionStatus,
    ActionType,
    EvidenceSourceType,
    PolicyCategory,
    PolicyDecisionType,
    RiskLevel,
)
from covenant.domain.models import (
    EvidenceReference,
    PolicyDecision,
    ProposedAction,
    VerificationResult,
    utc_now,
)
from covenant.synthetic_data.store import workspace_store
from covenant.tools.base import BaseTool, ToolResult, global_tool_registry


class DraftFollowupTool(BaseTool):
    name = "draft_followup"
    description = "Draft professional follow-up communication citing specific agreements and deadlines."
    parameters_schema = {
        "type": "object",
        "properties": {
            "commitment_id": {"type": "string"},
            "recipient_name": {"type": "string"},
            "recipient_email": {"type": "string"},
            "subject": {"type": "string"},
            "promise_summary": {"type": "string"},
            "original_due_date": {"type": "string"},
            "evidence_notes": {"type": "string"},
            "risk": {"type": "string"},
        },
        "required": ["commitment_id", "recipient_name", "subject", "promise_summary"],
    }

    async def execute(
        self,
        commitment_id: str,
        recipient_name: str,
        subject: str,
        promise_summary: str,
        recipient_email: Optional[str] = None,
        original_due_date: Optional[str] = None,
        evidence_notes: Optional[str] = None,
        risk: Optional[str] = None,
        **kwargs: Any,
    ) -> ToolResult:
        body = (
            f"Hi {recipient_name},\n\n"
            f"I am following up regarding our commitment for '{promise_summary}' "
            f"which was targeted for completion on {original_due_date or 'the agreed deadline'}.\n\n"
        )
        if evidence_notes:
            body += f"Context / Status: {evidence_notes}\n\n"
        body += (
            "Could you please provide an update or confirmation so we can keep downstream milestones aligned?\n\n"
            "Best regards,\nAlex North\nNorthstar Studio"
        )

        action = ProposedAction(
            commitment_id=commitment_id,
            action_type=ActionType.FOLLOWUP_EMAIL,
            description=f"Send reminder follow-up email to {recipient_name}",
            recipient=recipient_email or recipient_name,
            subject=subject,
            payload={"body": body, "recipient": recipient_email or recipient_name, "subject": subject},
            status=ActionStatus.PROPOSED,
            requires_human_approval=True,  # Policy requires human approval for external messages
            approval_reason="RULE-EXT-COMM: External communication to client/partner requires authorization.",
            risk=RiskLevel(risk) if risk and risk in RiskLevel.__members__ else RiskLevel.LOW,
            confidence=0.96,
        )
        return ToolResult(success=True, data=action.model_dump(mode="json"))


class SendFollowupTool(BaseTool):
    name = "send_followup"
    description = "Actually dispatch an approved follow-up email into the workspace communication stream."
    parameters_schema = {
        "type": "object",
        "properties": {
            "commitment_id": {"type": "string"},
            "recipient_email": {"type": "string"},
            "subject": {"type": "string"},
            "body": {"type": "string"},
        },
        "required": ["commitment_id", "recipient_email", "subject", "body"],
    }

    async def execute(
        self,
        commitment_id: str,
        recipient_email: str,
        subject: str,
        body: str,
        **kwargs: Any,
    ) -> ToolResult:
        # Actually modify the synthetic environment
        record = workspace_store.send_email(
            from_addr="Alex North <alex@northstarstudio.com>",
            to_addrs=[recipient_email],
            subject=subject,
            body=body,
            thread_id="TH-ATLAS-APPROVAL" if "atlas" in commitment_id.lower() else "TH-FOLLOWUP",
        )
        return ToolResult(
            success=True,
            data={
                "action_succeeded": True,
                "sent_email_id": record["id"],
                "dispatched_at": record["date"],
                "message": f"Follow-up dispatched to {recipient_email}.",
            },
        )


class CreateEscalationTool(BaseTool):
    name = "create_escalation"
    description = "Record a high-priority operational or contractual escalation notice."
    parameters_schema = {
        "type": "object",
        "properties": {
            "commitment_id": {"type": "string"},
            "title": {"type": "string"},
            "rationale": {"type": "string"},
        },
        "required": ["commitment_id", "title", "rationale"],
    }

    async def execute(
        self,
        commitment_id: str,
        title: str,
        rationale: str,
        **kwargs: Any,
    ) -> ToolResult:
        esc = workspace_store.record_escalation(commitment_id, title, rationale)
        return ToolResult(
            success=True,
            data={"escalation_id": esc["id"], "status": "ESCALATED", "title": title},
        )


class RequestHumanApprovalTool(BaseTool):
    name = "request_human_approval"
    description = "Package proposed action and evidence for human review on the Decision Surface."
    parameters_schema = {
        "type": "object",
        "properties": {
            "action_id": {"type": "string"},
            "rationale": {"type": "string"},
            "risk_level": {"type": "string"},
        },
        "required": ["action_id", "rationale"],
    }

    async def execute(
        self,
        action_id: str,
        rationale: str,
        risk_level: str = "LOW",
        **kwargs: Any,
    ) -> ToolResult:
        decision = PolicyDecision(
            action_id=action_id,
            category=PolicyCategory.HUMAN_APPROVAL,
            decision=PolicyDecisionType.HUMAN_APPROVAL_REQUIRED,
            rationale=rationale,
            risk_level=RiskLevel(risk_level) if risk_level in RiskLevel.__members__ else RiskLevel.LOW,
            requires_human_approval=True,
            rules_triggered=["RULE-EXT-COMM: Outbound messages to clients/partners require human authorization."],
        )
        return ToolResult(success=True, data=decision.model_dump(mode="json"))


class VerifyCommitmentTool(BaseTool):
    name = "verify_commitment"
    description = "Independently query workspace communications and records to verify if business outcome was achieved."
    parameters_schema = {
        "type": "object",
        "properties": {
            "commitment_id": {"type": "string"},
            "query_term": {"type": "string"},
            "executed_at": {"type": "string"},
        },
        "required": ["commitment_id"],
    }

    async def execute(
        self,
        commitment_id: str,
        query_term: Optional[str] = None,
        executed_at: Optional[Any] = None,
        **kwargs: Any,
    ) -> ToolResult:
        """
        True independent environment verification:
        Searches emails and project status to corroborate real outcome with temporal freshness checks.
        """
        is_verified = False
        rationale = ""
        found_evidence_ids = []
        is_rejected = False

        # 1. Parse execution timestamp for temporal freshness
        exec_dt: Optional[datetime] = None
        if executed_at:
            if isinstance(executed_at, str):
                try:
                    exec_dt = datetime.fromisoformat(executed_at.replace("Z", "+00:00"))
                except Exception:
                    exec_dt = None
            elif isinstance(executed_at, datetime):
                exec_dt = executed_at if executed_at.tzinfo else executed_at.replace(tzinfo=timezone.utc)

        def _is_fresh(item_date: Optional[str]) -> bool:
            if not exec_dt or not item_date:
                return True
            try:
                dt = datetime.fromisoformat(item_date.replace("Z", "+00:00"))
                return dt >= exec_dt
            except Exception:
                return True

        if "atlas" in commitment_id.lower():
            all_emails = getattr(workspace_store, "emails", [])

            # Check for explicit rejection / dispute emails first
            rejection_terms = ["cannot approve", "reject", "not approved", "declined", "dispute", "unresolved"]
            rejection_email = next(
                (
                    e for e in all_emails
                    if any(t in e.get("body", "").lower() for t in rejection_terms)
                    and _is_fresh(e.get("date"))
                ),
                None,
            )

            if rejection_email:
                is_verified = False
                is_rejected = True
                found_evidence_ids.append(rejection_email["id"])
                rationale = (
                    f"Counterparty explicitly rejected or withheld approval ({rejection_email['id']}): "
                    f"'{rejection_email.get('body', '')[:120]}...'"
                )
            else:
                # Search workspace emails for signoff / approval
                candidate_emails = [
                    e for e in all_emails
                    if "Signed_Atlas_Phase2_Signoff.pdf" in e.get("attachments", [])
                    or "formally approve" in e.get("body", "").lower()
                ]

                # Filter for freshness relative to action execution
                fresh_emails = [e for e in candidate_emails if _is_fresh(e.get("date"))]
                stale_emails = [e for e in candidate_emails if not _is_fresh(e.get("date"))]

                # Also check project milestone
                atlas_prj = workspace_store.get_project_by_id("PRJ-ATLAS")
                m2 = next((m for m in atlas_prj.get("milestones", []) if m["id"] == "M2"), None) if atlas_prj else None

                if fresh_emails:
                    signoff_email = fresh_emails[0]
                    if m2 and m2.get("status") == "APPROVED_BY_CLIENT":
                        is_verified = True
                        found_evidence_ids.append(signoff_email["id"])
                        rationale = (
                            f"Formal signed approval verified from {signoff_email['from']} ({signoff_email['id']}). "
                            "Milestone M2 status is APPROVED_BY_CLIENT."
                        )
                    else:
                        is_verified = True
                        found_evidence_ids.append(signoff_email["id"])
                        rationale = f"Written approval email received from {signoff_email['from']} ({signoff_email['id']})."
                elif stale_emails:
                    is_verified = False
                    rationale = (
                        f"Candidate approval artifact pre-dates action execution timestamp "
                        f"(stale evidence {stale_emails[0]['id']} rejected). Awaiting fresh counterparty verification."
                    )
                else:
                    is_verified = False
                    rationale = "Action was executed, but no corroborating client approval response has been received in inbox yet."

        elif "apex" in commitment_id.lower():
            all_emails = getattr(workspace_store, "emails", [])
            candidate_emails = [e for e in all_emails if "en route" in e.get("body", "").lower()]
            fresh_emails = [e for e in candidate_emails if _is_fresh(e.get("date"))]
            stale_emails = [e for e in candidate_emails if not _is_fresh(e.get("date"))]

            if fresh_emails:
                is_verified = True
                found_evidence_ids.append(fresh_emails[0]["id"])
                rationale = f"Technician dispatch confirmed by service manager ({fresh_emails[0]['id']})."
            elif stale_emails:
                is_verified = False
                rationale = (
                    f"Previous dispatch notice pre-dates current escalation ({stale_emails[0]['id']}). "
                    "No new calibration completion report found."
                )
            else:
                is_verified = False
                rationale = "No calibration completion report or dispatch confirmation found in records."

        else:
            query = (query_term or commitment_id).lower()
            all_emails = getattr(workspace_store, "emails", [])
            matching_fresh = [
                e for e in all_emails
                if (query in e.get("subject", "").lower() or query in e.get("body", "").lower())
                and any(k in e.get("body", "").lower() for k in ["confirmed", "completed", "delivered"])
                and _is_fresh(e.get("date"))
            ]
            if matching_fresh:
                is_verified = True
                found_evidence_ids.append(matching_fresh[0]["id"])
                rationale = f"Independent confirmation verified from {matching_fresh[0]['from']} ({matching_fresh[0]['id']})."
            else:
                is_verified = False
                rationale = "No independent outcome verification evidence found post-execution."

        res = VerificationResult(
            commitment_id=commitment_id,
            action_succeeded=True,
            business_outcome_verified=is_verified,
            is_verified=is_verified,
            rationale=rationale,
            evidence_ids=found_evidence_ids,
            confidence=0.98 if is_verified else (0.1 if is_rejected else 0.3),
        )
        return ToolResult(
            success=True,
            data={
                **res.model_dump(mode="json"),
                "is_rejected": is_rejected,
                "fresh_evidence_count": len(found_evidence_ids),
            },
        )


def register_action_tools():
    global_tool_registry.register(DraftFollowupTool())
    global_tool_registry.register(SendFollowupTool())
    global_tool_registry.register(CreateEscalationTool())
    global_tool_registry.register(RequestHumanApprovalTool())
    global_tool_registry.register(VerifyCommitmentTool())
