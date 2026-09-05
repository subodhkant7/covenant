"""Tests for SemanticComparator hardening & negative mismatch detection (Sections 10 & 11)."""

import pytest

from covenant.synthetic_data.store import workspace_store
from covenant_runtime_bridge.shadow.isolation import clone_workspace_store
from covenant_runtime_bridge.shadow.comparator import SemanticComparator
from covenant_runtime_bridge.shadow.contracts import MismatchCategory, ShadowOutcome


@pytest.fixture
def base_stores():
    init = clone_workspace_store(workspace_store)
    leg = clone_workspace_store(init)
    run = clone_workspace_store(init)
    return init, leg, run


def test_comparator_detects_target_mismatch(base_stores):
    """Verify target entity difference is NOT normalized away and triggers DimensionMismatch."""
    init, leg, run = base_stores
    leg_out = ShadowOutcome(branch_name="LEGACY", target_ids=["com_atlas"], tools_invoked=["draft_followup"])
    run_out = ShadowOutcome(branch_name="RUNTIME", target_ids=["com_apex"], tools_invoked=["draft_followup"])

    comp = SemanticComparator.compare("Scenario", "s1", "t1", "snp1", leg_out, run_out, init, leg, run)
    assert comp.overall_match is False
    assert comp.category_matches["target_identification"] is False
    assert any(m.dimension == "target_identification" for m in comp.dimension_mismatches)


def test_comparator_detects_action_mismatch(base_stores):
    """Verify action type difference (FOLLOWUP_EMAIL vs ESCALATION) triggers mismatch."""
    init, leg, run = base_stores
    leg_out = ShadowOutcome(branch_name="LEGACY", actions_proposed=["FOLLOWUP_EMAIL"], tools_invoked=["draft_followup"])
    run_out = ShadowOutcome(branch_name="RUNTIME", actions_proposed=["ESCALATION"], tools_invoked=["create_escalation"])

    comp = SemanticComparator.compare("Scenario", "s1", "t1", "snp1", leg_out, run_out, init, leg, run)
    assert comp.overall_match is False
    assert comp.category_matches["action_classification"] is False


def test_comparator_detects_approval_requirement_mismatch(base_stores):
    """Verify approval requirement mismatch is detected."""
    init, leg, run = base_stores
    leg_out = ShadowOutcome(branch_name="LEGACY", approvals_required=["com_1"], tools_invoked=["draft_followup"])
    run_out = ShadowOutcome(branch_name="RUNTIME", approvals_required=[], tools_invoked=["draft_followup"])

    comp = SemanticComparator.compare("Scenario", "s1", "t1", "snp1", leg_out, run_out, init, leg, run)
    assert comp.overall_match is False
    assert comp.category_matches["approval_requirement"] is False


def test_comparator_detects_tool_dispatch_mismatch(base_stores):
    """Verify missing or extra tool invocations trigger tool_dispatch mismatch."""
    init, leg, run = base_stores
    leg_out = ShadowOutcome(branch_name="LEGACY", tools_invoked=["draft_followup", "send_followup"])
    run_out = ShadowOutcome(branch_name="RUNTIME", tools_invoked=["draft_followup", "unexpected_tool"])

    comp = SemanticComparator.compare("Scenario", "s1", "t1", "snp1", leg_out, run_out, init, leg, run)
    assert comp.overall_match is False
    assert comp.category_matches["tool_dispatch"] is False
    tool_mismatch = next(m for m in comp.dimension_mismatches if m.dimension == "tool_dispatch")
    assert "unexpected_tool" in tool_mismatch.reason


def test_comparator_detects_side_effect_difference(base_stores):
    """Verify that unrecorded or differing side effects in the workspace are detected."""
    init, leg, run = base_stores
    # Mutate legacy store with an extra email
    leg.send_email("a@b.com", ["c@d.com"], "Extra", "Body")

    leg_out = ShadowOutcome(branch_name="LEGACY", tools_invoked=["draft_followup"])
    run_out = ShadowOutcome(branch_name="RUNTIME", tools_invoked=["draft_followup"])

    comp = SemanticComparator.compare("Scenario", "s1", "t1", "snp1", leg_out, run_out, init, leg, run)
    assert comp.overall_match is False
    assert comp.category_matches["workspace_side_effects"] is False
    assert comp.classifications["workspace_side_effects"] == MismatchCategory.ENVIRONMENT_DIFFERENCE
