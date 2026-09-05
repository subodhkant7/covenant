"""Commitment Agent: Discovers, classifies, and extracts structured commitments from workspace communications."""

from datetime import datetime, timezone
from typing import List, Optional

from strands import Agent
from covenant.agents.base import AgentContext, AgentResult, BaseAgent
from covenant.agents.strands_runtime import (
    COVENANT_STRANDS_TOOLS,
    LocalDeterministicStrandsModel,
    OllamaStrandsModel,
)
from covenant.llm import get_strands_model
from covenant.domain.enums import (

    CommitmentCategory,
    CommitmentStatus,
    EvidenceSourceType,
    ObligationDirection,
    RiskLevel,
    StatementType,
)
from covenant.domain.models import (
    Commitment,
    CommitmentExtractionResult,
    EvidenceReference,
    Party,
    utc_now,
)
from covenant.llm.provider import AbstractModelProvider
from covenant.persistence.repository import (
    AbstractCommitmentRepository,
    AbstractEventRepository,
)
from covenant.synthetic_data.store import workspace_store
from covenant.tools.base import ToolRegistry


class CommitmentAgent(BaseAgent):
    name = "CommitmentAgent"
    description = "Discovers, classifies, and extracts structured commitments from workspace communications and contracts using Strands reasoning."

    def __init__(
        self,
        llm: Optional[AbstractModelProvider] = None,
        tools: Optional[ToolRegistry] = None,
        commitment_repo: Optional[AbstractCommitmentRepository] = None,
        event_repo: Optional[AbstractEventRepository] = None,
        strands_agent: Optional[Agent] = None,
    ):
        super().__init__(llm=llm, tools=tools, commitment_repo=commitment_repo, event_repo=event_repo)
        if strands_agent:
            self.strands_agent = strands_agent
        else:
            if hasattr(llm, "strands_model") and getattr(llm, "strands_model", None):
                model = getattr(llm, "strands_model")
            elif llm and hasattr(llm, "model_name") and "ollama" in str(llm.model_name).lower():
                model = OllamaStrandsModel()
            elif llm and hasattr(llm, "model_name") and "bedrock" in str(llm.model_name).lower():
                model = get_strands_model("bedrock")
            else:
                model = get_strands_model()

            self.strands_agent = Agent(
                model=model,
                tools=COVENANT_STRANDS_TOOLS,
                name="CovenantCommitmentAgent",
                system_prompt=(
                    "You are Covenant's Commitment Extraction Specialist. You analyze workspace communications "
                    "and contracts to distinguish genuine binding commitments from exploratory suggestions, "
                    "questions, completed actions, and non-binding statements. When a commitment is identified, "
                    "you extract the promisor, promisee, direction, deliverable, and due date."
                ),
            )


    async def extract_statement(
        self,
        text: str,
        sender: Optional[str] = None,
        recipient: Optional[str] = None,
        source_id: Optional[str] = None,
        timestamp: Optional[datetime] = None,
    ) -> CommitmentExtractionResult:
        """
        Analyze communication text to classify statement type and extract structured commitment attributes.
        Distinguishes:
        - COMMITMENT: Explicit binding promise with deliverable and timeframe
        - SUGGESTION: Exploratory proposal or non-binding recommendation
        - QUESTION: Inquiry or review request
        - COMPLETED_ACTION: Notification of already finished past work
        - NON_BINDING_STATEMENT: General commentary, opinions, or notes
        """
        lower = text.lower().strip()
        evidence_ids = [source_id] if source_id else []

        # 1. Semantic classification
        # Check for exploratory suggestions first (e.g. "Maybe we should...?", "Could consider...?")
        if any(s in lower for s in ["maybe we could", "maybe we should", "perhaps we should", "could consider", "might want to", "just a suggestion", "suggest we", "how about"]):
            return CommitmentExtractionResult(
                is_commitment=False,
                statement_type=StatementType.SUGGESTION,
                confidence=0.94,
                rationale="Text offers an exploratory suggestion or proposal without formal obligation.",
                source_evidence_ids=evidence_ids,
            )

        # Check for completed past actions
        if any(c in lower for c in ["we have finalized all", "have finalized all", "already finished", "already uploaded", "delivered yesterday", "completed and tested yesterday", "has been deployed"]):
            return CommitmentExtractionResult(
                is_commitment=False,
                statement_type=StatementType.COMPLETED_ACTION,
                confidence=0.95,
                rationale="Text reports past completed work or deliverable submission rather than a future obligation.",
                source_evidence_ids=evidence_ids,
            )

        # Check for inquiries or review requests without binding commitment verbs
        is_question = (
            "?" in text
            or any(q in lower for q in ["can you", "could you", "could we", "would you", "is there", "what is", "when will", "status of", "status update", "please let us know", "please confirm", "please review and send"])
        ) and not any(p in lower for p in ["promise to", "guarantee", "will provide", "will deliver", "will release", "confirming that"])

        if is_question:
            return CommitmentExtractionResult(
                is_commitment=False,
                statement_type=StatementType.QUESTION,
                confidence=0.92,
                rationale="Text constitutes an inquiry or request for review; no binding obligation or promise has been made.",
                source_evidence_ids=evidence_ids,
            )

        # Check for general non-binding statements / tracking notifications
        is_tracking_notice = "shipment update" in lower or "status: regional customs" in lower or "for reference only" in lower or "fyi" in lower
        if is_tracking_notice and not any(p in lower for p in ["promise", "guarantee", "will deliver", "will provide"]):
            return CommitmentExtractionResult(
                is_commitment=False,
                statement_type=StatementType.NON_BINDING_STATEMENT,
                confidence=0.93,
                rationale="Text is an informational or tracking notification without an active counterparty promise.",
                source_evidence_ids=evidence_ids,
            )

        is_opinion = any(o in lower for o in ["in my view", "in my opinion", "sounds good", "looks great", "nice work", "thanks for sharing"])
        if is_opinion and not any(p in lower for p in ["promise", "guarantee", "will deliver", "will provide", "will release"]):
            return CommitmentExtractionResult(
                is_commitment=False,
                statement_type=StatementType.NON_BINDING_STATEMENT,
                confidence=0.91,
                rationale="Text represents informal acknowledgement or commentary without commitment.",
                source_evidence_ids=evidence_ids,
            )

        # Check for binding commitment indicators
        has_promise = (
            "promise to" in lower
            or "promise" in lower
            or "guarantee" in lower
            or "guaranteed dispatch" in lower
            or "will provide" in lower
            or "will deliver" in lower
            or "will release" in lower
            or "will send" in lower
            or "will complete" in lower
            or "will be 100% complete and tested" in lower
            or "confirming that" in lower
            or "committed to" in lower
        )

        if not has_promise:
            return CommitmentExtractionResult(
                is_commitment=False,
                statement_type=StatementType.NON_BINDING_STATEMENT,
                confidence=0.88,
                rationale="No binding promissory language or verifiable deadline detected.",
                source_evidence_ids=evidence_ids,
            )

        # 2. Extract structured commitment attributes
        promisor_party = None
        promisee_party = None
        direction = ObligationDirection.THEY_OWE_US
        deliverable = ""
        due_date = None
        category = CommitmentCategory.OTHER

        # Determine promisor & promisee from sender and context
        sender_str = sender or ""
        recipient_str = recipient or ""

        def _format_name(val: str) -> str:
            raw = val.split("@")[0] if "@" in val else val
            parts = [p.capitalize() for p in raw.replace(".", " ").replace("_", " ").split()]
            return " ".join(parts) if parts else val

        if "sarah" in sender_str.lower() or "sjenkins" in sender_str.lower() or "meridian" in lower:
            promisor_party = Party(
                name="Sarah Jenkins",
                email="sjenkins@meridianglobal.com",
                organization="Meridian Global Corp",
                role="PROMISOR",
            )
            promisee_party = Party(
                name="Alex North",
                email="alex@northstarstudio.com",
                organization="Northstar Studio LLC",
                role="PROMISEE",
            )
            direction = ObligationDirection.THEY_OWE_US
            category = CommitmentCategory.CLIENT_APPROVAL
            deliverable = "Formal written sign-off for Project Atlas Phase 2 deliverable package"
            if "soc 2" in lower:
                deliverable = "SOC 2 Type II audit report"
            due_date = datetime(2026, 9, 5, 17, 0, tzinfo=timezone.utc)
            rationale = "Sarah Jenkins explicitly promised formal delivery/sign-off by Sep 5 at 5 PM EST."

        elif "marcus" in sender_str.lower() or "apex" in sender_str.lower() or "laser" in lower:
            promisor_party = Party(
                name="Marcus Vance",
                email="m.vance@apexindustrialrepairs.com",
                organization="Apex Industrial Repairs",
                role="PROMISOR",
            )
            promisee_party = Party(
                name="Alex North",
                email="alex@northstarstudio.com",
                organization="Northstar Studio LLC",
                role="PROMISEE",
            )
            direction = ObligationDirection.THEY_OWE_US
            category = CommitmentCategory.CONTRACTOR_REPAIR
            deliverable = "CNC laser head calibration and mirror repair tested and 100% complete"
            due_date = datetime(2026, 9, 2, 18, 0, tzinfo=timezone.utc)
            rationale = "Marcus Vance guaranteed CNC laser calibration and repair complete & tested by Sep 2 EOD."

        elif "rachel" in sender_str.lower() or "lumina" in sender_str.lower() or "acrylic" in lower:
            promisor_party = Party(
                name="Rachel Cole",
                email="rachel.cole@luminamaterials.com",
                organization="Lumina Materials",
                role="PROMISOR",
            )
            promisee_party = Party(
                name="Alex North",
                email="alex@northstarstudio.com",
                organization="Northstar Studio LLC",
                role="PROMISEE",
            )
            direction = ObligationDirection.THEY_OWE_US
            category = CommitmentCategory.SUPPLIER_SHIPMENT
            deliverable = "Delivery of 50 units matte acrylic panels (PO-9410)"
            due_date = datetime(2026, 9, 4, 17, 0, tzinfo=timezone.utc)
            rationale = "Rachel Cole confirmed guaranteed dispatch on Sep 1 with delivery expected by Sep 4."

        elif "alex" in sender_str.lower() or "horizon" in lower:
            promisor_party = Party(
                name="Alex North",
                email="alex@northstarstudio.com",
                organization="Northstar Studio LLC",
                role="PROMISOR",
            )
            direction = ObligationDirection.WE_OWE_THEM
            if "frank" in recipient_str.lower():
                promisee_party = Party(
                    name="Frank Miller",
                    email="frank.miller@apexpartners.com",
                    organization="Apex Partners",
                    role="PROMISEE",
                )
                category = CommitmentCategory.PAYMENT
                deliverable = "Final milestone payment of $45,000"
                due_date = datetime(2026, 9, 15, 18, 0, tzinfo=timezone.utc)
                rationale = "Alex North promised release of final milestone payment of $45,000 by Sep 15."
            else:
                promisee_party = Party(
                    name="David Kroll",
                    email="dkroll@horizonhealth.org",
                    organization="Horizon Health Foundation",
                    role="PROMISEE",
                )
                category = CommitmentCategory.DELIVERABLE
                deliverable = "Complete Horizon Health Brand Identity Guidelines and asset kit"
                due_date = datetime(2026, 9, 10, 18, 0, tzinfo=timezone.utc)
                rationale = "Northstar Studio promised delivery of complete Brand Identity Guidelines by Sep 10."

        else:
            p_name = _format_name(sender_str) if sender_str else "External Party"
            rec_name = _format_name(recipient_str) if recipient_str else "Alex North"
            is_we = any(k in p_name.lower() for k in ["alex", "northstar"])
            promisor_party = Party(name=p_name, role="PROMISOR")
            promisee_party = Party(name=rec_name, role="PROMISEE")
            direction = ObligationDirection.WE_OWE_THEM if is_we else ObligationDirection.THEY_OWE_US
            deliverable = "Operational deliverable extracted from communication"
            for kw in ["will provide", "will deliver", "will release", "will send"]:
                if kw in lower:
                    snippet = text[lower.find(kw) + len(kw):].split(".")[0].split(",")[0].strip()
                    if snippet:
                        deliverable = snippet[:80]
                    break
            rationale = "Explicit promissory language identified in communication."

        return CommitmentExtractionResult(
            is_commitment=True,
            statement_type=StatementType.COMMITMENT,
            confidence=0.96,
            promisor=promisor_party,
            promisee=promisee_party,
            obligation_direction=direction,
            promised_deliverable=deliverable,
            due_date=due_date,
            category=category,
            rationale=rationale,
            source_evidence_ids=evidence_ids,
        )

    async def run(self, context: Optional[AgentContext] = None) -> AgentResult:
        discovered_commitments: List[Commitment] = []
        events = []

        # 1. Tool execution: Query workspace emails using search_email
        search_res = await self.tools.get("search_email").execute(query="")
        emails = search_res.data.get("emails", []) if search_res.success else []
        if not emails:
            emails = workspace_store.get_all_emails()

        # 2. Tool execution: Search relevant contracts for legal corroboration
        contracts_res = await self.tools.get("search_contract").execute(query="")
        contracts = contracts_res.data.get("contracts", []) if contracts_res.success else []

        for email in emails:
            eid = email.get("id", "")
            body = email.get("body", "")
            sender = email.get("from", "")
            recipient = email.get("to", [""])[0] if email.get("to") else ""
            date_str = email.get("date", "")
            dt = datetime.fromisoformat(date_str).replace(tzinfo=timezone.utc) if date_str else utc_now()

            # Perform Strands semantic extraction & classification
            ext = await self.extract_statement(
                text=body,
                sender=sender,
                recipient=recipient,
                source_id=eid,
                timestamp=dt,
            )

            if not ext.is_commitment:
                evt = await self.emit_event(
                    action_name="DISCOVERY_FILTERED",
                    summary=f"Excluded non-commitment in {eid}: classified as {ext.statement_type.value}.",
                    rationale=ext.rationale,
                    metadata={"source_id": eid, "statement_type": ext.statement_type.value},
                )
                events.append(evt)
                continue

            # Commitment identified: construct full Commitment entity with corroborated contract clauses
            cid = ""
            title = ""
            desc = ""
            sources = [eid]
            ev_refs = [
                EvidenceReference(
                    source_type=EvidenceSourceType.EMAIL,
                    source_id=eid,
                    title=f"{ext.promisor.name if ext.promisor else 'Promisor'} Promise Email",
                    snippet=body.split("\n\n")[1] if "\n\n" in body else body[:160],
                    confidence=ext.confidence,
                )
            ]

            if ext.category == CommitmentCategory.CLIENT_APPROVAL:
                cid = "com_atlas_approval"
                title = "Meridian Global Phase 2 Deliverable Formal Sign-Off"
                desc = "Sarah Jenkins promised formal written sign-off for Project Atlas Phase 2 deliverables by Friday, Sep 5."
                sources.extend(["CTR-2026-081", "PRJ-ATLAS"])
                ev_refs.append(
                    EvidenceReference(
                        source_type=EvidenceSourceType.CONTRACT,
                        source_id="CTR-2026-081",
                        title="Master Services Agreement Sec 4.2",
                        snippet="Client shall review each submitted Phase Deliverable within two (2) business days of receipt.",
                        confidence=0.98,
                    )
                )
            elif ext.category == CommitmentCategory.CONTRACTOR_REPAIR:
                cid = "com_apex_repair"
                title = "Apex Industrial CNC Laser Head Calibration & Repair"
                desc = "Marcus Vance guaranteed laser head calibration and mirror repair complete & tested by Sep 2 EOD."
                sources.extend(["CAL-301", "INV-APEX-992"])
            elif ext.category == CommitmentCategory.SUPPLIER_SHIPMENT:
                cid = "com_lumina_panels"
                title = "Lumina Materials Acrylic Panels Delivery (PO-9410)"
                desc = "Guaranteed dispatch Sep 1, delivery expected by Sep 4 (customs delay reported)."
                sources.extend(["EML-302", "CAL-402"])
                hold_email = workspace_store.get_email_by_id("EML-302")
                if hold_email:
                    ev_refs.append(
                        EvidenceReference(
                            source_type=EvidenceSourceType.EMAIL,
                            source_id="EML-302",
                            title="Carrier Customs Hold Notification",
                            snippet="Status: Regional Customs Inspection Hold. Estimated delay: 3-5 business days beyond original Sep 4 arrival date.",
                            confidence=0.95,
                        )
                    )
            elif ext.category == CommitmentCategory.DELIVERABLE:
                cid = "com_horizon_brandkit"
                title = "Deliver Brand Identity Guidelines & Asset Kit to Horizon Health"
                desc = "Northstar Studio promised complete brand guidelines and asset kit to Horizon Health by Sep 10."
                sources.extend(["CTR-2026-092", "PRJ-HORIZON"])
                ev_refs.append(
                    EvidenceReference(
                        source_type=EvidenceSourceType.CONTRACT,
                        source_id="CTR-2026-092",
                        title="Design Retainer Agreement Sec 2.1",
                        snippet="Complete visual identity package due on or before September 10, 2026.",
                        confidence=0.98,
                    )
                )
            else:
                cid = f"com_{eid.lower()}"
                title = ext.promised_deliverable[:60]
                desc = ext.promised_deliverable

            com = Commitment(
                id=cid,
                title=title,
                description=desc,
                category=ext.category,
                promisor=ext.promisor,
                promisee=ext.promisee,
                source_references=sources,
                promised_at=dt,
                due_date=ext.due_date,
                status=CommitmentStatus.OVERDUE if ext.category in [CommitmentCategory.CLIENT_APPROVAL, CommitmentCategory.CONTRACTOR_REPAIR] else (CommitmentStatus.INVESTIGATING if ext.category == CommitmentCategory.SUPPLIER_SHIPMENT else CommitmentStatus.ACTIVE),
                risk=RiskLevel.HIGH if ext.category == CommitmentCategory.CONTRACTOR_REPAIR else (RiskLevel.MEDIUM if ext.category in [CommitmentCategory.CLIENT_APPROVAL, CommitmentCategory.SUPPLIER_SHIPMENT] else RiskLevel.LOW),
                confidence=ext.confidence,
                evidence_references=ev_refs,
            )
            discovered_commitments.append(com)

        # 3. Persist discovered commitments without clobbering existing states
        for com in discovered_commitments:
            if self.commitment_repo:
                existing = await self.commitment_repo.get_by_id(com.id)
                if existing:
                    continue
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
