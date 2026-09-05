"""Integration tests for Covenant Decision API endpoints with authoritative runtime execution."""

from datetime import datetime, timezone
from pathlib import Path
import pytest
import httpx
from fastapi import FastAPI

from agent_runtime.core.contracts.event import EventType
from agent_runtime.core.contracts.policy import PolicyDecision, PolicyEvaluationContext
from agent_runtime.core.interfaces.policy import IPolicyRule
from agent_runtime.core.state.enums import PolicyDecisionType
from typing import Optional
from covenant.api.routes import (
    router,
    repo as default_repo,
    supervisor as default_supervisor,
    tools as default_tools,
    llm as default_llm,
    runtime_env as default_runtime_env,
)
from covenant.agents.supervisor import SupervisorAgent
from covenant.domain.enums import (
    ActionStatus,
    ActionType,
    CommitmentStatus,
    ObligationDirection,
    RiskLevel,
)
from covenant.domain.models import Commitment, ProposedAction, Party, utc_now
from covenant.persistence.sqlite_repo import SQLiteCommitmentRepository
from covenant.synthetic_data.store import workspace_store
from covenant_runtime_bridge.bootstrap import CovenantRuntimeBootstrap


class DenyAllPolicyRule(IPolicyRule):
    """Test policy rule that denies all tool requests unconditionally."""

    @property
    def rule_id(self) -> str:
        return "deny_all_rule"

    def evaluate(self, context: PolicyEvaluationContext) -> Optional[PolicyDecision]:
        return PolicyDecision(
            tool_request_id=context.tool_request.request_id,
            decision=PolicyDecisionType.DENY,
            rationale="Test policy prohibits this action unconditionally.",
        )



@pytest.fixture
async def api_client(tmp_path: Path):
    """Provides an HTTP client connected to an isolated test FastAPI application with runtime environment."""
    test_db = tmp_path / "test_api_decisions.db"
    test_repo = SQLiteCommitmentRepository(db_path=test_db)
    await test_repo.initialize()

    # Reset synthetic workspace store
    workspace_store.reset()

    # Create fresh isolated runtime environment
    test_runtime_env = CovenantRuntimeBootstrap.assemble()

    # Create test supervisor with test repo
    test_supervisor = SupervisorAgent(
        llm=default_llm,
        tools=default_tools,
        commitment_repo=test_repo,
        event_repo=test_repo,
    )

    # Monkeypatch routes module globals
    import covenant.api.routes as routes_mod
    orig_repo = routes_mod.repo
    orig_supervisor = routes_mod.supervisor
    orig_runtime_env = routes_mod.runtime_env

    routes_mod.repo = test_repo
    routes_mod.supervisor = test_supervisor
    routes_mod.runtime_env = test_runtime_env

    app = FastAPI()
    app.include_router(router)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client, test_repo, test_runtime_env

    # Restore originals
    routes_mod.repo = orig_repo
    routes_mod.supervisor = orig_supervisor
    routes_mod.runtime_env = orig_runtime_env


def _create_sample_commitment(
    cid: str,
    action_id: str,
    status: CommitmentStatus = CommitmentStatus.AWAITING_APPROVAL,
    action_status: ActionStatus = ActionStatus.AWAITING_APPROVAL,
) -> Commitment:
    return Commitment(
        id=cid,
        title="Project Atlas Phase 2 Formal Approval",
        description="Formal sign-off required for Phase 2 UI deliverables.",
        status=status,
        direction=ObligationDirection.THEY_OWE_US,
        promisor=Party(name="Sarah Jenkins", organization="Meridian Global", email="sjenkins@meridianglobal.com"),
        promisee=Party(name="Alex North", organization="Northstar Studio", email="alex@northstar.io"),
        risk=RiskLevel.MEDIUM,
        confidence=0.96,
        next_action=ProposedAction(
            id=action_id,
            commitment_id=cid,
            action_type=ActionType.FOLLOWUP_EMAIL,
            description="Send formal follow-up requesting approval per contract clause 4.2.",
            recipient="sjenkins@meridianglobal.com",
            subject="Action Required: Project Atlas Phase 2 Approval",
            payload={"body": "Hi Sarah, please provide the signed approval for Phase 2."},
            status=action_status,
            requires_human_approval=True,
            risk=RiskLevel.MEDIUM,
        ),
    )


@pytest.mark.asyncio
async def test_list_pending_decisions_endpoint(api_client):
    client, test_repo, _ = api_client

    # Empty state initially
    res = await client.get("/api/decisions")
    assert res.status_code == 200
    assert res.json() == []

    # Insert commitment with pending decision
    com = _create_sample_commitment("com_dec_1", "act_dec_1")
    await test_repo.save(com)

    res = await client.get("/api/decisions")
    assert res.status_code == 200
    data = res.json()
    assert len(data) == 1
    assert data[0]["commitment_id"] == "com_dec_1"
    assert data[0]["commitment_title"] == "Project Atlas Phase 2 Formal Approval"
    assert data[0]["action"]["id"] == "act_dec_1"
    assert data[0]["action"]["status"] == ActionStatus.AWAITING_APPROVAL.value
    assert data[0]["promisor"]["email"] == "sjenkins@meridianglobal.com"


@pytest.mark.asyncio
async def test_approve_decision_endpoint_lifecycle(api_client):
    client, test_repo, test_runtime_env = api_client

    com = _create_sample_commitment("com_dec_2", "act_dec_2")
    await test_repo.save(com)

    # Approve and dispatch via API
    payload = {
        "notes": "Approved by engineering director.",
        "edited_payload": {"body": "Revised follow-up body: Section 4.2 requires confirmation."},
    }
    res = await client.post("/api/decisions/act_dec_2/approve", json=payload)
    assert res.status_code == 200
    body = res.json()
    assert body["success"] is True
    assert "dispatch_details" in body
    assert "sent_email_id" in body["dispatch_details"]

    # Verify commitment state transitioned to VERIFYING
    com_result = body["commitment"]
    assert com_result["status"] == CommitmentStatus.VERIFYING.value
    assert com_result["next_action"]["status"] == ActionStatus.COMPLETED.value
    assert com_result["next_action"]["decision_notes"] == "Approved by engineering director."
    assert com_result["next_action"]["decided_at"] is not None
    assert com_result["next_action"]["executed_at"] is not None

    # Verify persistence in database
    persisted = await test_repo.get_by_id("com_dec_2")
    assert persisted is not None
    assert persisted.status == CommitmentStatus.VERIFYING
    assert persisted.next_action.status == ActionStatus.COMPLETED

    # Verify audit trail event recorded in domain repository
    events = await test_repo.list_events(commitment_id="com_dec_2")
    dispatch_events = [
        e for e in events
        if (getattr(e, "action_name", None) == "DISPATCH_ACTION" or getattr(e, "event_type", None) == "DISPATCH_ACTION")
    ]
    assert len(dispatch_events) >= 1
    assert "sjenkins@meridianglobal.com" in dispatch_events[0].summary

    # Verify email reached the synthetic workspace store
    sent = [e for e in workspace_store.emails if "Revised follow-up body" in e.get("body", "")]
    assert len(sent) == 1
    assert "sjenkins@meridianglobal.com" in sent[0]["to"]


@pytest.mark.asyncio
async def test_reject_decision_endpoint_lifecycle(api_client):
    client, test_repo, _ = api_client

    com = _create_sample_commitment("com_dec_3", "act_dec_3")
    await test_repo.save(com)

    # Reject via API
    payload = {"notes": "Client requested postponement via phone call."}
    res = await client.post("/api/decisions/act_dec_3/reject", json=payload)
    assert res.status_code == 200
    body = res.json()
    assert body["success"] is True

    # Verify commitment and action marked REJECTED
    com_result = body["commitment"]
    assert com_result["status"] == CommitmentStatus.REJECTED.value
    assert com_result["next_action"]["status"] == ActionStatus.REJECTED.value
    assert com_result["next_action"]["decision_notes"] == "Client requested postponement via phone call."
    assert com_result["next_action"]["decided_at"] is not None

    # Verify persistence
    persisted = await test_repo.get_by_id("com_dec_3")
    assert persisted is not None
    assert persisted.status == CommitmentStatus.REJECTED


@pytest.mark.asyncio
async def test_simulate_reply_and_verify_endpoint(api_client):
    client, test_repo, _ = api_client

    # com_atlas_approval is a known simulation target in workspace_store
    com = _create_sample_commitment(
        "com_atlas_approval",
        "act_atlas_approval",
        status=CommitmentStatus.VERIFYING,
        action_status=ActionStatus.COMPLETED,
    )
    await test_repo.save(com)

    # Trigger simulated counterparty reply
    res = await client.post("/api/simulate/reply/com_atlas_approval")
    assert res.status_code == 200
    body = res.json()
    assert body["success"] is True
    assert body["incoming_email"] is not None
    assert "sjenkins@meridianglobal.com" in body["incoming_email"]["from"]

    # Verify verification pass executed and transitioned commitment to RESOLVED
    persisted = await test_repo.get_by_id("com_atlas_approval")
    assert persisted is not None
    assert persisted.status == CommitmentStatus.RESOLVED
    assert persisted.resolution_timestamp is not None
    assert persisted.verification_result is not None
    assert persisted.verification_result.is_verified is True


@pytest.mark.asyncio
async def test_decision_endpoints_not_found(api_client):
    client, _, _ = api_client

    # Non-existent action approval
    res = await client.post("/api/decisions/act_nonexistent/approve", json={})
    assert res.status_code == 404

    # Non-existent action rejection
    res = await client.post("/api/decisions/act_nonexistent/reject", json={})
    assert res.status_code == 404

    # Non-existent commitment reply simulation
    res = await client.post("/api/simulate/reply/com_unknown_999")
    assert res.status_code == 404


# ==============================================================================
# Architectural Regression Tests (Phase 6: Tests A - F)
# ==============================================================================

@pytest.mark.asyncio
async def test_a_approved_action_uses_execution_engine(api_client):
    """Test A: Proves that approved action executes via ExecutionEngine and creates runtime records."""
    client, test_repo, test_runtime_env = api_client

    com = _create_sample_commitment("com_test_a", "act_test_a")
    await test_repo.save(com)

    res = await client.post("/api/decisions/act_test_a/approve", json={"notes": "Test A approval"})
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True

    # 1. Side effect occurred in environment
    sent_emails = [e for e in workspace_store.emails if "sjenkins@meridianglobal.com" in e.get("to", [])]
    assert len(sent_emails) == 1

    # 2. ExecutionEngine telemetry records exist in runtime event sink
    events = await test_runtime_env.event_sink.list_events(task_id="tsk_com_test_a")
    event_types = [e.event_type for e in events]
    assert EventType.TOOL_REQUESTED in event_types
    assert EventType.APPROVAL_DECIDED in event_types
    assert EventType.TOOL_EXECUTION_STARTED in event_types
    assert EventType.TOOL_EXECUTION_COMPLETED in event_types


@pytest.mark.asyncio
async def test_b_authorization_cannot_be_bypassed(api_client):
    """Test B: Attempt dispatch denied by runtime authorization matrix."""
    client, test_repo, test_runtime_env = api_client

    com = _create_sample_commitment("com_test_b", "act_test_b")
    await test_repo.save(com)

    initial_emails = len(workspace_store.emails)

    # Revoke permission in runtime authorization matrix
    test_runtime_env.permissions.revoke(
        test_runtime_env.organization_id,
        "covenant.resolver_agent",
        ["send_followup"],
    )

    # Attempt approval
    res = await client.post("/api/decisions/act_test_b/approve", json={"notes": "Unauthorized dispatch attempt"})
    assert res.status_code == 403
    assert "Permission denied" in res.json()["detail"]

    # Invariant: No side effect occurred
    assert len(workspace_store.emails) == initial_emails

    # Invariant: Commitment remained in AWAITING_APPROVAL
    persisted = await test_repo.get_by_id("com_test_b")
    assert persisted.status == CommitmentStatus.AWAITING_APPROVAL
    assert persisted.next_action.status == ActionStatus.AWAITING_APPROVAL


@pytest.mark.asyncio
async def test_c_policy_cannot_be_bypassed(api_client):
    """Test C: Attempt dispatch denied by runtime policy engine."""
    client, test_repo, test_runtime_env = api_client

    com = _create_sample_commitment("com_test_c", "act_test_c")
    await test_repo.save(com)

    initial_emails = len(workspace_store.emails)

    # Register denying policy rule in runtime policy engine
    test_runtime_env.policy.register_rule(DenyAllPolicyRule())

    res = await client.post("/api/decisions/act_test_c/approve", json={"notes": "Policy bypass attempt"})
    assert res.status_code == 403
    assert "Policy denied" in res.json()["detail"]

    # Invariant: No side effect occurred
    assert len(workspace_store.emails) == initial_emails

    # Invariant: Commitment not transitioned to VERIFYING
    persisted = await test_repo.get_by_id("com_test_c")
    assert persisted.status == CommitmentStatus.AWAITING_APPROVAL


@pytest.mark.asyncio
async def test_d_idempotency_is_preserved(api_client):
    """Test D: Submitting the same approved action twice executes side effect only once."""
    client, test_repo, test_runtime_env = api_client

    com = _create_sample_commitment("com_test_d", "act_test_d")
    await test_repo.save(com)

    initial_emails = len(workspace_store.emails)

    # First dispatch
    res1 = await client.post("/api/decisions/act_test_d/approve", json={"notes": "First attempt"})
    assert res1.status_code == 200
    assert res1.json()["success"] is True
    assert len(workspace_store.emails) == initial_emails + 1

    # Second dispatch (duplicate submission with identical execution key)
    res2 = await client.post("/api/decisions/act_test_d/approve", json={"notes": "First attempt"})
    assert res2.status_code == 200
    assert res2.json()["success"] is True

    # Invariant: Side effect did NOT execute twice
    assert len(workspace_store.emails) == initial_emails + 1


@pytest.mark.asyncio
async def test_e_audit_telemetry_remains_authoritative(api_client):
    """Test E: Verifies approval and execution generate authoritative runtime records."""
    client, test_repo, test_runtime_env = api_client

    com = _create_sample_commitment("com_test_e", "act_test_e")
    await test_repo.save(com)

    res = await client.post("/api/decisions/act_test_e/approve", json={"notes": "Audit verification"})
    assert res.status_code == 200

    # Check runtime telemetry sink
    task_events = await test_runtime_env.event_sink.list_events(task_id="tsk_com_test_e")
    assert len(task_events) >= 4

    appr_events = [e for e in task_events if e.event_type == EventType.APPROVAL_DECIDED]
    assert len(appr_events) >= 1
    assert "User" in appr_events[0].summary or "APPROVED" in appr_events[0].summary

    exec_events = [e for e in task_events if e.event_type == EventType.TOOL_EXECUTION_COMPLETED]
    assert len(exec_events) >= 1

    # Check domain audit log in repository
    domain_events = await test_repo.list_events(commitment_id="com_test_e")
    assert any(getattr(e, "event_type", None) == "DISPATCH_ACTION" for e in domain_events)


@pytest.mark.asyncio
async def test_f_verification_remains_separate(api_client):
    """Test F: Approval dispatch enters VERIFYING but does NOT mark commitment RESOLVED."""
    client, test_repo, test_runtime_env = api_client

    # com_atlas_approval is configured with known simulated evidence in workspace_store
    com = _create_sample_commitment("com_atlas_approval", "act_atlas_approval")
    await test_repo.save(com)

    res = await client.post("/api/decisions/act_atlas_approval/approve", json={"notes": "Approval only"})
    assert res.status_code == 200

    # Invariant: Commitment is in VERIFYING, NOT RESOLVED
    persisted = await test_repo.get_by_id("com_atlas_approval")
    assert persisted.status == CommitmentStatus.VERIFYING
    assert persisted.status != CommitmentStatus.RESOLVED
    assert persisted.resolution_timestamp is None
    assert persisted.verification_result is None

    # Only separate verification pass (via simulated counterparty reply) resolves the commitment
    sim_res = await client.post("/api/simulate/reply/com_atlas_approval")
    assert sim_res.status_code == 200

    resolved_com = await test_repo.get_by_id("com_atlas_approval")
    assert resolved_com.status == CommitmentStatus.RESOLVED
    assert resolved_com.resolution_timestamp is not None
    assert resolved_com.verification_result is not None
    assert resolved_com.verification_result.is_verified is True

