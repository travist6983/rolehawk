"""Scripted provider for tests and offline development. No network, deterministic."""

from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import AsyncIterator, Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel

from rolehawk.llm.errors import LLMAuthError, LLMRefusalError
from rolehawk.llm.models import CATALOG
from rolehawk.llm.types import (
    Completion,
    LLMRequest,
    ModelChoice,
    StreamDone,
    StreamEvent,
    Structured,
    TextDelta,
    ToolCall,
    Usage,
)


@dataclass
class FakeReply:
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: Usage = field(default_factory=lambda: Usage(input_tokens=100, output_tokens=20))
    model: str | None = None  # defaults to the requested model
    refusal: str | None = None  # a refusal category: raise LLMRefusalError instead


StructuredHandler = Callable[[LLMRequest, type[BaseModel]], BaseModel]


class FakeProvider:
    name = "fake"

    def __init__(
        self,
        replies: Iterable[FakeReply | Exception] = (),
        structured: Iterable[BaseModel | dict[str, Any] | Exception] = (),
        *,
        structured_handler: StructuredHandler | None = None,
        latency_s: float = 0.0,
        auth_ok: bool = True,
    ) -> None:
        self.replies: deque[FakeReply | Exception] = deque(replies)
        self.structured_replies: deque[BaseModel | dict[str, Any] | Exception] = deque(structured)
        self.structured_handler = structured_handler
        self.latency_s = latency_s
        self.auth_ok = auth_ok
        self.requests: list[LLMRequest] = []
        self.structured_requests: list[tuple[LLMRequest, type[BaseModel]]] = []

    def queue(self, *replies: FakeReply | Exception) -> None:
        self.replies.extend(replies)

    def queue_structured(self, *values: BaseModel | dict[str, Any] | Exception) -> None:
        self.structured_replies.extend(values)

    async def _delay(self) -> None:
        if self.latency_s:
            await asyncio.sleep(self.latency_s)

    async def complete(self, request: LLMRequest) -> Completion:
        self.requests.append(request)
        await self._delay()
        if not self.replies:
            raise AssertionError("FakeProvider: no scripted reply left for complete()/stream()")
        reply = self.replies.popleft()
        if isinstance(reply, Exception):
            raise reply
        if reply.refusal is not None:
            raise LLMRefusalError(reply.refusal, "scripted refusal")
        raw: list[dict[str, Any]] = [{"type": "thinking", "thinking": "", "signature": "fake"}]
        if reply.text:
            raw.append({"type": "text", "text": reply.text})
        raw += [
            {"type": "tool_use", "id": c.id, "name": c.name, "input": c.input}
            for c in reply.tool_calls
        ]
        return Completion(
            model=reply.model or request.model,
            text=reply.text,
            tool_calls=list(reply.tool_calls),
            stop_reason="tool_use" if reply.tool_calls else "end_turn",
            usage=reply.usage,
            raw=raw,
            request_id="req_fake",
        )

    async def stream(self, request: LLMRequest) -> AsyncIterator[StreamEvent]:
        completion = await self.complete(request)
        for index, word in enumerate(completion.text.split(" ")):
            yield TextDelta(word if index == 0 else f" {word}")
        yield StreamDone(completion)

    async def structured[T: BaseModel](self, request: LLMRequest, schema: type[T]) -> Structured[T]:
        self.structured_requests.append((request, schema))
        await self._delay()
        if self.structured_replies:
            item = self.structured_replies.popleft()
            if isinstance(item, Exception):
                raise item
            value = schema.model_validate(
                item.model_dump() if isinstance(item, BaseModel) else item
            )
        elif self.structured_handler is not None:
            value = schema.model_validate(self.structured_handler(request, schema).model_dump())
        else:
            raise AssertionError(f"FakeProvider: no scripted structured reply for {schema}")
        return Structured(
            value=value,
            model=request.model,
            usage=Usage(input_tokens=200, output_tokens=40),
            request_id="req_fake",
        )

    async def list_models(self) -> list[ModelChoice]:
        return [ModelChoice(id=m.id, display_name=m.label) for m in CATALOG.values()]

    async def check(self) -> None:
        if not self.auth_ok:
            raise LLMAuthError("fake auth failure")
