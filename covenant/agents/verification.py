"""Verification Agent: Verifies completion using evidence before resolving commitments."""

from typing import Any, Dict, List, Optional

from agent_runtime.core.contracts.context import Task
from agent_runtime.core.contracts.verification import (
    Evidence as RuntimeEvidence,
    VerificationResult as RuntimeVerificationResult,
)
from agent_runtime.core.interfaces.verification import IVerifier
from agent_runtime.core.telemetry.sink import InMemoryEventSink
from agent_runtime.core.verification.gate import VerificationGate
from covenant.agents.base import AgentContext, AgentResult, BaseAgent
from covenant.domain.enums import CommitmentStatus, EvidenceSourceType
from covenant.domain.models import EvidenceReference, VerificationResult, utc_now
from covenant.llm.provider import AbstractModelProvider
from covenant.persistence.repository import AbstractCommitmentRepository, AbstractEventRepository
from covenant.state_machine.machine import CommitmentStateMachine
from covenant.synthetic_data.store import workspace_store
from covenant.tools.base import ToolRegistry
from covenant_runtime_bridge.verification.verification_adapter import CovenantVerificationAdapter


class VerificationAgent(BaseAgent):
    name = "VerificationAgent"
    description = "Independently checks whether an action or obligation has been fulfilled before closing."

    def __init__(
        self,
        llm: Optional[AbstractModelProvider] = None,
        tools: Optional[ToolRegistry] = None,
        commitment_repo: Optional[AbstractCommitmentRepository] = None,
        event_repo: Optional[AbstractEventRepository] = None,
        verification_gate: Optional[VerificationGate] = None,
        verifier: Optional[IVerifier] = None,
    ):
        super().__init__(llm=llm, tools=tools, commitment_repo=commitment_repo, event_repo=event_repo)
        self.verification_gate = verification_gate
        self.verifier = verifier

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

        # Support explicit simulation override if passed in context parameters
        if context.parameters.get("simulated_signed_approval"):
            workspace_store.simulate_client_reply(commitment.id, fulfilled=True)
        elif context.parameters.get("simulated_rejection"):
            workspace_store.simulate_client_reply(commitment.id, fulfilled=False)

        # Authoritative runtime VerificationGate and verifier
        gate = self.verification_gate or VerificationGate(event_sink=InMemoryEventSink())
        verifier = self.verifier or CovenantVerificationAdapter(verify_tool=self.tools.get("verify_commitment"))

        task = Task(
            id=f"tsk_verif_{commitment.id}",
            organization_id="org_covenant_northstar",
            intent=f"Verify independent outcome for commitment: {commitment.title}",
            required_role="covenant.verifier",
        )

        # Evaluates real-world outcome proof before task closure.
        # Authority over task completion is held exclusively by VerificationGate.
        executed_at_str = (
            commitment.next_action.executed_at.isoformat()
            if commitment.next_action and commitment.next_action.executed_at
            else None
        )
        gate_result: RuntimeVerificationResult = await gate.verify_task(
            task=task,
            verifier=verifier,
            expected_outcome=f"Counterparty fulfillment for commitment '{commitment.title}' corroborated by independent proof",
            verification_criteria={
                "commitment_id": commitment.id,
                "executed_at": executed_at_str,
            },
        )

        is_verified = gate_result.verified
        rationale = gate_result.rationale
        evidence_ids = [ev.source_id for ev in gate_result.evidence]

        # Attach fresh corroborating evidence references to commitment
        for ev in gate_result.evidence:
            if not any(e.source_id == ev.source_id for e in commitment.evidence_references):
                commitment.evidence_references.append(
                    EvidenceReference(
                        source_type=EvidenceSourceType.EMAIL if "EML" in ev.source_id else EvidenceSourceType.PROJECT,
                        source_id=ev.source_id,
                        title=f"Verification Proof: {ev.summary}",
                        snippet=rationale,
                        confidence=0.98 if is_verified else 0.4,
                    )
                )

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
                    reason=f"Business outcome independently verified by VerificationGate: {rationale}",
                )
        else:
            # If explicit rejection occurred, transition to FAILED if permitted, otherwise remain in VERIFYING
            is_rejection_signal = (
                context.parameters.get("simulated_rejection")
                or context.parameters.get("mark_failed")
                or "explicitly rejected" in rationale.lower()
                or "disputed" in rationale.lower()
                or "withheld approval" in rationale.lower()
                or "withheld" in rationale.lower()
            )
            if is_rejection_signal:
                if CommitmentStateMachine.can_transition(commitment.status, CommitmentStatus.FAILED):
                    CommitmentStateMachine.transition(
                        commitment=commitment,
                        target_state=CommitmentStatus.FAILED,
                        agent_name=self.name,
                        reason=f"Business outcome verification rejected by VerificationGate: {rationale}",
                    )
        attempt_count = int(commitment.metadata.get("verification_attempts", 0)) + 1
        commitment.metadata["verification_attempts"] = attempt_count

        await self.commitment_repo.save(commitment)

        summary_text = (
            f"Verification confirmed (check #{attempt_count}) for '{commitment.title}': OUTCOME VERIFIED -> RESOLVED"
            if is_verified
            else f"Verification check #{attempt_count} (Autonomous Monitor): Awaiting counterparty response"
        )

        evt = await self.emit_event(
            action_name="VERIFY_RESOLUTION",
            summary=summary_text,
            commitment_id=commitment.id,
            tool_name="verify_commitment",
            new_state=commitment.status,
            rationale=rationale,
            metadata={
                "attempt_number": attempt_count,
                "gate_verified": is_verified,
                "evidence_ids": evidence_ids,
                "monitoring_source": "background_monitor",
            },
        )
        events.append(evt)

        return AgentResult(
            agent_name=self.name,
            success=True,
            summary=f"Verification completed via VerificationGate. Outcome Verified: {is_verified}",
            data={
                "action_succeeded": True,
                "business_outcome_verified": is_verified,
                "is_verified": is_verified,
                "rationale": rationale,
                "status": commitment.status.value,
                "evidence_ids": evidence_ids,
            },
            events=events,
        )
