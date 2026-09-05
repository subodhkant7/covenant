"""Authorization and scoping exceptions."""


class AuthorizationError(Exception):
    """Base exception for runtime authorization failures."""
    pass


class PermissionDeniedError(AuthorizationError):
    """Raised when an agent is not authorized to invoke a tool."""

    def __init__(self, organization_id: str, agent_id: str, tool_name: str, message: str = ""):
        self.organization_id = organization_id
        self.agent_id = agent_id
        self.tool_name = tool_name
        detail = message or f"Agent '{agent_id}' is not authorized to invoke tool '{tool_name}' in organization '{organization_id}'."
        super().__init__(detail)


class OrganizationScopeError(AuthorizationError):
    """Raised when a task or agent attempts to access resources outside its organization scope."""
    pass
