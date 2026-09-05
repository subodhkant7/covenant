"""Unix Domain Socket IPC Transport for Out-of-Process External Agents.

Implements length-prefixed binary framing, hard payload limits (1 MiB),
secure runtime-owned socket management (0o700 directory permissions),
and fail-closed connection handling.
"""

import asyncio
import json
import os
import struct
import sys
import tempfile
import time
from typing import Any, Dict, Optional
from uuid import uuid4

from agent_runtime.adapters.external_agent import (
    ExternalAgentRequest,
    ExternalAgentResponse,
    IExternalAgentTransport,
)
from agent_runtime.core.contracts.event import Event, EventType
from agent_runtime.core.interfaces.telemetry import IEventSink

# 1 MiB hard message payload limit (Section 6)
MAX_EXTERNAL_AGENT_MESSAGE_BYTES = 1024 * 1024

# 4-byte big-endian unsigned integer length prefix (Section 5)
HEADER_FORMAT = "!I"
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)


class MessageSizeExceededError(Exception):
    """Raised when an inbound or outbound message exceeds MAX_EXTERNAL_AGENT_MESSAGE_BYTES."""
    pass


class ProtocolFramingError(Exception):
    """Raised when protocol framing is truncated, corrupt, or invalid."""
    pass


class TransportConnectionError(Exception):
    """Raised when transport connection is closed, reset, or unavailable."""
    pass


async def read_framed_message(
    reader: asyncio.StreamReader,
    max_bytes: int = MAX_EXTERNAL_AGENT_MESSAGE_BYTES,
) -> bytes:
    """Reads a length-prefixed binary framed message from a stream.

    Enforces the byte limit BEFORE buffering the body to prevent memory exhaustion attacks.
    """
    try:
        header = await reader.readexactly(HEADER_SIZE)
    except asyncio.IncompleteReadError as e:
        if len(e.partial) == 0:
            raise TransportConnectionError("Connection closed by peer before header could be read.")
        raise ProtocolFramingError(f"Incomplete framing header: expected {HEADER_SIZE} bytes, received {len(e.partial)}")

    (msg_length,) = struct.unpack(HEADER_FORMAT, header)

    if msg_length > max_bytes:
        raise MessageSizeExceededError(
            f"Inbound message size {msg_length} bytes exceeds limit of {max_bytes} bytes."
        )

    try:
        body = await reader.readexactly(msg_length)
    except asyncio.IncompleteReadError as e:
        raise ProtocolFramingError(
            f"Incomplete message body: expected {msg_length} bytes, received {len(e.partial)}"
        )

    return body


async def write_framed_message(
    writer: asyncio.StreamWriter,
    payload: bytes,
    max_bytes: int = MAX_EXTERNAL_AGENT_MESSAGE_BYTES,
) -> None:
    """Writes a length-prefixed binary framed message to a stream."""
    if len(payload) > max_bytes:
        raise MessageSizeExceededError(
            f"Outbound message size {len(payload)} bytes exceeds limit of {max_bytes} bytes."
        )

    header = struct.pack(HEADER_FORMAT, len(payload))
    writer.write(header + payload)
    await writer.drain()


class UnixSocketExternalAgentTransport(IExternalAgentTransport):
    """Unix Domain Socket IPC transport mediating between Runtime and separate worker process.

    Guarantees:
    1. Zero Python object references cross the transport (JSON data only).
    2. Length-prefixed framing prevents partial reads and message concatenation.
    3. Payload limits (1 MiB) strictly enforced before JSON or Pydantic parsing.
    4. Sockets reside in secure, runtime-owned temporary directories with 0o700 permissions.
    5. Clean socket and worker cleanup on shutdown or crash.
    """

    def __init__(
        self,
        socket_dir: Optional[str] = None,
        event_sink: Optional[IEventSink] = None,
        max_message_bytes: int = MAX_EXTERNAL_AGENT_MESSAGE_BYTES,
    ):
        self.event_sink = event_sink
        self.max_message_bytes = max_message_bytes

        # Section 7: Generate unique socket path in restrictive directory (0o700)
        if socket_dir:
            self.socket_dir = socket_dir
            self._managed_dir = False
        else:
            self.socket_dir = tempfile.mkdtemp(prefix="agent-runtime-")
            os.chmod(self.socket_dir, 0o700)
            self._managed_dir = True

        self.socket_path = os.path.join(self.socket_dir, f"agent-{uuid4().hex[:8]}.sock")

        self.server: Optional[asyncio.Server] = None
        self.client_reader: Optional[asyncio.StreamReader] = None
        self.client_writer: Optional[asyncio.StreamWriter] = None
        self.connected_event = asyncio.Event()

        self.worker_process: Optional[asyncio.subprocess.Process] = None
        self.worker_pid: Optional[int] = None
        self._is_closed = False

    async def start(self) -> str:
        """Starts the Unix Domain Socket listener and returns the socket path."""
        self.server = await asyncio.start_unix_server(
            self._handle_incoming_connection,
            path=self.socket_path,
        )
        return self.socket_path

    async def _handle_incoming_connection(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """Accepts the connection from the external worker process."""
        self.client_reader = reader
        self.client_writer = writer
        self.connected_event.set()

        if self.event_sink:
            await self.event_sink.record(
                Event(
                    trace_id=f"trc_transport_{uuid4().hex[:8]}",
                    organization_id="system",
                    event_type=EventType.EXTERNAL_AGENT_CONNECTED,
                    summary="External agent connected via Unix domain socket.",
                    payload={
                        "socket_path": self.socket_path,
                        "worker_pid": self.worker_pid,
                    },
                )
            )

    async def spawn_worker(
        self,
        worker_mode: str = "normal",
        worker_script: Optional[str] = None,
        timeout: float = 5.0,
        custom_env: Optional[Dict[str, str]] = None,
    ) -> asyncio.subprocess.Process:
        """Spawns an out-of-process external agent worker with a strictly minimal environment."""
        if not self.server:
            await self.start()

        # Section 8: Construct explicit minimal environment (no DB URL, secrets, or handles)
        repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        minimal_env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "PYTHONPATH": repo_root,
            "LANG": os.environ.get("LANG", "en_US.UTF-8"),
            "WORKER_MODE": worker_mode,
        }
        if custom_env:
            minimal_env.update(custom_env)

        target_script = worker_script or os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "external_agent_worker.py",
        )

        cmd = [
            sys.executable,
            target_script,
            "--socket",
            self.socket_path,
            "--mode",
            worker_mode,
        ]

        self.worker_process = await asyncio.create_subprocess_exec(
            *cmd,
            env=minimal_env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        self.worker_pid = self.worker_process.pid

        if self.event_sink:
            await self.event_sink.record(
                Event(
                    trace_id=f"trc_proc_{self.worker_pid}",
                    organization_id="system",
                    event_type=EventType.EXTERNAL_AGENT_PROCESS_STARTED,
                    summary=f"External agent process {self.worker_pid} started in mode '{worker_mode}'.",
                    payload={"worker_pid": self.worker_pid, "mode": worker_mode},
                )
            )

        # Wait for worker to connect to the socket
        try:
            await asyncio.wait_for(self.connected_event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            await self.close()
            raise TransportConnectionError(
                f"Worker process {self.worker_pid} failed to connect to socket within {timeout}s."
            )

        return self.worker_process

    async def send_and_receive(self, request: ExternalAgentRequest) -> ExternalAgentResponse:
        """Sends length-prefixed JSON request and retrieves length-prefixed JSON response."""
        if self._is_closed:
            raise TransportConnectionError("Transport is closed.")

        if not self.client_writer or not self.client_reader:
            raise TransportConnectionError("External agent process is not connected.")

        # Check if worker died unexpectedly
        if self.worker_process and self.worker_process.returncode is not None:
            raise TransportConnectionError(
                f"External agent process {self.worker_pid} terminated prematurely with code {self.worker_process.returncode}."
            )

        start_time = time.monotonic()
        trace_id = f"trc_{request.task.task_id}"

        # 1. Serialize and write framed request
        try:
            req_json = request.model_dump_json()
            req_bytes = req_json.encode("utf-8")
            await write_framed_message(self.client_writer, req_bytes, max_bytes=self.max_message_bytes)
        except Exception as exc:
            if self.event_sink:
                await self.event_sink.record(
                    Event(
                        trace_id=trace_id,
                        organization_id=request.task.organization_id,
                        task_id=request.task.task_id,
                        event_type=EventType.EXTERNAL_AGENT_PROTOCOL_ERROR,
                        summary=f"Failed to write outbound framed request: {str(exc)}",
                        payload={"error": str(exc), "worker_pid": self.worker_pid},
                    )
                )
            raise TransportConnectionError(f"Failed to send request over Unix socket: {str(exc)}") from exc

        # 2. Read framed response with size limit enforcement
        try:
            resp_bytes = await read_framed_message(self.client_reader, max_bytes=self.max_message_bytes)
        except (MessageSizeExceededError, ProtocolFramingError) as pe:
            if self.event_sink:
                await self.event_sink.record(
                    Event(
                        trace_id=trace_id,
                        organization_id=request.task.organization_id,
                        task_id=request.task.task_id,
                        event_type=EventType.EXTERNAL_AGENT_PROTOCOL_ERROR,
                        summary=f"Inbound protocol framing violation: {str(pe)}",
                        payload={"error": str(pe), "worker_pid": self.worker_pid},
                    )
                )
            raise pe
        except (asyncio.IncompleteReadError, ConnectionResetError, BrokenPipeError, TransportConnectionError) as ce:
            if self.event_sink:
                await self.event_sink.record(
                    Event(
                        trace_id=trace_id,
                        organization_id=request.task.organization_id,
                        task_id=request.task.task_id,
                        event_type=EventType.EXTERNAL_AGENT_DISCONNECTED,
                        summary="External agent disconnected unexpectedly during read.",
                        payload={"error": str(ce), "worker_pid": self.worker_pid},
                    )
                )
            raise TransportConnectionError(f"Connection lost while awaiting worker response: {str(ce)}") from ce

        # 3. Deserialize JSON and validate response
        duration = time.monotonic() - start_time
        try:
            resp_data = json.loads(resp_bytes.decode("utf-8"))
        except Exception as je:
            if self.event_sink:
                await self.event_sink.record(
                    Event(
                        trace_id=trace_id,
                        organization_id=request.task.organization_id,
                        task_id=request.task.task_id,
                        event_type=EventType.EXTERNAL_AGENT_PROTOCOL_ERROR,
                        summary="External agent response was not valid JSON.",
                        payload={"error": str(je), "worker_pid": self.worker_pid},
                    )
                )
            raise ProtocolFramingError(f"Worker returned invalid JSON: {str(je)}") from je

        # Pydantic validation enforces extra="forbid"
        try:
            response = ExternalAgentResponse.model_validate(resp_data)
        except Exception as ve:
            if self.event_sink:
                await self.event_sink.record(
                    Event(
                        trace_id=trace_id,
                        organization_id=request.task.organization_id,
                        task_id=request.task.task_id,
                        event_type=EventType.EXTERNAL_AGENT_PROTOCOL_ERROR,
                        summary="External agent response schema validation failed.",
                        payload={"error": str(ve), "worker_pid": self.worker_pid},
                    )
                )
            raise ve

        return response

    async def close(self) -> None:
        """Shuts down client connection, server listener, worker process, and cleans up socket."""
        if self._is_closed:
            return
        self._is_closed = True

        # Close client stream
        if self.client_writer:
            try:
                self.client_writer.close()
                await self.client_writer.wait_closed()
            except Exception:
                pass
            self.client_writer = None
            self.client_reader = None

        # Close server
        if self.server:
            try:
                self.server.close()
                await self.server.wait_closed()
            except Exception:
                pass
            self.server = None

        # Terminate worker process if running
        if self.worker_process and self.worker_process.returncode is None:
            try:
                self.worker_process.terminate()
                try:
                    await asyncio.wait_for(self.worker_process.wait(), timeout=1.0)
                except asyncio.TimeoutError:
                    self.worker_process.kill()
                    await self.worker_process.wait()
            except Exception:
                pass

            if self.event_sink and self.worker_pid:
                try:
                    await self.event_sink.record(
                        Event(
                            trace_id=f"trc_proc_{self.worker_pid}",
                            organization_id="system",
                            event_type=EventType.EXTERNAL_AGENT_PROCESS_EXITED,
                            summary=f"External agent process {self.worker_pid} terminated with code {self.worker_process.returncode}.",
                            payload={
                                "worker_pid": self.worker_pid,
                                "return_code": self.worker_process.returncode,
                            },
                        )
                    )
                except Exception:
                    pass

        # Remove socket file
        if os.path.exists(self.socket_path):
            try:
                os.remove(self.socket_path)
            except OSError:
                pass

        # Remove temporary directory if managed
        if self._managed_dir and os.path.exists(self.socket_dir):
            try:
                os.rmdir(self.socket_dir)
            except OSError:
                pass
