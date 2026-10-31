from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import APIRouter
from fastapi.sse import EventSourceResponse, ServerSentEvent

from offerbound.api.deps import RuntimeDep
from offerbound.services.stream import sse_events

router = APIRouter(prefix="/api", tags=["events"])


@router.get("/events", response_class=EventSourceResponse)
async def stream_events(runtime: RuntimeDep) -> AsyncIterator[ServerSentEvent]:
    """Live progress stream. Event types: `ready`, `task.updated`."""
    async for event in sse_events(runtime.bus):
        yield event
