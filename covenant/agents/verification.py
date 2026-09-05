"""Verification Agent: Verifies completion using evidence before resolving commitments."""

from covenant.agents.base import AgentContext, AgentResult, BaseAgent
from covenant.domain.enums import CommitmentStatus
from covenant.domain.models import VerificationResult, utc_now
from covenant.state_machine.machine import CommitmentStateMachine
from covenant.synthetic_data.store import workspace_store


class VerificationAgent(BaseAgent):
    name = "VerificationAgent"
    description = "Independently checks whether an action or obligation has been fulfilled before closing."

    async def run(self, context: AgentContext) -> AgentResult:
        cid = context.target_commitment_id
        if not cid or not self.commitment_repo:
            return AgentResult(agent_name=self.name, success=False, summary="Missing commitment ID or repository.")

        commitment = await self.commitment_repo.get_by_id(cid)
        if not commitment:
            return AgentResult(agent_name=self.name, success=False, summary=f"Commitment '{cid}' not found.")

        events = []

        # Check if commitment has verification requirements or evidence
        # Move to VERIFYING state if permitted
        if CommitmentStateMachine.can_transition(commitment.status, CommitmentStatus.VERIFYING):
            CommitmentStateMachine.transition(
                commitment=commitment,
                target_state=CommitmentStatus.VERIFYING,
                agent_name=self.name,
                reason="Initiated verification pass.",
            )

        # Execute real independent verification tool against workspace environment
        verif_res = await self.tools.get("verify_commitment").execute(commitment_id=commitment.id)
        if verif_res.success:
            data = verif_res.data
            is_verified = data.get("is_verified", False)
            rationale = data.get("rationale", "Verification evaluated.")
            evidence_ids = data.get("evidence_ids", [])
        else:
            is_verified = False
            rationale = verif_res.error or "Verification check failed."
            evidence_ids = []

        # Also support explicit simulation override if passed in context parameters
        if "simulated_signed_approval" in context.parameters:
            if context.parameters["simulated_signed_approval"]:
                # Ensure world reply is simulated if requested
                workspace_store.simulate_client_reply(commitment.id)
                recheck = await self.tools.get("verify_commitment").execute(commitment_id=commitment.id)
                if recheck.success:
                    is_verified = recheck.data.get("is_verified", True)
                    rationale = recheck.data.get("rationale", rationale)
                    evidence_ids = recheck.data.get("evidence_ids", evidence_ids)

        vres = VerificationResult(
            commitment_id=commitment.id,
            action_succeeded=True,
            business_outcome_verified=is_verified,
            is_verified=is_verified,
            rationale=rationale,
            evidence_ids=evidence_ids,
            confidence=0.98 if is_verified else 0.4,
        )
        commitment.verification_result = vres

        # Deterministic application state machine enforces closure condition
        if is_verified:
            if CommitmentStateMachine.can_transition(commitment.status, CommitmentStatus.RESOLVED):
                CommitmentStateMachine.transition(
                    commitment=commitment,
                    target_state=CommitmentStatus.RESOLVED,
                    agent_name=self.name,
                    reason=f"Business outcome independently verified: {rationale}",
                )

        await self.commitment_repo.save(commitment)

        evt = await self.emit_event(
            action_name="VERIFY_RESOLUTION",
            summary=f"Verification result for '{commitment.title}': {'OUTCOME VERIFIED -> RESOLVED' if is_verified else 'AWAITING RESPONSE'}",
            commitment_id=commitment.id,
            tool_name="verify_commitment",
            new_state=commitment.status,
            rationale=rationale,
        )
        events.append(evt)

        return AgentResult(
            agent_name=self.name,
            success=True,
            summary=f"Verification completed. Outcome Verified: {is_verified}",
            data={
                "action_succeeded": True,
                "business_outcome_verified": is_verified,
                "is_verified": is_verified,
                "rationale": rationale,
                "status": commitment.status.value,
            },
            events=events,
        )
