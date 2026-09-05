"""Shadow execution package for Covenant vs Runtime comparison."""

from covenant_runtime_bridge.shadow.comparator import SemanticComparator
from covenant_runtime_bridge.shadow.contracts import (
    MismatchCategory,
    ShadowComparison,
    ShadowMode,
    ShadowOutcome,
    ShadowRun,
)
from covenant_runtime_bridge.shadow.harness import ShadowExecutionHarness
from covenant_runtime_bridge.shadow.isolation import (
    ExternalSideEffectBlockedError,
    ExternalSideEffectGuard,
    clone_workspace_store,
    compute_workspace_fingerprint,
    diff_workspace_states,
)
from covenant_runtime_bridge.shadow.metrics import ShadowMetricsCollector, shadow_metrics

__all__ = [
    "MismatchCategory",
    "ShadowMode",
    "ShadowOutcome",
    "ShadowComparison",
    "ShadowRun",
    "SemanticComparator",
    "ExternalSideEffectBlockedError",
    "ExternalSideEffectGuard",
    "clone_workspace_store",
    "compute_workspace_fingerprint",
    "diff_workspace_states",
    "ShadowMetricsCollector",
    "shadow_metrics",
    "ShadowExecutionHarness",
]
