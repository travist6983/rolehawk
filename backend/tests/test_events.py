import asyncio

import pytest

from offerbound.services import events as events_module
from offerbound.services.events import EventBus
from offerbound.services.stream import sse_events

pytestmark = pytest.mark.anyio


async def test_publish_reaches_all_subscribers_and_unsubscribes() -> None:
    bus = EventBus()
    async with bus.subscribe() as a, bus.subscribe() as b:
        assert bus.subscriber_count == 2
        bus.publish("task.updated", {"id": "1"})
        assert a.get_nowait().data == {"id": "1"}
        assert b.get_nowait().data == {"id": "1"}
    assert bus.subscriber_count == 0


async def test_slow_subscriber_drops_oldest(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(events_module, "QUEUE_SIZE", 3)
    bus = EventBus()
    async with bus.subscribe() as queue:
        for n in range(5):
            bus.publish("tick", {"n": n})
        assert [queue.get_nowait().data["n"] for _ in range(3)] == [2, 3, 4]


async def test_sse_stream_formats_events() -> None:
    bus = EventBus()
    stream = sse_events(bus)
    ready = await anext(stream)
    assert ready.event == "ready"
    assert bus.subscriber_count == 1

    bus.publish("task.updated", {"id": "abc", "status": "running"})
    event = await asyncio.wait_for(anext(stream), timeout=1)
    assert event.event == "task.updated"
    assert event.data == {"id": "abc", "status": "running"}
    assert event.id is not None

    await stream.aclose()
    assert bus.subscriber_count == 0
