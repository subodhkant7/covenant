"""Step 9: Tests for Covenant Autonomous Monitoring Control Plane.

Validates:
- POST /api/monitoring/cycles
- GET /api/monitoring/cycles/{cycle_id}
- GET /api/monitoring/cycles (listing)
- Concurrency control (atomic reservation, HTTP 409 Conflict on concurrent trigger)
- Operational counters and telemetry recording (SUPERVISOR_CYCLE_START, SUPERVISOR_CYCLE_COMPLETE)
- Error semantics (failure reported as HTTP 500 with FAILED status, no false 200s)
- Security boundary (no private LLM chain-of-thought exposed)
- End-to-end Atlas lifecycle (discovery -> risk -> proposed action -> human approval)
- Post-dispatch verification cycle (VERIFYING -> fresh evidence -> RESOLVED)
- Idempotency across successive monitoring cycles
"""

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
import pytest
import httpx
from fastapi import FastAPI

from covenant.agents.supervisor import SupervisorAgent
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
    CommitmentStatus,
    ObligationDirection,
    RiskLevel,
)
from covenant.domain.models import utc_now
from covenant.persistence.sqlite_repo import SQLiteCommitmentRepository
from covenant.synthetic_data.store import workspace_store
from covenant_runtime_bridge.bootstrap import CovenantRuntimeBootstrap


@pytest.fixture
def clean_workspace():
    """Reset the synthetic workspace before and after test."""
    workspace_store.reset()
    yield workspace_store
    workspace_store.reset()


@pytest.fixture
async def control_plane_client(tmp_path: Path, clean_workspace):
    """Provides an HTTP client connected to an isolated test FastAPI application."""
    test_db = tmp_path / "test_monitoring_control_plane.db"
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

    # Restore
    routes_mod.repo = orig_repo
    routes_mod.supervisor = orig_supervisor
    routes_mod.runtime_env = orig_runtime_env


@pytest.mark.asyncio
async def test_start_monitoring_cycle(control_plane_client):
    """POST /api/monitoring/cycles starts a cycle and persists the result."""
    client, test_repo, _, _ = control_plane_client

    resp = await client.post("/api/monitoring/cycles")
    assert resp.status_code == 200
    data = resp.json()

    assert "cycle_id" in data
    assert data["cycle_id"].startswith("cycle_")
    assert data["status"] == "COMPLETED"
    assert data["commitments_scanned"] >= 4

    # Verify persisted in repository
    persisted = await test_repo.get_cycle_record(data["cycle_id"])
    assert persisted is not None
    assert persisted["cycle_id"] == data["cycle_id"]
    assert persisted["status"] == "COMPLETED"
    assert persisted["commitments_scanned"] == data["commitments_scanned"]


@pytest.mark.asyncio
async def test_get_monitoring_cycle(control_plane_client):
    """GET /api/monitoring/cycles/{cycle_id} returns the operational cycle record."""
    client, test_repo, _, _ = control_plane_client

    # Trigger cycle
    post_resp = await client.post("/api/monitoring/cycles")
    assert post_resp.status_code == 200
    cycle_id = post_resp.json()["cycle_id"]

    # Retrieve cycle
    get_resp = await client.get(f"/api/monitoring/cycles/{cycle_id}")
    assert get_resp.status_code == 200
    data = get_resp.json()

    assert data["cycle_id"] == cycle_id
    assert data["status"] == "COMPLETED"
    assert data["commitments_scanned"] >= 4
    assert isinstance(data["errors"], list)

    # 404 for unknown cycle
    notFound_resp = await client.get("/api/monitoring/cycles/cycle_unknown_999")
    assert notFound_resp.status_code == 404


@pytest.mark.asyncio
async def test_monitoring_cycle_response_contains_summary(control_plane_client):
    """Response exposes exact operational counters without unnecessary transient objects."""
    client, _, _, _ = control_plane_client

    resp = await client.post("/api/monitoring/cycles")
    assert resp.status_code == 200
    data = resp.json()

    expected_keys = [
        "cycle_id",
        "status",
        "started_at",
        "completed_at",
        "commitments_scanned",
        "commitments_changed",
        "actions_proposed",
        "approval_requests",
        "executions",
        "verifications",
        "resolved",
        "failed",
        "errors",
    ]
    for k in expected_keys:
        assert k in data, f"Key '{k}' missing from cycle response"

    assert isinstance(data["commitments_scanned"], int)
    assert isinstance(data["commitments_changed"], int)
    assert isinstance(data["actions_proposed"], int)
    assert isinstance(data["approval_requests"], int)
    assert isinstance(data["executions"], int)
    assert isinstance(data["verifications"], int)
    assert isinstance(data["resolved"], int)
    assert isinstance(data["failed"], int)
    assert isinstance(data["errors"], list)


@pytest.mark.asyncio
async def test_monitoring_cycle_records_start_and_completion_events(control_plane_client):
    """Cycle emits SUPERVISOR_CYCLE_START and SUPERVISOR_CYCLE_COMPLETE telemetry."""
    client, test_repo, _, _ = control_plane_client

    resp = await client.post("/api/monitoring/cycles")
    assert resp.status_code == 200
    cycle_id = resp.json()["cycle_id"]

    events = await test_repo.list_events(limit=100)
    cycle_events = [e for e in events if e.metadata and e.metadata.get("cycle_id") == cycle_id]

    start_events = [e for e in cycle_events if e.action_name == "SUPERVISOR_CYCLE_START"]
    complete_events = [e for e in cycle_events if e.action_name == "SUPERVISOR_CYCLE_COMPLETE"]

    assert len(start_events) == 1
    assert len(complete_events) == 1

    complete_meta = complete_events[0].metadata
    assert complete_meta["status"] == "COMPLETED"
    assert "commitments_scanned" in complete_meta
    assert "commitments_changed" in complete_meta
    assert "cycle_id" in complete_meta


@pytest.mark.asyncio
async def test_monitoring_cycle_uses_canonical_supervisor(control_plane_client):
    """API endpoint calls SupervisorAgent.run_monitoring_cycle directly."""
    client, _, _, test_supervisor = control_plane_client

    with patch.object(
        test_supervisor, "run_monitoring_cycle", wraps=test_supervisor.run_monitoring_cycle
    ) as mock_cycle:
        resp = await client.post("/api/monitoring/cycles")
        assert resp.status_code == 200
        mock_cycle.assert_called_once()


@pytest.mark.asyncio
async def test_concurrent_monitoring_cycle_trigger_is_controlled(control_plane_client):
    """Simultaneous monitoring triggers are controlled via persistent reservation (409 Conflict)."""
    client, test_repo, _, _ = control_plane_client

    # Manually reserve an active cycle
    active_cycle_id = "cycle_active_in_flight"
    reserved, _ = await test_repo.reserve_or_start_cycle(active_cycle_id)
    assert reserved is True

    # Next attempt via API must be rejected with 409 Conflict
    resp = await client.post("/api/monitoring/cycles")
    assert resp.status_code == 409
    detail = resp.json()["detail"]
    assert "active" in str(detail).lower() or active_cycle_id in str(detail)


@pytest.mark.asyncio
async def test_failed_monitoring_cycle_is_reported(control_plane_client):
    """Failure during a cycle results in HTTP 500 with FAILED status and no false 200."""
    client, test_repo, _, test_supervisor = control_plane_client

    # Simulate an internal failure inside the supervisor
    async def failing_cycle(ctx=None, cycle_id=None):
        raise RuntimeError("Simulated internal scanner failure")

    with patch.object(test_supervisor, "run_monitoring_cycle", side_effect=failing_cycle):
        resp = await client.post("/api/monitoring/cycles")
        assert resp.status_code == 500
        error_data = resp.json()["detail"]
        assert error_data["status"] == "FAILED"
        assert "Simulated internal scanner failure" in str(error_data["errors"])

        # Ensure cycle record was persisted with FAILED status
        failed_id = error_data["cycle_id"]
        persisted = await test_repo.get_cycle_record(failed_id)
        assert persisted is not None
        assert persisted["status"] == "FAILED"
        assert "Simulated internal scanner failure" in persisted["errors"][0]


@pytest.mark.asyncio
async def test_monitoring_cycle_does_not_expose_private_reasoning(control_plane_client):
    """Responses and persisted records expose only operational metadata, not private model reasoning."""
    client, _, _, _ = control_plane_client

    resp = await client.post("/api/monitoring/cycles")
    assert resp.status_code == 200
    data = resp.json()

    forbidden_fields = ["thought", "thoughts", "chain_of_thought", "internal_reasoning", "system_prompt", "raw_llm"]
    for field in forbidden_fields:
        assert field not in data, f"Forbidden private reasoning field '{field}' found in response"

    get_resp = await client.get(f"/api/monitoring/cycles/{data['cycle_id']}")
    assert get_resp.status_code == 200
    get_data = get_resp.json()

    for field in forbidden_fields:
        assert field not in get_data, f"Forbidden private reasoning field '{field}' found in GET response"


@pytest.mark.asyncio
async def test_end_to_end_atlas_monitoring_and_approval(control_plane_client):
    """
    Phase 10: Trigger cycle -> com_atlas_approval discovered, evaluated, risk assessed,
    follow-up proposed, policy requires approval, no autonomous side effect -> approve via API.
    """
    client, test_repo, _, _ = control_plane_client

    # 1. Trigger cycle via control plane
    cycle_resp = await client.post("/api/monitoring/cycles")
    assert cycle_resp.status_code == 200
    cycle_data = cycle_resp.json()
    assert cycle_data["status"] == "COMPLETED"
    assert cycle_data["approval_requests"] >= 1

    # 2. Verify Atlas state
    atlas = await test_repo.get_by_id("com_atlas_approval")
    assert atlas is not None
    assert atlas.status == CommitmentStatus.AWAITING_APPROVAL
    assert atlas.next_action is not None
    assert atlas.next_action.status == ActionStatus.AWAITING_APPROVAL
    action_id = atlas.next_action.id

    # 3. Approve through existing human approval endpoint
    appr_resp = await client.post(
        f"/api/decisions/{action_id}/approve",
        json={"notes": "Approved for Sarah Jenkins follow-up"},
    )
    assert appr_resp.status_code == 200
    appr_data = appr_resp.json()
    assert appr_data["success"] is True

    # 4. Commitment transitions to VERIFYING (not prematurely RESOLVED)
    updated_atlas = await test_repo.get_by_id("com_atlas_approval")
    assert updated_atlas.status == CommitmentStatus.VERIFYING


@pytest.mark.asyncio
async def test_post_dispatch_cycle_and_verification(control_plane_client):
    """
    Phase 11: After dispatch, trigger cycle (evaluates via VerificationAgent/Gate, unfulfilled).
    Then simulate client reply, trigger cycle again -> fresh evidence corroborated -> RESOLVED.
    """
    client, test_repo, _, _ = control_plane_client

    # 1. Initial cycle & approval
    await client.post("/api/monitoring/cycles")
    atlas = await test_repo.get_by_id("com_atlas_approval")
    await client.post(
        f"/api/decisions/{atlas.next_action.id}/approve",
        json={"notes": "Approved"},
    )
    atlas = await test_repo.get_by_id("com_atlas_approval")
    assert atlas.status == CommitmentStatus.VERIFYING

    # 2. Trigger monitoring cycle while still awaiting external client reply
    cycle_2 = await client.post("/api/monitoring/cycles")
    assert cycle_2.status_code == 200
    c2_data = cycle_2.json()
    assert c2_data["verifications"] >= 1
    assert c2_data["resolved"] == 0  # No premature resolution

    # 3. Simulate legitimate fulfillment by external actor in workspace
    workspace_store.simulate_client_reply("com_atlas_approval", fulfilled=True)

    # 4. Trigger next monitoring cycle
    cycle_3 = await client.post("/api/monitoring/cycles")
    assert cycle_3.status_code == 200
    c3_data = cycle_3.json()
    assert c3_data["verifications"] >= 1
    assert c3_data["resolved"] >= 1

    # 5. Verify commitment is now legitimately RESOLVED
    final_atlas = await test_repo.get_by_id("com_atlas_approval")
    assert final_atlas.status == CommitmentStatus.RESOLVED
    assert final_atlas.verification_result is not None
    assert final_atlas.verification_result.is_verified is True


@pytest.mark.asyncio
async def test_monitoring_cycle_idempotency(control_plane_client):
    """
    Phase 12: Triggering cycle twice against unchanged workspace produces no duplicate
    commitments, no duplicate proposals, and no duplicate outbound actions.
    """
    client, test_repo, _, _ = control_plane_client

    # First cycle
    c1 = await client.post("/api/monitoring/cycles")
    assert c1.status_code == 200
    comms_1 = await test_repo.list_all()
    count_1 = len(comms_1)

    # Second cycle with no workspace changes
    c2 = await client.post("/api/monitoring/cycles")
    assert c2.status_code == 200
    c2_data = c2.json()

    # In second cycle, nothing changed
    assert c2_data["commitments_changed"] == 0
    assert c2_data["actions_proposed"] == 0

    comms_2 = await test_repo.list_all()
    assert len(comms_2) == count_1
