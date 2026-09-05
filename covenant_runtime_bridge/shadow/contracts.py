"""Shadow execution contracts, outcomes, and metrics for behavioral parity evaluation."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4


class MismatchCategory(str, Enum):
    """Scientific categorization of observable behavioral discrepancies."""
    MATCH = "MATCH"
    EXPECTED_DIFFERENCE = "EXPECTED_DIFFERENCE"
    LEGACY_BUG = "LEGACY_BUG"
    RUNTIME_BUG = "RUNTIME_BUG"
    ADAPTER_BUG = "ADAPTER_BUG"
    ENVIRONMENT_DIFFERENCE = "ENVIRONMENT_DIFFERENCE"
    UNEXPLAINED = "UNEXPLAINED"
    SHADOW_SKIPPED = "SHADOW_SKIPPED"


class ShadowMode(str, Enum):
    """Operational mode for shadow comparison."""
    OFF = "OFF"          # Shadow execution disabled; legacy authoritative
    SHADOW = "SHADOW"    # Shadow comparison active; legacy authoritative, runtime observational
    LEGACY = "LEGACY"    # Legacy only (identical to OFF)


@dataclass
class ShadowOutcome:
    """Standardized record of observable outcomes from an isolated execution branch."""
    branch_name: str  # "LEGACY" or "RUNTIME"
    target_ids: List[str] = field(default_factory=list)
    discovered_count: int = 0
    investigated_count: int = 0
    actions_proposed: List[str] = field(default_factory=list)
    approvals_required: List[str] = field(default_factory=list)
    tools_invoked: List[str] = field(default_factory=list)
    side_effects_produced: List[Dict[str, Any]] = field(default_factory=list)
    verification_outcomes: Dict[str, bool] = field(default_factory=dict)
    final_domain_states: Dict[str, str] = field(default_factory=dict)
    execution_duration_ms: float = 0.0
    success: bool = True
    error: Optional[str] = None
    fingerprint_after: str = ""


@dataclass
class DimensionMismatch:
    """Structured evidence for a specific behavioral discrepancy."""
    dimension: str
    legacy_value: Any
    runtime_value: Any
    classification: MismatchCategory
    reason: str


@dataclass
class ShadowComparison:
    """Evaluates semantic equivalence between legacy and runtime shadow branches."""
    scenario_name: str
    shadow_run_id: str
    trace_id: str
    input_snapshot_id: str
    legacy_initial_fingerprint: str
    runtime_initial_fingerprint: str
    input_equivalence: bool
    category_matches: Dict[str, bool] = field(default_factory=dict)
    classifications: Dict[str, MismatchCategory] = field(default_factory=dict)
    dimension_mismatches: List[DimensionMismatch] = field(default_factory=list)
    overall_classification: MismatchCategory = MismatchCategory.MATCH
    overall_match: bool = True
    legacy_duration_ms: float = 0.0
    runtime_duration_ms: float = 0.0
    post_run_state_match: bool = True
    diff_summary: List[str] = field(default_factory=list)


@dataclass
class ShadowRun:
    """Full envelope for a shadow run attempt."""
    shadow_run_id: str = field(default_factory=lambda: f"shd_{uuid4().hex[:8]}")
    trace_id: str = field(default_factory=lambda: f"trc_{uuid4().hex[:8]}")
    input_snapshot_id: str = field(default_factory=lambda: f"snp_{uuid4().hex[:8]}")
    mode: ShadowMode = ShadowMode.SHADOW
    status: str = "COMPLETED"  # "COMPLETED", "SHADOW_SKIPPED", "FAILED"
    classification: MismatchCategory = MismatchCategory.MATCH
    legacy_outcome: Optional[ShadowOutcome] = None
    runtime_outcome: Optional[ShadowOutcome] = None
    comparison: Optional[ShadowComparison] = None
    skip_reason: Optional[str] = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
