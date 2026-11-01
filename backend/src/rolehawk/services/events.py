"""In-process pub/sub that feeds the SSE endpoint. One bounded queue per subscriber; a slow
client drops its oldest events rather than stalling publishers."""

from __future__ import annotations

import asyncio
import itertools
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

QUEUE_SIZE = 1000


@dataclass(frozen=True)
class Event:
    type: str
    data: dict[str, Any]
    id: int = field(default=0)


class EventBus:
    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue[Event]] = set()
        self._ids = itertools.count(1)

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)

    def publish(self, type_: str, data: dict[str, Any]) -> Event:
        event = Event(type=type_, data=data, id=next(self._ids))
        for queue in self._subscribers:
            if queue.full():
                queue.get_nowait()
            queue.put_nowait(event)
        return event

    @asynccontextmanager
    async def subscribe(self) -> AsyncIterator[asyncio.Queue[Event]]:
        queue: asyncio.Queue[Event] = asyncio.Queue(maxsize=QUEUE_SIZE)
        self._subscribers.add(queue)
        try:
            yield queue
        finally:
            self._subscribers.discard(queue)
