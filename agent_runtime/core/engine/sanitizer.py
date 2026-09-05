"""Sanitizer for tool arguments, execution results, observations, and events."""

import json
import re
from typing import Any, Dict, List
from agent_runtime.core.contracts.tool import Observation

# Common sensitive regex patterns
SECRET_KEY_PATTERN = re.compile(
    r"(?i)(api[_-]?key|secret|password|bearer|token|auth|credential|private[_-]?key)"
)
SECRET_VALUE_PATTERNS = [
    re.compile(r"sk-[a-zA-Z0-9_\-]{10,}"),
    re.compile(r"Bearer\s+[a-zA-Z0-9\-\._~+/]+=*"),
    re.compile(r"(?i)(api[_-]?key|secret|password|bearer|token)\s*[:=]\s*['\"]?([a-zA-Z0-9_\-\.]{8,})['\"]?"),
]


class ObservationSanitizer:
    """
    Transforms raw tool arguments, execution outputs, and event payloads into
    safe, bounded, secret-free data structures.
    """

    def __init__(self, max_bytes: int = 32768):
        self.max_bytes = max_bytes

    def redact_text(self, text: str) -> str:
        sanitized = text
        for pattern in SECRET_VALUE_PATTERNS:
            sanitized = pattern.sub("[REDACTED_SECRET]", sanitized)
        return sanitized

    def sanitize_payload(self, data: Any) -> Any:
        """Recursively walks nested structures and redacts sensitive keys/values."""
        if data is None:
            return None
        if isinstance(data, str):
            return self.redact_text(data)
        if isinstance(data, (int, float, bool)):
            return data
        if isinstance(data, list):
            return [self.sanitize_payload(item) for item in data]
        if isinstance(data, dict):
            cleaned = {}
            for k, v in data.items():
                if SECRET_KEY_PATTERN.search(str(k)):
                    cleaned[k] = "[REDACTED_SECRET]"
                else:
                    cleaned[k] = self.sanitize_payload(v)
            return cleaned
        return self.redact_text(str(data))

    def sanitize_arguments(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Specific helper for tool argument dictionaries."""
        return self.sanitize_payload(arguments) or {}

    def sanitize(
        self,
        raw_result: Any,
        tool_name: str,
        execution_id: str,
        is_error: bool = False,
        error_message: str = None,
    ) -> Observation:
        if is_error:
            clean_err = self.redact_text(error_message or "Tool execution failed.")
            return Observation(
                execution_id=execution_id,
                tool_name=tool_name,
                success=False,
                data=None,
                error=clean_err,
                is_terminal_failure=False,
                truncated=False,
            )

        # Recursively sanitize nested structures
        cleaned_data = self.sanitize_payload(raw_result)

        # Convert to string to inspect size bounds
        try:
            raw_str = json.dumps(cleaned_data, default=str)
        except Exception:
            raw_str = str(cleaned_data)

        truncated = False
        if len(raw_str.encode("utf-8")) > self.max_bytes:
            raw_str = raw_str[: self.max_bytes] + "... [TRUNCATED_OBSERVATION]"
            truncated = True
            try:
                final_data = json.loads(raw_str)
            except Exception:
                final_data = raw_str
        else:
            final_data = cleaned_data

        return Observation(
            execution_id=execution_id,
            tool_name=tool_name,
            success=True,
            data=final_data,
            error=None,
            is_terminal_failure=False,
            truncated=truncated,
        )
