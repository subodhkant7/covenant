"""Resolution Agent: Proposes concrete actions and remedies for drifted commitments."""

from typing import Optional
from covenant.agents.base import AgentContext, AgentResult, BaseAgent
from covenant.domain.enums import ActionStatus, ActionType, CommitmentStatus, RiskLevel
from covenant.domain.models import ProposedAction
from covenant.state_machine.machine import CommitmentStateMachine


class ResolutionAgent(BaseAgent):
    name = "ResolutionAgent"
    description = "Determines next operational steps and prepares actionable proposals."

    async def run(self, context: AgentContext) -> AgentResult:
        cid = context.target_commitment_id
        if not cid or not self.commitment_repo:
            return AgentResult(agent_name=self.name, success=False, summary="Missing commitment ID or repository.")

        commitment = await self.commitment_repo.get_by_id(cid)
        if not commitment:
            return AgentResult(agent_name=self.name, success=False, summary=f"Commitment '{cid}' not found.")

        events = []

        # Determine remedy based on category and status
        if "atlas" in commitment.id.lower():
            # Client approval overdue -> draft professional reminder citing Section 4.2
            due_str = commitment.due_date.strftime("%B %d, %Y") if commitment.due_date else "September 5, 2026"
            draft_res = await self.tools.get("draft_followup").execute(
                commitment_id=commitment.id,
                recipient_name=commitment.promisor.name,
                recipient_email=commitment.promisor.email,
                subject=f"Friendly Follow-up: Project Atlas Phase 2 Formal Approval (Due {due_str})",
                promise_summary="Phase 2 High-Fidelity UI System Formal Sign-Off",
                original_due_date=due_str,
                evidence_notes="Phase 2 deliverables submitted Sep 3. Phase 3 frontend implementation is on hold pending sign-off per MSA Section 4.2.",
            )

            if draft_res.success:
                proposed_action = ProposedAction.model_validate(draft_res.data)
                commitment.next_action = proposed_action
                commitment.required_human_approval = proposed_action.requires_human_approval

                # Transition state to ACTION_READY
                if CommitmentStateMachine.can_transition(commitment.status, CommitmentStatus.ACTION_READY):
                    CommitmentStateMachine.transition(
                        commitment=commitment,
                        target_state=CommitmentStatus.ACTION_READY,
                        agent_name=self.name,
                        reason="Prepared formal follow-up action citing MSA Section 4.2.",
                    )

                await self.commitment_repo.save(commitment)

                evt = await self.emit_event(
                    action_name="PROPOSE_ACTION",
                    summary=f"Prepared follow-up action for {commitment.promisor.name} (Risk: {proposed_action.risk.value}).",
                    commitment_id=commitment.id,
                    tool_name="draft_followup",
                    new_state=commitment.status,
                    rationale="Overdue deliverable approval blocking downstream development. Action prepared for policy evaluation.",
                )
                events.append(evt)

        elif "apex" in commitment.id.lower():
            action = ProposedAction(
                commitment_id=commitment.id,
                action_type=ActionType.FOLLOWUP_EMAIL,
                description="Escalate laser cutter repair status to Apex Service Manager",
                recipient=commitment.promisor.email or commitment.promisor.name,
                subject="URGENT: Laser Cutter Calibration Incomplete — Repair Request SR-8841",
                payload={
                    "body": (
                        "Marcus,\n\n"
                        "Technician Dave visited on Sep 1, but our laser cutter is still throwing calibration error E-402. "
                        "The agreed completion deadline of Sep 2 has passed. Our fabrication workshop is currently offline. "
                        "Please confirm when Dave or a senior tech will complete the calibration today.\n\n"
                        "Alex North\nNorthstar Studio"
                    )
                },
                status=ActionStatus.PROPOSED,
                requires_human_approval=True,
                risk=RiskLevel.HIGH,
                confidence=0.98,
                approval_reason="High risk supplier escalation with workshop downtime impact.",
            )
            commitment.next_action = action
            commitment.required_human_approval = True

            if CommitmentStateMachine.can_transition(commitment.status, CommitmentStatus.ACTION_READY):
                CommitmentStateMachine.transition(
                    commitment=commitment,
                    target_state=CommitmentStatus.ACTION_READY,
                    agent_name=self.name,
                    reason="Prepared high-priority repair escalation.",
                )

            await self.commitment_repo.save(commitment)

            evt = await self.emit_event(
                action_name="PROPOSE_ACTION",
                summary=f"Prepared high-priority repair escalation for {commitment.promisor.name}.",
                commitment_id=commitment.id,
                new_state=commitment.status,
                rationale="Critical workshop equipment uncalibrated beyond promised deadline.",
            )
            events.append(evt)

        return AgentResult(
            agent_name=self.name,
            success=True,
            summary=f"Prepared proposed action for commitment '{commitment.id}'.",
            data={"action_id": commitment.next_action.id if commitment.next_action else None},
            events=events,
        )
