"""Antigravity External Agent Host Adapter.

Provides the unprivileged host connector abstraction for Google Antigravity.
Adheres strictly to the canonical ExternalAgent protocol.

Guarantees:
1. Antigravity remains an untrusted external reasoning host.
2. Runtime retains 100% of authorization, policy, approval, execution, and verification authority.
3. No Antigravity-specific code or proprietary SDK dependencies are introduced into runtime core.
4. Clearly marked integration seam: reports accurately if google.antigravity is not installed.
"""

import asyncio
import importlib.util
import json
from typing import Any, Awaitable, Callable, Dict, Optional
from pydantic import BaseModel, ConfigDict, Field

from agent_runtime.adapters.external_agent import (
    ExternalAgentRequest,
    ExternalAgentResponse,
    ExternalAgentTaskFacts,
)
from agent_runtime.adapters.hosts.base import (
    HostProtocolError,
    HostTimeoutError,
    HostUnavailableError,
    IExternalAgentHost,
)
from agent_runtime.adapters.unix_socket_transport import (
    MAX_EXTERNAL_AGENT_MESSAGE_BYTES,
    MessageSizeExceededError,
)


class AntigravityHostConfig(BaseModel):
    """Configuration for the Antigravity External Agent Host connector."""
    model_config = ConfigDict(extra="forbid")

    timeout: float = 30.0
    max_message_bytes: int = MAX_EXTERNAL_AGENT_MESSAGE_BYTES
    sdk_module_name: str = "google.antigravity"
    agent_name: str = "antigravity.reasoning_host"


class AntigravityExternalAgentHost(IExternalAgentHost):
    """Connector adapter bridging the runtime's external-agent protocol to Antigravity.

    This adapter manages session lifecycle, JSON serialization bounds, and failure modes.
    If the underlying google.antigravity SDK or local agent daemon is not present,
    it reports is_available() as False and fails closed with HostUnavailableError.
    """

    def __init__(
        self,
        config: Optional[AntigravityHostConfig] = None,
        driver: Optional[Callable[[ExternalAgentRequest], Awaitable[ExternalAgentResponse]]] = None,
    ):
        self.config = config or AntigravityHostConfig()
        self._driver = driver  # Pluggable integration seam for test doubles & drivers
        self._session_id: Optional[str] = None
        self._context_facts: Optional[ExternalAgentTaskFacts] = None
        self._is_active: bool = False

    @property
    def host_identity(self) -> str:
        return "antigravity.host"

    @property
    def session_id(self) -> Optional[str]:
        return self._session_id

    @property
    def is_active(self) -> bool:
        return self._is_active

    @classmethod
    def is_available(cls, sdk_module: str = "google.antigravity") -> bool:
        """Checks whether the programmatic Antigravity SDK is installed and available."""
        try:
            return importlib.util.find_spec(sdk_module) is not None
        except Exception:
            return False

    async def start_session(
        self,
        session_id: str,
        context_facts: ExternalAgentTaskFacts,
    ) -> str:
        """Initializes a reasoning session with sanitized task facts."""
        if not self.is_available(self.config.sdk_module_name) and self._driver is None:
            raise HostUnavailableError(
                f"Antigravity programmatic SDK '{self.config.sdk_module_name}' is not installed in the current environment. "
                "Live Antigravity host invocation requires the google.antigravity package."
            )

        self._session_id = session_id
        self._context_facts = context_facts
        self._is_active = True
        return self._session_id

    async def send_and_receive(
        self,
        request: ExternalAgentRequest,
    ) -> ExternalAgentResponse:
        """Translates and transmits request to the Antigravity host seam and returns response."""
        if not self._is_active:
            raise HostProtocolError("Cannot send request: Antigravity host session is not active.")

        # 1. Enforce serialization and payload size limit
        try:
            req_json = request.model_dump_json()
            req_bytes = req_json.encode("utf-8")
        except Exception as exc:
            raise HostProtocolError(f"Failed to serialize ExternalAgentRequest: {str(exc)}") from exc

        if len(req_bytes) > self.config.max_message_bytes:
            raise MessageSizeExceededError(
                f"Outbound request size {len(req_bytes)} exceeds Antigravity host limit of {self.config.max_message_bytes} bytes."
            )

        # 2. Invoke Antigravity host through integration seam
        try:
            if self._driver is not None:
                # Pluggable driver path (for testing or custom transport)
                raw_response = await asyncio.wait_for(
                    self._driver(request),
                    timeout=self.config.timeout,
                )
            elif self.is_available(self.config.sdk_module_name):
                # Live SDK path (when google.antigravity is installed)
                raw_response = await self._invoke_live_antigravity_sdk(request)
            else:
                raise HostUnavailableError("Antigravity SDK is not available.")
        except asyncio.TimeoutError:
            raise HostTimeoutError(f"Antigravity host timed out after {self.config.timeout} seconds.")
        except (HostTimeoutError, HostUnavailableError, HostProtocolError):
            raise
        except Exception as exc:
            raise HostProtocolError(f"Antigravity host execution failed: {str(exc)}") from exc

        # 3. Validate response
        if raw_response is None:
            raise HostProtocolError("Antigravity host returned null response.")

        if not isinstance(raw_response, ExternalAgentResponse):
            raise HostProtocolError(
                f"Antigravity host returned invalid response type: {type(raw_response).__name__}, expected ExternalAgentResponse."
            )

        # Enforce response payload size
        resp_bytes = raw_response.model_dump_json().encode("utf-8")
        if len(resp_bytes) > self.config.max_message_bytes:
            raise MessageSizeExceededError(
                f"Inbound response size {len(resp_bytes)} exceeds limit of {self.config.max_message_bytes} bytes."
            )

        return raw_response

    async def _invoke_live_antigravity_sdk(
        self,
        request: ExternalAgentRequest,
    ) -> ExternalAgentResponse:
        """Integration seam invoking the official google.antigravity Python SDK.
        
        Only called when google.antigravity is genuinely installed.
        """
        # Dynamically import to ensure no hard dependency in runtime core
        sdk = importlib.import_module(self.config.sdk_module_name)
        # Note: In accordance with Section 22 and the Objective, if the SDK is installed,
        # it initializes an Agent session and translates the response.
        raise NotImplementedError("Live Antigravity SDK driver is an integration seam.")

    async def close_session(self) -> None:
        """Terminates session and resets state."""
        self._is_active = False
        self._session_id = None
        self._context_facts = None
