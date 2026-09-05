"""Test double implementation of IExternalAgentHost for testing host abstraction."""

from typing import Any, Callable, Dict, List, Optional

from agent_runtime.adapters.external_agent import (
    ExternalAgentRequest,
    ExternalAgentResponse,
    ExternalAgentTaskFacts,
)
from agent_runtime.adapters.hosts.base import (
    HostProtocolError,
    IExternalAgentHost,
)


class ScriptedExternalAgentHost(IExternalAgentHost):
    """Generic scripted test double implementing IExternalAgentHost."""

    def __init__(
        self,
        host_id: str = "scripted.test_host",
        script: Optional[Callable[[ExternalAgentRequest], ExternalAgentResponse]] = None,
    ):
        self._host_id = host_id
        self._script = script
        self._session_id: Optional[str] = None
        self._context_facts: Optional[ExternalAgentTaskFacts] = None
        self._is_active: bool = False
        self.received_requests: List[ExternalAgentRequest] = []

    @property
    def host_identity(self) -> str:
        return self._host_id

    @property
    def session_id(self) -> Optional[str]:
        return self._session_id

    @property
    def is_active(self) -> bool:
        return self._is_active

    async def start_session(
        self,
        session_id: str,
        context_facts: ExternalAgentTaskFacts,
    ) -> str:
        self._session_id = session_id
        self._context_facts = context_facts
        self._is_active = True
        return self._session_id

    async def send_and_receive(
        self,
        request: ExternalAgentRequest,
    ) -> ExternalAgentResponse:
        if not self._is_active:
            raise HostProtocolError("Session is not active.")

        self.received_requests.append(request)

        if self._script:
            return self._script(request)

        raise HostProtocolError("No script provided for scripted host.")

    async def close_session(self) -> None:
        self._is_active = False
        self._session_id = None
        self._context_facts = None
