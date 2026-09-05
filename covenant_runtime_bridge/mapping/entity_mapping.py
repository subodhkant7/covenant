"""Domain entity mapping: Covenant Commitment <-> Generic Runtime TaskScope."""

from typing import Optional
from covenant.domain.models import Commitment
from agent_runtime.core.contracts.context import TaskScope
from agent_runtime.core.state.enums import ScopeType


def map_commitment_to_task_scope(commitment: Commitment) -> TaskScope:
    """Encapsulates a Covenant commitment within a generic runtime TaskScope."""
    return TaskScope(
        scope_type=ScopeType.ENTITY,
        entity_type="covenant.commitment",
        entity_ids=[commitment.id],
        filter_criteria={
            "category": commitment.category.value,
            "risk": commitment.risk.value,
            "promisor_org": commitment.promisor.organization or commitment.promisor.name,
        },
    )


def extract_commitment_id_from_scope(scope: TaskScope) -> Optional[str]:
    """Safely extracts the commitment ID from a generic TaskScope without assumptions."""
    if scope.entity_type == "covenant.commitment" and scope.entity_ids:
        return scope.entity_ids[0]
    return None
