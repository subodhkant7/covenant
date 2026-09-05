"""External Agent Sanitizer: Multi-layer recursive redaction and execution handle isolation."""

import io
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple
from pydantic import BaseModel

from agent_runtime.core.contracts.tool import Observation


class UnsafeContextError(ValueError):
    """Raised when an untrusted or raw execution handle is detected in external context."""
    pass


# Comprehensive pattern matching sensitive keys in dictionaries
SECRET_KEY_REGEX = re.compile(
    r"(?i)^(.*_)?(api[_-]?key|access[_-]?token|refresh[_-]?token|bearer[_-]?token|private[_-]?key|secret|password|passwd|authorization|cookie|credentials|connection[_-]?string)(_.*)?$"
)

# Common sensitive regex patterns in arbitrary strings
PATTERN_PRIVATE_KEY = re.compile(r"-----BEGIN (?:[A-Z ]+)?PRIVATE KEY-----[\s\S]+?-----END (?:[A-Z ]+)?PRIVATE KEY-----")
PATTERN_BEARER = re.compile(r"(?i)Bearer\s+[a-zA-Z0-9\-\._~+/]+=*")
PATTERN_TOKEN = re.compile(r"\b(sk-[a-zA-Z0-9_\-]{8,}|ghp_[a-zA-Z0-9]{15,}|glpat-[a-zA-Z0-9_\-]{15,}|ey[a-zA-Z0-9_-]{12,}\.[a-zA-Z0-9_-]{12,}\.[a-zA-Z0-9_-]{12,})\b")
PATTERN_URL_CREDENTIALS = re.compile(r"(?i)([a-z0-9+.-]+):\/\/[^:\s\/]+:([^@\s\/]+)@")
PATTERN_KEY_VAL = re.compile(r"(?i)(api[_-]?key|access[_-]?token|secret|password|passwd)\s*[:=]\s*['\"]?([^\s'\",;]{6,})['\"]?")

SECRET_VALUE_PATTERNS = [
    PATTERN_PRIVATE_KEY,
    PATTERN_BEARER,
    PATTERN_TOKEN,
    PATTERN_URL_CREDENTIALS,
    PATTERN_KEY_VAL,
]


class ExternalAgentSanitizer:
    """Authoritative sanitizer protecting the external agent boundary.

    Guarantees:
    1. Secrets (tokens, keys, passwords, cookies, auth headers) are recursively redacted.
    2. Business identifiers (PRJ-ATLAS, com_atlas_approval, invoice-123) are preserved.
    3. Raw execution handles (callables, DB connections, open files, sockets) fail closed.
    4. Data structures remain structurally usable and strictly JSON-serializable.
    5. Private chain-of-thought is excluded from external context.
    """

    def __init__(self, max_payload_bytes: int = 65536):
        self.max_payload_bytes = max_payload_bytes

    def redact_text(self, text: str) -> str:
        """Redacts sensitive patterns within text while preserving ordinary text and IDs."""
        if not text or not isinstance(text, str):
            return text

        sanitized = text
        for pattern in SECRET_VALUE_PATTERNS:
            if pattern is PATTERN_URL_CREDENTIALS:
                # For URL credentials, preserve scheme and host, redact password
                sanitized = pattern.sub(r"\1://[REDACTED_USER]:[REDACTED_SECRET]@", sanitized)
            elif pattern is PATTERN_KEY_VAL:
                # For key-value patterns, preserve key, redact secret value
                sanitized = pattern.sub(r"\1: [REDACTED_SECRET]", sanitized)
            else:
                sanitized = pattern.sub("[REDACTED_SECRET]", sanitized)
        return sanitized

    def _check_unsafe_object(self, obj: Any) -> None:
        """Fails closed if obj is or encapsulates an un-serializable execution handle."""
        # Check classes or modules
        if isinstance(obj, type) or hasattr(obj, "__file__"):
            raise UnsafeContextError(f"Class or module reference of type '{type(obj).__name__}' cannot be exposed to external agent.")

        # Check callables (functions, methods, lambdas)
        if callable(obj):
            raise UnsafeContextError(f"Callable object of type '{type(obj).__name__}' cannot be exposed to external agent.")

        # Check I/O and file handles
        if isinstance(obj, io.IOBase) or hasattr(obj, "fileno") or (hasattr(obj, "read") and hasattr(obj, "write")):
            raise UnsafeContextError(f"System resource handle of type '{type(obj).__name__}' cannot be exposed to external agent.")

        # Check database / runtime engine / socket / subprocess instances by type name
        type_name = type(obj).__name__
        if any(h in type_name for h in ["Connection", "Engine", "Registry", "Repository", "Store", "Matrix", "Gate", "Manager", "Popen", "Socket"]):
            raise UnsafeContextError(f"Runtime execution handle of type '{type_name}' cannot be exposed to external agent.")

    def sanitize_payload(self, data: Any, fail_on_unsafe: bool = True) -> Any:
        """Recursively walks data structures to redact secrets and reject execution handles."""
        if data is None:
            return None

        # Check for execution handles
        if fail_on_unsafe:
            self._check_unsafe_object(data)

        # Primitives
        if isinstance(data, (int, float, bool)):
            return data

        if isinstance(data, str):
            return self.redact_text(data)

        if isinstance(data, datetime):
            return data.isoformat()

        # Pydantic models
        if isinstance(data, BaseModel):
            return self.sanitize_payload(data.model_dump(mode="json"), fail_on_unsafe=fail_on_unsafe)

        # Lists and Tuples
        if isinstance(data, (list, tuple)):
            return [self.sanitize_payload(item, fail_on_unsafe=fail_on_unsafe) for item in data]

        # Sets
        if isinstance(data, (set, frozenset)):
            sanitized_list = [self.sanitize_payload(item, fail_on_unsafe=fail_on_unsafe) for item in data]
            try:
                return sorted(sanitized_list, key=str)
            except Exception:
                return sanitized_list

        # Dictionaries
        if isinstance(data, dict):
            cleaned: Dict[str, Any] = {}
            for k, v in data.items():
                if fail_on_unsafe:
                    self._check_unsafe_object(k)

                k_str = str(k)
                if SECRET_KEY_REGEX.search(k_str):
                    cleaned[k_str] = "[REDACTED_SECRET]"
                else:
                    cleaned[k_str] = self.sanitize_payload(v, fail_on_unsafe=fail_on_unsafe)
            return cleaned

        # Any unknown object: if fail_on_unsafe is True, reject!
        if fail_on_unsafe:
            raise UnsafeContextError(
                f"Object of type '{type(data).__name__}' cannot be safely serialized to external agent protocol."
            )
        return "[UNSERIALIZABLE_OBJECT]"

    def sanitize_context_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Sanitizes task input_data or context parcels."""
        if not isinstance(data, dict):
            raise UnsafeContextError(f"Context data must be a dictionary, received {type(data).__name__}.")
        return self.sanitize_payload(data, fail_on_unsafe=True)

    def sanitize_observation_data(self, data: Any) -> Any:
        """Sanitizes tool execution results before external delivery."""
        return self.sanitize_payload(data, fail_on_unsafe=True)

    def sanitize_telemetry_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Redacts secrets and eliminates private thought traces from telemetry."""
        cleaned = self.sanitize_payload(payload, fail_on_unsafe=False)
        if isinstance(cleaned, dict):
            cleaned.pop("thought", None)
            cleaned.pop("chain_of_thought", None)
        return cleaned
