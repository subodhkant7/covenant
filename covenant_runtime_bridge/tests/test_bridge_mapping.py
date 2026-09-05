"""Tests for Covenant domain entity and state mapping."""

import pytest
from covenant.domain.enums import CommitmentCategory, CommitmentStatus, RiskLevel
from covenant.domain.models import Commitment, Party
from agent_runtime.core.state.enums import TaskState
from covenant_runtime_bridge.mapping.entity_mapping import (
    extract_commitment_id_from_scope,
    map_commitment_to_task_scope,
)
from covenant_runtime_bridge.mapping.state_mapping import (
    derive_commitment_status_from_task,
    map_commitment_status_to_task_state,
)
from covenant_runtime_bridge.mapping.task_factory import CovenantTaskFactory


@pytest.fixture
def sample_commitment():
    return Commitment(
        id="com_sample_01",
        title="Deliver Phase 2 Artifacts",
        description="Formal signoff for phase 2",
        category=CommitmentCategory.DELIVERABLE,
        promisor=Party(name="Alice", organization="VendorCorp"),
        promisee=Party(name="Bob", organization="ClientCorp"),
        status=CommitmentStatus.OVERDUE,
        risk=RiskLevel.HIGH,
    )


def test_commitment_status_to_task_state_mapping():
    assert map_commitment_status_to_task_state(CommitmentStatus.OVERDUE) == TaskState.PENDING
    assert map_commitment_status_to_task_state(CommitmentStatus.INVESTIGATING) == TaskState.RUNNING
    assert map_commitment_status_to_task_state(CommitmentStatus.AWAITING_APPROVAL) == TaskState.BLOCKED
    assert map_commitment_status_to_task_state(CommitmentStatus.VERIFYING) == TaskState.VERIFYING
    assert map_commitment_status_to_task_state(CommitmentStatus.RESOLVED) == TaskState.COMPLETED
    assert map_commitment_status_to_task_state(CommitmentStatus.FAILED) == TaskState.FAILED


def test_derive_commitment_status_from_task():
    # Task COMPLETED -> Commitment RESOLVED
    assert derive_commitment_status_from_task(TaskState.COMPLETED, CommitmentStatus.VERIFYING) == CommitmentStatus.RESOLVED
    # Task BLOCKED -> Commitment AWAITING_APPROVAL
    assert derive_commitment_status_from_task(TaskState.BLOCKED, CommitmentStatus.ACTION_READY) == CommitmentStatus.AWAITING_APPROVAL
    # Task RUNNING on overdue -> Commitment INVESTIGATING
    assert derive_commitment_status_from_task(TaskState.RUNNING, CommitmentStatus.OVERDUE) == CommitmentStatus.INVESTIGATING


def test_entity_mapping_and_scope(sample_commitment):
    scope = map_commitment_to_task_scope(sample_commitment)
    assert scope.entity_type == "covenant.commitment"
    assert scope.entity_ids == ["com_sample_01"]
    assert scope.filter_criteria["risk"] == "HIGH"

    cid = extract_commitment_id_from_scope(scope)
    assert cid == "com_sample_01"


def test_task_factory_creation(sample_commitment):
    # Discovery Task
    disc_task = CovenantTaskFactory.create_discovery_task()
    assert disc_task.required_role == "covenant.discovery"
    assert disc_task.organization_id == "org_covenant_northstar"
    assert disc_task.status == TaskState.PENDING

    # Investigation Task
    inv_task = CovenantTaskFactory.create_investigation_task(sample_commitment)
    assert inv_task.required_role == "covenant.investigator"
    assert inv_task.input_payload["commitment_id"] == "com_sample_01"
    assert inv_task.scope.entity_ids == ["com_sample_01"]

    # Resolution Task
    res_task = CovenantTaskFactory.create_resolution_task(sample_commitment)
    assert res_task.required_role == "covenant.resolver"
    assert res_task.requires_verification is True
