"""Tests for causal event telemetry."""

import pytest

from agent_runtime.core.contracts.event import Event, EventType
from agent_runtime.core.telemetry.sink import InMemoryEventSink


@pytest.mark.asyncio
async def test_event_sink_recording_and_trace_filtering():
    sink = InMemoryEventSink()

    e1 = Event(
        trace_id="trc_100",
        organization_id="org_1",
        task_id="tsk_1",
        event_type=EventType.TASK_CREATED,
        summary="Task 1 created",
    )
    e2 = Event(
        trace_id="trc_100",
        parent_event_id=e1.event_id,
        organization_id="org_1",
        task_id="tsk_1",
        event_type=EventType.TASK_ROUTED,
        summary="Task 1 routed to agent A",
    )
    e3 = Event(
        trace_id="trc_200",
        organization_id="org_1",
        task_id="tsk_2",
        event_type=EventType.TASK_CREATED,
        summary="Task 2 created",
    )

    await sink.record(e1)
    await sink.record(e2)
    await sink.record(e3)

    trc_100_events = await sink.list_events(trace_id="trc_100")
    assert len(trc_100_events) == 2
    assert trc_100_events[1].parent_event_id == e1.event_id

    tsk_2_events = await sink.list_events(task_id="tsk_2")
    assert len(tsk_2_events) == 1
    assert tsk_2_events[0].summary == "Task 2 created"
