"""CovenantTaskFactory: Factory for creating generic runtime Tasks from Covenant domain entities."""

from typing import Optional
from uuid import uuid4

from covenant.domain.models import Commitment
from agent_runtime.core.contracts.context import Task, TaskScope
from agent_runtime.core.state.enums import ScopeType, TaskState
from covenant_runtime_bridge.mapping.entity_mapping import map_commitment_to_task_scope


class CovenantTaskFactory:
    """
    Translates Covenant domain events and commitments into generic runtime Tasks.
    The runtime core has zero awareness of this factory.
    """
    DEFAULT_ORGANIZATION_ID = "org_covenant_northstar"

    @classmethod
    def create_discovery_task(cls, organization_id: Optional[str] = None) -> Task:
        org_id = organization_id or cls.DEFAULT_ORGANIZATION_ID
        return Task(
            id=f"tsk_cov_disc_{uuid4().hex[:8]}",
            organization_id=org_id,
            intent="Discover and structure promises across workspace communications",
            required_role="covenant.discovery",
            scope=TaskScope(
                scope_type=ScopeType.ORGANIZATION,
                entity_type="covenant.workspace",
                filter_criteria={"scan_type": "FULL_WORKSPACE"},
            ),
            input_payload={
                "domain": "covenant",
                "action": "DISCOVERY_SCAN",
            },
            requires_verification=False,
        )

    @classmethod
    def create_investigation_task(
        cls,
        commitment: Commitment,
        organization_id: Optional[str] = None,
    ) -> Task:
        org_id = organization_id or cls.DEFAULT_ORGANIZATION_ID
        return Task(
            id=f"tsk_cov_inv_{commitment.id}",
            organization_id=org_id,
            intent=f"Investigate evidence and cross-corroborate state for commitment: {commitment.title}",
            required_role="covenant.investigator",
            scope=map_commitment_to_task_scope(commitment),
            input_payload={
                "domain": "covenant",
                "commitment_id": commitment.id,
                "title": commitment.title,
                "status": commitment.status.value,
                "risk": commitment.risk.value,
                "category": commitment.category.value,
                "promisor": str(commitment.promisor),
            },
            requires_verification=False,
        )

    @classmethod
    def create_resolution_task(
        cls,
        commitment: Commitment,
        organization_id: Optional[str] = None,
    ) -> Task:
        org_id = organization_id or cls.DEFAULT_ORGANIZATION_ID
        return Task(
            id=f"tsk_cov_res_{commitment.id}",
            organization_id=org_id,
            intent=f"Formulate and execute resolution remedy for commitment: {commitment.title}",
            required_role="covenant.resolver",
            scope=map_commitment_to_task_scope(commitment),
            input_payload={
                "domain": "covenant",
                "commitment_id": commitment.id,
                "title": commitment.title,
                "status": commitment.status.value,
                "risk": commitment.risk.value,
                "due_date": commitment.due_date.isoformat() if commitment.due_date else None,
            },
            requires_verification=True,
        )
