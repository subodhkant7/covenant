"""Benchmark Data Models & Evaluation Contracts.

Defines strongly typed contracts for benchmark cases, expected outcomes,
and evaluation metrics independently from runtime implementation details.
"""

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from covenant.domain.enums import (
    ActionType,
    CommitmentStatus,
    ObligationDirection,
    PolicyDecisionType,
    RiskLevel,
    StatementType,
)


class BenchmarkCategory(str, Enum):
    COMMITMENT_UNDERSTANDING = "COMMITMENT_UNDERSTANDING"
    EVIDENCE_REASONING = "EVIDENCE_REASONING"
    RISK_ASSESSMENT = "RISK_ASSESSMENT"
    ACTION_POLICY = "ACTION_POLICY"
    VERIFICATION = "VERIFICATION"


class ExpectedOutcome(BaseModel):
    """Independently defined expected outcomes for a benchmark case."""
    commitment_detected: Optional[bool] = None
    statement_type: Optional[StatementType] = None
    obligation_direction: Optional[ObligationDirection] = None
    evidence_classification: Optional[str] = None  # e.g. "FACT", "INFERENCE", "CORROBORATION", "GAP", "CONTRADICTION"
    evidence_gap_detected: Optional[bool] = None
    contradiction_detected: Optional[bool] = None
    risk_level: Optional[RiskLevel] = None
    recommended_action: Optional[ActionType] = None
    policy_decision: Optional[PolicyDecisionType] = None
    approval_required: Optional[bool] = None
    execution_allowed: Optional[bool] = None
    verification_required: Optional[bool] = None
    final_state: Optional[CommitmentStatus] = None


class BenchmarkCase(BaseModel):
    """Single benchmark scenario with independent inputs and expectations."""
    id: str
    name: str
    category: BenchmarkCategory
    description: str
    is_adversarial: bool = False
    input_payload: Dict[str, Any] = Field(default_factory=dict)
    expected: ExpectedOutcome


class CaseEvaluationResult(BaseModel):
    """Evaluation result for an individual benchmark case."""
    case_id: str
    case_name: str
    category: BenchmarkCategory
    passed: bool
    is_adversarial: bool = False
    checks: Dict[str, bool] = Field(default_factory=dict)
    failures: List[str] = Field(default_factory=list)
    observed: Dict[str, Any] = Field(default_factory=dict)
    expected: Dict[str, Any] = Field(default_factory=dict)


class BenchmarkMetrics(BaseModel):
    """Comprehensive benchmark metrics calculated across all cases."""
    total_cases: int = 0
    passed_cases: int = 0
    pass_rate: float = 0.0

    # Core Reasoning & Classification Metrics
    commitment_extraction_accuracy: float = 0.0
    evidence_grounding_accuracy: float = 0.0
    evidence_gap_detection_rate: float = 0.0
    contradiction_detection_accuracy: float = 0.0
    risk_classification_accuracy: float = 0.0
    policy_correctness_rate: float = 0.0

    # Strict Zero-Tolerance Safety Invariant Metrics
    approval_bypass_rate: float = 0.0  # Target: 0.0%
    false_resolution_rate: float = 0.0  # Target: 0.0%
    stale_proof_acceptance_rate: float = 0.0  # Target: 0.0%
    execution_fulfillment_conflation_rate: float = 0.0  # Target: 0.0%


class BenchmarkReport(BaseModel):
    """Consolidated benchmark evaluation report with structured accounting."""
    timestamp: str
    total_cases: int
    passed_cases: int
    failed_cases: int
    pass_rate: float
    category_scores: Dict[str, Dict[str, int]]
    metrics: BenchmarkMetrics
    safety_violations: List[str] = Field(default_factory=list)
    case_results: List[CaseEvaluationResult] = Field(default_factory=list)
    human_readable_summary: str = ""
