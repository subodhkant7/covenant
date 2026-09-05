"""Shadow metrics aggregation and reporting with mathematically consistent accounting."""

import threading
from typing import Any, Dict, List, Tuple
from covenant_runtime_bridge.shadow.contracts import (
    MismatchCategory,
    ShadowComparison,
    ShadowRun,
)


class ShadowMetricsCollector:
    """
    Thread-safe collector for shadow run observations and comparisons.
    Enforces strict mathematical invariant:
    total_runs == sum(classification_counts.values())
    """

    def __init__(self):
        self._lock = threading.Lock()
        self.runs: List[ShadowRun] = []

    def record(self, run: ShadowRun) -> None:
        with self._lock:
            self.runs.append(run)

    def get_summary(self) -> Dict[str, Any]:
        with self._lock:
            total_runs = len(self.runs)
            completed_runs = [r for r in self.runs if r.status == "COMPLETED"]
            skipped_runs = [r for r in self.runs if r.status == "SHADOW_SKIPPED"]
            failed_runs = [r for r in self.runs if r.status == "FAILED"]

            matches = 0
            mismatches = 0
            # Initialize all categories to 0
            classification_counts: Dict[str, int] = {cat.value: 0 for cat in MismatchCategory}

            total_legacy_ms = 0.0
            total_runtime_ms = 0.0

            # Dimension-level counters: {dimension_name: [matches, total_evaluated]}
            dimension_stats: Dict[str, List[int]] = {
                "target_identification": [0, 0],
                "discovery_count": [0, 0],
                "action_classification": [0, 0],
                "approval_requirement": [0, 0],
                "tool_dispatch": [0, 0],
                "verification": [0, 0],
                "final_domain_state": [0, 0],
                "workspace_side_effects": [0, 0],
            }

            for r in self.runs:
                # Every run increments exactly one classification counter
                classification_counts[r.classification.value] = classification_counts.get(r.classification.value, 0) + 1

                if r.status == "COMPLETED" and r.comparison:
                    if r.comparison.overall_match:
                        matches += 1
                    else:
                        mismatches += 1

                    total_legacy_ms += r.comparison.legacy_duration_ms
                    total_runtime_ms += r.comparison.runtime_duration_ms

                    for dim, matched in r.comparison.category_matches.items():
                        if dim in dimension_stats:
                            dimension_stats[dim][1] += 1
                            if matched:
                                dimension_stats[dim][0] += 1

            comp_count = len(completed_runs)
            avg_leg = (total_legacy_ms / comp_count) if comp_count > 0 else 0.0
            avg_run = (total_runtime_ms / comp_count) if comp_count > 0 else 0.0

            # Convert dimension stats to string representations e.g. "100/100"
            dimension_parity = {
                dim: f"{stats[0]}/{stats[1]}" for dim, stats in dimension_stats.items()
            }

            # Verify mathematical consistency
            assert sum(classification_counts.values()) == total_runs, "Invariant violation: counts sum != total_runs"

            return {
                "total_shadow_runs": total_runs,
                "completed_runs": comp_count,
                "skipped_runs": len(skipped_runs),
                "failed_runs": len(failed_runs),
                "matches": matches,
                "mismatches": mismatches,
                "parity_rate_pct": round((matches / comp_count * 100), 2) if comp_count > 0 else 0.0,
                "classification_counts": classification_counts,
                "dimension_parity": dimension_parity,
                "avg_legacy_duration_ms": round(avg_leg, 2),
                "avg_runtime_duration_ms": round(avg_run, 2),
                "overhead_ratio": round(avg_run / avg_leg, 2) if avg_leg > 0 else 1.0,
            }

    def reset(self) -> None:
        with self._lock:
            self.runs.clear()


# Global singleton instance for runtime metrics monitoring
shadow_metrics = ShadowMetricsCollector()
