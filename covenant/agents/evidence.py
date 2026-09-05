"""Evidence Agent: Cross-corroborates evidence across sources to establish state."""

from typing import List
from covenant.agents.base import AgentContext, AgentResult, BaseAgent
from covenant.domain.enums import CommitmentStatus, EvidenceSourceType
from covenant.domain.models import EvidenceReference
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

        await self.commitment_repo.save(commitment)

        evt = await self.emit_event(
            action_name="CORROBORATE_EVIDENCE",
            summary=f"Gathered {len(new_evidence)} new evidence references for '{commitment.title}'.",
            commitment_id=commitment.id,
            tool_name="workspace_tools",
            rationale="Cross-referenced emails, contract terms, and project milestones to determine factual state.",
        )
        events.append(evt)

        return AgentResult(
            agent_name=self.name,
            success=True,
            summary=f"Corroborated {len(new_evidence)} evidence sources.",
            data={"evidence_count": len(commitment.evidence_references)},
            events=events,
        )
