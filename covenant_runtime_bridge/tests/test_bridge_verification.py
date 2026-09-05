"""Tests for Covenant verification adapter."""

import pytest
from agent_runtime.core.contracts.context import TaskContext, TaskScope
from agent_runtime.core.contracts.verification import VerificationRequest
from covenant.synthetic_data.store import workspace_store
from covenant_runtime_bridge.verification.verification_adapter import CovenantVerificationAdapter


@pytest.mark.asyncio
async def test_verification_unverified_initially():
    workspace_store.reset()
    verifier = CovenantVerificationAdapter()
    req = VerificationRequest(
        task_id="tsk_cov_res_com_atlas_approval",
        expected_outcome="Signed approval received",
        verification_criteria={"commitment_id": "com_atlas_approval"},
    )
    ctx = TaskContext(
        task_id="tsk_cov_res_com_atlas_approval",
        organization_id="org_covenant_northstar",
        intent="Verify signoff",
        required_role="covenant.resolver",
        scope=TaskScope(entity_type="covenant.commitment", entity_ids=["com_atlas_approval"]),
    )

    result = await verifier.verify(req, ctx)
    # Initially without client reply, outcome is NOT verified
    assert result.verified is False
    assert "no corroborating client approval" in result.rationale


@pytest.mark.asyncio
async def test_verification_verified_after_reply():
    # Simulate client signed approval reply into synthetic environment
    workspace_store.simulate_client_reply("com_atlas_approval")

    verifier = CovenantVerificationAdapter()
    req = VerificationRequest(
        task_id="tsk_cov_res_com_atlas_approval",
        expected_outcome="Signed approval received",
        verification_criteria={"commitment_id": "com_atlas_approval"},
    )
    ctx = TaskContext(
        task_id="tsk_cov_res_com_atlas_approval",
        organization_id="org_covenant_northstar",
        intent="Verify signoff",
        required_role="covenant.resolver",
        scope=TaskScope(entity_type="covenant.commitment", entity_ids=["com_atlas_approval"]),
    )

    result = await verifier.verify(req, ctx)
    assert result.verified is True
    assert "Formal signed approval verified" in result.rationale
    assert len(result.evidence) >= 1
