"""Tests for Synthetic Data Store and Northstar Studio Workflows."""

import pytest
from covenant.synthetic_data.store import workspace_store


def test_synthetic_email_search():
    results = workspace_store.search_emails("Phase 2")
    assert len(results) >= 2
    assert any("EML-101" == e["id"] for e in results)
    assert any("EML-102" == e["id"] for e in results)


def test_synthetic_contract_clauses():
    contracts = workspace_store.search_contracts("Meridian")
    assert len(contracts) == 1
    assert contracts[0]["id"] == "CTR-2026-081"
    assert any(cl["section"] == "4.2" for cl in contracts[0]["key_clauses"])


def test_synthetic_project_milestones():
    workspace_store.reset()
    proj = workspace_store.get_project_by_id("PRJ-ATLAS")
    assert proj is not None
    assert proj["name"] == "Project Atlas Mobile & Web Experience"
    milestone_2 = next(m for m in proj["milestones"] if m["id"] == "M2")
    assert milestone_2["status"] == "SUBMITTED_AWAITING_APPROVAL"
