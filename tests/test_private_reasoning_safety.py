"""Tests ensuring strict private reasoning safety and output boundary hardening."""

import pytest
from typing import Dict, Any

from covenant.llm.provider import (
    strip_private_reasoning_text,
    sanitize_model_payload,
    ChatMessage,
    LLMResponse,
)
from covenant.domain.models import Commitment, Party, ProposedAction, AgentEvent, utc_now
from covenant.domain.enums import CommitmentStatus, ActionStatus, ActionType, RiskLevel, CommitmentCategory
from covenant.state_machine.machine import CommitmentStateMachine


def test_strip_private_reasoning_text():
    """Verify that <think> and <thought> tags with chain-of-thought are deterministically removed."""
    sample = (
        "<think>\n"
        "Here is my internal reasoning about why this is a commitment.\n"
        "The user wants me to output JSON.\n"
        "</think>\n"
        "{\"is_commitment\": true, \"confidence\": 0.95}"
    )
    cleaned = strip_private_reasoning_text(sample)
    assert cleaned == "{\"is_commitment\": true, \"confidence\": 0.95}"
    assert "internal reasoning" not in cleaned
    assert "<think>" not in cleaned
    assert "</think>" not in cleaned

    # Case insensitivity and thought tag
    sample2 = "<THOUGHT>Private thoughts</THOUGHT>Final answer here."
    cleaned2 = strip_private_reasoning_text(sample2)
    assert cleaned2 == "Final answer here."

    # Orphaned tag
    sample3 = "Orphaned tag <think> without closing."
    cleaned3 = strip_private_reasoning_text(sample3)
    assert "<think>" not in cleaned3


def test_sanitize_model_payload_strips_thinking():
    """Verify that dictionary structures are scrubbed of private reasoning fields."""
    raw_ollama = {
        "model": "qwen3.5:2b-q4_K_M",
        "created_at": "2026-09-14T21:00:00Z",
        "message": {
            "role": "assistant",
            "content": "<think>Drafting steps...</think>Operational answer",
            "thinking": "Thinking Process: step 1, step 2, step 3...",
            "thought": "More hidden internal reasoning",
        },
        "thinking": "Top-level reasoning trace",
        "total_duration": 42000000000,
        "eval_count": 80,
    }

    sanitized = sanitize_model_payload(raw_ollama)

    # Assert no private reasoning keys exist anywhere in payload
    assert "thinking" not in sanitized
    assert "thinking" not in sanitized.get("message", {})
    assert "thought" not in sanitized.get("message", {})
    assert sanitized["message"]["content"] == "Operational answer"
    assert "Drafting steps" not in sanitized["message"]["content"]
    assert sanitized["model"] == "qwen3.5:2b-q4_K_M"
    assert sanitized["eval_count"] == 80


def test_commitment_fixture_schema_integrity():
    """Regression test ensuring evaluation fixtures satisfy the actual domain schema."""
    promisor = Party(name="Sarah Jenkins", organization="Meridian Global", email="sjenkins@meridianglobal.com")
    promisee = Party(name="Alex North", organization="Northstar Studio", email="alex@northstarstudio.com")

    comm = Commitment(
        id="com_fixture_test",
        title="Test Commitment Fixture",
        description="Validating domain model requirements",
        promisor=promisor,
        promisee=promisee,
        category=CommitmentCategory.CLIENT_APPROVAL,
        status=CommitmentStatus.AWAITING_APPROVAL,
        risk=RiskLevel.HIGH,
    )

    action = ProposedAction(
        id="act_fixture_test",
        commitment_id="com_fixture_test",
        action_type=ActionType.FOLLOWUP_EMAIL,
        description="Follow-up email for sign-off",
        recipient="sjenkins@meridianglobal.com",
        subject="Follow-up",
        payload={"to": "sjenkins@meridianglobal.com"},
        risk=RiskLevel.HIGH,
        requires_human_approval=True,
    )

    comm.next_action = action

    assert comm.promisor.name == "Sarah Jenkins"
    assert comm.promisee.name == "Alex North"
    assert comm.status == CommitmentStatus.AWAITING_APPROVAL

    # State machine transition validity checks
    assert not CommitmentStateMachine.can_transition(CommitmentStatus.AWAITING_APPROVAL, CommitmentStatus.RESOLVED)
    assert CommitmentStateMachine.can_transition(CommitmentStatus.AWAITING_APPROVAL, CommitmentStatus.EXECUTING)
