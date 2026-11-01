from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol

from pydantic import BaseModel

from rolehawk.llm.types import (
    Completion,
    LLMRequest,
    ModelChoice,
    StreamEvent,
    Structured,
    Usage,
)


class LLMProvider(Protocol):
    """One backend that can serve Claude requests. Implementations: AnthropicProvider (API
    key), FakeProvider (tests). Every method raises rolehawk.llm.errors types only."""

    name: str

    async def complete(self, request: LLMRequest) -> Completion: ...

    def stream(self, request: LLMRequest) -> AsyncIterator[StreamEvent]: ...

    async def structured[T: BaseModel](
        self, request: LLMRequest, schema: type[T]
    ) -> Structured[T]: ...

    async def list_models(self) -> list[ModelChoice]: ...

    async def check(self) -> Usage:
        """One tiny real call that proves the key works and the account can pay. Returns its
        usage so the caller can meter it; raises rolehawk.llm.errors types."""
        ...
