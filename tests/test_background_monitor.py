"""Tests for the BackgroundMonitor autonomous service."""

import asyncio
from pathlib import Path
import pytest

from covenant.agents.base import AgentContext
from covenant.agents.supervisor import SupervisorAgent
from covenant.domain.enums import CommitmentStatus
from covenant.llm.ollama_provider import DeterministicFallbackProvider
from covenant.orchestration.background_monitor import BackgroundMonitor
from covenant.persistence.sqlite_repo import SQLiteCommitmentRepository
from covenant.synthetic_data.store import workspace_store
from covenant.tools import initialize_tools


@pytest.mark.asyncio
async def test_background_monitor_scan_cycle(tmp_path: Path):
    """Verify that BackgroundMonitor scans commitments and advances lifecycle autonomously."""
    db_file = tmp_path / "monitor_test.db"
    repo = SQLiteCommitmentRepository(db_path=db_file)
    await repo.initialize()
    workspace_store.reset()

    tools = initialize_tools()
    llm = DeterministicFallbackProvider()
    supervisor = SupervisorAgent(llm=llm, tools=tools, commitment_repo=repo, event_repo=repo)

    monitor = BackgroundMonitor(
        supervisor=supervisor,
        commitment_repo=repo,
        event_repo=repo,
        interval_seconds=1,
    )

    # Initial scan to discover commitments
    await supervisor.run(AgentContext(session_id="initial_run"))

    # Run monitor cycle
    count = await monitor.scan_cycle()
    assert count >= 3
    assert monitor.cycle_count == 1

    # Check that overdue commitment with policy was placed on Decision Surface
    atlas_com = await repo.get_by_id("com_atlas_approval")
    assert atlas_com.status == CommitmentStatus.AWAITING_APPROVAL

    # Simulate start and stop of background task
    monitor.start()
    assert monitor.is_running is True
    await asyncio.sleep(0.1)
    await monitor.stop()
    assert monitor.is_running is False
