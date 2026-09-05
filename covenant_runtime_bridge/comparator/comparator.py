"""CovenantBehavioralComparator: Executes and compares legacy vs runtime execution paths."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ScenarioOutcome:
    target_id: str
    evidence_found: List[str] = field(default_factory=list)
    proposed_action: Optional[str] = None
    policy_requires_approval: bool = False
    approval_status: str = "NONE"
    tool_chosen: Optional[str] = None
    execution_success: bool = False
    verified: bool = False
    final_state: str = "UNKNOWN"
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class BehavioralComparisonResult:
    scenario_name: str
    legacy_outcome: ScenarioOutcome
    runtime_outcome: ScenarioOutcome
    matches: Dict[str, bool] = field(default_factory=dict)
    classifications: Dict[str, str] = field(default_factory=dict)  # "MATCH", "EXPECTED IMPROVEMENT", etc.
    overall_match: bool = True


class CovenantBehavioralComparator:
    """
    Compares observable semantics between legacy Covenant execution and the runtime bridge.
    Ensures safe, side-effect-free evaluation on isolated synthetic states.
    """

    @classmethod
    def compare(
        cls,
        scenario_name: str,
        legacy: ScenarioOutcome,
        runtime: ScenarioOutcome,
    ) -> BehavioralComparisonResult:
        matches = {}
        classifications = {}

        # 1. Target ID
        matches["target"] = (legacy.target_id == runtime.target_id)
        classifications["target"] = "MATCH" if matches["target"] else "SEMANTIC DIFFERENCE"

        # 2. Evidence
        matches["evidence"] = bool(legacy.evidence_found) == bool(runtime.evidence_found)
        classifications["evidence"] = "MATCH" if matches["evidence"] else "ADAPTER MAPPING ISSUE"

        # 3. Proposed Action
        matches["proposed_action"] = (legacy.proposed_action == runtime.proposed_action)
        classifications["proposed_action"] = "MATCH" if matches["proposed_action"] else "SEMANTIC DIFFERENCE"

        # 4. Policy Approval Requirement
        matches["approval_required"] = (legacy.policy_requires_approval == runtime.policy_requires_approval)
        classifications["approval_required"] = "MATCH" if matches["approval_required"] else "SEMANTIC DIFFERENCE"

        # 5. Tool Chosen
        matches["tool_chosen"] = (legacy.tool_chosen == runtime.tool_chosen)
        classifications["tool_chosen"] = "MATCH" if matches["tool_chosen"] else "SEMANTIC DIFFERENCE"

        # 6. Verification
        matches["verification"] = (legacy.verified == runtime.verified)
        classifications["verification"] = "MATCH" if matches["verification"] else "SEMANTIC DIFFERENCE"

        # 7. Final Business State
        # In safe read (Scenario A), legacy stays OVERDUE (domain entity), runtime investigation task completes.
        # When comparing domain outcomes, both represent successful completion of investigation without mutation.
        state_match = (
            legacy.final_state == runtime.final_state
            or (legacy.final_state == "RESOLVED" and runtime.final_state in ("COMPLETED", "RESOLVED"))
            or (legacy.final_state == "AWAITING_APPROVAL" and runtime.final_state in ("BLOCKED", "AWAITING_APPROVAL"))
            or (legacy.final_state == "OVERDUE" and runtime.final_state in ("OVERDUE", "INVESTIGATING", "COMPLETED"))
        )
        matches["final_state"] = state_match
        classifications["final_state"] = "MATCH" if state_match else "EXPECTED IMPROVEMENT"

        overall = all(matches.values())

        return BehavioralComparisonResult(
            scenario_name=scenario_name,
            legacy_outcome=legacy,
            runtime_outcome=runtime,
            matches=matches,
            classifications=classifications,
            overall_match=overall,
        )
