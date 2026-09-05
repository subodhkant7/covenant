import contextvars
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union
from uuid import uuid4

from pydantic import BaseModel, Field, computed_field

from covenant.domain.enums import (
    ActionStatus,
    ActionType,
    CommitmentCategory,
    CommitmentHealth,
    CommitmentStatus,
    ConfidenceLevel,
    EvidenceSourceType,
    ObligationDirection,
    PolicyCategory,
    PolicyDecisionType,
    RiskLevel,
    StatementType,
)

_clock_override: contextvars.ContextVar[Optional[datetime]] = contextvars.ContextVar("_clock_override", default=None)


def ensure_utc(dt: Union[datetime, str]) -> datetime:
    """Normalize any datetime or ISO string to a timezone-aware UTC datetime."""
    if isinstance(dt, str):
        dt_clean = dt.replace("Z", "+00:00") if dt.endswith("Z") else dt
        dt = datetime.fromisoformat(dt_clean)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def utc_now() -> datetime:
    """Return current UTC timestamp with timezone awareness.
    
    If a clock override or time freeze is active, returns the frozen instant.
    """
    override = _clock_override.get()
    if override is not None:
        return ensure_utc(override)
    return datetime.now(timezone.utc)


def set_clock_override(dt: Optional[Union[datetime, str]]) -> Optional[datetime]:
    """Set or clear the clock override for the current context."""
    if dt is None:
        _clock_override.set(None)
        return None
    val = ensure_utc(dt)
    _clock_override.set(val)
    return val


class time_freeze:
    """Context manager for deterministic time execution."""

    def __init__(self, frozen_time: Union[datetime, str]):
        self.frozen_time = ensure_utc(frozen_time)
        self.token = None

    def __enter__(self) -> datetime:
        self.token = _clock_override.set(self.frozen_time)
        return self.frozen_time

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.token is not None:
            _clock_override.reset(self.token)


def calculate_overdue_duration(
    due_date: Optional[Union[datetime, str]],
    reference_time: Optional[Union[datetime, str]] = None,
) -> Dict[str, Any]:
    """Canonical overdue calculation:
    
    - Normalizes both due_date and reference_time to UTC.
    - Calculates exact elapsed seconds.
    - Determines is_overdue strictly when elapsed_seconds > 0.
    - Derives hours_overdue and days_overdue from elapsed_seconds.
    """
    if due_date is None:
        return {
            "is_overdue": False,
            "elapsed_seconds": 0.0,
            "hours_overdue": 0.0,
            "days_overdue": 0.0,
        }

    due_utc = ensure_utc(due_date)
    ref_utc = ensure_utc(reference_time) if reference_time is not None else utc_now()

    elapsed = (ref_utc - due_utc).total_seconds()
    is_overdue = elapsed > 0.0

    return {
        "is_overdue": is_overdue,
        "elapsed_seconds": elapsed,
        "hours_overdue": max(0.0, elapsed / 3600.0) if is_overdue else 0.0,
        "days_overdue": max(0.0, elapsed / 86400.0) if is_overdue else 0.0,
    }


class Party(BaseModel):
    """Represents a person or organization participating in a commitment."""
    name: str = Field(..., description="Full name or company name")
    email: Optional[str] = Field(None, description="Contact email address")
    organization: Optional[str] = Field(None, description="Associated organization or company")
    role: str = Field(default="PARTICIPANT", description="PROMISOR, PROMISEE, or STAKEHOLDER")

    def __str__(self) -> str:
        if self.organization and self.organization != self.name:
            return f"{self.name} ({self.organization})"
        return self.name


class EvidenceReference(BaseModel):
    """Corroborating proof or source record linking to a commitment."""
    id: str = Field(default_factory=lambda: f"ev_{uuid4().hex[:8]}")
    source_type: EvidenceSourceType = Field(..., description="Origin source type")
    source_id: str = Field(..., description="External or internal ID in synthetic/real store")
    title: str = Field(..., description="Human-readable title or subject")
    snippet: str = Field(..., description="Relevant text snippet or quote")
    timestamp: datetime = Field(default_factory=utc_now)
    url_or_path: Optional[str] = Field(None, description="Reference link or filepath")
    confidence: float = Field(default=0.9, ge=0.0, le=1.0)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class EvidenceClaim(BaseModel):
    """Structured factual or inferential claim extracted from workspace evidence."""
    source_id: str = Field(..., description="ID of source evidence, e.g. PRJ-ATLAS, EML-102")
    claim: str = Field(..., description="Specific factual claim or finding")
    is_fact: bool = Field(default=True, description="True if grounded in documentary record, False if inferred")
    relevance: str = Field(default="HIGH", description="Relevance to commitment fulfillment: HIGH, MEDIUM, LOW")
    confidence: float = Field(default=0.95, ge=0.0, le=1.0)


class EvidenceConflict(BaseModel):
    """Represents a contradiction or tension detected between multiple evidence sources."""
    source_a: str = Field(..., description="Primary evidence source ID")
    source_b: str = Field(..., description="Conflicting evidence source ID")
    description: str = Field(..., description="Concise explanation of the contradiction")
    conflict_type: str = Field(default="TIMELINE_MISMATCH", description="STATUS_CONTRADICTION, TIMELINE_MISMATCH, or MISSING_PREREQUISITE")
    severity: RiskLevel = Field(default=RiskLevel.MEDIUM)


class EvidenceAssessment(BaseModel):
    """Structured reasoning output from EvidenceAgent synthesis across workspace records."""
    finding: str = Field(..., description="Core factual conclusion synthesized across evidence")
    factual_claims: List[EvidenceClaim] = Field(default_factory=list)
    conflicts: List[EvidenceConflict] = Field(default_factory=list)
    corroborations: List[str] = Field(default_factory=list, description="Cross-source factual agreements")
    evidence_gaps: List[str] = Field(default_factory=list, description="Missing expected records or confirmations")
    confidence: float = Field(default=0.9, ge=0.0, le=1.0)
    is_blocking_downstream: bool = Field(default=False)
    recommended_risk: RiskLevel = Field(default=RiskLevel.LOW)
    rationale: str = Field(default="", description="Concise reasoning rationale without private chain-of-thought")


class CommitmentExtractionResult(BaseModel):
    """Structured reasoning output from CommitmentAgent."""
    is_commitment: bool = Field(..., description="Whether statement constitutes a binding obligation")
    statement_type: StatementType = Field(..., description="Classification of the statement")
    confidence: float = Field(default=0.9, ge=0.0, le=1.0)
    promisor: Optional[Party] = None
    promisee: Optional[Party] = None
    obligation_direction: ObligationDirection = ObligationDirection.THEY_OWE_US
    promised_deliverable: str = Field(default="", description="What was explicitly promised or agreed")
    due_date: Optional[datetime] = None
    category: CommitmentCategory = CommitmentCategory.OTHER
    rationale: str = Field(default="", description="Reasoning explaining why this is or is not a commitment")
    source_evidence_ids: List[str] = Field(default_factory=list)


class ActionHistoryItem(BaseModel):
    """Immutable audit entry for an action taken on a commitment."""
    id: str = Field(default_factory=lambda: f"act_hist_{uuid4().hex[:8]}")
    timestamp: datetime = Field(default_factory=utc_now)
    agent_name: str
    action_type: Optional[ActionType] = None
    summary: str
    details: Dict[str, Any] = Field(default_factory=dict)
    state_before: Optional[CommitmentStatus] = None
    state_after: Optional[CommitmentStatus] = None
    approved_by: Optional[str] = None


class VerificationRequirement(BaseModel):
    """Specific conditions that must be established before resolving a commitment."""
    id: str = Field(default_factory=lambda: f"vreq_{uuid4().hex[:8]}")
    criteria: str = Field(..., description="Description of verifiable condition")
    expected_source_type: EvidenceSourceType = Field(EvidenceSourceType.EMAIL)
    verification_tool: str = Field(default="verify_commitment")
    satisfied: bool = False
    satisfied_at: Optional[datetime] = None
    evidence_reference_id: Optional[str] = None


class VerificationResult(BaseModel):
    """Result of an independent verification check by VerificationAgent."""
    id: str = Field(default_factory=lambda: f"vres_{uuid4().hex[:8]}")
    commitment_id: str
    action_succeeded: bool = True
    business_outcome_verified: bool = False
    is_verified: bool = False
    rationale: str
    evidence_ids: List[str] = Field(default_factory=list)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    verified_at: datetime = Field(default_factory=utc_now)


class ProposedAction(BaseModel):
    """A concrete operational step prepared by ResolutionAgent."""
    id: str = Field(default_factory=lambda: f"act_{uuid4().hex[:8]}")
    commitment_id: str
    action_type: ActionType
    description: str
    recipient: Optional[str] = None
    subject: Optional[str] = None
    payload: Dict[str, Any] = Field(default_factory=dict)
    status: ActionStatus = ActionStatus.PROPOSED
    requires_human_approval: bool = True
    approval_reason: Optional[str] = None
    risk: RiskLevel = RiskLevel.LOW
    confidence: float = Field(default=0.95, ge=0.0, le=1.0)
    created_at: datetime = Field(default_factory=utc_now)
    decided_at: Optional[datetime] = None
    executed_at: Optional[datetime] = None
    decision_notes: Optional[str] = None


class PolicyDecision(BaseModel):
    """Deterministic evaluation of whether an action requires human approval."""
    id: str = Field(default_factory=lambda: f"pol_{uuid4().hex[:8]}")
    action_id: str
    category: PolicyCategory = PolicyCategory.HUMAN_APPROVAL
    decision: PolicyDecisionType
    rationale: str
    risk_level: RiskLevel
    requires_human_approval: bool
    rules_triggered: List[str] = Field(default_factory=list)
    evaluated_at: datetime = Field(default_factory=utc_now)


class AgentEvent(BaseModel):
    """Structured audit log entry for system observability and UI timeline."""
    event_id: str = Field(default_factory=lambda: f"evt_{uuid4().hex[:10]}")
    id: Optional[str] = None
    timestamp: datetime = Field(default_factory=utc_now)
    workflow_id: Optional[str] = None
    commitment_id: Optional[str] = None
    agent: str = Field(default="System", description="Agent name responsible for event")
    agent_name: Optional[str] = None
    event_type: str = Field(default="ACTION", description="DISCOVERY, EVALUATION, POLICY, ACTION, VERIFICATION")
    action_name: Optional[str] = None
    tool: Optional[str] = None
    tool_name: Optional[str] = None
    summary: str
    result_status: str = Field(default="SUCCESS", description="SUCCESS, FAILED, PENDING, BLOCKED")
    inputs_summary: Optional[str] = None
    result_summary: Optional[str] = None
    state_before: Optional[CommitmentStatus] = None
    previous_state: Optional[CommitmentStatus] = None
    state_after: Optional[CommitmentStatus] = None
    new_state: Optional[CommitmentStatus] = None
    confidence: Optional[float] = None
    risk: Optional[RiskLevel] = None
    human_required: bool = False
    correlation_id: Optional[str] = None
    rationale: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def model_post_init(self, __context: Any) -> None:
        if not self.id:
            self.id = self.event_id
        if self.agent and not self.agent_name:
            self.agent_name = self.agent
        elif self.agent_name and self.agent == "System":
            self.agent = self.agent_name
        if self.event_type and not self.action_name:
            self.action_name = self.event_type
        elif self.action_name and self.event_type == "ACTION":
            self.event_type = self.action_name
        if not self.tool and self.tool_name:
            self.tool = self.tool_name
        if not self.tool_name and self.tool:
            self.tool_name = self.tool
        if not self.state_before and self.previous_state:
            self.state_before = self.previous_state
        if not self.previous_state and self.state_before:
            self.previous_state = self.state_before
        if not self.state_after and self.new_state:
            self.state_after = self.new_state
        if not self.new_state and self.state_after:
            self.new_state = self.state_after


class Commitment(BaseModel):
    """
    Core Domain Entity: Represents an explicit or implicit obligation/promise
    between parties with deterministic lifecycle and verifiable evidence.
    """
    id: str = Field(default_factory=lambda: f"com_{uuid4().hex[:8]}")
    title: str = Field(..., description="Concise commitment title")
    description: str = Field(..., description="Detailed description of what was promised")
    category: CommitmentCategory = Field(default=CommitmentCategory.OTHER)
    
    # Participants
    promisor: Party = Field(..., description="Party that made the promise (owes the action)")
    promisee: Party = Field(..., description="Party expecting fulfillment")
    
    # Traceability & References
    source_references: List[str] = Field(default_factory=list, description="Original source IDs e.g. email_01, contract_03")
    evidence_references: List[EvidenceReference] = Field(default_factory=list)
    
    # Temporal State
    created_at: datetime = Field(default_factory=utc_now)
    promised_at: Optional[datetime] = Field(None, description="When the promise was originally made")
    due_date: Optional[datetime] = Field(None, description="Expected fulfillment deadline")
    resolution_timestamp: Optional[datetime] = Field(None, description="When status reached RESOLVED")
    
    # State & Assessment
    status: CommitmentStatus = Field(default=CommitmentStatus.DISCOVERED)
    risk: RiskLevel = Field(default=RiskLevel.LOW)
    confidence: float = Field(default=0.9, ge=0.0, le=1.0)
    evidence_assessment: Optional[EvidenceAssessment] = None
    
    # Causality & Action Plan
    dependencies: List[str] = Field(default_factory=list, description="IDs of other commitments blocking this one")
    next_action: Optional[ProposedAction] = None
    required_human_approval: bool = False
    
    # Audit & Verification
    action_history: List[ActionHistoryItem] = Field(default_factory=list)
    verification_requirements: List[VerificationRequirement] = Field(default_factory=list)
    verification_result: Optional[VerificationResult] = None
    
    tags: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @computed_field
    def obligation_direction(self) -> ObligationDirection:
        """Determines if Northstar Studio owes this, or is owed this."""
        system_keywords = ["northstar", "northstar studio", "alex", "alex north", "we", "us"]
        promisor_str = f"{self.promisor.name} {self.promisor.organization or ''}".lower()
        promisee_str = f"{self.promisee.name} {self.promisee.organization or ''}".lower()

        promisor_is_us = any(k in promisor_str for k in system_keywords)
        promisee_is_us = any(k in promisee_str for k in system_keywords)

        if promisor_is_us and not promisee_is_us:
            return ObligationDirection.WE_OWE_THEM
        elif promisee_is_us and not promisor_is_us:
            return ObligationDirection.THEY_OWE_US
        return ObligationDirection.THIRD_PARTY

    @computed_field
    def is_overdue(self) -> bool:
        """Checks if current time exceeds due date without resolution."""
        if not self.due_date:
            return False
        if self.status in [CommitmentStatus.RESOLVED, CommitmentStatus.CANCELLED, CommitmentStatus.REJECTED]:
            return False
        return calculate_overdue_duration(self.due_date, utc_now())["is_overdue"]

    @computed_field
    def days_overdue(self) -> float:
        """Normalized duration in days that this commitment has been overdue."""
        if not self.due_date or self.status in [CommitmentStatus.RESOLVED, CommitmentStatus.CANCELLED, CommitmentStatus.REJECTED]:
            return 0.0
        return calculate_overdue_duration(self.due_date, utc_now())["days_overdue"]

    @computed_field
    def hours_overdue(self) -> float:
        """Normalized duration in hours that this commitment has been overdue."""
        if not self.due_date or self.status in [CommitmentStatus.RESOLVED, CommitmentStatus.CANCELLED, CommitmentStatus.REJECTED]:
            return 0.0
        return calculate_overdue_duration(self.due_date, utc_now())["hours_overdue"]

    def overdue_duration(self, reference_time: Optional[Union[datetime, str]] = None) -> Dict[str, Any]:
        """Calculate normalized overdue duration against reference time or current clock."""
        return calculate_overdue_duration(self.due_date, reference_time or utc_now())

    @computed_field
    def health(self) -> CommitmentHealth:
        """Dynamic operational health of the commitment."""
        if self.status == CommitmentStatus.RESOLVED:
            return CommitmentHealth.VERIFIED
        if self.status in [CommitmentStatus.AWAITING_APPROVAL, CommitmentStatus.EXECUTING, CommitmentStatus.VERIFYING]:
            return CommitmentHealth.RECOVERING
        if self.is_overdue or self.status == CommitmentStatus.OVERDUE:
            return CommitmentHealth.OVERDUE
        if self.risk in [RiskLevel.HIGH, RiskLevel.CRITICAL]:
            return CommitmentHealth.AT_RISK
        if self.status == CommitmentStatus.INVESTIGATING:
            return CommitmentHealth.DRIFTING
        return CommitmentHealth.STABLE
