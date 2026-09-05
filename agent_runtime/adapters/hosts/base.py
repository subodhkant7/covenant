"""Base abstractions for External Reasoning Agent Hosts.

Provides the transport-neutral IExternalAgentHost contract and the
HostExternalAgentTransport adapter that connects external hosts to the
runtime's existing ExternalAgentAdapter.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from agent_runtime.adapters.external_agent import (
    ExternalAgentRequest,
    ExternalAgentResponse,
    ExternalAgentTaskFacts,
    IExternalAgentTransport,
)
from agent_runtime.core.contracts.event import Event, EventType
from agent_runtime.core.interfaces.telemetry import IEventSink


class HostUnavailableError(Exception):
    """Raised when the requested external reasoning host binary or SDK is unavailable."""
    pass


class HostProtocolError(Exception):
    """Raised when a host violates the protocol contract or returns an invalid payload."""
    pass


class HostTimeoutError(Exception):
    """Raised when a host fails to respond within the configured timeout interval."""
    pass


class IExternalAgentHost(ABC):
    """Transport-neutral contract for an external reasoning agent host.
    
    Manages session lifecycle and request-response message passing without
    exposing runtime handles, databases, or execution authority to the host.
    """

    @property
    @abstractmethod
    def host_identity(self) -> str:
        """Returns the unique identifier of the external host implementation."""
        pass

    @property
    @abstractmethod
    def session_id(self) -> Optional[str]:
        """Returns the active session identifier, if any."""
        pass

    @property
    @abstractmethod
    def is_active(self) -> bool:
        """Returns True if the host session is started and ready for requests."""
        pass

    @abstractmethod
    async def start_session(
        self,
        session_id: str,
        context_facts: ExternalAgentTaskFacts,
    ) -> str:
        """Initializes a reasoning session on the external host with sanitized task facts."""
        pass

    @abstractmethod
    async def send_and_receive(
        self,
        request: ExternalAgentRequest,
    ) -> ExternalAgentResponse:
        """Transports an ExternalAgentRequest to the host and retrieves the ExternalAgentResponse."""
        pass

    @abstractmethod
    async def close_session(self) -> None:
        """Terminates the host session and cleans up resources."""
        pass


class HostExternalAgentTransport(IExternalAgentTransport):
    """Adapts an IExternalAgentHost to the runtime's IExternalAgentTransport contract.
    
    Allows any IExternalAgentHost implementation to plug directly into the existing
    ExternalAgentAdapter without altering runtime core contracts or state machines.
    """

    def __init__(
        self,
        host: IExternalAgentHost,
        event_sink: Optional[IEventSink] = None,
        auto_start_session: bool = True,
    ):
        self.host = host
        self.event_sink = event_sink
        self.auto_start_session = auto_start_session

    async def send_and_receive(
        self,
        request: ExternalAgentRequest,
    ) -> ExternalAgentResponse:
        """Mediates request-response exchange through the external host."""
        trace_id = f"trc_{request.task.task_id}"

        # Auto-start session if not active
        if not self.host.is_active and self.auto_start_session:
            session_id = f"sess_{request.task.task_id}_{request.task.organization_id}"
            await self.host.start_session(session_id, request.task)
            if self.event_sink:
                await self.event_sink.record(
                    Event(
                        trace_id=trace_id,
                        organization_id=request.task.organization_id,
                        task_id=request.task.task_id,
                        event_type=EventType.EXTERNAL_AGENT_HOST_STARTED,
                        summary=f"Started session '{session_id}' on host '{self.host.host_identity}'.",
                        payload={"host": self.host.host_identity, "session_id": session_id},
                    )
                )

        if self.event_sink:
            await self.event_sink.record(
                Event(
                    trace_id=trace_id,
                    organization_id=request.task.organization_id,
                    task_id=request.task.task_id,
                    event_type=EventType.EXTERNAL_AGENT_HOST_REQUESTED,
                    summary=f"Sent turn {request.current_turn} to host '{self.host.host_identity}'.",
                    payload={"host": self.host.host_identity, "turn_index": request.current_turn},
                )
            )

        try:
            response = await self.host.send_and_receive(request)
        except HostTimeoutError as te:
            if self.event_sink:
                await self.event_sink.record(
                    Event(
                        trace_id=trace_id,
                        organization_id=request.task.organization_id,
                        task_id=request.task.task_id,
                        event_type=EventType.EXTERNAL_AGENT_HOST_TIMEOUT,
                        summary=f"Host '{self.host.host_identity}' timed out.",
                        payload={"host": self.host.host_identity, "error": str(te)},
                    )
                )
            raise
        except Exception as exc:
            if self.event_sink:
                await self.event_sink.record(
                    Event(
                        trace_id=trace_id,
                        organization_id=request.task.organization_id,
                        task_id=request.task.task_id,
                        event_type=EventType.EXTERNAL_AGENT_HOST_FAILED,
                        summary=f"Host '{self.host.host_identity}' encountered error: {str(exc)}",
                        payload={"host": self.host.host_identity, "error": str(exc)},
                    )
                )
            raise

        if self.event_sink:
            await self.event_sink.record(
                Event(
                    trace_id=trace_id,
                    organization_id=request.task.organization_id,
                    task_id=request.task.task_id,
                    event_type=EventType.EXTERNAL_AGENT_HOST_RESPONDED,
                    summary=f"Host '{self.host.host_identity}' responded with {response.response_type.value}.",
                    payload={
                        "host": self.host.host_identity,
                        "turn_index": request.current_turn,
                        "response_type": response.response_type.value,
                    },
                )
            )

        return response

    async def close(self) -> None:
        """Closes the underlying host session."""
        if self.host.is_active:
            if self.event_sink:
                await self.event_sink.record(
                    Event(
                        trace_id=f"trc_close_{self.host.session_id or 'none'}",
                        organization_id="system",
                        event_type=EventType.EXTERNAL_AGENT_HOST_CLOSED,
                        summary=f"Closed session on host '{self.host.host_identity}'.",
                        payload={"host": self.host.host_identity, "session_id": self.host.session_id},
                    )
                )
            await self.host.close_session()
