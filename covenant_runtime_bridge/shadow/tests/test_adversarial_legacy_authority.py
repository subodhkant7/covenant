"""Adversarial Legacy Authority Invariant Tests."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import pytest

from covenant.agents.supervisor import SupervisorAgent
from covenant.domain.enums import CommitmentStatus
from covenant.llm.ollama_provider import DeterministicFallbackProvider
from covenant.orchestration.background_monitor import BackgroundMonitor
from covenant.persistence.sqlite_repo import SQLiteCommitmentRepository
from covenant.tools import initialize_tools

from covenant_runtime_bridge.shadow.benchmark import sample_atlas_commitment
from covenant_runtime_bridge.shadow.contracts import ShadowMode, ShadowOutcome
from covenant_runtime_bridge.shadow.harness import ShadowExecutionHarness


def overdue_atlas_commitment():
    c = sample_atlas_commitment()
    c.due_date = datetime.now(timezone.utc) - timedelta(days=2)
    c.status = CommitmentStatus.DUE
    return c


@pytest.mark.asyncio
async def test_legacy_authority_preserved_when_runtime_crashes(tmp_path: Path):
    """
    CRITICAL INVARIANT:
    Legacy succeeds, Runtime crashes -> Legacy result returned authoritatively.
    Runtime crash MUST NOT abort or corrupt the authoritative workflow.
    """
    db_file = tmp_path / "auth_runtime_crash.db"
    repo = SQLiteCommitmentRepository(db_path=db_file)
    await repo.initialize()

    c = overdue_atlas_commitment()
    await repo.save(c)

    tools = initialize_tools()
    llm = DeterministicFallbackProvider()
    supervisor = SupervisorAgent(llm=llm, tools=tools, commitment_repo=repo, event_repo=repo)

    class CrashingRuntimeHarness(ShadowExecutionHarness):
        async def _run_runtime_branch(self, *args, **kwargs):
            raise RuntimeError("Catastrophic runtime bridge crash simulated")

    harness = CrashingRuntimeHarness(mode=ShadowMode.SHADOW)
    monitor = BackgroundMonitor(
        supervisor=supervisor,
        commitment_repo=repo,
        event_repo=repo,
        shadow_mode="SHADOW",
        shadow_harness=harness,
    )

    # Monitor scan cycle must complete without propagating the runtime crash
    evaluated = await monitor.scan_cycle()
    assert evaluated == 1

    # Authoritative legacy transition succeeded
    updated = await repo.get_by_id(c.id)
    assert updated.status in (CommitmentStatus.OVERDUE, CommitmentStatus.ACTION_READY, CommitmentStatus.AWAITING_APPROVAL)


@pytest.mark.asyncio
async def test_legacy_authority_preserved_when_runtime_returns_mismatch(tmp_path: Path):
    """
    CRITICAL INVARIANT:
    Legacy produces Outcome A, Runtime produces Outcome B.
    Authoritative production state must reflect Outcome A (Legacy), NOT Outcome B (Runtime).
    """
    db_file = tmp_path / "auth_mismatch.db"
    repo = SQLiteCommitmentRepository(db_path=db_file)
    await repo.initialize()

    c = overdue_atlas_commitment()
    await repo.save(c)

    tools = initialize_tools()
    llm = DeterministicFallbackProvider()
    supervisor = SupervisorAgent(llm=llm, tools=tools, commitment_repo=repo, event_repo=repo)

    class MismatchingRuntimeHarness(ShadowExecutionHarness):
        async def _run_runtime_branch(self, *args, **kwargs):
            return ShadowOutcome(
                branch_name="RUNTIME",
                target_ids=["com_completely_wrong_target"],
                final_domain_states={"com_completely_wrong_target": "REJECTED"},
                success=True,
            )

    harness = MismatchingRuntimeHarness(mode=ShadowMode.SHADOW)
    monitor = BackgroundMonitor(
        supervisor=supervisor,
        commitment_repo=repo,
        event_repo=repo,
        shadow_mode="SHADOW",
        shadow_harness=harness,
    )

    await monitor.scan_cycle()

    # Authoritative DB reflects real target c.id, never the runtime mismatch target
    assert (await repo.get_by_id("com_completely_wrong_target")) is None
    authoritative_c = await repo.get_by_id(c.id)
    assert authoritative_c is not None
    assert authoritative_c.status != CommitmentStatus.REJECTED


@pytest.mark.asyncio
async def test_no_silent_runtime_takeover_when_legacy_fails(tmp_path: Path):
    """
    CRITICAL INVARIANT:
    Legacy crashes, Runtime succeeds.
    System MUST NOT silently swap in the runtime result as authoritative.
    Legacy authority means legacy failure fails the production cycle loudly.
    """
    db_file = tmp_path / "legacy_crash.db"
    repo = SQLiteCommitmentRepository(db_path=db_file)
    await repo.initialize()

    c = overdue_atlas_commitment()
    await repo.save(c)

    class CrashingSupervisor:
        class FakeEvidenceAgent:
            async def run(self, *args, **kwargs):
                raise RuntimeError("Legacy supervisor crashed!")

        evidence_agent = FakeEvidenceAgent()
        resolution_agent = FakeEvidenceAgent()
        policy_agent = FakeEvidenceAgent()

    harness = ShadowExecutionHarness(mode=ShadowMode.SHADOW)
    monitor = BackgroundMonitor(
        supervisor=CrashingSupervisor(),
        commitment_repo=repo,
        event_repo=repo,
        shadow_mode="SHADOW",
        shadow_harness=harness,
    )

    # Legacy crash MUST raise or fail the cycle, NOT silently report success with runtime state
    with pytest.raises(RuntimeError) as exc_info:
        await monitor.scan_cycle()
    assert "Legacy supervisor crashed!" in str(exc_info.value)
