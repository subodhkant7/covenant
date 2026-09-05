"""Step 6: End-to-end tests for Covenant post-dispatch verification loop.

Proves the complete post-dispatch lifecycle:
human approval
    ↓
runtime dispatch
    ↓
external/world change
    ↓
fresh evidence
    ↓
independent verification (VerificationGate)
    ↓
final commitment outcome (RESOLVED)

Enforces:
Execution success ≠ Commitment verification
Authority over task/commitment completion held exclusively by VerificationGate.
"""

from datetime import datetime, timezone
from pathlib import Path
import pytest
import httpx
from fastapi import FastAPI

from agent_runtime.core.contracts.context import Task
from agent_runtime.core.contracts.event import EventType
from agent_runtime.core.contracts.verification import (
    Evidence as RuntimeEvidence,
    VerificationRequest,
    VerificationResult as RuntimeVerificationResult,
)
from agent_runtime.core.interfaces.verification import IVerifier
from agent_runtime.core.telemetry.sink import InMemoryEventSink
from agent_runtime.core.verification.gate import VerificationGate
from covenant.agents.base import AgentContext
from covenant.agents.supervisor import SupervisorAgent
from covenant.agents.verification import VerificationAgent
from covenant.api.routes import (
    router,
    repo as default_repo,
    supervisor as default_supervisor,
    tools as default_tools,
    llm as default_llm,
    runtime_env as default_runtime_env,
)
from covenant.domain.enums import (
    ActionStatus,
    ActionType,
    CommitmentStatus,
    ObligationDirection,
    RiskLevel,
)
from covenant.domain.models import (
    ActionHistoryItem,
    Commitment,
    Party,
    ProposedAction,
    VerificationResult,
    utc_now,
)
from covenant.persistence.sqlite_repo import SQLiteCommitmentRepository
from covenant.state_machine.exceptions import GuardConditionFailedError
from covenant.state_machine.machine import CommitmentStateMachine
from covenant.synthetic_data.store import workspace_store
from covenant.tools import initialize_tools
from covenant_runtime_bridge.bootstrap import CovenantRuntimeBootstrap
from covenant_runtime_bridge.verification.verification_adapter import CovenantVerificationAdapter


@pytest.fixture
def clean_workspace():
    """Reset the synthetic workspace before and after test."""
    workspace_store.reset()
    yield workspace_store
    workspace_store.reset()


@pytest.fixture
async def isolated_env(tmp_path: Path, clean_workspace):
    """Provides an isolated SQLite repo, runtime environment, and supervisor."""
    db_file = tmp_path / "test_verification.db"
    repo = SQLiteCommitmentRepository(db_path=db_file)
    await repo.initialize()

    runtime_env = CovenantRuntimeBootstrap.assemble()
    tools = initialize_tools()
    llm = default_llm
    supervisor = SupervisorAgent(
        llm=llm,
        tools=tools,
        commitment_repo=repo,
        event_repo=repo,
        runtime_env=runtime_env,
    )
    return repo, runtime_env, supervisor, tools


@pytest.fixture
async def api_client(tmp_path: Path, clean_workspace):
    """Provides an HTTP client connected to an isolated test FastAPI application."""
    test_db = tmp_path / "test_api_verification.db"
    test_repo = SQLiteCommitmentRepository(db_path=test_db)
    await test_repo.initialize()

    test_runtime_env = CovenantRuntimeBootstrap.assemble()
    test_supervisor = SupervisorAgent(
        llm=default_llm,
        tools=default_tools,
        commitment_repo=test_repo,
        event_repo=test_repo,
        runtime_env=test_runtime_env,
    )

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
        yield client, test_repo, test_runtime_env, test_supervisor

    routes_mod.repo = orig_repo
    routes_mod.supervisor = orig_supervisor
    routes_mod.runtime_env = orig_runtime_env


def _build_test_commitment(cid: str = "com_atlas_approval", action_id: str = "act_atlas_approval") -> Commitment:
    action = ProposedAction(
        id=action_id,
        commitment_id=cid,
        action_type=ActionType.FOLLOWUP_EMAIL,
        description="Follow up with Meridian Global regarding Phase 2 formal signoff.",
        recipient="sjenkins@meridianglobal.com",
        subject="Follow-up: Project Atlas Phase 2 Formal Approval",
        payload={
            "tool": "send_followup",
            "body": "Hi Sarah, Following up on Phase 2 deliverables per MSA Section 4.2.",
        },
        status=ActionStatus.AWAITING_APPROVAL,
        requires_human_approval=True,
    )
    return Commitment(
        id=cid,
        title="Meridian Global Phase 2 Deliverable Formal Sign-Off",
        description="Deliver Phase 2 High-Fidelity UI System per MSA Section 4.2.",
        promisor=Party(name="Sarah Jenkins", email="sjenkins@meridianglobal.com", organization="Meridian Global Corp"),
        promisee=Party(name="Alex North", email="alex@northstarstudio.com", organization="Northstar Studio LLC"),
        obligation_direction=ObligationDirection.THEY_OWE_US,
        due_date=datetime(2026, 9, 5, 17, 0, tzinfo=timezone.utc),
        status=CommitmentStatus.AWAITING_APPROVAL,
        risk=RiskLevel.HIGH,
        confidence=0.92,
        next_action=action,
    )


# ==============================================================================
# 1. Authority Model: Execution Success != Verification Success
# ==============================================================================
@pytest.mark.asyncio
async def test_tool_execution_success_does_not_equal_verification(isolated_env):
    """Proves that successful action execution moves commitment to VERIFYING,
    NOT to RESOLVED. VerificationGate must independently determine fulfillment.
    """
    repo, runtime_env, supervisor, tools = isolated_env
    com = _build_test_commitment()
    await repo.save(com)

    # 1. Simulate human approval and dispatch via runtime engine
    send_tool = tools.get("send_followup")
    dispatch_res = await send_tool.execute(
        commitment_id=com.id,
        recipient_email=com.next_action.recipient,
        subject=com.next_action.subject,
        body=com.next_action.payload["body"],
    )
    assert dispatch_res.success is True
    assert dispatch_res.data["action_succeeded"] is True

    # Transition commitment to EXECUTING and then VERIFYING
    com.next_action.status = ActionStatus.APPROVED
    CommitmentStateMachine.transition(
        commitment=com,
        target_state=CommitmentStatus.EXECUTING,
        agent_name="HumanUser",
        reason="Human approved dispatch.",
        approved_by="User",
    )
    CommitmentStateMachine.transition(
        commitment=com,
        target_state=CommitmentStatus.VERIFYING,
        agent_name="System",
        reason="Action executed. Awaiting independent client verification.",
    )
    await repo.save(com)

    # INVARIANT: Commitment is in VERIFYING, NOT RESOLVED
    persisted = await repo.get_by_id(com.id)
    assert persisted.status == CommitmentStatus.VERIFYING
    assert persisted.status != CommitmentStatus.RESOLVED
    assert persisted.resolution_timestamp is None

    # 2. Run verification immediately (before client response arrives)
    verif_res = await supervisor.verify_commitment(com.id)
    assert verif_res.success is True
    assert verif_res.data["action_succeeded"] is True
    assert verif_res.data["business_outcome_verified"] is False
    assert verif_res.data["status"] == CommitmentStatus.VERIFYING.value

    # Commitment remains strictly in VERIFYING
    persisted_after = await repo.get_by_id(com.id)
    assert persisted_after.status == CommitmentStatus.VERIFYING


# ==============================================================================
# 2. Negative Verification Case: Counterparty Does NOT Fulfill
# ==============================================================================
@pytest.mark.asyncio
async def test_negative_verification_outcome_when_counterparty_does_not_fulfill(isolated_env):
    """Proves that when counterparty replies with a rejection or does not fulfill,
    VerificationGate evaluates verified=False, preventing resolution.
    """
    repo, runtime_env, supervisor, tools = isolated_env
    com = _build_test_commitment()
    com.status = CommitmentStatus.VERIFYING
    await repo.save(com)

    # Counterparty sends non-fulfilling response (rejection)
    reply = workspace_store.simulate_client_reply(com.id, fulfilled=False)
    assert reply is not None
    assert "CANNOT approve" in reply["body"]

    # Trigger verification pass
    verif_res = await supervisor.verify_commitment(com.id)
    assert verif_res.data["business_outcome_verified"] is False
    assert verif_res.data["is_verified"] is False

    # Commitment did NOT transition to RESOLVED
    persisted = await repo.get_by_id(com.id)
    assert persisted.status != CommitmentStatus.RESOLVED
    assert persisted.verification_result is not None
    assert persisted.verification_result.is_verified is False


# ==============================================================================
# 3. Positive Verification Case: Counterparty Fulfills With Fresh Evidence
# ==============================================================================
@pytest.mark.asyncio
async def test_positive_verification_outcome_with_fresh_evidence(isolated_env):
    """Proves that when counterparty produces valid fresh evidence,
    VerificationGate corroborates the outcome and transitions commitment to RESOLVED.
    """
    repo, runtime_env, supervisor, tools = isolated_env
    com = _build_test_commitment()
    com.status = CommitmentStatus.VERIFYING
    initial_evidence_count = len(com.evidence_references)
    await repo.save(com)

    # Counterparty sends formal approval
    reply = workspace_store.simulate_client_reply(com.id, fulfilled=True)
    assert reply is not None
    assert "Signed_Atlas_Phase2_Signoff.pdf" in reply["attachments"]

    # Trigger VerificationAgent (wires through VerificationGate)
    verif_res = await supervisor.verify_commitment(com.id)
    assert verif_res.data["business_outcome_verified"] is True
    assert verif_res.data["status"] == CommitmentStatus.RESOLVED.value

    # Verify persisted commitment state
    persisted = await repo.get_by_id(com.id)
    assert persisted.status == CommitmentStatus.RESOLVED
    assert persisted.resolution_timestamp is not None
    assert persisted.verification_result is not None
    assert persisted.verification_result.is_verified is True
    assert len(persisted.verification_result.evidence_ids) >= 1

    # Fresh evidence attached to provenance
    assert len(persisted.evidence_references) > initial_evidence_count
    assert any(e.source_id == reply["id"] for e in persisted.evidence_references)


# ==============================================================================
# 4. Anti-Forgery & Separation: Host Cannot Self-Declare Fulfillment
# ==============================================================================
@pytest.mark.asyncio
async def test_host_cannot_forge_verification_without_gate(isolated_env):
    """Proves that neither host code nor an agent can self-declare a commitment
    RESOLVED without an authentic positive VerificationResult.
    """
    repo, _, _, _ = isolated_env
    com = _build_test_commitment()
    com.status = CommitmentStatus.VERIFYING
    com.verification_result = None
    await repo.save(com)

    # 1. Transition to RESOLVED without verification result MUST fail closed
    with pytest.raises(GuardConditionFailedError, match="Cannot resolve commitment without verified outcome"):
        CommitmentStateMachine.transition(
            commitment=com,
            target_state=CommitmentStatus.RESOLVED,
            agent_name="AttackerHost",
            reason="Attempting to self-declare resolved without proof",
        )

    # 2. Transition with negative verification result MUST fail closed
    com.verification_result = VerificationResult(
        commitment_id=com.id,
        is_verified=False,
        business_outcome_verified=False,
        rationale="Proof unverified.",
    )
    with pytest.raises(GuardConditionFailedError, match="Cannot resolve commitment without verified outcome"):
        CommitmentStateMachine.transition(
            commitment=com,
            target_state=CommitmentStatus.RESOLVED,
            agent_name="AttackerHost",
            reason="Attempting to resolve with false verification",
        )


# ==============================================================================
# 5. VerificationGate Authoritative Telemetry & Event Sink Logging
# ==============================================================================
@pytest.mark.asyncio
async def test_verification_gate_telemetry_recording():
    """Proves VerificationGate records VERIFICATION_STARTED and VERIFICATION_DONE events."""
    sink = InMemoryEventSink()
    gate = VerificationGate(sink)

    class StubVerifier(IVerifier):
        async def verify(self, request, context):
            return RuntimeVerificationResult(
                task_id=request.task_id,
                verified=True,
                rationale="Outcome corroborated by stub.",
                evidence=[
                    RuntimeEvidence(
                        source_type="STUB",
                        source_id="stub_proof_001",
                        summary="Stub confirmation",
                    )
                ],
            )

    task = Task(
        id="tsk_gate_test",
        organization_id="org_test",
        intent="Verify gate authority",
        required_role="verifier",
    )
    res = await gate.verify_task(
        task=task,
        verifier=StubVerifier(),
        expected_outcome="Stub corroboration",
    )
    assert res.verified is True

    events = await sink.list_events(task_id="tsk_gate_test")
    event_types = [e.event_type for e in events]
    assert EventType.VERIFICATION_STARTED in event_types
    assert EventType.VERIFICATION_DONE in event_types


# ==============================================================================
# 6. Persistence: Full State Reload Consistency
# ==============================================================================
@pytest.mark.asyncio
async def test_verification_persistence_across_process_reload(tmp_path: Path, clean_workspace):
    """Proves verified commitment state, evidence, and audit events reload cleanly from SQLite."""
    db_file = tmp_path / "test_reload.db"
    repo1 = SQLiteCommitmentRepository(db_path=db_file)
    await repo1.initialize()

    runtime_env1 = CovenantRuntimeBootstrap.assemble()
    supervisor1 = SupervisorAgent(
        tools=initialize_tools(),
        commitment_repo=repo1,
        event_repo=repo1,
        runtime_env=runtime_env1,
    )

    com = _build_test_commitment("com_atlas_reload")
    com.status = CommitmentStatus.VERIFYING
    await repo1.save(com)

    # Simulate reply and verify
    workspace_store.simulate_client_reply(com.id, fulfilled=True)
    await supervisor1.verify_commitment(com.id)

    # Process reload simulation: create fresh repo2 from same db_file
    repo2 = SQLiteCommitmentRepository(db_path=db_file)
    await repo2.initialize()

    reloaded = await repo2.get_by_id(com.id)
    assert reloaded is not None
    assert reloaded.status == CommitmentStatus.RESOLVED
    assert reloaded.resolution_timestamp is not None
    assert reloaded.verification_result is not None
    assert reloaded.verification_result.is_verified is True
    assert len(reloaded.verification_result.evidence_ids) >= 1

    events = await repo2.list_events(commitment_id=com.id)
    verif_events = [e for e in events if e.action_name == "VERIFY_RESOLUTION"]
    assert len(verif_events) >= 1
    assert verif_events[0].new_state == CommitmentStatus.RESOLVED.value


# ==============================================================================
# 7. End-to-End API Lifecycle Flow
# ==============================================================================
@pytest.mark.asyncio
async def test_e2e_api_post_dispatch_verification_lifecycle(api_client):
    """Exercises the complete external HTTP lifecycle:
    POST /api/decisions/{action_id}/approve
       ↓
    GET /api/commitments/{commitment_id} -> VERIFYING
       ↓
    POST /api/simulate/reply/{commitment_id}
       ↓
    GET /api/commitments/{commitment_id} -> RESOLVED
    """
    client, test_repo, _, _ = api_client
    com = _build_test_commitment("com_atlas_approval", "act_atlas_approval")
    await test_repo.save(com)

    # Step 1: Approve and dispatch action
    appr_resp = await client.post("/api/decisions/act_atlas_approval/approve", json={"notes": "Authorized by user"})
    assert appr_resp.status_code == 200
    assert appr_resp.json()["success"] is True

    # Step 2: Query commitment -> confirms in VERIFYING (NOT RESOLVED)
    get_resp1 = await client.get("/api/commitments/com_atlas_approval")
    assert get_resp1.status_code == 200
    com_state1 = get_resp1.json()
    assert com_state1["status"] == "VERIFYING"
    assert com_state1["resolution_timestamp"] is None

    # Step 3: Simulate external reply (world changes)
    sim_resp = await client.post("/api/simulate/reply/com_atlas_approval", json={"fulfilled": True})
    assert sim_resp.status_code == 200
    sim_body = sim_resp.json()
    assert sim_body["success"] is True
    assert sim_body["verification"]["business_outcome_verified"] is True
    assert sim_body["commitment"]["status"] == "RESOLVED"

    # Step 4: Query commitment again -> confirms in RESOLVED
    get_resp2 = await client.get("/api/commitments/com_atlas_approval")
    assert get_resp2.status_code == 200
    com_state2 = get_resp2.json()
    assert com_state2["status"] == "RESOLVED"
    assert com_state2["resolution_timestamp"] is not None
    assert com_state2["verification_result"]["is_verified"] is True


# ==============================================================================
# 8. Autonomous Scan Cycle Auto-Verifies Commitments Awaiting Verification
# ==============================================================================
@pytest.mark.asyncio
async def test_supervisor_scan_cycle_auto_verifies_verifying_commitments(api_client):
    """Proves that a periodic autonomous supervisor scan cycle detects world changes
    and verifies commitments in VERIFYING state without manual intervention.
    """
    client, test_repo, _, _ = api_client
    com = _build_test_commitment("com_atlas_approval", "act_atlas_approval")
    await test_repo.save(com)

    # Approve action -> commitment enters VERIFYING
    await client.post("/api/decisions/act_atlas_approval/approve", json={})

    # External actor replies in workspace
    workspace_store.simulate_client_reply("com_atlas_approval", fulfilled=True)

    # Autonomous scan triggered (e.g. background cron)
    scan_resp = await client.post("/api/scan")
    assert scan_resp.status_code == 200

    # Commitment is automatically verified and RESOLVED
    final_com = await test_repo.get_by_id("com_atlas_approval")
    assert final_com.status == CommitmentStatus.RESOLVED
    assert final_com.resolution_timestamp is not None
    assert final_com.verification_result.is_verified is True
