"""Step 4: End-to-end Tests for Covenant Commitment Intelligence Vertical Slice.

Proves the complete pipeline:
Workspace evidence
    ↓
Commitment discovery
    ↓
Commitment extraction
    ↓
Evidence corroboration
    ↓
Risk / drift assessment
    ↓
Commitment persistence
    ↓
Resolution / action proposal
    ↓
Policy evaluation
    ↓
Decision Surface (API)

Verifies that side effects remain unexecuted throughout this intelligence workflow.
"""

from datetime import datetime, timezone
from pathlib import Path
import pytest
from httpx import ASGITransport, AsyncClient

from covenant.agents.base import AgentContext
from covenant.agents.commitment import CommitmentAgent
from covenant.agents.evidence import EvidenceAgent
from covenant.agents.policy import PolicyAgent
from covenant.agents.resolution import ResolutionAgent
from covenant.agents.supervisor import SupervisorAgent
from covenant.api.main import app
import covenant.api.routes as routes
from covenant.domain.enums import (
    ActionStatus,
    ActionType,
    CommitmentStatus,
    EvidenceSourceType,
    PolicyDecisionType,
    RiskLevel,
)
from covenant.domain.models import Commitment, ProposedAction, utc_now
from covenant.llm.ollama_provider import DeterministicFallbackProvider
from covenant.persistence.sqlite_repo import SQLiteCommitmentRepository
from covenant.synthetic_data.store import workspace_store
from covenant.tools import initialize_tools
from covenant.tools.commitment_tools import CalculateRiskTool


@pytest.fixture
def clean_workspace():
    """Reset the synthetic workspace to baseline state before test."""
    workspace_store.reset()
    yield workspace_store
    workspace_store.reset()


@pytest.fixture
async def isolated_repo(tmp_path: Path):
    """Provide an isolated SQLite commitment repository."""
    db_file = tmp_path / "test_intelligence.db"
    repo = SQLiteCommitmentRepository(db_path=db_file)
    await repo.initialize()
    return repo


# ==============================================================================
# Test A — Commitment Discovery
# ==============================================================================
@pytest.mark.asyncio
async def test_a_commitment_discovery(clean_workspace, isolated_repo):
    """Given workspace evidence (EML-101, EML-102, CTR-2026-081), verify a real

    commitment is discovered and extracted with all expected structured
    fields.
    """
    tools = initialize_tools()
    llm = DeterministicFallbackProvider()
    agent = CommitmentAgent(llm=llm, tools=tools, commitment_repo=isolated_repo, event_repo=isolated_repo)

    ctx = AgentContext(session_id="discovery_test_001")
    result = await agent.run(ctx)

    assert result.success is True
    assert result.data.get("count", 0) >= 1
    assert "com_atlas_approval" in result.data.get("commitment_ids", [])

    # Retrieve discovered commitment
    com = await isolated_repo.get_by_id("com_atlas_approval")
    assert com is not None
    assert "Meridian Global" in com.title
    assert "Formal Sign-Off" in com.title
    assert com.promisor.name == "Sarah Jenkins"
    assert com.promisor.organization == "Meridian Global Corp"
    assert com.promisee.name == "Alex North"
    assert com.promisee.organization == "Northstar Studio LLC"
    assert com.due_date is not None
    assert com.due_date == datetime(2026, 9, 5, 17, 0, tzinfo=timezone.utc)
    assert "EML-102" in com.source_references
    assert "CTR-2026-081" in com.source_references
    assert "PRJ-ATLAS" in com.source_references

    # Initial evidence references attached during extraction
    source_ids = [e.source_id for e in com.evidence_references]
    assert "EML-102" in source_ids
    assert "CTR-2026-081" in source_ids


# ==============================================================================
# Test B — Evidence Corroboration
# ==============================================================================
@pytest.mark.asyncio
async def test_b_evidence_corroboration(clean_workspace, isolated_repo):
    """Verify the commitment is corroborated against at least two distinct

    workspace sources (PRJ-ATLAS milestone records and INBOX_SCAN).
    """
    tools = initialize_tools()
    llm = DeterministicFallbackProvider()

    # Step 1: Discover commitment
    commit_agent = CommitmentAgent(llm=llm, tools=tools, commitment_repo=isolated_repo, event_repo=isolated_repo)
    await commit_agent.run(AgentContext(session_id="corrob_setup"))

    # Step 2: Run EvidenceAgent
    evidence_agent = EvidenceAgent(llm=llm, tools=tools, commitment_repo=isolated_repo, event_repo=isolated_repo)
    ctx = AgentContext(
        session_id="corrob_test_002",
        target_commitment_id="com_atlas_approval",
        parameters={"effective_time": "2026-09-06T12:00:00+00:00"},
    )
    result = await evidence_agent.run(ctx)

    assert result.success is True
    com = await isolated_repo.get_by_id("com_atlas_approval")
    assert com is not None

    # Verify at least two corroborating evidence sources were attached
    ev_sources = {e.source_id: e for e in com.evidence_references}
    assert "PRJ-ATLAS" in ev_sources
    assert "INBOX_SCAN" in ev_sources

    # Verify project status evidence reflects downstream blocker
    atlas_ev = ev_sources["PRJ-ATLAS"]
    assert atlas_ev.source_type == EvidenceSourceType.PROJECT
    assert "SUBMITTED_AWAITING_APPROVAL" in atlas_ev.snippet
    assert "BLOCKED_ON_APPROVAL" in atlas_ev.snippet

    # Verify inbox corroboration reflects no formal sign-off received
    inbox_ev = ev_sources["INBOX_SCAN"]
    assert inbox_ev.source_type == EvidenceSourceType.EMAIL
    assert "Formal written sign-off found: False" in inbox_ev.snippet


# ==============================================================================
# Test C — Persistence
# ==============================================================================
@pytest.mark.asyncio
async def test_c_commitment_persistence(clean_workspace, isolated_repo):
    """Verify the discovered commitment survives round-trip persistence in

    SQLite with full fidelity of all relations, evidence, and audit logs.
    """
    tools = initialize_tools()
    llm = DeterministicFallbackProvider()

    # Discover and save
    commit_agent = CommitmentAgent(llm=llm, tools=tools, commitment_repo=isolated_repo, event_repo=isolated_repo)
    await commit_agent.run(AgentContext(session_id="persist_001"))

    # Retrieve and verify
    reloaded = await isolated_repo.get_by_id("com_atlas_approval")
    assert reloaded is not None
    assert reloaded.id == "com_atlas_approval"
    assert reloaded.title == "Meridian Global Phase 2 Deliverable Formal Sign-Off"
    assert len(reloaded.evidence_references) >= 2
    assert len(reloaded.source_references) == 3

    # Add an evidence reference and verify update persistence
    evidence_agent = EvidenceAgent(llm=llm, tools=tools, commitment_repo=isolated_repo, event_repo=isolated_repo)
    await evidence_agent.run(AgentContext(
        session_id="persist_002",
        target_commitment_id="com_atlas_approval",
        parameters={"effective_time": "2026-09-06T12:00:00+00:00"},
    ))

    reloaded_after_ev = await isolated_repo.get_by_id("com_atlas_approval")
    assert reloaded_after_ev is not None
    assert len(reloaded_after_ev.evidence_references) >= 4

    # Verify events were persisted to SQLite
    events = await isolated_repo.list_events(commitment_id="com_atlas_approval")
    assert len(events) >= 2
    event_actions = [e.action_name for e in events]
    assert "DISCOVER_COMMITMENT" in event_actions
    assert "CORROBORATE_EVIDENCE" in event_actions


# ==============================================================================
# Test D — Dynamic Risk & Drift Calculation
# ==============================================================================
@pytest.mark.asyncio
async def test_d_risk_drift_calculation(clean_workspace, isolated_repo):
    """Verify the correct risk/drift classification is derived dynamically from

    actual evidence inputs and CalculateRiskTool, rather than being hardcoded.
    """
    # 1. Test the calculation logic on various inputs
    tool = CalculateRiskTool()

    # Case 1: On track -> LOW
    res_on_track = await tool.execute(is_overdue=False)
    assert res_on_track.data["risk"] == RiskLevel.LOW.value

    # Case 2: Overdue under 48 hours with NO blocker -> LOW
    res_recent_noblock = await tool.execute(is_overdue=True, days_overdue=1.0, is_blocking_downstream=False)
    assert res_recent_noblock.data["risk"] == RiskLevel.LOW.value

    # Case 3: Overdue with downstream blocker (Project Atlas situation) -> MEDIUM
    res_atlas_situation = await tool.execute(is_overdue=True, days_overdue=0.8, is_blocking_downstream=True)
    assert res_atlas_situation.data["risk"] == RiskLevel.MEDIUM.value
    assert "downstream" in res_atlas_situation.data["rationale"].lower() or "attention" in res_atlas_situation.data["rationale"].lower()

    # Case 4: Overdue >= 2 days with downstream blocker -> HIGH
    res_high = await tool.execute(is_overdue=True, days_overdue=2.5, is_blocking_downstream=True)
    assert res_high.data["risk"] == RiskLevel.HIGH.value

    # 2. Test dynamic calculation through EvidenceAgent on Project Atlas
    tools = initialize_tools()
    llm = DeterministicFallbackProvider()
    commit_agent = CommitmentAgent(llm=llm, tools=tools, commitment_repo=isolated_repo, event_repo=isolated_repo)
    await commit_agent.run(AgentContext(session_id="risk_setup"))

    evidence_agent = EvidenceAgent(llm=llm, tools=tools, commitment_repo=isolated_repo, event_repo=isolated_repo)
    # Simulate current time as Sep 6, 2026 (0.8 days overdue with downstream blocker)
    await evidence_agent.run(AgentContext(
        session_id="risk_eval",
        target_commitment_id="com_atlas_approval",
        parameters={"effective_time": "2026-09-06T12:00:00+00:00"},
    ))

    com = await isolated_repo.get_by_id("com_atlas_approval")
    assert com is not None
    assert com.risk == RiskLevel.MEDIUM
    assert com.status == CommitmentStatus.OVERDUE


# ==============================================================================
# Test E — Resolution Proposal (Remedy Remains a Proposal)
# ==============================================================================
@pytest.mark.asyncio
async def test_e_resolution_proposal(clean_workspace, isolated_repo):
    """Verify ResolutionAgent generates an actionable proposed remedy citing

    Section 4.2, and that the remedy remains an unexecuted proposal.
    """
    tools = initialize_tools()
    llm = DeterministicFallbackProvider()

    # Setup commitment and corroborate evidence
    commit_agent = CommitmentAgent(llm=llm, tools=tools, commitment_repo=isolated_repo, event_repo=isolated_repo)
    await commit_agent.run(AgentContext(session_id="res_setup"))
    evidence_agent = EvidenceAgent(llm=llm, tools=tools, commitment_repo=isolated_repo, event_repo=isolated_repo)
    await evidence_agent.run(AgentContext(session_id="res_corrob", target_commitment_id="com_atlas_approval"))

    # Run ResolutionAgent
    res_agent = ResolutionAgent(llm=llm, tools=tools, commitment_repo=isolated_repo, event_repo=isolated_repo)
    result = await res_agent.run(AgentContext(session_id="res_run", target_commitment_id="com_atlas_approval"))

    assert result.success is True
    com = await isolated_repo.get_by_id("com_atlas_approval")
    assert com is not None
    assert com.status == CommitmentStatus.ACTION_READY
    assert com.next_action is not None

    action: ProposedAction = com.next_action
    assert action.action_type == ActionType.FOLLOWUP_EMAIL
    assert action.recipient == "sjenkins@meridianglobal.com"
    assert "Section 4.2" in action.payload.get("body", "")
    assert action.risk == com.risk
    assert action.requires_human_approval is True

    # Critical Step 4 Rule: Remedy has NOT executed
    assert action.status == ActionStatus.PROPOSED
    assert action.executed_at is None
    # No outbound email was dispatched into the workspace
    outbound_emails = [e for e in clean_workspace.emails if e["id"].startswith("EML-OUT-")]
    assert len(outbound_emails) == 0


# ==============================================================================
# Test F — Policy Evaluation
# ==============================================================================
@pytest.mark.asyncio
async def test_f_policy_decision(clean_workspace, isolated_repo):
    """Verify PolicyAgent evaluates RULE-EXT-COMM, produces

    HUMAN_APPROVAL_REQUIRED, and transitions state to AWAITING_APPROVAL.
    """
    tools = initialize_tools()
    llm = DeterministicFallbackProvider()

    # Run up to resolution proposal
    commit_agent = CommitmentAgent(llm=llm, tools=tools, commitment_repo=isolated_repo, event_repo=isolated_repo)
    await commit_agent.run(AgentContext(session_id="pol_setup"))
    evidence_agent = EvidenceAgent(llm=llm, tools=tools, commitment_repo=isolated_repo, event_repo=isolated_repo)
    await evidence_agent.run(AgentContext(session_id="pol_corrob", target_commitment_id="com_atlas_approval"))
    res_agent = ResolutionAgent(llm=llm, tools=tools, commitment_repo=isolated_repo, event_repo=isolated_repo)
    await res_agent.run(AgentContext(session_id="pol_res", target_commitment_id="com_atlas_approval"))

    # Run PolicyAgent
    policy_agent = PolicyAgent(llm=llm, tools=tools, commitment_repo=isolated_repo, event_repo=isolated_repo)
    result = await policy_agent.run(AgentContext(session_id="pol_run", target_commitment_id="com_atlas_approval"))

    assert result.success is True
    decision_data = result.data.get("decision", {})
    assert decision_data.get("decision") == PolicyDecisionType.HUMAN_APPROVAL_REQUIRED.value
    assert decision_data.get("requires_human_approval") is True
    assert any("RULE-EXT-COMM" in r for r in decision_data.get("rules_triggered", []))

    # Verify commitment and action state transitions
    com = await isolated_repo.get_by_id("com_atlas_approval")
    assert com is not None
    assert com.status == CommitmentStatus.AWAITING_APPROVAL
    assert com.required_human_approval is True
    assert com.next_action is not None
    assert com.next_action.status == ActionStatus.AWAITING_APPROVAL

    # Ensure side effect remains unexecuted
    assert com.next_action.executed_at is None
    assert not any(e["id"].startswith("EML-OUT-") for e in clean_workspace.emails)


# ==============================================================================
# Test G — API Visibility
# ==============================================================================
@pytest.mark.asyncio
async def test_g_api_visibility(clean_workspace, isolated_repo, monkeypatch):
    """Verify the resulting commitment and actionable decision can be retrieved

    through the real HTTP API (GET /api/decisions) and side effects remain
    unexecuted.
    """
    # Point the API router singleton to our isolated test repository
    monkeypatch.setattr(routes, "repo", isolated_repo)

    tools = initialize_tools()
    llm = DeterministicFallbackProvider()

    # Run complete intelligence pipeline to reach Decision Surface
    commit_agent = CommitmentAgent(llm=llm, tools=tools, commitment_repo=isolated_repo, event_repo=isolated_repo)
    await commit_agent.run(AgentContext(session_id="api_setup"))
    evidence_agent = EvidenceAgent(llm=llm, tools=tools, commitment_repo=isolated_repo, event_repo=isolated_repo)
    await evidence_agent.run(AgentContext(session_id="api_corrob", target_commitment_id="com_atlas_approval"))
    res_agent = ResolutionAgent(llm=llm, tools=tools, commitment_repo=isolated_repo, event_repo=isolated_repo)
    await res_agent.run(AgentContext(session_id="api_res", target_commitment_id="com_atlas_approval"))
    policy_agent = PolicyAgent(llm=llm, tools=tools, commitment_repo=isolated_repo, event_repo=isolated_repo)
    await policy_agent.run(AgentContext(session_id="api_pol", target_commitment_id="com_atlas_approval"))

    # Test through FastAPI HTTP client
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Query /api/decisions
        resp = await client.get("/api/decisions")
        assert resp.status_code == 200
        decisions = resp.json()

        # Verify our commitment appears on the Decision Surface
        atlas_decision = next((d for d in decisions if d["commitment_id"] == "com_atlas_approval"), None)
        assert atlas_decision is not None
        assert atlas_decision["commitment_title"] == "Meridian Global Phase 2 Deliverable Formal Sign-Off"
        assert atlas_decision["risk"] == "MEDIUM"
        assert atlas_decision["promisor"]["name"] == "Sarah Jenkins"
        assert atlas_decision["promisee"]["name"] == "Alex North"

        # Evidence references present
        evidence_list = atlas_decision["evidence"]
        assert len(evidence_list) >= 4
        ev_sources = [e["source_id"] for e in evidence_list]
        assert "EML-102" in ev_sources
        assert "CTR-2026-081" in ev_sources
        assert "PRJ-ATLAS" in ev_sources
        assert "INBOX_SCAN" in ev_sources

        # Proposed action present with unexecuted status
        action = atlas_decision["action"]
        assert action["action_type"] == "FOLLOWUP_EMAIL"
        assert action["status"] == "AWAITING_APPROVAL"
        assert action["requires_human_approval"] is True
        assert action["recipient"] == "sjenkins@meridianglobal.com"
        assert "Section 4.2" in action["payload"]["body"]

        # 2. Query /api/commitments/com_atlas_approval
        single_resp = await client.get("/api/commitments/com_atlas_approval")
        assert single_resp.status_code == 200
        com_payload = single_resp.json()
        assert com_payload["status"] == "AWAITING_APPROVAL"
        assert com_payload["risk"] == "MEDIUM"

    # Verify side effect was NOT executed
    assert not any(e["id"].startswith("EML-OUT-") for e in clean_workspace.emails)


# ==============================================================================
# Full End-to-End Orchestrated Scan Workflow
# ==============================================================================
@pytest.mark.asyncio
async def test_end_to_end_intelligence_workflow(clean_workspace, isolated_repo, monkeypatch):
    """Proves that a single supervisor scan cycle executes the entire

    intelligence pipeline seamlessly from workspace evidence to persisted
    decision surface without executing side effects.
    """
    monkeypatch.setattr(routes, "repo", isolated_repo)

    tools = initialize_tools()
    llm = DeterministicFallbackProvider()
    supervisor = SupervisorAgent(llm=llm, tools=tools, commitment_repo=isolated_repo, event_repo=isolated_repo)
    monkeypatch.setattr(routes, "supervisor", supervisor)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Trigger scan cycle via API
        scan_resp = await client.post("/api/scan")
        assert scan_resp.status_code == 200
        scan_data = scan_resp.json()
        assert scan_data["success"] is True

        # Fetch decisions
        dec_resp = await client.get("/api/decisions")
        assert dec_resp.status_code == 200
        decisions = dec_resp.json()

        # Decision exists on surface
        atlas = next((d for d in decisions if d["commitment_id"] == "com_atlas_approval"), None)
        assert atlas is not None
        assert atlas["risk"] == "MEDIUM"
        assert atlas["action"]["status"] == "AWAITING_APPROVAL"

        # Side effects NOT executed
        assert not any(e["id"].startswith("EML-OUT-") for e in clean_workspace.emails)
