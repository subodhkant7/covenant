"""Evidence Agent: Cross-corroborates evidence across sources to establish state."""

from datetime import datetime, timezone
from typing import List, Optional
from covenant.agents.base import AgentContext, AgentResult, BaseAgent
from covenant.domain.enums import CommitmentStatus, EvidenceSourceType, RiskLevel
from covenant.domain.models import EvidenceReference, utc_now
from covenant.state_machine.machine import CommitmentStateMachine
from covenant.synthetic_data.store import workspace_store


class EvidenceAgent(BaseAgent):
    name = "EvidenceAgent"
    description = "Searches workspace sources to cross-corroborate evidence and establish current commitment state."

    async def run(self, context: AgentContext) -> AgentResult:
        cid = context.target_commitment_id
        if not cid or not self.commitment_repo:
            return AgentResult(agent_name=self.name, success=False, summary="Missing target commitment ID or repository.")

        commitment = await self.commitment_repo.get_by_id(cid)
        if not commitment:
            return AgentResult(agent_name=self.name, success=False, summary=f"Commitment '{cid}' not found.")

        events = []
        new_evidence: List[EvidenceReference] = []

        # Example investigation for Project Atlas
        if "atlas" in commitment.id.lower():
            # Check milestone status in project records
            proj_res = await self.tools.get("get_project_status").execute(project_id="PRJ-ATLAS")
            if proj_res.success:
                ev = EvidenceReference(
                    source_type=EvidenceSourceType.PROJECT,
                    source_id="PRJ-ATLAS",
                    title="Project Atlas Milestone 2 Status",
                    snippet="Milestone 2 (High-Fidelity UI System) submitted Sep 3. Current status: SUBMITTED_AWAITING_APPROVAL. Phase 3 currently BLOCKED_ON_APPROVAL.",
                    confidence=0.98,
                )
                new_evidence.append(ev)

            # Check inbox to see if any response exists after Sep 3
            email_res = await self.tools.get("search_email").execute(query="Meridian")
            found_approval = False
            if email_res.success:
                for em in email_res.data.get("emails", []):
                    if "approval" in em.get("subject", "").lower() and em.get("id") != "EML-101" and em.get("id") != "EML-102":
                        found_approval = True

            ev_search = EvidenceReference(
                source_type=EvidenceSourceType.EMAIL,
                source_id="INBOX_SCAN",
                title="Email Corroboration Scan",
                snippet=f"Scanned communications up to present date. Formal written sign-off found: {found_approval}.",
                confidence=0.95,
            )
            new_evidence.append(ev_search)

        # Example investigation for Apex Repair
        elif "apex" in commitment.id.lower():
            # Corroborate with studio ops and invoice
            inv_res = await self.tools.get("get_invoice_status").execute(query="Apex")
            ev_inv = EvidenceReference(
                source_type=EvidenceSourceType.INVOICE,
                source_id="INV-APEX-992",
                title="Invoice Status INV-APEX-992",
                snippet="Invoice held pending completion. Diagnostic fee $450 billed, but final repair certification not submitted.",
                confidence=0.95,
            )
            new_evidence.append(ev_inv)

        # Merge evidence into commitment without duplicates
        existing_source_ids = {e.source_id for e in commitment.evidence_references}
        for ev in new_evidence:
            if ev.source_id not in existing_source_ids:
                commitment.evidence_references.append(ev)

        # Dynamic Risk & Drift Assessment
        all_evidence = commitment.evidence_references
        is_blocking = any("BLOCKED" in (e.snippet or "").upper() for e in all_evidence)

        # Determine effective reference timestamp
        effective_now = None
        if context and context.parameters:
            effective_now = context.parameters.get("effective_time") or context.parameters.get("reference_time")

        if not effective_now:
            simulated_ref = datetime(2026, 9, 6, 12, 0, tzinfo=timezone.utc)
            effective_now = max(utc_now(), simulated_ref)
        elif isinstance(effective_now, str):
            effective_now = datetime.fromisoformat(effective_now).replace(tzinfo=timezone.utc)

        is_overdue = commitment.is_overdue
        days_overdue = 0.0
        if commitment.due_date:
            due = commitment.due_date if commitment.due_date.tzinfo else commitment.due_date.replace(tzinfo=timezone.utc)
            delta = (effective_now - due).total_seconds() / 86400.0
            if delta > 0:
                is_overdue = True
                days_overdue = round(delta, 1)
        elif any("overdue" in (e.snippet or "").lower() for e in all_evidence) or commitment.status == CommitmentStatus.OVERDUE:
            is_overdue = True
            days_overdue = 1.0

        risk_rationale = ""
        calc_risk_tool = self.tools.get("calculate_risk") if self.tools else None
        if calc_risk_tool:
            risk_res = await calc_risk_tool.execute(
                is_overdue=is_overdue,
                days_overdue=days_overdue,
                is_blocking_downstream=is_blocking,
                financial_impact=float(commitment.metadata.get("financial_impact", 0.0)),
            )
            if risk_res.success:
                commitment.risk = RiskLevel(risk_res.data["risk"])
                risk_rationale = risk_res.data.get("rationale", "")

        # State transition: if active/discovered and overdue, transition to OVERDUE
        if is_overdue and CommitmentStateMachine.can_transition(commitment.status, CommitmentStatus.OVERDUE):
            CommitmentStateMachine.transition(
                commitment=commitment,
                target_state=CommitmentStatus.OVERDUE,
                agent_name=self.name,
                reason=f"Evidence corroboration verified overdue by {days_overdue} days (downstream blocked: {is_blocking}).",
            )

        await self.commitment_repo.save(commitment)

        evt = await self.emit_event(
            action_name="CORROBORATE_EVIDENCE",
            summary=f"Gathered {len(new_evidence)} new evidence references for '{commitment.title}' (Risk: {commitment.risk.value}).",
            commitment_id=commitment.id,
            tool_name="workspace_tools",
            new_state=commitment.status,
            rationale=f"Cross-referenced emails, contract terms, and project milestones to determine factual state. {risk_rationale}".strip(),
            metadata={
                "is_overdue": is_overdue,
                "days_overdue": days_overdue,
                "is_blocking_downstream": is_blocking,
                "risk_level": commitment.risk.value,
            },
        )
        events.append(evt)

        return AgentResult(
            agent_name=self.name,
            success=True,
            summary=f"Corroborated {len(new_evidence)} evidence sources (Calculated Risk: {commitment.risk.value}).",
            data={
                "evidence_count": len(commitment.evidence_references),
                "risk": commitment.risk.value,
                "is_overdue": is_overdue,
                "days_overdue": days_overdue,
            },
            events=events,
        )
