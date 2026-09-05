from typing import Any, Dict, List, Optional
from uuid import uuid4

from covenant.agents.base import AgentContext, AgentResult, BaseAgent
from covenant.agents.commitment import CommitmentAgent
from covenant.agents.evidence import EvidenceAgent
from covenant.agents.policy import PolicyAgent
from covenant.agents.resolution import ResolutionAgent
from covenant.agents.verification import VerificationAgent
from covenant.domain.enums import ActionStatus, CommitmentStatus, RiskLevel
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
        runtime_env: Optional[Any] = None,
        verification_gate: Optional[Any] = None,
    ):
        super().__init__(llm=llm, tools=tools, commitment_repo=commitment_repo, event_repo=event_repo)
        self.runtime_env = runtime_env
        self.commitment_agent = CommitmentAgent(llm, tools, commitment_repo, event_repo)
        self.evidence_agent = EvidenceAgent(llm, tools, commitment_repo, event_repo)
        self.resolution_agent = ResolutionAgent(llm, tools, commitment_repo, event_repo)
        self.policy_agent = PolicyAgent(llm, tools, commitment_repo, event_repo)
        gate = verification_gate or (runtime_env.verification_gate if runtime_env else None)
        verifier = runtime_env.verifier if runtime_env else None
        self.verification_agent = VerificationAgent(
            llm=llm,
            tools=tools,
            commitment_repo=commitment_repo,
            event_repo=event_repo,
            verification_gate=gate,
            verifier=verifier,
        )

    async def run(self, context: AgentContext) -> AgentResult:
        """Run full workspace scan and autonomous agent pipeline (delegates to canonical monitoring cycle)."""
        return await self.run_monitoring_cycle(context)

    async def run_monitoring_cycle(self, context: Optional[AgentContext] = None) -> AgentResult:
        """
        Execute a complete, bounded autonomous monitoring cycle across workspace commitments.
        Enforces deterministic lifecycle transitions, active state filtering, duplicate suppression,
        policy governance, approval boundaries, and post-dispatch verification.
        """
        events = []
        cycle_id = f"cycle_{uuid4().hex[:8]}"
        ctx = context or AgentContext(session_id=f"monitor_{uuid4().hex[:6]}")

        start_evt = await self.emit_event(
            action_name="SUPERVISOR_CYCLE_START",
            summary="Supervisor initiated automated commitment discovery and monitoring scan.",
            rationale="Periodic bounded monitoring cycle triggered across workspace communications.",
            metadata={"cycle_id": cycle_id},
        )
        events.append(start_evt)

        # Step 1: Incremental Discovery of commitments from workspace sources
        disc_res = await self.commitment_agent.run(ctx)
        events.extend(disc_res.events)

        if not self.commitment_repo:
            return AgentResult(
                agent_name=self.name,
                success=True,
                summary="Discovery completed (no persistence repo).",
                events=events,
            )

        # Step 2: Query active commitments and evaluate through bounded governance loop
        all_commitments = await self.commitment_repo.list_all()
        processed_count = 0

        for com in all_commitments:
            sub_ctx = AgentContext(
                session_id=ctx.session_id,
                target_commitment_id=com.id,
                parameters=ctx.parameters,
            )

            # Phase 7: Explicit Lifecycle Protection
            # Terminal states must never be clobbered or reset by rediscovery
            if com.status in [
                CommitmentStatus.RESOLVED,
                CommitmentStatus.CANCELLED,
                CommitmentStatus.REJECTED,
                CommitmentStatus.FAILED,
            ]:
                continue

            # In-flight execution protected
            if com.status == CommitmentStatus.EXECUTING:
                continue

            # Phase 8: Approval Boundary Protection
            # Commitments in AWAITING_APPROVAL are already formulated and awaiting human sign-off
            if com.status == CommitmentStatus.AWAITING_APPROVAL:
                continue

            # Phase 7 & 10: Post-Dispatch Verification Loop
            if com.status == CommitmentStatus.VERIFYING:
                # Independent verification pass on commitments awaiting outcome corroboration
                verif_res = await self.verification_agent.run(sub_ctx)
                events.extend(verif_res.events)
                processed_count += 1
                continue

            # Active evaluation states:
            # DISCOVERED, ACTIVE, WAITING, DUE, OVERDUE, INVESTIGATING, ACTION_READY
            processed_count += 1

            # 2a. Evidence Corroboration & Risk Assessment
            ev_res = await self.evidence_agent.run(sub_ctx)
            events.extend(ev_res.events)

            # Reload updated commitment state from repository
            updated_com = await self.commitment_repo.get_by_id(com.id)
            if not updated_com:
                continue

            # 2b. Action Proposal: Propose remediation if needed and no active proposal exists
            needs_action = (
                updated_com.is_overdue
                or updated_com.status in [
                    CommitmentStatus.OVERDUE,
                    CommitmentStatus.INVESTIGATING,
                    CommitmentStatus.DUE,
                    CommitmentStatus.ACTION_READY,
                ]
                or updated_com.risk in [RiskLevel.HIGH, RiskLevel.CRITICAL]
            )

            if needs_action:
                has_active_action = (
                    updated_com.next_action
                    and updated_com.next_action.status in [
                        ActionStatus.AWAITING_APPROVAL,
                        ActionStatus.APPROVED,
                        ActionStatus.COMPLETED,
                    ]
                )
                if not has_active_action:
                    res_res = await self.resolution_agent.run(sub_ctx)
                    events.extend(res_res.events)
                    updated_com = await self.commitment_repo.get_by_id(com.id)
                    if not updated_com:
                        continue

            # 2c. Policy Evaluation: Enforce human-in-the-loop governance
            if (
                updated_com.next_action
                and updated_com.next_action.status == ActionStatus.PROPOSED
            ):
                pol_res = await self.policy_agent.run(sub_ctx)
                events.extend(pol_res.events)

        complete_evt = await self.emit_event(
            action_name="SUPERVISOR_CYCLE_COMPLETE",
            summary=f"Scan cycle complete. Monitored {len(all_commitments)} commitments ({processed_count} evaluated).",
            rationale="All commitments evaluated against policy boundaries.",
            metadata={"cycle_id": cycle_id, "total": len(all_commitments), "evaluated": processed_count},
        )
        events.append(complete_evt)

        return AgentResult(
            agent_name=self.name,
            success=True,
            summary=f"Evaluated {len(all_commitments)} commitments across specialist agents.",
            data={"total_commitments": len(all_commitments), "evaluated": processed_count, "cycle_id": cycle_id},
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
