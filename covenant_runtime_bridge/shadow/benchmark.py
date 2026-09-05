"""Shadow Benchmark CLI: Executes reproducible shadow runs with verifiable accounting."""

import argparse
import asyncio
from datetime import datetime, timezone
import sys

from covenant.domain.enums import CommitmentCategory, CommitmentStatus, RiskLevel
from covenant.domain.models import Commitment, Party
from covenant.synthetic_data.store import workspace_store
from covenant_runtime_bridge.shadow.contracts import ShadowMode
from covenant_runtime_bridge.shadow.harness import ShadowExecutionHarness
from covenant_runtime_bridge.shadow.metrics import shadow_metrics


def sample_atlas_commitment() -> Commitment:
    return Commitment(
        id="com_atlas_approval",
        title="Meridian Global Phase 2 Deliverable Formal Sign-Off",
        description="Sarah Jenkins promised formal sign-off for Atlas deliverables.",
        category=CommitmentCategory.CLIENT_APPROVAL,
        promisor=Party(name="Sarah Jenkins", email="sjenkins@meridianglobal.com", organization="Meridian Global Corp"),
        promisee=Party(name="Alex North", email="alex@northstarstudio.com", organization="Northstar Studio LLC"),
        status=CommitmentStatus.OVERDUE,
        risk=RiskLevel.MEDIUM,
    )


async def run_benchmark(num_runs: int = 100) -> None:
    shadow_metrics.reset()
    harness = ShadowExecutionHarness(mode=ShadowMode.SHADOW)

    print(f"Starting Shadow Benchmark with {num_runs} requested runs...")
    started = 0

    for i in range(num_runs):
        started += 1
        # Scenario distribution:
        # - 85 runs Scenario B (Approval-Gated with full resolution & corroboration)
        # - 15 runs Scenario D (Verification failure / unfulfilled client reply)
        sim_corroboration = (i % 7 != 0)
        c = sample_atlas_commitment()

        scenario_name = (
            "Scenario B — Approval-Gated Action"
            if sim_corroboration
            else "Scenario D — Verification Failure"
        )
        await harness.execute_scenario_b_approval_gated(
            commitment=c,
            scenario_name=scenario_name,
            simulate_corroboration=sim_corroboration,
        )

    summary = shadow_metrics.get_summary()

    print("\nSHADOW BENCHMARK")
    print("================")
    print(f"Requested: {num_runs}")
    print(f"Started:   {started}")
    print(f"Completed: {summary['completed_runs']}")
    print(f"Skipped:   {summary['skipped_runs']}")
    print(f"Failed:    {summary['failed_runs']}\n")

    for cat_name, count in summary["classification_counts"].items():
        print(f"{cat_name}: {count}")

    print("\nDimension parity:")
    for dim, parity in summary["dimension_parity"].items():
        print(f"{dim:<26} {parity}")

    print(f"\nTiming Baseline (synthetic microbenchmark only):")
    print(f"Average Legacy Duration:  {summary['avg_legacy_duration_ms']} ms")
    print(f"Average Runtime Duration: {summary['avg_runtime_duration_ms']} ms")
    print(f"Ratio:                    {summary['overhead_ratio']}x")


def main():
    parser = argparse.ArgumentParser(description="Run Shadow Benchmark Suite")
    parser.add_argument("--runs", type=int, default=100, help="Number of benchmark shadow runs to execute")
    args = parser.parse_args()

    asyncio.run(run_benchmark(num_runs=args.runs))


if __name__ == "__main__":
    main()
