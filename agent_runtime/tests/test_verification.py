"""Tests for VerificationGate and independent outcome corroboration."""

import pytest

from agent_runtime.core.contracts.context import Task
from agent_runtime.core.contracts.verification import (
    Evidence,
    VerificationRequest,
    VerificationResult,
)
from agent_runtime.core.interfaces.verification import IVerifier
from agent_runtime.core.telemetry.sink import InMemoryEventSink
from agent_runtime.core.verification.gate import VerificationGate


class StubSuccessfulVerifier(IVerifier):
    async def verify(self, request: VerificationRequest, context):
        ev = Evidence(
            source_type="HTTP_PROBE",
            source_id="https://api.internal/health",
            summary="Port 443 active with HTTP 200",
            collected_by="StubVerifier",
        )
        return VerificationResult(
            task_id=request.task_id,
            verified=True,
            rationale="Service health corroborated.",
            evidence=[ev],
            verified_by="StubVerifier",
        )


class StubFailingVerifier(IVerifier):
    async def verify(self, request: VerificationRequest, context):
        return VerificationResult(
            task_id=request.task_id,
            verified=False,
            rationale="No positive response observed within window.",
            evidence=[],
            verified_by="StubVerifier",
        )


@pytest.mark.asyncio
async def test_verification_gate_success():
    sink = InMemoryEventSink()
    gate = VerificationGate(sink)
    task = Task(organization_id="org_test", intent="Verify service", required_role="verifier")

    res = await gate.verify_task(
        task=task,
        verifier=StubSuccessfulVerifier(),
        expected_outcome="Service is responding on 443",
    )
    assert res.verified is True
    assert len(res.evidence) == 1
    assert res.evidence[0].source_type == "HTTP_PROBE"

    events = await sink.list_events(task_id=task.id)
    assert len(events) == 2  # STARTED and DONE


@pytest.mark.asyncio
async def test_verification_gate_failure():
    sink = InMemoryEventSink()
    gate = VerificationGate(sink)
    task = Task(organization_id="org_test", intent="Verify service", required_role="verifier")

    res = await gate.verify_task(
        task=task,
        verifier=StubFailingVerifier(),
        expected_outcome="Service is responding on 443",
    )
    assert res.verified is False
    assert "No positive response" in res.rationale
