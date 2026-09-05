"""Deterministic ToolPermissionMatrix."""

from typing import Dict, Iterable, Set, Tuple
from agent_runtime.core.authorization.exceptions import PermissionDeniedError


class ToolPermissionMatrix:
    """
    Deterministic permission matrix mapping (organization_id, agent_id) -> Set[tool_names].
    Also supports explicit global system tools via an isolated whitelist.
    """

    def __init__(self):
        # Maps (organization_id, agent_id) -> Set[allowed_tool_names]
        self._grants: Dict[Tuple[str, str], Set[str]] = {}
        # Explicit global tools permitted to any agent in any organization (e.g. echo, clock)
        self._system_tools: Set[str] = set()

    def grant(self, organization_id: str, agent_id: str, tool_names: Iterable[str]) -> None:
        """Grants tool invocation rights to a specific agent in an organization."""
        key = (organization_id, agent_id)
        if key not in self._grants:
            self._grants[key] = set()
        self._grants[key].update(tool_names)

    def revoke(self, organization_id: str, agent_id: str, tool_names: Iterable[str]) -> None:
        """Revokes specific tool permissions."""
        key = (organization_id, agent_id)
        if key in self._grants:
            self._grants[key].difference_update(tool_names)

    def register_system_tool(self, tool_name: str) -> None:
        """Explicitly whitelists a safe read-only system tool across all organizations."""
        self._system_tools.add(tool_name)

    def is_authorized(self, organization_id: str, agent_id: str, tool_name: str) -> bool:
        """O(1) permission check."""
        if tool_name in self._system_tools:
            return True
        allowed = self._grants.get((organization_id, agent_id), set())
        return tool_name in allowed

    def authorize(self, organization_id: str, agent_id: str, tool_name: str) -> None:
        """Asserts permission or raises PermissionDeniedError."""
        if not self.is_authorized(organization_id, agent_id, tool_name):
            raise PermissionDeniedError(organization_id, agent_id, tool_name)
