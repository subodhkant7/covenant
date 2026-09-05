"""Tests for BackgroundMonitor integration with SHADOW, LEGACY, and OFF modes."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import pytest

from covenant.agents.supervisor import SupervisorAgent
from covenant.domain.enums import CommitmentCategory, CommitmentStatus, RiskLevel
from covenant.domain.models import Commitment, Party
from covenant.llm.ollama_provider import DeterministicFallbackProvider
from covenant.orchestration.background_monitor import BackgroundMonitor
from covenant.persistence.sqlite_repo import SQLiteCommitmentRepository
from covenant.synthetic_data.store import workspace_store
from covenant.tools import initialize_tools

from covenant_runtime_bridge.shadow.contracts import ShadowMode
from covenant_runtime_bridge.shadow.harness import ShadowExecutionHarness
from covenant_runtime_bridge.shadow.metrics import shadow_metrics


def sample_monitor_atlas_commitment() -> Commitment:
    return Commitment(
        id="com_atlas_approval",
        title="Meridian Global Phase 2 Deliverable Formal Sign-Off",
        description="Sarah Jenkins promised formal written sign-off for Atlas deliverables.",
        category=CommitmentCategory.CLIENT_APPROVAL,
        promisor=Party(name="Sarah Jenkins", email="sjenkins@meridianglobal.com", organization="Meridian Global Corp"),
        promisee=Party(name="Alex North", email="alex@northstarstudio.com", organization="Northstar Studio LLC"),
        due_date=datetime.now(timezone.utc) - timedelta(days=2),
        status=CommitmentStatus.DUE,
        risk=RiskLevel.MEDIUM,
    )


@pytest.fixture(autouse=True)
def reset_world():
    workspace_store.reset()
    shadow_metrics.reset()
    yield
    workspace_store.reset()


@pytest.mark.asyncio
async def test_monitor_shadow_mode_active(tmp_path: Path):
    """Verify BackgroundMonitor in SHADOW mode executes shadow harness alongside legacy."""
    db_file = tmp_path / "monitor_shadow.db"
    repo = SQLiteCommitmentRepository(db_path=db_file)
    await repo.initialize()

    c = sample_monitor_atlas_commitment()
    await repo.save(c)

    tools = initialize_tools()
    llm = DeterministicFallbackProvider()
    supervisor = SupervisorAgent(llm=llm, tools=tools, commitment_repo=repo, event_repo=repo)

    harness = ShadowExecutionHarness(mode=ShadowMode.SHADOW)
    monitor = BackgroundMonitor(
        supervisor=supervisor,
        commitment_repo=repo,
        event_repo=repo,
        shadow_mode="SHADOW",
        shadow_harness=harness,
    )

    # Run scan cycle
    evaluated = await monitor.scan_cycle()
    assert evaluated == 1
    assert monitor.shadow_runs_count == 1

    # Check metrics
    summary = shadow_metrics.get_summary()
    assert summary["total_shadow_runs"] == 1
    assert summary["matches"] == 1


@pytest.mark.asyncio
async def test_monitor_legacy_mode_does_not_shadow(tmp_path: Path):
    """Verify BackgroundMonitor in LEGACY mode runs legacy only and triggers zero shadow runs."""
    db_file = tmp_path / "monitor_legacy.db"
    repo = SQLiteCommitmentRepository(db_path=db_file)
    await repo.initialize()

    c = sample_monitor_atlas_commitment()
    await repo.save(c)

    tools = initialize_tools()
    llm = DeterministicFallbackProvider()
    supervisor = SupervisorAgent(llm=llm, tools=tools, commitment_repo=repo, event_repo=repo)

    harness = ShadowExecutionHarness(mode=ShadowMode.SHADOW)
    monitor = BackgroundMonitor(
        supervisor=supervisor,
        commitment_repo=repo,
        event_repo=repo,
        shadow_mode="LEGACY",
        shadow_harness=harness,
    )

    evaluated = await monitor.scan_cycle()
    assert evaluated == 1
    assert monitor.shadow_runs_count == 0
    assert shadow_metrics.get_summary()["total_shadow_runs"] == 0


@pytest.mark.asyncio
async def test_monitor_shadow_fails_closed_safely(tmp_path: Path):
    """Verify BackgroundMonitor handles a crashing shadow harness gracefully without breaking legacy."""
    db_file = tmp_path / "monitor_fail_closed.db"
    repo = SQLiteCommitmentRepository(db_path=db_file)
    await repo.initialize()

    c = sample_monitor_atlas_commitment()
    await repo.save(c)

    tools = initialize_tools()
    llm = DeterministicFallbackProvider()
    supervisor = SupervisorAgent(llm=llm, tools=tools, commitment_repo=repo, event_repo=repo)

    class BrokenHarness:
        async def execute_scenario_b_approval_gated(self, **kwargs):
            raise RuntimeError("Simulated internal shadow failure")

    monitor = BackgroundMonitor(
        supervisor=supervisor,
        commitment_repo=repo,
        event_repo=repo,
        shadow_mode="SHADOW",
        shadow_harness=BrokenHarness(),
    )

    # Authoritative legacy cycle must succeed despite broken shadow harness!
    evaluated = await monitor.scan_cycle()
    assert evaluated == 1
    updated_c = await repo.get_by_id(c.id)
    assert updated_c.status in [CommitmentStatus.OVERDUE, CommitmentStatus.AWAITING_APPROVAL]
