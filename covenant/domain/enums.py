"""Domain enumerations for Covenant."""

from enum import Enum


class CommitmentStatus(str, Enum):
    """Lifecycle states of a commitment."""
    DISCOVERED = "DISCOVERED"
    ACTIVE = "ACTIVE"
    WAITING = "WAITING"
    DUE = "DUE"
    OVERDUE = "OVERDUE"
    INVESTIGATING = "INVESTIGATING"
    ACTION_READY = "ACTION_READY"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    EXECUTING = "EXECUTING"
    VERIFYING = "VERIFYING"
    RESOLVED = "RESOLVED"
    BLOCKED = "BLOCKED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"
    ESCALATED = "ESCALATED"


class RiskLevel(str, Enum):
    """Risk severity associated with a commitment or action."""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ConfidenceLevel(str, Enum):
    """Confidence score/category of extraction, state, or verification."""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class CommitmentCategory(str, Enum):
    """Business categorization of commitments."""
    CLIENT_APPROVAL = "CLIENT_APPROVAL"
    SUPPLIER_SHIPMENT = "SUPPLIER_SHIPMENT"
    CONTRACTOR_REPAIR = "CONTRACTOR_REPAIR"
    PAYMENT = "PAYMENT"
    DELIVERABLE = "DELIVERABLE"
    INVOICE = "INVOICE"
    DOCUMENT_REQUEST = "DOCUMENT_REQUEST"
    REFUND = "REFUND"
    OTHER = "OTHER"


class EvidenceSourceType(str, Enum):
    """Origin source type for corroborating evidence."""
    EMAIL = "EMAIL"
    CONTRACT = "CONTRACT"
    INVOICE = "INVOICE"
    PROJECT = "PROJECT"
    CALENDAR = "CALENDAR"
    EXTERNAL_API = "EXTERNAL_API"
    MANUAL_ENTRY = "MANUAL_ENTRY"


class ActionType(str, Enum):
    """Action categories that agents can propose or execute."""
    FOLLOWUP_EMAIL = "FOLLOWUP_EMAIL"
    STATUS_CHECK = "STATUS_CHECK"
    ESCALATE_DISPUTE = "ESCALATE_DISPUTE"
    ISSUE_INVOICE = "ISSUE_INVOICE"
    REQUEST_APPROVAL = "REQUEST_APPROVAL"
    UPDATE_RECORD = "UPDATE_RECORD"
    NOTIFY_STAKEHOLDER = "NOTIFY_STAKEHOLDER"


class ActionStatus(str, Enum):
    """Execution status for a proposed action."""
    PROPOSED = "PROPOSED"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    APPROVED = "APPROVED"
    EXECUTING = "EXECUTING"
    COMPLETED = "COMPLETED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"


class CommitmentHealth(str, Enum):
    """Dynamic operational health of a commitment."""
    STABLE = "STABLE"
    DRIFTING = "DRIFTING"
    AT_RISK = "AT_RISK"
    OVERDUE = "OVERDUE"
    RECOVERING = "RECOVERING"
    VERIFIED = "VERIFIED"


class PolicyCategory(str, Enum):
    """Categorization of autonomy permissions."""
    AUTONOMOUS = "AUTONOMOUS"
    HUMAN_APPROVAL = "HUMAN_APPROVAL"
    BLOCKED = "BLOCKED"


class PolicyDecisionType(str, Enum):
    """Deterministic policy determination for an action."""
    AUTONOMOUS_PERMITTED = "AUTONOMOUS_PERMITTED"
    HUMAN_APPROVAL_REQUIRED = "HUMAN_APPROVAL_REQUIRED"
    BLOCKED_BY_POLICY = "BLOCKED_BY_POLICY"


class ObligationDirection(str, Enum):
    """Directional relationship of the commitment."""
    THEY_OWE_US = "THEY_OWE_US"
    WE_OWE_THEM = "WE_OWE_THEM"
    THIRD_PARTY = "THIRD_PARTY"
