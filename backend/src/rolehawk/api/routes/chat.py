from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.sse import EventSourceResponse, ServerSentEvent
from pydantic import BaseModel, Field

from rolehawk.api.deps import RuntimeDep
from rolehawk.chat.service import (
    ChatMessageView,
    ChatSessionNotFoundError,
    ChatSessionView,
    ViewContext,
)

router = APIRouter(prefix="/api/chat", tags=["chat"])


class SessionIn(BaseModel):
    title: str | None = Field(default=None, max_length=255)


class MessageIn(BaseModel):
    text: str = Field(min_length=1, max_length=20_000)
    view: ViewContext | None = None


@router.post("/sessions", status_code=201)
async def create_session(runtime: RuntimeDep, body: SessionIn | None = None) -> ChatSessionView:
    return await asyncio.to_thread(runtime.chat.create_session, body.title if body else None)


@router.get("/sessions")
async def list_sessions(runtime: RuntimeDep) -> list[ChatSessionView]:
    return await asyncio.to_thread(runtime.chat.list_sessions)


@router.get("/sessions/{session_id}/messages")
async def list_messages(session_id: str, runtime: RuntimeDep) -> list[ChatMessageView]:
    try:
        return await asyncio.to_thread(runtime.chat.messages, session_id)
    except ChatSessionNotFoundError:
        raise HTTPException(status_code=404, detail="Chat session not found") from None


async def existing_session(session_id: str, runtime: RuntimeDep) -> str:
    """Checked as a dependency so a missing session is a 404 before any streaming starts."""
    try:
        await asyncio.to_thread(runtime.chat.messages, session_id)
    except ChatSessionNotFoundError:
        raise HTTPException(status_code=404, detail="Chat session not found") from None
    return session_id


@router.post("/sessions/{session_id}/messages", response_class=EventSourceResponse)
async def send_message(
    session_id: Annotated[str, Depends(existing_session)], body: MessageIn, runtime: RuntimeDep
) -> AsyncIterator[ServerSentEvent]:
    """Streams the reply as SSE: text, tool_call, tool_result, card, error, done, and
    finally memory_proposals when facts were found."""
    async for event in runtime.chat.send(session_id, body.text, body.view):
        yield ServerSentEvent(event=event.type, data=event.data)
