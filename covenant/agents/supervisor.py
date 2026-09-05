from typing import Any, Dict, List, Optional
from uuid import uuid4

from covenant.agents.base import AgentContext, AgentResult, BaseAgent
from covenant.agents.commitment import CommitmentAgent
from covenant.agents.evidence import EvidenceAgent
from covenant.agents.policy import PolicyAgent
from covenant.agents.resolution import ResolutionAgent
from covenant.agents.verification import VerificationAgent
from covenant.domain.enums import ActionStatus, CommitmentStatus, RiskLevel
from covenant.domain.models import Commitment, utc_now
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

    async def run_monitoring_cycle(
        self,
        context: Optional[AgentContext] = None,
        cycle_id: Optional[str] = None,
    ) -> AgentResult:
        """
        Execute a complete, bounded autonomous monitoring cycle across workspace commitments.
        Enforces deterministic lifecycle transitions, active state filtering, duplicate suppression,
        policy governance, approval boundaries, post-dispatch verification, telemetry, and persistence.
        """
        events = []
        cycle_id = cycle_id or f"cycle_{uuid4().hex[:8]}"
        ctx = context or AgentContext(session_id=f"monitor_{uuid4().hex[:6]}")
        started_at = utc_now()
        errors: List[str] = []

        # Operational counters
        commitments_scanned = 0
        commitments_changed = 0
        actions_proposed = 0
        approval_requests = 0
        executions = 0
        verifications = 0
        resolved = 0
        failed = 0

        start_evt = await self.emit_event(
            action_name="SUPERVISOR_CYCLE_START",
            summary=f"Supervisor initiated monitoring cycle {cycle_id}.",
            rationale="Periodic bounded monitoring cycle triggered across workspace communications.",
            metadata={
                "cycle_id": cycle_id,
                "started_at": started_at.isoformat(),
            },
        )
        events.append(start_evt)

        # Snapshot pre-state of existing commitments
        pre_commitments = {}
        if self.commitment_repo:
            try:
                for c in await self.commitment_repo.list_all():
                    pre_commitments[c.id] = (
                        c.status,
                        c.risk,
                        len(c.evidence_references),
                        c.next_action.status if c.next_action else None,
                    )
            except Exception as e:
                errors.append(f"Error capturing pre-state: {str(e)}")

        # Step 1: Incremental Discovery of commitments from workspace sources
        try:
            disc_res = await self.commitment_agent.run(ctx)
            events.extend(disc_res.events)
        except Exception as e:
            errors.append(f"Discovery error: {str(e)}")

        if not self.commitment_repo:
            completed_at = utc_now()
            status = "FAILED" if errors else "COMPLETED"
            summary = f"Monitoring cycle {cycle_id} completed without persistence repo."
            complete_evt = await self.emit_event(
                action_name="SUPERVISOR_CYCLE_COMPLETE",
                summary=summary,
                rationale="Discovery completed (no persistence repo).",
                metadata={
                    "cycle_id": cycle_id,
                    "status": status,
                    "started_at": started_at.isoformat(),
                    "completed_at": completed_at.isoformat(),
                    "commitments_scanned": 0,
                    "commitments_changed": 0,
                    "actions_proposed": 0,
                    "approval_requests": 0,
                    "executions": 0,
                    "verifications": 0,
                    "resolved": 0,
                    "failed": 0,
                    "errors": errors,
                },
            )
            events.append(complete_evt)
            return AgentResult(
                agent_name=self.name,
                success=(status == "COMPLETED"),
                summary=summary,
                data={
                    "cycle_id": cycle_id,
                    "status": status,
                    "started_at": started_at.isoformat(),
                    "completed_at": completed_at.isoformat(),
                    "commitments_scanned": 0,
                    "commitments_changed": 0,
                    "actions_proposed": 0,
                    "approval_requests": 0,
                    "executions": 0,
                    "verifications": 0,
                    "resolved": 0,
                    "failed": 0,
                    "errors": errors,
                    "total_commitments": 0,
                    "evaluated": 0,
                },
                events=events,
            )

        # Step 2: Query active commitments and evaluate through bounded governance loop
        try:
            all_commitments = await self.commitment_repo.list_all()
        except Exception as e:
            errors.append(f"Failed to query commitments: {str(e)}")
            all_commitments = []

        commitments_scanned = len(all_commitments)
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
                try:
                    verifications += 1
                    verif_res = await self.verification_agent.run(sub_ctx)
                    events.extend(verif_res.events)
                    processed_count += 1
                    updated_v = await self.commitment_repo.get_by_id(com.id)
                    if updated_v:
                        if updated_v.status == CommitmentStatus.RESOLVED:
                            resolved += 1
                        elif updated_v.status == CommitmentStatus.FAILED:
                            failed += 1
                except Exception as e:
                    errors.append(f"Verification error on {com.id}: {str(e)}")
                continue

            # Active evaluation states:
            # DISCOVERED, ACTIVE, WAITING, DUE, OVERDUE, INVESTIGATING, ACTION_READY
            processed_count += 1

            try:
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
                        if (
                            updated_com.next_action
                            and updated_com.next_action.status == ActionStatus.PROPOSED
                        ):
                            actions_proposed += 1

                # 2c. Policy Evaluation: Enforce human-in-the-loop governance
                if (
                    updated_com.next_action
                    and updated_com.next_action.status == ActionStatus.PROPOSED
                ):
                    pol_res = await self.policy_agent.run(sub_ctx)
                    events.extend(pol_res.events)
                    updated_com = await self.commitment_repo.get_by_id(com.id)
                    if updated_com:
                        if (
                            updated_com.status == CommitmentStatus.AWAITING_APPROVAL
                            or (
                                updated_com.next_action
                                and updated_com.next_action.status == ActionStatus.AWAITING_APPROVAL
                            )
                        ):
                            approval_requests += 1
            except Exception as e:
                errors.append(f"Evaluation error on {com.id}: {str(e)}")

        # Calculate commitments_changed by checking latest states against pre_commitments
        try:
            latest_commitments = await self.commitment_repo.list_all()
            for c in latest_commitments:
                post_sig = (
                    c.status,
                    c.risk,
                    len(c.evidence_references),
                    c.next_action.status if c.next_action else None,
                )
                if c.id not in pre_commitments:
                    commitments_changed += 1
                elif pre_commitments[c.id] != post_sig:
                    commitments_changed += 1
        except Exception as e:
            errors.append(f"Error calculating changed commitments: {str(e)}")

        completed_at = utc_now()
        status = "FAILED" if errors else "COMPLETED"

        summary = (
            f"Monitoring cycle {cycle_id} {status.lower()}: {commitments_scanned} scanned, "
            f"{commitments_changed} changed, {actions_proposed} proposed, "
            f"{approval_requests} approval requests, {verifications} verifications, {resolved} resolved."
        )

        complete_evt = await self.emit_event(
            action_name="SUPERVISOR_CYCLE_COMPLETE",
            summary=summary,
            rationale="All commitments evaluated against policy boundaries.",
            metadata={
                "cycle_id": cycle_id,
                "status": status,
                "started_at": started_at.isoformat(),
                "completed_at": completed_at.isoformat(),
                "commitments_scanned": commitments_scanned,
                "commitments_changed": commitments_changed,
                "actions_proposed": actions_proposed,
                "approval_requests": approval_requests,
                "executions": executions,
                "verifications": verifications,
                "resolved": resolved,
                "failed": failed,
                "errors": errors,
            },
        )
        events.append(complete_evt)

        cycle_data = {
            "cycle_id": cycle_id,
            "status": status,
            "started_at": started_at.isoformat(),
            "completed_at": completed_at.isoformat(),
            "commitments_scanned": commitments_scanned,
            "commitments_changed": commitments_changed,
            "actions_proposed": actions_proposed,
            "approval_requests": approval_requests,
            "executions": executions,
            "verifications": verifications,
            "resolved": resolved,
            "failed": failed,
            "errors": errors,
            "summary": summary,
            "metadata": {
                "session_id": ctx.session_id,
            },
            "total_commitments": commitments_scanned,
            "evaluated": processed_count,
        }

        # Persist cycle record if supported
        if hasattr(self.commitment_repo, "save_cycle_record"):
            try:
                await self.commitment_repo.save_cycle_record(cycle_data)
            except Exception as e:
                errors.append(f"Error saving cycle record: {str(e)}")

        return AgentResult(
            agent_name=self.name,
            success=(status == "COMPLETED"),
            summary=summary,
            data=cycle_data,
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
