"""Evidence and verification contracts."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4
from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Evidence(BaseModel):
    """Provenance-bearing factual observation."""
    id: str = Field(default_factory=lambda: f"evi_{uuid4().hex[:8]}")
    source_type: str
    source_id: str
    summary: str
    payload: Dict[str, Any] = Field(default_factory=dict)
    captured_at: datetime = Field(default_factory=utc_now)
    collected_by: str = ""


class VerificationRequest(BaseModel):
    """Request for independent outcome verification."""
    task_id: str
    expected_outcome: str
    verification_criteria: Dict[str, Any] = Field(default_factory=dict)
    deadline: Optional[datetime] = None


class VerificationResult(BaseModel):
    """Result of independent verification pass."""
    task_id: str
    verified: bool
    rationale: str = ""
    evidence: List[Evidence] = Field(default_factory=list)
    verified_at: datetime = Field(default_factory=utc_now)
    verified_by: str = ""
