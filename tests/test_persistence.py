"""Tests for SQLite Repository and Persistence."""

import os
from datetime import datetime, timezone
from pathlib import Path
import pytest

from covenant.domain.enums import CommitmentCategory, CommitmentStatus, RiskLevel
from covenant.domain.models import AgentEvent, Commitment, EvidenceReference, EvidenceSourceType, Party
from covenant.persistence.sqlite_repo import SQLiteCommitmentRepository


@pytest.fixture
async def temp_repo(tmp_path: Path):
    db_file = tmp_path / "test_covenant.db"
    repo = SQLiteCommitmentRepository(db_path=db_file)
    await repo.initialize()
    return repo


@pytest.mark.asyncio
async def test_sqlite_save_and_retrieve(temp_repo: SQLiteCommitmentRepository):
    c = Commitment(
        id="test_com_persist_01",
        title="Persist Test",
        description="Testing SQLite storage",
        category=CommitmentCategory.CLIENT_APPROVAL,
        promisor=Party(name="Sarah Jenkins", organization="Meridian Global"),
        promisee=Party(name="Alex North", organization="Northstar Studio"),
        due_date=datetime(2026, 9, 5, 17, 0, tzinfo=timezone.utc),
        status=CommitmentStatus.OVERDUE,
        risk=RiskLevel.MEDIUM,
        evidence_references=[
            EvidenceReference(
                source_type=EvidenceSourceType.EMAIL,
                source_id="EML-102",
                title="Promise Email",
                snippet="I will sign off by Friday.",
            )
        ],
    )

    await temp_repo.save(c)
    fetched = await temp_repo.get_by_id("test_com_persist_01")

    assert fetched is not None
    assert fetched.id == "test_com_persist_01"
    assert fetched.title == "Persist Test"
    assert fetched.status == CommitmentStatus.OVERDUE
    assert len(fetched.evidence_references) == 1
    assert fetched.evidence_references[0].source_id == "EML-102"


@pytest.mark.asyncio
async def test_sqlite_event_recording(temp_repo: SQLiteCommitmentRepository):
    evt = AgentEvent(
        commitment_id="test_com_persist_01",
        agent_name="SupervisorAgent",
        action_name="SCAN_START",
        summary="Automated scan started",
        rationale="Periodic evaluation",
    )
    await temp_repo.record_event(evt)

    events = await temp_repo.list_events(commitment_id="test_com_persist_01")
    assert len(events) == 1
    assert events[0].agent_name == "SupervisorAgent"
    assert events[0].summary == "Automated scan started"
