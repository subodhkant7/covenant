"""Tests for Domain Models."""

from datetime import datetime, timezone
import pytest
from covenant.domain.enums import (
    CommitmentCategory,
    CommitmentStatus,
    ObligationDirection,
    RiskLevel,
)
from covenant.domain.models import (
    Commitment,
    EvidenceReference,
    EvidenceSourceType,
    Party,
)


def test_party_representation():
    p = Party(name="Alex North", organization="Northstar Studio LLC", role="PROMISOR")
    assert str(p) == "Alex North (Northstar Studio LLC)"
    assert p.name == "Alex North"


def test_commitment_creation_and_obligation_direction():
    # They Owe Us
    c1 = Commitment(
        title="Client Sign-Off",
        description="Sarah promised approval",
        category=CommitmentCategory.CLIENT_APPROVAL,
        promisor=Party(name="Sarah Jenkins", organization="Meridian Global"),
        promisee=Party(name="Alex North", organization="Northstar Studio"),
        due_date=datetime(2026, 8, 1, 17, 0, tzinfo=timezone.utc),
    )
    assert c1.obligation_direction == ObligationDirection.THEY_OWE_US
    assert c1.status == CommitmentStatus.DISCOVERED
    assert c1.is_overdue is True

    # We Owe Them
    c2 = Commitment(
        title="Brand Kit Delivery",
        description="Alex promised deliverable to David",
        category=CommitmentCategory.DELIVERABLE,
        promisor=Party(name="Alex North", organization="Northstar Studio"),
        promisee=Party(name="David Kroll", organization="Horizon Health"),
        due_date=datetime(2028, 1, 1, tzinfo=timezone.utc),
    )
    assert c2.obligation_direction == ObligationDirection.WE_OWE_THEM
    assert c2.is_overdue is False


def test_evidence_reference_serialization():
    ev = EvidenceReference(
        source_type=EvidenceSourceType.EMAIL,
        source_id="EML-102",
        title="Email Promise",
        snippet="I promise to sign off by Friday.",
        confidence=0.95,
    )
    data = ev.model_dump(mode="json")
    assert data["source_id"] == "EML-102"
    assert data["source_type"] == "EMAIL"
    assert data["confidence"] == 0.95
