"""Adapters module exports."""

from agent_runtime.adapters.mock_model import MockModelProvider
from agent_runtime.adapters.model_agent import ModelDrivenAgent
from agent_runtime.adapters.ollama_model import ModelProviderError, OllamaModelProvider
from agent_runtime.adapters.external_agent import (
    ExternalAgentAdapter,
    ExternalAgentObservation,
    ExternalAgentRequest,
    ExternalAgentResponse,
    ExternalAgentResponseType,
    ExternalAgentTaskFacts,
    ExternalAgentToolDescription,
    ExternalAgentToolProposal,
    ExternalAgentTurn,
    IExternalAgent,
    IExternalAgentTransport,
    InProcessExternalAgentTransport,
)
from agent_runtime.adapters.unix_socket_transport import (
    MAX_EXTERNAL_AGENT_MESSAGE_BYTES,
    MessageSizeExceededError,
    ProtocolFramingError,
    TransportConnectionError,
    UnixSocketExternalAgentTransport,
    read_framed_message,
    write_framed_message,
)
from agent_runtime.adapters.hosts import (
    AntigravityExternalAgentHost,
    AntigravityHostConfig,
    HostExternalAgentTransport,
    HostProtocolError,
    HostTimeoutError,
    HostUnavailableError,
    IExternalAgentHost,
    ScriptedExternalAgentHost,
)

__all__ = [
    "MockModelProvider",
    "ModelDrivenAgent",
    "ModelProviderError",
    "OllamaModelProvider",
    "ExternalAgentAdapter",
    "ExternalAgentObservation",
    "ExternalAgentRequest",
    "ExternalAgentResponse",
    "ExternalAgentResponseType",
    "ExternalAgentTaskFacts",
    "ExternalAgentToolDescription",
    "ExternalAgentToolProposal",
    "ExternalAgentTurn",
    "IExternalAgent",
    "IExternalAgentTransport",
    "InProcessExternalAgentTransport",
    "MAX_EXTERNAL_AGENT_MESSAGE_BYTES",
    "MessageSizeExceededError",
    "ProtocolFramingError",
    "TransportConnectionError",
    "UnixSocketExternalAgentTransport",
    "read_framed_message",
    "write_framed_message",
    "IExternalAgentHost",
    "HostExternalAgentTransport",
    "HostUnavailableError",
    "HostProtocolError",
    "HostTimeoutError",
    "AntigravityExternalAgentHost",
    "AntigravityHostConfig",
    "ScriptedExternalAgentHost",
]
