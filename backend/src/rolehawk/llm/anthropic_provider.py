"""Claude via the official `anthropic` SDK with the user's API key.

Request shape (checked against the SDK and API docs, 2026-10-31):
- Thinking is left at the model default (adaptive); depth is controlled by `effort`.
- Models with server-side refusal fallback get `fallbacks="default"` under its beta header.
- Tools are `strict` so tool inputs always match their schema; inputs are still validated.
- Assistant content is kept verbatim (`raw`) so thinking blocks replay unchanged within a
  tool loop, which the API requires.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from typing import Any, Literal, cast

import anthropic
import httpx2
from anthropic.types.beta import BetaMessage, BetaTextBlock, BetaToolUseBlock
from pydantic import BaseModel, ValidationError

from rolehawk import keychain
from rolehawk.keychain import SecretName
from rolehawk.llm import models
from rolehawk.llm.errors import (
    LLMAuthError,
    LLMError,
    LLMOutputError,
    LLMRefusalError,
    LLMTruncatedError,
    LLMUnavailableError,
)
from rolehawk.llm.types import (
    Completion,
    LLMRequest,
    Message,
    ModelChoice,
    StopReason,
    StreamDone,
    StreamEvent,
    Structured,
    SystemBlock,
    TextDelta,
    ToolCall,
    Usage,
)

FALLBACK_BETA = "server-side-fallback-2026-07-01"
ENV_API_KEY = "ANTHROPIC_API_KEY"
_STOP_REASONS: set[str] = {"end_turn", "tool_use", "max_tokens", "stop_sequence", "pause_turn"}

KeySource = Literal["keychain", "env", "none"]


def resolve_api_key() -> tuple[str | None, KeySource]:
    """The keychain wins; ANTHROPIC_API_KEY is a developer convenience."""
    try:
        stored = keychain.get_secret(SecretName.ANTHROPIC_API_KEY)
    except Exception:  # a broken keychain must not crash startup
        stored = None
    if stored:
        return stored, "keychain"
    env = os.environ.get(ENV_API_KEY, "").strip()
    if env:
        return env, "env"
    return None, "none"


def map_error(exc: anthropic.APIError) -> LLMError:
    if isinstance(exc, anthropic.AuthenticationError | anthropic.PermissionDeniedError):
        return LLMAuthError(str(exc))
    if isinstance(
        exc, anthropic.RateLimitError | anthropic.APIConnectionError | anthropic.InternalServerError
    ):
        return LLMUnavailableError(str(exc))
    if isinstance(exc, anthropic.APIStatusError) and exc.status_code >= 500:
        return LLMUnavailableError(str(exc))
    return LLMError(str(exc))


def _usage(usage: Any) -> Usage:
    return Usage(
        input_tokens=usage.input_tokens or 0,
        output_tokens=usage.output_tokens or 0,
        cache_read_tokens=getattr(usage, "cache_read_input_tokens", None) or 0,
        cache_write_tokens=getattr(usage, "cache_creation_input_tokens", None) or 0,
    )


def _check_refusal(message: BetaMessage) -> None:
    if message.stop_reason == "refusal":
        details = getattr(message, "stop_details", None)
        raise LLMRefusalError(
            category=getattr(details, "category", None),
            explanation=getattr(details, "explanation", None),
        )


class AnthropicProvider:
    name = "anthropic_api"

    def __init__(
        self,
        api_key: str,
        *,
        http_client: httpx2.AsyncClient | None = None,
        max_retries: int = 2,
        timeout: float = 300.0,
    ) -> None:
        if http_client is not None:
            self._client = anthropic.AsyncAnthropic(
                api_key=api_key, max_retries=max_retries, timeout=timeout, http_client=http_client
            )
        else:
            self._client = anthropic.AsyncAnthropic(
                api_key=api_key, max_retries=max_retries, timeout=timeout
            )

    # --- request building -------------------------------------------------------------

    @staticmethod
    def _system_block(block: SystemBlock) -> dict[str, Any]:
        result: dict[str, Any] = {"type": "text", "text": block.text}
        if block.cache:
            result["cache_control"] = {"type": "ephemeral"}
        return result

    @staticmethod
    def _message(message: Message) -> dict[str, Any]:
        if message.role == "assistant":
            content: Any = list(message.raw) if message.raw is not None else message.text
            return {"role": "assistant", "content": content}
        if message.tool_results:
            blocks: list[dict[str, Any]] = [
                {
                    "type": "tool_result",
                    "tool_use_id": result.tool_call_id,
                    "content": result.content,
                    "is_error": result.is_error,
                }
                for result in message.tool_results
            ]
            if message.text:
                blocks.append({"type": "text", "text": message.text})
            return {"role": "user", "content": blocks}
        return {"role": "user", "content": message.text}

    def build_params(self, request: LLMRequest) -> dict[str, Any]:
        params: dict[str, Any] = {
            "model": request.model,
            "max_tokens": request.max_tokens,
            "messages": [self._message(m) for m in request.messages],
        }
        if request.system:
            params["system"] = [self._system_block(b) for b in request.system]
        if request.effort is not None:
            params["output_config"] = {"effort": request.effort}
        if request.tools:
            params["tools"] = [
                {
                    "name": tool.name,
                    "description": tool.description,
                    "input_schema": tool.input_schema,
                    "strict": True,
                }
                for tool in request.tools
            ]
        if models.has_server_fallback(request.model):
            params["betas"] = [FALLBACK_BETA]
            params["fallbacks"] = "default"
        return params

    # --- response mapping -------------------------------------------------------------

    @staticmethod
    def to_completion(message: BetaMessage) -> Completion:
        _check_refusal(message)
        text = "".join(b.text for b in message.content if isinstance(b, BetaTextBlock))
        calls = [
            ToolCall(id=b.id, name=b.name, input=dict(cast(dict[str, Any], b.input)))
            for b in message.content
            if isinstance(b, BetaToolUseBlock)
        ]
        stop = message.stop_reason or "other"
        stop_reason = cast(StopReason, stop if stop in _STOP_REASONS else "other")
        if stop_reason == "max_tokens" and calls:
            raise LLMTruncatedError("tool input truncated at max_tokens")
        return Completion(
            model=message.model,
            text=text,
            tool_calls=calls,
            stop_reason=stop_reason,
            usage=_usage(message.usage),
            raw=[block.to_dict(exclude_none=True) for block in message.content],
            request_id=getattr(message, "_request_id", None),
        )

    # --- LLMProvider ------------------------------------------------------------------

    async def complete(self, request: LLMRequest) -> Completion:
        try:
            message = await self._client.beta.messages.create(**self.build_params(request))
        except anthropic.APIError as exc:
            raise map_error(exc) from exc
        return self.to_completion(cast(BetaMessage, message))

    async def stream(self, request: LLMRequest) -> AsyncIterator[StreamEvent]:
        try:
            async with self._client.beta.messages.stream(**self.build_params(request)) as stream:
                async for event in stream:
                    if event.type == "text":
                        yield TextDelta(event.text)
                message = await stream.get_final_message()
        except anthropic.APIError as exc:
            raise map_error(exc) from exc
        yield StreamDone(self.to_completion(message))

    async def structured[T: BaseModel](self, request: LLMRequest, schema: type[T]) -> Structured[T]:
        params = self.build_params(request)
        params.pop("tools", None)
        try:
            message = await self._client.beta.messages.parse(output_format=schema, **params)
        except anthropic.APIError as exc:
            raise map_error(exc) from exc
        except ValidationError as exc:
            raise LLMOutputError(str(exc)) from exc
        _check_refusal(message)
        if message.stop_reason == "max_tokens":
            raise LLMTruncatedError("structured output truncated at max_tokens")
        value = message.parsed_output
        if value is None:
            raise LLMOutputError("no structured output in response")
        return Structured(
            value=value,
            model=message.model,
            usage=_usage(message.usage),
            request_id=getattr(message, "_request_id", None),
        )

    async def list_models(self) -> list[ModelChoice]:
        try:
            return [
                ModelChoice(
                    id=m.id,
                    display_name=m.display_name,
                    max_input_tokens=getattr(m, "max_input_tokens", None),
                    max_output_tokens=getattr(m, "max_tokens", None),
                )
                async for m in self._client.models.list()
            ]
        except anthropic.APIError as exc:
            raise map_error(exc) from exc

    async def check(self) -> None:
        try:
            await self._client.models.list(limit=1)
        except anthropic.APIError as exc:
            raise map_error(exc) from exc
