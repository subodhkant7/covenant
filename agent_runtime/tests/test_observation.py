"""Tests for ObservationSanitizer."""

from agent_runtime.core.engine.sanitizer import ObservationSanitizer


def test_secret_redaction():
    sanitizer = ObservationSanitizer()

    raw_output = {
        "user": "alice",
        "api_key": "sk-1234567890abcdef1234567890",
        "auth_header": "Bearer secret_token_xyz_999",
        "data": "normal content",
    }
    obs = sanitizer.sanitize(raw_output, tool_name="fetch_user", execution_id="exec_1")
    assert obs.success is True
    assert obs.data["user"] == "alice"
    assert "sk-" not in str(obs.data["api_key"])
    assert "[REDACTED_SECRET]" in str(obs.data["api_key"])
    assert "[REDACTED_SECRET]" in str(obs.data["auth_header"])


def test_observation_truncation():
    sanitizer = ObservationSanitizer(max_bytes=100)
    huge_output = "A" * 500

    obs = sanitizer.sanitize(huge_output, tool_name="fetch_big_log", execution_id="exec_2")
    assert obs.truncated is True
    assert len(obs.data) < 200
    assert "[TRUNCATED_OBSERVATION]" in obs.data
