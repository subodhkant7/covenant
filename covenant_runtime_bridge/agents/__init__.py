"""Covenant agent adapters implementing the runtime IAgent contract."""

from covenant_runtime_bridge.agents.discovery_agent import AdaptedCommitmentAgent
from covenant_runtime_bridge.agents.investigator_agent import AdaptedEvidenceAgent
from covenant_runtime_bridge.agents.resolver_agent import AdaptedResolutionAgent

__all__ = [
    "AdaptedCommitmentAgent",
    "AdaptedEvidenceAgent",
    "AdaptedResolutionAgent",
]
