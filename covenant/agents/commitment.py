"""Commitment Agent: Discovers and structures promises from workspace sources."""

from datetime import datetime, timezone
from typing import List, Optional
from covenant.agents.base import AgentContext, AgentResult, BaseAgent
from covenant.domain.enums import CommitmentCategory, CommitmentStatus, RiskLevel
from covenant.domain.models import Commitment, EvidenceReference, EvidenceSourceType, Party, utc_now
from covenant.synthetic_data.store import workspace_store


class CommitmentAgent(BaseAgent):
    name = "CommitmentAgent"
    description = "Discovers commitments from workspace communications, contracts, and milestones."

    async def run(self, context: AgentContext) -> AgentResult:
        discovered_commitments: List[Commitment] = []
        events = []

        # 1. Scan synthetic emails for promises
        search_res = await self.tools.get("search_email").execute(query="promise")
        emails = search_res.data.get("emails", []) if search_res.success else []

        # Scan for Atlas approval promise (EML-102)
        atlas_email = workspace_store.get_email_by_id("EML-102")
        if atlas_email:
            c1 = Commitment(
                id="com_atlas_approval",
                title="Meridian Global Phase 2 Deliverable Formal Sign-Off",
                description="Sarah Jenkins promised formal written sign-off for Project Atlas Phase 2 deliverables by Friday, Sep 5.",
                category=CommitmentCategory.CLIENT_APPROVAL,
                promisor=Party(name="Sarah Jenkins", email="sjenkins@meridianglobal.com", organization="Meridian Global Corp", role="PROMISOR"),
                promisee=Party(name="Alex North", email="alex@northstarstudio.com", organization="Northstar Studio LLC", role="PROMISEE"),
                source_references=["EML-102", "CTR-2026-081", "PRJ-ATLAS"],
                promised_at=datetime.fromisoformat("2026-09-03T14:30:00").replace(tzinfo=timezone.utc),
                due_date=datetime.fromisoformat("2026-09-05T17:00:00").replace(tzinfo=timezone.utc),
                status=CommitmentStatus.OVERDUE,
                risk=RiskLevel.MEDIUM,
                confidence=0.96,
                evidence_references=[
                    EvidenceReference(
                        source_type=EvidenceSourceType.EMAIL,
                        source_id="EML-102",
                        title="Sarah Jenkins Promise Email",
                        snippet="I will review this with our executive steering committee and promise to provide our formal written sign-off by Friday, September 5th at 5 PM EST.",
                    ),
                    EvidenceReference(
                        source_type=EvidenceSourceType.CONTRACT,
                        source_id="CTR-2026-081",
                        title="Master Services Agreement Sec 4.2",
                        snippet="Client shall review each submitted Phase Deliverable within two (2) business days of receipt.",
                    ),
                ],
            )
            discovered_commitments.append(c1)

        # Scan for Apex Industrial Repair promise (EML-201)
        apex_email = workspace_store.get_email_by_id("EML-201")
        if apex_email:
            c2 = Commitment(
                id="com_apex_repair",
                title="Apex Industrial CNC Laser Head Calibration & Repair",
                description="Marcus Vance guaranteed laser head calibration and mirror repair complete & tested by Sep 2 EOD.",
                category=CommitmentCategory.CONTRACTOR_REPAIR,
                promisor=Party(name="Marcus Vance", email="m.vance@apexindustrialrepairs.com", organization="Apex Industrial Repairs", role="PROMISOR"),
                promisee=Party(name="Alex North", email="alex@northstarstudio.com", organization="Northstar Studio LLC", role="PROMISEE"),
                source_references=["EML-201", "CAL-301", "INV-APEX-992"],
                promised_at=datetime.fromisoformat("2026-08-29T09:00:00").replace(tzinfo=timezone.utc),
                due_date=datetime.fromisoformat("2026-09-02T18:00:00").replace(tzinfo=timezone.utc),
                status=CommitmentStatus.OVERDUE,
                risk=RiskLevel.HIGH,
                confidence=0.98,
                evidence_references=[
                    EvidenceReference(
                        source_type=EvidenceSourceType.EMAIL,
                        source_id="EML-201",
                        title="Work Order Confirmation EML-201",
                        snippet="we guarantee the laser head calibration and mirror repair will be 100% complete and tested by Wednesday, September 2nd EOD.",
                    ),
                ],
            )
            discovered_commitments.append(c2)

        # Scan for Lumina Materials Shipment (EML-301 / EML-302)
        lumina_email = workspace_store.get_email_by_id("EML-301")
        if lumina_email:
            c3 = Commitment(
                id="com_lumina_panels",
                title="Lumina Materials Acrylic Panels Delivery (PO-9410)",
                description="Guaranteed dispatch Sep 1, delivery expected by Sep 4 (customs delay reported).",
                category=CommitmentCategory.SUPPLIER_SHIPMENT,
                promisor=Party(name="Rachel Cole", email="rachel.cole@luminamaterials.com", organization="Lumina Materials", role="PROMISOR"),
                promisee=Party(name="Alex North", email="alex@northstarstudio.com", organization="Northstar Studio LLC", role="PROMISEE"),
                source_references=["EML-301", "EML-302", "CAL-402"],
                promised_at=datetime.fromisoformat("2026-08-26T11:20:00").replace(tzinfo=timezone.utc),
                due_date=datetime.fromisoformat("2026-09-04T17:00:00").replace(tzinfo=timezone.utc),
                status=CommitmentStatus.INVESTIGATING,
                risk=RiskLevel.MEDIUM,
                confidence=0.92,
                evidence_references=[
                    EvidenceReference(
                        source_type=EvidenceSourceType.EMAIL,
                        source_id="EML-301",
                        title="Order Confirmation PO-9410",
                        snippet="Guaranteed dispatch on September 1st, with delivery to your studio by September 4th.",
                    ),
                    EvidenceReference(
                        source_type=EvidenceSourceType.EMAIL,
                        source_id="EML-302",
                        title="Carrier Customs Hold Notification",
                        snippet="Status: Regional Customs Inspection Hold. Estimated delay: 3-5 business days beyond original Sep 4 arrival date.",
                    ),
                ],
            )
            discovered_commitments.append(c3)

        # Scan for Horizon Health Brand Kit (EML-401 - We Owe Them)
        horizon_email = workspace_store.get_email_by_id("EML-401")
        if horizon_email:
            c4 = Commitment(
                id="com_horizon_brandkit",
                title="Deliver Brand Identity Guidelines & Asset Kit to Horizon Health",
                description="Northstar Studio promised complete brand guidelines and asset kit to Horizon Health by Sep 10.",
                category=CommitmentCategory.DELIVERABLE,
                promisor=Party(name="Alex North", email="alex@northstarstudio.com", organization="Northstar Studio LLC", role="PROMISOR"),
                promisee=Party(name="David Kroll", email="dkroll@horizonhealth.org", organization="Horizon Health Foundation", role="PROMISEE"),
                source_references=["EML-401", "CTR-2026-092", "PRJ-HORIZON"],
                promised_at=datetime.fromisoformat("2026-09-01T15:00:00").replace(tzinfo=timezone.utc),
                due_date=datetime.fromisoformat("2026-09-10T18:00:00").replace(tzinfo=timezone.utc),
                status=CommitmentStatus.ACTIVE,
                risk=RiskLevel.LOW,
                confidence=0.95,
                evidence_references=[
                    EvidenceReference(
                        source_type=EvidenceSourceType.EMAIL,
                        source_id="EML-401",
                        title="Milestone Commitment EML-401",
                        snippet="Northstar Studio will deliver the complete Horizon Health Brand Identity Guidelines and asset kit by September 10th, 2026.",
                    ),
                    EvidenceReference(
                        source_type=EvidenceSourceType.CONTRACT,
                        source_id="CTR-2026-092",
                        title="Design Retainer Agreement Sec 2.1",
                        snippet="Complete visual identity package due on or before September 10, 2026.",
                    ),
                ],
            )
            discovered_commitments.append(c4)

        # Persist discovered commitments
        for com in discovered_commitments:
            if self.commitment_repo:
                await self.commitment_repo.save(com)
            evt = await self.emit_event(
                action_name="DISCOVER_COMMITMENT",
                summary=f"Discovered commitment '{com.title}' from {com.promisor.name} due {com.due_date.strftime('%Y-%m-%d') if com.due_date else 'N/A'}",
                commitment_id=com.id,
                new_state=com.status,
                rationale="Structured promise identified from workspace communications and contract records.",
            )
            events.append(evt)

        return AgentResult(
            agent_name=self.name,
            success=True,
            summary=f"Discovered {len(discovered_commitments)} commitments across workspace sources.",
            data={"count": len(discovered_commitments), "commitment_ids": [c.id for c in discovered_commitments]},
            events=events,
        )
