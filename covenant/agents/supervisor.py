"""Supervisor Agent: Master orchestrator coordinating specialist agents."""

from typing import Any, Dict, List, Optional
from covenant.agents.base import AgentContext, AgentResult, BaseAgent
from covenant.agents.commitment import CommitmentAgent
from covenant.agents.evidence import EvidenceAgent
from covenant.agents.policy import PolicyAgent
from covenant.agents.resolution import ResolutionAgent
from covenant.agents.verification import VerificationAgent
from covenant.domain.enums import CommitmentStatus
from covenant.domain.models import Commitment
from covenant.llm.provider import AbstractModelProvider
from covenant.persistence.repository import AbstractCommitmentRepository, AbstractEventRepository
from covenant.tools.base import ToolRegistry


class SupervisorAgent(BaseAgent):
    name = "SupervisorAgent"
    description = "Interprets the workflow, delegates to specialist agents, and coordinates end-to-end resolution."

    def __init__(
        self,
        llm: Optional[AbstractModelProvider] = None,
        tools: Optional[ToolRegistry] = None,
        commitment_repo: Optional[AbstractCommitmentRepository] = None,
        event_repo: Optional[AbstractEventRepository] = None,
    ):
        super().__init__(llm=llm, tools=tools, commitment_repo=commitment_repo, event_repo=event_repo)
        self.commitment_agent = CommitmentAgent(llm, tools, commitment_repo, event_repo)
        self.evidence_agent = EvidenceAgent(llm, tools, commitment_repo, event_repo)
        self.resolution_agent = ResolutionAgent(llm, tools, commitment_repo, event_repo)
        self.policy_agent = PolicyAgent(llm, tools, commitment_repo, event_repo)
        self.verification_agent = VerificationAgent(llm, tools, commitment_repo, event_repo)

    async def run(self, context: AgentContext) -> AgentResult:
        """Run full workspace scan and autonomous agent pipeline."""
        events = []

        await self.emit_event(
            action_name="SUPERVISOR_CYCLE_START",
            summary="Supervisor initiated automated commitment discovery and monitoring scan.",
            rationale="Periodic background scan triggered across workspace communications.",
        )

        # Step 1: Commitment Discovery
        disc_res = await self.commitment_agent.run(context)
        events.extend(disc_res.events)

        if not self.commitment_repo:
            return AgentResult(agent_name=self.name, success=True, summary="Discovery completed (no persistence repo).", events=events)

        # Step 2: Evaluate discovered and active commitments
        all_commitments = await self.commitment_repo.list_all()
        for com in all_commitments:
            sub_ctx = AgentContext(session_id=context.session_id, target_commitment_id=com.id)

            # If overdue or investigating, run evidence and resolution pipeline
            if com.status in [CommitmentStatus.OVERDUE, CommitmentStatus.INVESTIGATING, CommitmentStatus.DUE] or com.is_overdue:
                # Evidence corroboration
                ev_res = await self.evidence_agent.run(sub_ctx)
                events.extend(ev_res.events)

                # Action proposal
                res_res = await self.resolution_agent.run(sub_ctx)
                events.extend(res_res.events)

                # Policy evaluation
                pol_res = await self.policy_agent.run(sub_ctx)
                events.extend(pol_res.events)

        await self.emit_event(
            action_name="SUPERVISOR_CYCLE_COMPLETE",
            summary=f"Scan cycle complete. Monitored {len(all_commitments)} commitments.",
            rationale="All commitments evaluated against policy boundaries.",
        )

        return AgentResult(
            agent_name=self.name,
            success=True,
            summary=f"Evaluated {len(all_commitments)} commitments across specialist agents.",
            data={"total_commitments": len(all_commitments)},
            events=events,
        )

    async def verify_commitment(self, commitment_id: str, simulated_params: Optional[Dict[str, Any]] = None) -> AgentResult:
        """Run verification workflow on specific commitment."""
        ctx = AgentContext(
            session_id="manual_verification",
            target_commitment_id=commitment_id,
            parameters=simulated_params or {},
        )
        return await self.verification_agent.run(ctx)
