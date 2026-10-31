"""Turns event-bus traffic into Server-Sent Events."""

from __future__ import annotations

from collections.abc import AsyncGenerator

from fastapi.sse import ServerSentEvent

from offerbound.services.events import EventBus

RETRY_MS = 3000


async def sse_events(bus: EventBus) -> AsyncGenerator[ServerSentEvent]:
    async with bus.subscribe() as queue:
        yield ServerSentEvent(event="ready", data={}, retry=RETRY_MS)
        while True:
            event = await queue.get()
            yield ServerSentEvent(event=event.type, data=event.data, id=str(event.id))
