"""External Agent Host connector exports."""

from agent_runtime.adapters.hosts.base import (
    HostExternalAgentTransport,
    HostProtocolError,
    HostTimeoutError,
    HostUnavailableError,
    IExternalAgentHost,
)
from agent_runtime.adapters.hosts.antigravity_host import (
    AntigravityExternalAgentHost,
    AntigravityHostConfig,
)
from agent_runtime.adapters.hosts.test_double import (
    ScriptedExternalAgentHost,
)

__all__ = [
    "IExternalAgentHost",
    "HostExternalAgentTransport",
    "HostUnavailableError",
    "HostProtocolError",
    "HostTimeoutError",
    "AntigravityExternalAgentHost",
    "AntigravityHostConfig",
    "ScriptedExternalAgentHost",
]
