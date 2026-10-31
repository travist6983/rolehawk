"""The one entry point the rest of the backend uses to call Claude."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable, Sequence

from pydantic import BaseModel

from offerbound.config import LLMSettings
from offerbound.llm.errors import LLMNotConfiguredError
from offerbound.llm.meter import Estimate, SpendMeter
from offerbound.llm.provider import LLMProvider
from offerbound.llm.routing import Route, route
from offerbound.llm.types import (
    Completion,
    LLMRequest,
    Message,
    StreamDone,
    StreamEvent,
    SystemBlock,
    Task,
    ToolDef,
    Usage,
)

ProviderFactory = Callable[[], LLMProvider | None]


class LLMService:
    def __init__(
        self,
        provider_factory: ProviderFactory,
        settings: Callable[[], LLMSettings],
        meter: SpendMeter,
    ) -> None:
        self._provider_factory = provider_factory
        self._settings = settings
        self.meter = meter

    def provider(self) -> LLMProvider:
        provider = self._provider_factory()
        if provider is None:
            raise LLMNotConfiguredError("no Anthropic API key configured")
        return provider

    @property
    def configured(self) -> bool:
        return self._provider_factory() is not None

    def route(self, task: Task) -> Route:
        return route(task, self._settings())

    def _request(
        self,
        task: Task,
        system: Sequence[SystemBlock],
        messages: Sequence[Message],
        tools: Sequence[ToolDef] = (),
    ) -> LLMRequest:
        r = self.route(task)
        # Snapshot the sequences: callers keep appending to their history lists.
        return LLMRequest(
            model=r.model,
            system=tuple(system),
            messages=tuple(messages),
            max_tokens=r.max_tokens,
            effort=r.effort,
            tools=tuple(tools),
        )

    async def _preflight(self) -> LLMProvider:
        provider = self.provider()
        await asyncio.to_thread(self.meter.check_cap, self._settings().monthly_cap_usd)
        return provider

    async def _record(
        self,
        command: str,
        provider: LLMProvider,
        completion_model: str,
        usage: Usage,
        task_id: str | None,
    ) -> None:
        await asyncio.to_thread(
            self.meter.record,
            command=command,
            provider=provider.name,
            model=completion_model,
            usage=usage,
            task_id=task_id,
        )

    async def complete(
        self,
        *,
        command: str,
        task: Task,
        system: Sequence[SystemBlock],
        messages: Sequence[Message],
        tools: Sequence[ToolDef] = (),
        task_id: str | None = None,
    ) -> Completion:
        provider = await self._preflight()
        completion = await provider.complete(self._request(task, system, messages, tools))
        await self._record(command, provider, completion.model, completion.usage, task_id)
        return completion

    async def stream(
        self,
        *,
        command: str,
        task: Task,
        system: Sequence[SystemBlock],
        messages: Sequence[Message],
        tools: Sequence[ToolDef] = (),
        task_id: str | None = None,
    ) -> AsyncIterator[StreamEvent]:
        provider = await self._preflight()
        async for event in provider.stream(self._request(task, system, messages, tools)):
            if isinstance(event, StreamDone):
                usage = event.completion.usage
                await self._record(command, provider, event.completion.model, usage, task_id)
            yield event

    async def structured[T: BaseModel](
        self,
        *,
        command: str,
        task: Task,
        system: Sequence[SystemBlock],
        messages: Sequence[Message],
        schema: type[T],
        task_id: str | None = None,
    ) -> T:
        provider = await self._preflight()
        result = await provider.structured(self._request(task, system, messages), schema)
        await self._record(command, provider, result.model, result.usage, task_id)
        return result.value

    def estimate(
        self, task: Task, *, input_tokens: int, output_tokens: int, calls: int = 1
    ) -> Estimate:
        """Pre-run cost estimate for a batch command, shown before it starts."""
        return self.meter.estimate(
            model=self.route(task).model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            calls=calls,
            cap_usd=self._settings().monthly_cap_usd,
        )
