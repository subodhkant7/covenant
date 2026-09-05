"""Tests for state isolation, snapshot fingerprinting, and external side-effect blocking."""

import socket
import pytest

from covenant.synthetic_data.store import workspace_store
from covenant_runtime_bridge.shadow.isolation import (
    ExternalSideEffectBlockedError,
    ExternalSideEffectGuard,
    clone_workspace_store,
    compute_workspace_fingerprint,
    diff_workspace_states,
)


def test_snapshot_cloning_and_independence():
    """Verify that mutations on a clone do not affect the original store."""
    original = workspace_store
    clone = clone_workspace_store(original)

    orig_email_count = len(original.emails)
    assert len(clone.emails) == orig_email_count

    # Mutate clone
    clone.send_email(
        from_addr="test@test.com",
        to_addrs=["client@test.com"],
        subject="Isolated Test",
        body="Isolated body",
    )

    # Clone has +1 email, original is completely unchanged
    assert len(clone.emails) == orig_email_count + 1
    assert len(original.emails) == orig_email_count


def test_snapshot_fingerprint_deterministic():
    """Verify that identical states yield identical hashes, and any mutation changes the hash."""
    clone_a = clone_workspace_store(workspace_store)
    clone_b = clone_workspace_store(workspace_store)

    fp_a = compute_workspace_fingerprint(clone_a)
    fp_b = compute_workspace_fingerprint(clone_b)
    assert fp_a == fp_b

    # Mutate clone_b
    clone_b.record_escalation("com_1", "Escalation", "Risk")
    fp_b_mutated = compute_workspace_fingerprint(clone_b)
    assert fp_a != fp_b_mutated


def test_external_side_effect_guard_blocks_real_network():
    """Verify that ExternalSideEffectGuard fails closed on unauthorized external socket calls."""
    guard = ExternalSideEffectGuard()
    with guard:
        with pytest.raises(ExternalSideEffectBlockedError) as exc_info:
            # Simulate an attempt to connect to an external server
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect(("api.external-vendor.com", 443))
        assert "Blocked external network call" in str(exc_info.value)


def test_diff_workspace_states():
    """Verify that diff_workspace_states accurately extracts additions and milestone changes."""
    initial = clone_workspace_store(workspace_store)
    final = clone_workspace_store(initial)

    final.send_email("me@corp.com", ["you@corp.com"], "Hello", "Body")
    final.record_escalation("com_101", "Late delivery", "Critical")

    diff = diff_workspace_states(initial, final)
    assert diff["new_emails_count"] == 1
    assert diff["new_escalations_count"] == 1
