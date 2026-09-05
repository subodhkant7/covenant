"""Semantic Comparator for shadow execution evaluation with rigorous evidence accounting."""

from typing import Any, Dict, List, Optional
from covenant_runtime_bridge.shadow.contracts import (
    DimensionMismatch,
    MismatchCategory,
    ShadowComparison,
    ShadowOutcome,
)
from covenant_runtime_bridge.shadow.isolation import (
    SyntheticWorkspaceStore,
    diff_workspace_states,
)


class SemanticComparator:
    """
    Evaluates semantic outcomes between legacy and runtime branches.
    Provides structured evidence for every discrepancy and avoids loose normalization.
    """

    @classmethod
    def compare(
        cls,
        scenario_name: str,
        shadow_run_id: str,
        trace_id: str,
        input_snapshot_id: str,
        legacy: ShadowOutcome,
        runtime: ShadowOutcome,
        initial_store: SyntheticWorkspaceStore,
        legacy_final_store: SyntheticWorkspaceStore,
        runtime_final_store: SyntheticWorkspaceStore,
    ) -> ShadowComparison:
        matches: Dict[str, bool] = {}
        classifications: Dict[str, MismatchCategory] = {}
        mismatches: List[DimensionMismatch] = []
        diff_summary: List[str] = []

        # 1. Target Equivalence
        leg_targets = sorted(legacy.target_ids)
        run_targets = sorted(runtime.target_ids)
        targets_match = (leg_targets == run_targets)
        matches["target_identification"] = targets_match
        classifications["target_identification"] = MismatchCategory.MATCH if targets_match else MismatchCategory.ADAPTER_BUG
        if not targets_match:
            mismatches.append(DimensionMismatch(
                dimension="target_identification",
                legacy_value=leg_targets,
                runtime_value=run_targets,
                classification=MismatchCategory.ADAPTER_BUG,
                reason="Identified targets differ between legacy and runtime branches.",
            ))
            diff_summary.append(f"Target mismatch: Legacy={leg_targets} vs Runtime={run_targets}")

        # 2. Discovery Count Equivalence
        disc_match = (legacy.discovered_count == runtime.discovered_count)
        matches["discovery_count"] = disc_match
        classifications["discovery_count"] = MismatchCategory.MATCH if disc_match else MismatchCategory.EXPECTED_DIFFERENCE
        if not disc_match:
            mismatches.append(DimensionMismatch(
                dimension="discovery_count",
                legacy_value=legacy.discovered_count,
                runtime_value=runtime.discovered_count,
                classification=MismatchCategory.EXPECTED_DIFFERENCE,
                reason="Discovered entity counts differ.",
            ))
            diff_summary.append(f"Discovery count: Legacy={legacy.discovered_count} vs Runtime={runtime.discovered_count}")

        # 3. Action Proposal Equivalence
        leg_actions = sorted(legacy.actions_proposed)
        run_actions = sorted(runtime.actions_proposed)
        actions_match = (leg_actions == run_actions)
        matches["action_classification"] = actions_match
        classifications["action_classification"] = MismatchCategory.MATCH if actions_match else MismatchCategory.SEMANTIC_DIFFERENCE if hasattr(MismatchCategory, "SEMANTIC_DIFFERENCE") else MismatchCategory.ADAPTER_BUG
        if not actions_match:
            mismatches.append(DimensionMismatch(
                dimension="action_classification",
                legacy_value=leg_actions,
                runtime_value=run_actions,
                classification=MismatchCategory.ADAPTER_BUG,
                reason="Proposed action types differ between branches.",
            ))
            diff_summary.append(f"Action mismatch: Legacy={leg_actions} vs Runtime={run_actions}")

        # 4. Approval Requirement Equivalence
        leg_appr = sorted(legacy.approvals_required)
        run_appr = sorted(runtime.approvals_required)
        approval_match = (bool(leg_appr) == bool(run_appr))
        matches["approval_requirement"] = approval_match
        classifications["approval_requirement"] = MismatchCategory.MATCH if approval_match else MismatchCategory.ADAPTER_BUG
        if not approval_match:
            mismatches.append(DimensionMismatch(
                dimension="approval_requirement",
                legacy_value=leg_appr,
                runtime_value=run_appr,
                classification=MismatchCategory.ADAPTER_BUG,
                reason="Policy authorization requirement differs between branches.",
            ))
            diff_summary.append(f"Approval requirement mismatch: Legacy={leg_appr} vs Runtime={run_appr}")

        # 5. Tool Selection Equivalence (Strict Operational Check)
        leg_tools = sorted(set(legacy.tools_invoked))
        run_tools = sorted(set(runtime.tools_invoked))
        tools_match = (leg_tools == run_tools)
        matches["tool_dispatch"] = tools_match
        classifications["tool_dispatch"] = MismatchCategory.MATCH if tools_match else MismatchCategory.ADAPTER_BUG
        if not tools_match:
            mismatches.append(DimensionMismatch(
                dimension="tool_dispatch",
                legacy_value=leg_tools,
                runtime_value=run_tools,
                classification=MismatchCategory.ADAPTER_BUG,
                reason=f"Tools dispatched differ: missing in runtime={[t for t in leg_tools if t not in run_tools]}, extra in runtime={[t for t in run_tools if t not in leg_tools]}",
            ))
            diff_summary.append(f"Tools mismatch: Legacy={leg_tools} vs Runtime={run_tools}")

        # 6. Verification Outcomes Equivalence
        ver_match = (legacy.verification_outcomes == runtime.verification_outcomes)
        matches["verification"] = ver_match
        classifications["verification"] = MismatchCategory.MATCH if ver_match else MismatchCategory.ADAPTER_BUG
        if not ver_match:
            mismatches.append(DimensionMismatch(
                dimension="verification",
                legacy_value=legacy.verification_outcomes,
                runtime_value=runtime.verification_outcomes,
                classification=MismatchCategory.ADAPTER_BUG,
                reason="Independent outcome verification results do not agree.",
            ))
            diff_summary.append(f"Verification mismatch: Legacy={legacy.verification_outcomes} vs Runtime={runtime.verification_outcomes}")

        # 7. Final Domain States
        states_match = True
        for cid, leg_st in legacy.final_domain_states.items():
            run_st = runtime.final_domain_states.get(cid, "UNKNOWN")
            if not cls._states_are_synonymous(leg_st, run_st):
                states_match = False
                mismatches.append(DimensionMismatch(
                    dimension="final_domain_state",
                    legacy_value=leg_st,
                    runtime_value=run_st,
                    classification=MismatchCategory.ADAPTER_BUG,
                    reason=f"Final state for commitment '{cid}' is incompatible: Legacy='{leg_st}' vs Runtime='{run_st}'",
                ))
                diff_summary.append(f"State mismatch for '{cid}': Legacy='{leg_st}' vs Runtime='{run_st}'")
        matches["final_domain_state"] = states_match
        classifications["final_domain_state"] = MismatchCategory.MATCH if states_match else MismatchCategory.ADAPTER_BUG

        # 8. Post-Run State Diff Comparison (Detecting hidden side-effects)
        leg_diff = diff_workspace_states(initial_store, legacy_final_store)
        run_diff = diff_workspace_states(initial_store, runtime_final_store)
        post_state_match = (
            leg_diff["new_emails_count"] == run_diff["new_emails_count"]
            and leg_diff["new_escalations_count"] == run_diff["new_escalations_count"]
            and len(leg_diff["modified_milestones"]) == len(run_diff["modified_milestones"])
        )
        matches["workspace_side_effects"] = post_state_match
        classifications["workspace_side_effects"] = MismatchCategory.MATCH if post_state_match else MismatchCategory.ENVIRONMENT_DIFFERENCE
        if not post_state_match:
            mismatches.append(DimensionMismatch(
                dimension="workspace_side_effects",
                legacy_value=leg_diff,
                runtime_value=run_diff,
                classification=MismatchCategory.ENVIRONMENT_DIFFERENCE,
                reason="Post-run sandbox world mutations (emails, escalations, milestones) differ.",
            ))
            diff_summary.append(f"Workspace side-effect diff: Legacy={leg_diff} vs Runtime={run_diff}")

        overall = len(mismatches) == 0
        overall_cat = MismatchCategory.MATCH if overall else mismatches[0].classification

        return ShadowComparison(
            scenario_name=scenario_name,
            shadow_run_id=shadow_run_id,
            trace_id=trace_id,
            input_snapshot_id=input_snapshot_id,
            legacy_initial_fingerprint=legacy.fingerprint_after,
            runtime_initial_fingerprint=runtime.fingerprint_after,
            input_equivalence=True,
            category_matches=matches,
            classifications=classifications,
            dimension_mismatches=mismatches,
            overall_classification=overall_cat,
            overall_match=overall,
            legacy_duration_ms=legacy.execution_duration_ms,
            runtime_duration_ms=runtime.execution_duration_ms,
            post_run_state_match=post_state_match,
            diff_summary=diff_summary,
        )

    @classmethod
    def _states_are_synonymous(cls, leg: str, run: str) -> bool:
        if leg == run:
            return True
        pairs = {
            ("RESOLVED", "COMPLETED"),
            ("COMPLETED", "RESOLVED"),
            ("AWAITING_APPROVAL", "BLOCKED"),
            ("BLOCKED", "AWAITING_APPROVAL"),
            ("OVERDUE", "PENDING"),
            ("OVERDUE", "COMPLETED"),
            ("INVESTIGATING", "RUNNING"),
            ("VERIFYING", "VERIFYING"),
        }
        return (leg, run) in pairs
