"""Verification Adapter: Wraps Covenant's verification logic into runtime IVerifier."""

from typing import Optional
from covenant.tools.action_tools import VerifyCommitmentTool
from agent_runtime.core.contracts.context import TaskContext
from agent_runtime.core.contracts.verification import Evidence, VerificationRequest, VerificationResult
from agent_runtime.core.interfaces.verification import IVerifier
from covenant_runtime_bridge.mapping.entity_mapping import extract_commitment_id_from_scope


class CovenantVerificationAdapter(IVerifier):
    """
    Adapts Covenant verification behavior into the runtime IVerifier contract.
    Ensures runtime VerificationGate can corroborate real external outcome before Task completion.
    """

    def __init__(self, verify_tool: Optional[VerifyCommitmentTool] = None):
        self.verify_tool = verify_tool or VerifyCommitmentTool()

    async def verify(
        self,
        request: VerificationRequest,
        context: Optional[TaskContext] = None,
    ) -> VerificationResult:
        criteria = request.verification_criteria or {}
        scope = getattr(context, "scope", None) if context else None
        cid = (
            criteria.get("commitment_id")
            or (extract_commitment_id_from_scope(scope) if scope else None)
            or request.task_id.replace("tsk_cov_res_", "").replace("tsk_cov_inv_", "")
        )

        # Execute Covenant's independent verification check
        res = await self.verify_tool.execute(commitment_id=cid)
        if not res.success:
            return VerificationResult(
                task_id=request.task_id,
                verified=False,
                rationale=res.error or f"Verification tool failed for commitment '{cid}'.",
                verified_by="CovenantVerificationAdapter",
            )

        data = res.data or {}
        is_verified = data.get("is_verified", False)
        rationale = data.get("rationale", "Verification check completed.")
        evidence_ids = data.get("evidence_ids", [])

        evidence_items = [
            Evidence(
                source_type="COVENANT_WORKSPACE",
                source_id=eid,
                summary=f"Corroborating workspace artifact {eid}",
                collected_by="CovenantVerificationAdapter",
            )
            for eid in evidence_ids
        ]

        return VerificationResult(
            task_id=request.task_id,
            verified=is_verified,
            rationale=rationale,
            evidence=evidence_items,
            verified_by="CovenantVerificationAdapter",
        )
