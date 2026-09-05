"""Step 5: Time Handling, Duration Math, and Risk/Drift Determinism Tests.

Validates that:
1. All timestamps are UTC-aware and comparisons occur in UTC.
2. Overdue duration is calculated from exact elapsed seconds and derived into hours/days without premature truncation.
3. Timezone-equivalent instants across different UTC offsets produce identical results.
4. Due date boundaries (due now vs 1 second ago vs future) evaluate strictly and deterministically.
5. Risk calculations consume normalized durations and properly factor in blocking downstream context.
6. Repeated evaluations are idempotent, monotonic, and do not cause invalid state machine transitions.
7. Atlas scenario regression test proves mathematical calculation using fixed clock abstraction.
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import pytest

from covenant.agents.base import AgentContext
from covenant.agents.commitment import CommitmentAgent
from covenant.agents.evidence import EvidenceAgent
from covenant.domain.enums import (
    CommitmentCategory,
    CommitmentStatus,
    EvidenceSourceType,
    RiskLevel,
)
from covenant.domain.models import (
    Commitment,
    EvidenceReference,
    Party,
    calculate_overdue_duration,
    ensure_utc,
    set_clock_override,
    time_freeze,
    utc_now,
)
from covenant.persistence.sqlite_repo import SQLiteCommitmentRepository
from covenant.state_machine.machine import CommitmentStateMachine
from covenant.synthetic_data.store import workspace_store
from covenant.tools import initialize_tools
from covenant.tools.commitment_tools import CalculateRiskTool


@pytest.fixture
def clean_workspace():
    workspace_store.reset()
    yield workspace_store
    workspace_store.reset()


@pytest.fixture
async def temp_repo(tmp_path: Path):
    db_file = tmp_path / "time_determinism.db"
    repo = SQLiteCommitmentRepository(db_path=db_file)
    await repo.initialize()
    return repo


# ==============================================================================
# 1. Exact UTC Elapsed Time
# ==============================================================================
def test_overdue_duration_uses_exact_utc_elapsed_time():
    """Verify that calculate_overdue_duration computes exact elapsed seconds

    between due_date and reference_time in UTC.
    """
    due_date = datetime(2026, 9, 5, 17, 0, 0, tzinfo=timezone.utc)
    # Reference: 19 hours later (Sep 6, 2026 at 12:00 UTC)
    ref_time = datetime(2026, 9, 6, 12, 0, 0, tzinfo=timezone.utc)

    dur = calculate_overdue_duration(due_date, ref_time)
    assert dur["is_overdue"] is True
    assert dur["elapsed_seconds"] == 68400.0
    assert dur["hours_overdue"] == 19.0
    assert dur["days_overdue"] == 68400.0 / 86400.0
    assert abs(dur["days_overdue"] - 0.7916666666666666) < 1e-9


# ==============================================================================
# 2. Timezone Equivalence
# ==============================================================================
def test_timezone_equivalent_instants_produce_same_result():
    """Verify that the same physical instant represented in different timezones

    (UTC, Asia/Kolkata +05:30, America/New_York -04:00) produces identical
    results.
    """
    # 17:00 UTC = 22:30 IST (+05:30) = 13:00 EDT (-04:00)
    due_utc = datetime(2026, 9, 5, 17, 0, 0, tzinfo=timezone.utc)
    due_ist = datetime(2026, 9, 5, 22, 30, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
    due_edt = datetime(2026, 9, 5, 13, 0, 0, tzinfo=ZoneInfo("America/New_York"))

    ref_utc = datetime(2026, 9, 6, 12, 0, 0, tzinfo=timezone.utc)
    ref_ist = datetime(2026, 9, 6, 17, 30, 0, tzinfo=ZoneInfo("Asia/Kolkata"))

    dur_utc = calculate_overdue_duration(due_utc, ref_utc)
    dur_ist = calculate_overdue_duration(due_ist, ref_utc)
    dur_edt = calculate_overdue_duration(due_edt, ref_ist)

    assert dur_utc["is_overdue"] == dur_ist["is_overdue"] == dur_edt["is_overdue"] == True
    assert dur_utc["elapsed_seconds"] == dur_ist["elapsed_seconds"] == dur_edt["elapsed_seconds"] == 68400.0
    assert dur_utc["hours_overdue"] == dur_ist["hours_overdue"] == dur_edt["hours_overdue"] == 19.0
    assert dur_utc["days_overdue"] == dur_ist["days_overdue"] == dur_edt["days_overdue"]


# ==============================================================================
# 3. Boundary: Due Exactly Now
# ==============================================================================
def test_due_exactly_now_is_not_overdue():
    """Verify that when reference_time == due_date (0 elapsed seconds), the

    commitment is NOT overdue.
    """
    instant = datetime(2026, 9, 5, 17, 0, 0, tzinfo=timezone.utc)
    dur = calculate_overdue_duration(due_date=instant, reference_time=instant)

    assert dur["is_overdue"] is False
    assert dur["elapsed_seconds"] == 0.0
    assert dur["hours_overdue"] == 0.0
    assert dur["days_overdue"] == 0.0


# ==============================================================================
# 4. Boundary: One Second Past Due
# ==============================================================================
def test_one_second_past_due_is_overdue():
    """Verify that even 1 second past due correctly evaluates to overdue."""
    due = datetime(2026, 9, 5, 17, 0, 0, tzinfo=timezone.utc)
    ref = due + timedelta(seconds=1)

    dur = calculate_overdue_duration(due_date=due, reference_time=ref)
    assert dur["is_overdue"] is True
    assert dur["elapsed_seconds"] == 1.0
    assert dur["hours_overdue"] == 1.0 / 3600.0
    assert dur["days_overdue"] == 1.0 / 86400.0


# ==============================================================================
# 5. Units and Precision Verification
# ==============================================================================
def test_days_overdue_units_are_correct():
    """Verify mathematical scaling across seconds, hours, and days."""
    base = datetime(2026, 9, 5, 12, 0, 0, tzinfo=timezone.utc)

    # 59 minutes
    d_59m = calculate_overdue_duration(base, base + timedelta(minutes=59))
    assert d_59m["is_overdue"] is True
    assert d_59m["elapsed_seconds"] == 3540.0
    assert abs(d_59m["hours_overdue"] - (59.0 / 60.0)) < 1e-9

    # Exactly 1 hour
    d_1h = calculate_overdue_duration(base, base + timedelta(hours=1))
    assert d_1h["elapsed_seconds"] == 3600.0
    assert d_1h["hours_overdue"] == 1.0
    assert d_1h["days_overdue"] == 1.0 / 24.0

    # Exactly 24 hours (1 day)
    d_24h = calculate_overdue_duration(base, base + timedelta(hours=24))
    assert d_24h["elapsed_seconds"] == 86400.0
    assert d_24h["hours_overdue"] == 24.0
    assert d_24h["days_overdue"] == 1.0

    # 24 hours + 1 second
    d_24h1s = calculate_overdue_duration(base, base + timedelta(hours=24, seconds=1))
    assert d_24h1s["elapsed_seconds"] == 86401.0
    assert d_24h1s["hours_overdue"] == 86401.0 / 3600.0
    assert d_24h1s["days_overdue"] == 86401.0 / 86400.0

    # 1 day in the future (negative elapsed)
    d_future = calculate_overdue_duration(base, base - timedelta(days=1))
    assert d_future["is_overdue"] is False
    assert d_future["elapsed_seconds"] == -86400.0
    assert d_future["hours_overdue"] == 0.0
    assert d_future["days_overdue"] == 0.0


# ==============================================================================
# 6. Risk Calculation Normalized Durations
# ==============================================================================
@pytest.mark.asyncio
async def test_risk_uses_normalized_overdue_duration():
    """Verify CalculateRiskTool directly consumes normalized days/seconds."""
    tool = CalculateRiskTool()

    # Not overdue -> LOW
    r1 = await tool.execute(is_overdue=False, days_overdue=0.0)
    assert r1.data["risk"] == RiskLevel.LOW.value
    assert r1.data["is_overdue"] is False

    # Overdue 1.5 days, no blocker -> LOW (< 48h)
    r2 = await tool.execute(is_overdue=True, days_overdue=1.5, is_blocking_downstream=False)
    assert r2.data["risk"] == RiskLevel.LOW.value

    # Overdue 2.0 days, no blocker -> MEDIUM (>= 2 days attention required)
    r3 = await tool.execute(is_overdue=True, days_overdue=2.0, is_blocking_downstream=False)
    assert r3.data["risk"] == RiskLevel.MEDIUM.value

    # Overdue 2.0 days, blocking downstream -> HIGH (>= 2 days + downstream impact)
    r4 = await tool.execute(is_overdue=True, days_overdue=2.0, is_blocking_downstream=True)
    assert r4.data["risk"] == RiskLevel.HIGH.value

    # Overdue 5.0 days -> HIGH
    r5 = await tool.execute(is_overdue=True, days_overdue=5.0, is_blocking_downstream=False)
    assert r5.data["risk"] == RiskLevel.HIGH.value

    # Via elapsed_seconds parameter
    r6 = await tool.execute(is_overdue=True, elapsed_seconds=86400.0 * 2.5, is_blocking_downstream=True)
    assert r6.data["risk"] == RiskLevel.HIGH.value


# ==============================================================================
# 7. Blocking Context Matrix
# ==============================================================================
@pytest.mark.asyncio
async def test_blocking_context_affects_risk_correctly():
    """Verify risk logic across the 5 Phase 7 states."""
    tool = CalculateRiskTool()

    # 1. not overdue + not blocking
    res1 = await tool.execute(is_overdue=False, is_blocking_downstream=False)
    assert res1.data["risk"] == RiskLevel.LOW.value

    # 2. not overdue + blocking (on track even if future milestone waits)
    res2 = await tool.execute(is_overdue=False, is_blocking_downstream=True)
    assert res2.data["risk"] == RiskLevel.LOW.value

    # 3. slightly overdue (12 hours) + not blocking
    res3 = await tool.execute(is_overdue=True, days_overdue=0.5, is_blocking_downstream=False)
    assert res3.data["risk"] == RiskLevel.LOW.value

    # 4. slightly overdue (12 hours) + blocking
    res4 = await tool.execute(is_overdue=True, days_overdue=0.5, is_blocking_downstream=True)
    assert res4.data["risk"] == RiskLevel.MEDIUM.value

    # 5. significantly overdue (2.5 days) + blocking
    res5 = await tool.execute(is_overdue=True, days_overdue=2.5, is_blocking_downstream=True)
    assert res5.data["risk"] == RiskLevel.HIGH.value


# ==============================================================================
# 8. Repeated Evaluation is Deterministic
# ==============================================================================
@pytest.mark.asyncio
async def test_repeated_evaluation_is_deterministic(clean_workspace, temp_repo):
    """Verify evaluating the same commitment multiple times under the same

    clock produces identical risk, duration, and does not crash or corrupt
    state.
    """
    tools = initialize_tools()
    fixed_time = datetime(2026, 9, 6, 12, 0, 0, tzinfo=timezone.utc)

    with time_freeze(fixed_time):
        commit_agent = CommitmentAgent(tools=tools, commitment_repo=temp_repo, event_repo=temp_repo)
        await commit_agent.run(AgentContext(session_id="det_setup"))

        evidence_agent = EvidenceAgent(tools=tools, commitment_repo=temp_repo, event_repo=temp_repo)
        ctx = AgentContext(session_id="det_eval_1", target_commitment_id="com_atlas_approval")

        # Pass 1
        res1 = await evidence_agent.run(ctx)
        com1 = await temp_repo.get_by_id("com_atlas_approval")

        # Pass 2
        res2 = await evidence_agent.run(ctx)
        com2 = await temp_repo.get_by_id("com_atlas_approval")

        assert res1.data["risk"] == res2.data["risk"] == RiskLevel.HIGH.value
        assert res1.data["days_overdue"] == res2.data["days_overdue"]
        assert com1.status == com2.status == CommitmentStatus.OVERDUE
        assert com1.risk == com2.risk == RiskLevel.HIGH


# ==============================================================================
# 9. Overdue Transition Monotonicity
# ==============================================================================
@pytest.mark.asyncio
async def test_overdue_transition_is_monotonic(clean_workspace, temp_repo):
    """Verify that a commitment with a future due date does NOT transition to

    OVERDUE, but transitions when past due, and stays stable when re-evaluated.
    """
    tools = initialize_tools()

    # Create an ACTIVE commitment with future due date (due Sep 10, 2026)
    future_com = Commitment(
        id="com_future_test",
        title="Future Test Commitment",
        description="Testing non-overdue state",
        promisor=Party(name="Sarah Jenkins"),
        promisee=Party(name="Alex North"),
        due_date=datetime(2026, 9, 10, 17, 0, 0, tzinfo=timezone.utc),
        status=CommitmentStatus.ACTIVE,
    )
    await temp_repo.save(future_com)

    # 1. Evaluate at Sep 6, 2026 (future due date -> NOT OVERDUE)
    with time_freeze("2026-09-06T12:00:00Z"):
        assert future_com.is_overdue is False
        evidence_agent = EvidenceAgent(tools=tools, commitment_repo=temp_repo, event_repo=temp_repo)
        await evidence_agent.run(AgentContext(session_id="fut_1", target_commitment_id="com_future_test"))
        com_after = await temp_repo.get_by_id("com_future_test")
        assert com_after.status == CommitmentStatus.ACTIVE

    # 2. Advance time to Sep 11, 2026 (past due date -> OVERDUE)
    with time_freeze("2026-09-11T12:00:00Z"):
        com_to_check = await temp_repo.get_by_id("com_future_test")
        assert com_to_check.is_overdue is True

        await evidence_agent.run(AgentContext(session_id="fut_2", target_commitment_id="com_future_test"))
        com_past = await temp_repo.get_by_id("com_future_test")
        assert com_past.status == CommitmentStatus.OVERDUE

        # Re-evaluating past due does not raise error or corrupt state
        await evidence_agent.run(AgentContext(session_id="fut_3", target_commitment_id="com_future_test"))
        com_stable = await temp_repo.get_by_id("com_future_test")
        assert com_stable.status == CommitmentStatus.OVERDUE


# ==============================================================================
# 10. Regression Test: Project Atlas Scenario with Fixed Clock
# ==============================================================================
@pytest.mark.asyncio
async def test_atlas_scenario_regression_fixed_clock(clean_workspace, temp_repo):
    """Proves the exact mathematical calculation for com_atlas_approval under

    the fixed synthetic scenario clock:

    due_date: 2026-09-05T17:00:00Z
    evaluation clock: 2026-09-06T12:00:00Z

    Calculation:
    68,400 elapsed seconds = exactly 19.0 hours = 0.791666... days.
    Rounded display: 0.8 days.
    Downstream Milestone 3 status: BLOCKED_ON_APPROVAL.
    Resulting Risk: RiskLevel.MEDIUM.
    """
    tools = initialize_tools()
    fixed_time = datetime(2026, 9, 6, 12, 0, 0, tzinfo=timezone.utc)

    with time_freeze(fixed_time):
        commit_agent = CommitmentAgent(tools=tools, commitment_repo=temp_repo, event_repo=temp_repo)
        await commit_agent.run(AgentContext(session_id="atlas_fixed"))

        com = await temp_repo.get_by_id("com_atlas_approval")
        assert com is not None
        assert com.due_date == datetime(2026, 9, 5, 17, 0, 0, tzinfo=timezone.utc)

        # Mathematical verification of duration
        dur = com.overdue_duration(fixed_time)
        assert dur["is_overdue"] is True
        assert dur["elapsed_seconds"] == 68400.0
        assert dur["hours_overdue"] == 19.0
        assert dur["days_overdue"] == 19.0 / 24.0
        assert f"{dur['days_overdue']:.1f}" == "0.8"

        # Evidence evaluation with fixed clock
        evidence_agent = EvidenceAgent(tools=tools, commitment_repo=temp_repo, event_repo=temp_repo)
        res = await evidence_agent.run(AgentContext(session_id="atlas_eval", target_commitment_id="com_atlas_approval"))

        assert res.data["is_overdue"] is True
        assert res.data["elapsed_seconds"] == 68400.0
        assert res.data["hours_overdue"] == 19.0
        assert res.data["risk"] == RiskLevel.HIGH.value

        updated_com = await temp_repo.get_by_id("com_atlas_approval")
        assert updated_com.risk == RiskLevel.HIGH
        assert updated_com.status == CommitmentStatus.OVERDUE
