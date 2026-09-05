"""VerificationGate: Authoritative outcome validation engine."""

from typing import Any, Dict
from agent_runtime.core.contracts.context import Task
from agent_runtime.core.contracts.event import Event, EventType
from agent_runtime.core.contracts.verification import VerificationRequest, VerificationResult
from agent_runtime.core.interfaces.telemetry import IEventSink
from agent_runtime.core.interfaces.verification import IVerifier


class VerificationGate:
    """
    Evaluates real-world outcome proof before task closure.
    Authority over task completion is held exclusively by this gate.
    """

    def __init__(self, event_sink: IEventSink):
        self.event_sink = event_sink

    async def verify_task(
        self,
        task: Task,
        verifier: IVerifier,
        expected_outcome: str,
        verification_criteria: Dict[str, Any] = None,
        context: Dict[str, Any] = None,
    ) -> VerificationResult:
        trace_id = task.workflow_run_id or f"trc_{task.id}"
        req = VerificationRequest(
            task_id=task.id,
            expected_outcome=expected_outcome,
            verification_criteria=verification_criteria or {},
        )

        await self.event_sink.record(
            Event(
                trace_id=trace_id,
                organization_id=task.organization_id,
                task_id=task.id,
                event_type=EventType.VERIFICATION_STARTED,
                summary=f"Initiated verification pass for task '{task.id}'.",
                payload={"expected_outcome": expected_outcome},
            )
        )

        result = await verifier.verify(req, context or {})

        await self.event_sink.record(
            Event(
                trace_id=trace_id,
                organization_id=task.organization_id,
                task_id=task.id,
                event_type=EventType.VERIFICATION_DONE,
                summary=f"Verification completed: verified={result.verified}.",
                payload={
                    "verified": result.verified,
                    "evidence_count": len(result.evidence),
                    "rationale": result.rationale,
                },
            )
        )

        return result
