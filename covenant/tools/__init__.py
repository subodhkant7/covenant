"""Tools module exports and initializer."""

from covenant.tools.action_tools import register_action_tools
from covenant.tools.base import (
    BaseTool,
    ToolRegistry,
    ToolResult,
    global_tool_registry,
)
from covenant.tools.commitment_tools import register_commitment_tools
from covenant.tools.workspace_tools import register_workspace_tools


def initialize_tools() -> ToolRegistry:
    """Register all workspace, commitment, and action tools."""
    register_workspace_tools()
    register_commitment_tools()
    register_action_tools()
    return global_tool_registry


# Initialize default registry
initialize_tools()

__all__ = [
    "BaseTool",
    "ToolRegistry",
    "ToolResult",
    "global_tool_registry",
    "initialize_tools",
]
