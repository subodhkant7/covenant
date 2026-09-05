"""Authorization package exports."""

from agent_runtime.core.authorization.exceptions import (
    AuthorizationError,
    OrganizationScopeError,
    PermissionDeniedError,
)
from agent_runtime.core.authorization.matrix import ToolPermissionMatrix

__all__ = [
    "AuthorizationError",
    "OrganizationScopeError",
    "PermissionDeniedError",
    "ToolPermissionMatrix",
]
