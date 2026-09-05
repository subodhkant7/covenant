"""Backend tests for Commitment Decision Trace contract and API endpoint."""

from datetime import datetime, timezone
import json
from pathlib import Path
import pytest
import httpx
from fastapi import FastAPI

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
    EvidenceSourceType,
    ObligationDirection,
    RiskLevel,
)
from covenant.domain.models import (
    AgentEvent,
    Commitment,
    EvidenceReference,
    Party,
    ProposedAction,
    utc_now,
)
from covenant.persistence.sqlite_repo import SQLiteCommitmentRepository
from covenant.synthetic_data.store import workspace_store
from covenant_runtime_bridge.bootstrap import CovenantRuntimeBootstrap


@pytest.fixture
async def api_client(tmp_path: Path):
    """Provides an HTTP client connected to an isolated test FastAPI application."""
    test_db = tmp_path / "test_trace.db"
    test_repo = SQLiteCommitmentRepository(db_path=test_db)
    await test_repo.initialize()

    workspace_store.reset()
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
        approval_reason="RULE-EXT-COMM: Outbound messages to external clients/vendors require human approval.",
        risk=RiskLevel.HIGH,
    )
    ev1 = EvidenceReference(
        source_type=EvidenceSourceType.CONTRACT,
        source_id="MSA-SEC-4.2",
        title="Meridian MSA Section 4.2 Signoff Clause",
        snippet="Meridian Global shall execute written sign-off within 5 business days of deliverable submission.",
        confidence=0.95,
    )
    ev2 = EvidenceReference(
        source_type=EvidenceSourceType.EMAIL,
        source_id="EML-ATLAS-DELIV",
        title="Phase 2 High-Fidelity UI System Delivered",
        snippet="Delivered complete Phase 2 UI component library and documentation package.",
        confidence=0.92,
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
        confidence=0.94,
        next_action=action,
        evidence_references=[ev1, ev2],
        source_references=["MSA-SEC-4.2", "EML-ATLAS-DELIV"],
    )


@pytest.mark.asyncio
async def test_commitment_trace_contains_authoritative_lifecycle(api_client):
    """Verifies that the decision trace contains the 10 chronological stages and authoritative domain data."""
    client, test_repo, _, _ = api_client
    com = _build_test_commitment()
    await test_repo.save(com)

    # Record initial discovery and risk events in audit log
    await test_repo.record_event(
        AgentEvent(
            agent="CommitmentAgent",
            event_type="DISCOVERY",
            action_name="DISCOVER_COMMITMENT",
            summary=f"Detected commitment: {com.title}",
            commitment_id=com.id,
            result_status="SUCCESS",
        )
    )
    await test_repo.record_event(
        AgentEvent(
            agent="RiskAgent",
            event_type="EVALUATION",
            action_name="CALCULATE_RISK",
            summary="Calculated risk as HIGH based on imminent due date and client counterparty status.",
            commitment_id=com.id,
            result_status="SUCCESS",
            rationale="Imminent delivery deadline requiring formal signoff.",
        )
    )

    resp = await client.get(f"/api/commitments/{com.id}/trace")
    assert resp.status_code == 200
    trace = resp.json()

    assert trace["commitment_id"] == "com_atlas_approval"
    assert trace["title"] == "Meridian Global Phase 2 Deliverable Formal Sign-Off"
    assert trace["current_state"] == "AWAITING_APPROVAL"
    assert trace["current_risk"] == "HIGH"
    assert trace["timeline_source"] == "persisted_sqlite_audit_events"

    # Verify 10 stages exist in chronological sequence
    stage_names = [s["name"] for s in trace["stages"]]
    assert stage_names == [
        "Commitment detected",
        "Evidence gathered",
        "Risk calculated",
        "Action proposed",
        "Policy decision",
        "Human approval",
        "Action executed",
        "Verification started",
        "Verification evidence",
        "Final outcome",
    ]

    # Commitment detected, Evidence, Risk, Action, Policy are completed; Human approval is active
    assert trace["stages"][0]["status"] == "COMPLETED"
    assert trace["stages"][1]["status"] == "COMPLETED"
    assert trace["stages"][2]["status"] == "COMPLETED"
    assert trace["stages"][3]["status"] == "COMPLETED"
    assert trace["stages"][4]["status"] == "COMPLETED"
    assert trace["stages"][5]["status"] == "ACTIVE"
    assert trace["stages"][6]["status"] == "PENDING"

    # Timeline has real persisted events
    assert len(trace["timeline"]) >= 2
    assert any(t["actor"] == "CommitmentAgent" for t in trace["timeline"])
    assert any(t["actor"] == "RiskAgent" for t in trace["timeline"])


@pytest.mark.asyncio
async def test_commitment_trace_contains_evidence(api_client):
    """Verifies that corroborating evidence records are clearly exposed with references, summaries, and types."""
    client, test_repo, _, _ = api_client
    com = _build_test_commitment()
    await test_repo.save(com)

    resp = await client.get(f"/api/commitments/{com.id}/trace")
    assert resp.status_code == 200
    trace = resp.json()

    evidence = trace["evidence"]
    assert len(evidence) == 2

    contract_ev = next(e for e in evidence if e["source_type"].upper() == "CONTRACT")
    assert contract_ev["source_id"] == "MSA-SEC-4.2"
    assert "Section 4.2" in contract_ev["title"]
    assert "within 5 business days" in contract_ev["snippet"]
    assert contract_ev["confidence"] == 0.95

    email_ev = next(e for e in evidence if e["source_type"].upper() == "EMAIL")
    assert email_ev["source_id"] == "EML-ATLAS-DELIV"
    assert "Delivered complete Phase 2" in email_ev["snippet"]


@pytest.mark.asyncio
async def test_commitment_trace_contains_policy_and_approval(api_client):
    """Verifies that policy triggers, human authorization status, and execution dispatch details are recorded."""
    client, test_repo, _, _ = api_client
    com = _build_test_commitment()
    await test_repo.save(com)

    # Initial trace: awaiting approval
    resp1 = await client.get(f"/api/commitments/{com.id}/trace")
    assert resp1.status_code == 200
    trace1 = resp1.json()

    assert trace1["policy_decision"]["decision"] == "HUMAN_APPROVAL_REQUIRED"
    assert trace1["policy_decision"]["requires_human_approval"] is True
    assert any("RULE-EXT-COMM" in r for r in trace1["policy_decision"]["rules_triggered"])
    assert trace1["approval"]["status"] == "PENDING"
    assert trace1["approval"]["reviewer"] is None
    assert trace1["execution"]["status"] == "NOT_STARTED"

    # Human approves via API
    appr_resp = await client.post(f"/api/decisions/{com.next_action.id}/approve", json={"notes": "Signed off by Alex"})
    assert appr_resp.status_code == 200

    # Trace after approval & dispatch
    resp2 = await client.get(f"/api/commitments/{com.id}/trace")
    assert resp2.status_code == 200
    trace2 = resp2.json()

    assert trace2["current_state"] == "VERIFYING"
    assert trace2["approval"]["status"] == "APPROVED"
    assert trace2["approval"]["reviewer"] == "User"
    assert trace2["approval"]["authority"] == "Human Operator"
    assert trace2["approval"]["decision_timestamp"] is not None

    assert trace2["execution"]["status"] == "COMPLETED"
    assert trace2["execution"]["tool_name"] == "send_followup"
    assert trace2["execution"]["authority"] == "ExecutionEngine"
    assert "Dispatched" in trace2["execution"]["result_summary"]


@pytest.mark.asyncio
async def test_commitment_trace_contains_verification(api_client):
    """Verifies that verification state transitions, authoritative gate proofs, and final outcomes are reflected."""
    client, test_repo, _, _ = api_client
    com = _build_test_commitment()
    await test_repo.save(com)

    # 1. Approve & dispatch action
    await client.post(f"/api/decisions/{com.next_action.id}/approve", json={})

    # Check trace in VERIFYING state
    verif_trace_resp = await client.get(f"/api/commitments/{com.id}/trace")
    verif_trace = verif_trace_resp.json()
    assert verif_trace["current_state"] == "VERIFYING"
    assert verif_trace["verification"]["status"] == "IN_PROGRESS"
    assert verif_trace["final_outcome"]["is_resolved"] is False

    # 2. Simulate external counterparty reply (world changes)
    sim_resp = await client.post(f"/api/simulate/reply/{com.id}", json={"fulfilled": True})
    assert sim_resp.status_code == 200

    # 3. Fetch trace after successful verification
    resolved_resp = await client.get(f"/api/commitments/{com.id}/trace")
    assert resolved_resp.status_code == 200
    resolved_trace = resolved_resp.json()

    assert resolved_trace["current_state"] == "RESOLVED"
    assert resolved_trace["verification"]["status"] == "VERIFIED"
    assert resolved_trace["verification"]["gate_result"] == "PASSED"
    assert resolved_trace["verification"]["authority"] == "VerificationGate (Authoritative Verifier)"
    assert len(resolved_trace["verification"]["fresh_evidence"]) > 0

    assert resolved_trace["final_outcome"]["status"] == "RESOLVED"
    assert resolved_trace["final_outcome"]["is_resolved"] is True
    assert resolved_trace["final_outcome"]["resolved_at"] is not None
    assert "fulfilled and independently verified" in resolved_trace["final_outcome"]["summary"]


@pytest.mark.asyncio
async def test_commitment_trace_does_not_expose_private_reasoning(api_client):
    """Ensures no private chain-of-thought, internal prompts, or secrets are exposed in trace."""
    client, test_repo, _, _ = api_client
    com = _build_test_commitment()
    await test_repo.save(com)

    resp = await client.get(f"/api/commitments/{com.id}/trace")
    assert resp.status_code == 200
    raw_payload = resp.text

    # Security check: zero hidden reasoning or credentials leaked
    assert "chain_of_thought" not in raw_payload
    assert "model_internal_prompt" not in raw_payload
    assert "api_key" not in raw_payload
    assert "secret_token" not in raw_payload
    assert "db_connection" not in raw_payload


@pytest.mark.asyncio
async def test_commitment_trace_negative_scenario(api_client):
    """Tests Phase 13 negative scenario: verification rejection moves commitment to FAILED or VERIFYING, never RESOLVED."""
    client, test_repo, _, test_supervisor = api_client
    com = _build_test_commitment()
    await test_repo.save(com)

    # Approve action
    await client.post(f"/api/decisions/{com.next_action.id}/approve", json={})

    # Simulate counterparty negative outcome / dispute
    workspace_store.simulate_client_reply(com.id, fulfilled=False)

    # Trigger verification pass with simulated rejection
    await test_supervisor.verify_commitment(com.id, {"simulated_rejection": True, "mark_failed": True})

    neg_resp = await client.get(f"/api/commitments/{com.id}/trace")
    assert neg_resp.status_code == 200
    neg_trace = neg_resp.json()

    # The UI/API MUST NOT display RESOLVED
    assert neg_trace["current_state"] in ("VERIFYING", "FAILED")
    assert neg_trace["final_outcome"]["is_resolved"] is False
    assert neg_trace["verification"]["gate_result"] == "FAILED"
    assert neg_trace["final_outcome"]["status"] != "RESOLVED"


@pytest.mark.asyncio
async def test_commitment_trace_404_when_not_found(api_client):
    """Verifies that querying a non-existent commitment trace returns 404."""
    client, _, _, _ = api_client
    resp = await client.get("/api/commitments/com_nonexistent_999/trace")
    assert resp.status_code == 404
