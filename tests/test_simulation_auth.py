"""Regression tests for dedicated /api/simulate/* authentication and authorization."""

import logging
from pathlib import Path
import pytest
import httpx
from fastapi import FastAPI

from covenant.api.routes import router
from covenant.config import settings
from covenant.domain.enums import (
    ActionStatus,
    ActionType,
    CommitmentStatus,
    ObligationDirection,
    RiskLevel,
)
from covenant.domain.models import Commitment, ProposedAction, Party
from covenant.persistence.sqlite_repo import SQLiteCommitmentRepository
from covenant.synthetic_data.store import workspace_store
from covenant_runtime_bridge.bootstrap import CovenantRuntimeBootstrap
from covenant.agents.supervisor import SupervisorAgent
from covenant.tools import initialize_tools
from covenant.llm.factory import get_model_provider


def _create_sample_commitment(
    cid: str,
    action_id: str,
    status: CommitmentStatus = CommitmentStatus.VERIFYING,
    action_status: ActionStatus = ActionStatus.COMPLETED,
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


@pytest.fixture
async def sim_test_env(tmp_path: Path):
    """Sets up an isolated test FastAPI environment."""
    test_db = tmp_path / "test_sim_auth.db"
    test_repo = SQLiteCommitmentRepository(db_path=test_db)
    await test_repo.initialize()

    workspace_store.reset()
    test_runtime_env = CovenantRuntimeBootstrap.assemble()
    test_tools = initialize_tools()
    test_llm = get_model_provider("deterministic")
    test_supervisor = SupervisorAgent(
        llm=test_llm,
        tools=test_tools,
        commitment_repo=test_repo,
        event_repo=test_repo,
    )

    import covenant.api.routes as routes_mod
    orig_repo = routes_mod.repo
    orig_supervisor = routes_mod.supervisor
    orig_runtime_env = routes_mod.runtime_env

    routes_mod.repo = test_repo
    routes_mod.supervisor = test_supervisor
    routes_mod.runtime_env = test_runtime_env

    # Seed a commitment in VERIFYING state for simulation tests
    sample_com = _create_sample_commitment("com_atlas_approval", "act_atlas_approval")
    await test_repo.save(sample_com)

    app = FastAPI()
    app.include_router(router)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client, test_repo

    routes_mod.repo = orig_repo
    routes_mod.supervisor = orig_supervisor
    routes_mod.runtime_env = orig_runtime_env


@pytest.mark.asyncio
async def test_simulate_without_token_returns_401(sim_test_env, monkeypatch):
    """1. POST without X-Simulation-Token returns 401."""
    client, _ = sim_test_env
    monkeypatch.setattr(settings, "simulation_token", "super-secret-test-token-xyz")
    monkeypatch.setattr(settings, "environment", "production")

    res = await client.post("/api/simulate/reply/com_atlas_approval", json={"fulfilled": True})
    assert res.status_code == 401
    assert res.json() == {"detail": "Unauthorized"}


@pytest.mark.asyncio
async def test_simulate_with_incorrect_token_returns_401(sim_test_env, monkeypatch):
    """2. POST with incorrect token returns 401."""
    client, _ = sim_test_env
    monkeypatch.setattr(settings, "simulation_token", "super-secret-test-token-xyz")
    monkeypatch.setattr(settings, "environment", "production")

    res = await client.post(
        "/api/simulate/reply/com_atlas_approval",
        headers={"X-Simulation-Token": "wrong-token-guess"},
        json={"fulfilled": True},
    )
    assert res.status_code == 401
    assert res.json() == {"detail": "Unauthorized"}


@pytest.mark.asyncio
async def test_simulate_with_correct_token_succeeds(sim_test_env, monkeypatch):
    """3. POST with correct token succeeds with expected simulation response."""
    client, test_repo = sim_test_env
    monkeypatch.setattr(settings, "simulation_token", "super-secret-test-token-xyz")
    monkeypatch.setattr(settings, "environment", "production")

    res = await client.post(
        "/api/simulate/reply/com_atlas_approval",
        headers={"X-Simulation-Token": "super-secret-test-token-xyz"},
        json={"fulfilled": True},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["incoming_email"] is not None
    assert "sjenkins@meridianglobal.com" in data["incoming_email"]["from"]

    # Verify commitment state updated to RESOLVED
    persisted = await test_repo.get_by_id("com_atlas_approval")
    assert persisted is not None
    assert persisted.status == CommitmentStatus.RESOLVED


@pytest.mark.asyncio
async def test_normal_application_routes_unaffected(sim_test_env, monkeypatch):
    """4. Normal application routes remain public/unchanged without simulation token."""
    client, _ = sim_test_env
    monkeypatch.setattr(settings, "simulation_token", "super-secret-test-token-xyz")
    monkeypatch.setattr(settings, "environment", "production")

    # Health
    h_res = await client.get("/api/health")
    assert h_res.status_code == 200
    assert h_res.json()["status"] == "healthy"

    # Model health
    m_res = await client.get("/api/health/model")
    assert m_res.status_code == 200

    # Commitments
    c_res = await client.get("/api/commitments")
    assert c_res.status_code == 200
    assert isinstance(c_res.json(), list)

    # Decisions
    d_res = await client.get("/api/decisions")
    assert d_res.status_code == 200

    # Stats
    s_res = await client.get("/api/stats")
    assert s_res.status_code == 200


@pytest.mark.asyncio
async def test_token_never_appears_in_response_or_logs(sim_test_env, monkeypatch, caplog):
    """5. Token never appears in response body or logs."""
    client, _ = sim_test_env
    secret_token = "ultra-private-test-token-never-leak-999"
    monkeypatch.setattr(settings, "simulation_token", secret_token)
    monkeypatch.setattr(settings, "environment", "production")

    with caplog.at_level(logging.DEBUG):
        # Test 401 response
        r1 = await client.post("/api/simulate/reply/com_atlas_approval", headers={"X-Simulation-Token": "bad"})
        assert secret_token not in r1.text

        # Test 200 response
        r2 = await client.post("/api/simulate/reply/com_atlas_approval", headers={"X-Simulation-Token": secret_token})
        assert secret_token not in r2.text

    for record in caplog.records:
        assert secret_token not in record.message


@pytest.mark.asyncio
async def test_production_fails_closed_when_token_unconfigured(sim_test_env, monkeypatch):
    """Production fails closed (401) if simulation_token is missing or empty."""
    client, _ = sim_test_env
    monkeypatch.setattr(settings, "simulation_token", None)
    monkeypatch.setattr(settings, "environment", "production")

    res = await client.post("/api/simulate/reply/com_atlas_approval", json={"fulfilled": True})
    assert res.status_code == 401
    assert res.json() == {"detail": "Unauthorized"}


@pytest.mark.asyncio
async def test_development_permits_simulation_when_token_unconfigured(sim_test_env, monkeypatch):
    """In development/local, if simulation_token is unset, simulation is allowed for local dev convenience."""
    client, _ = sim_test_env
    monkeypatch.setattr(settings, "simulation_token", None)
    monkeypatch.setattr(settings, "environment", "local")

    res = await client.post("/api/simulate/reply/com_atlas_approval", json={"fulfilled": True})
    assert res.status_code == 200
    assert res.json()["success"] is True
