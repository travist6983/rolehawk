"""Provider-neutral request/response types. Providers translate these to their own API."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Literal

Effort = Literal["low", "medium", "high", "xhigh", "max"]


class Task(StrEnum):
    """What a call is for; routing maps each task to a model and effort."""

    RANK = "rank"
    EXTRACT = "extract"
    WRITE = "write"
    REVIEW = "review"
    CHAT = "chat"


@dataclass(frozen=True)
class SystemBlock:
    text: str
    cache: bool = False  # mark the end of a stable prefix for prompt caching


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    input: dict[str, Any]


@dataclass(frozen=True)
class ToolResult:
    tool_call_id: str
    content: str
    is_error: bool = False


@dataclass(frozen=True)
class Message:
    """One conversation turn.

    `raw` holds the provider's native assistant content (including thinking blocks) and is
    replayed verbatim within a single tool loop, as the API requires. Across user turns,
    history is rebuilt from text only, which keeps it append-only and cache-friendly.
    """

    role: Literal["user", "assistant"]
    text: str = ""
    tool_results: Sequence[ToolResult] = ()
    raw: Sequence[Any] | None = None


@dataclass(frozen=True)
class ToolDef:
    name: str
    description: str
    input_schema: dict[str, Any]


@dataclass(frozen=True)
class LLMRequest:
    model: str
    system: Sequence[SystemBlock]
    messages: Sequence[Message]
    max_tokens: int = 16000
    effort: Effort | None = None
    tools: Sequence[ToolDef] = ()


@dataclass(frozen=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0

    def __add__(self, other: Usage) -> Usage:
        return Usage(
            self.input_tokens + other.input_tokens,
            self.output_tokens + other.output_tokens,
            self.cache_read_tokens + other.cache_read_tokens,
            self.cache_write_tokens + other.cache_write_tokens,
        )


StopReason = Literal["end_turn", "tool_use", "max_tokens", "stop_sequence", "pause_turn", "other"]


@dataclass(frozen=True)
class Completion:
    model: str  # the model that actually served the response (may be a fallback)
    text: str
    tool_calls: Sequence[ToolCall]
    stop_reason: StopReason
    usage: Usage
    raw: Sequence[Any] = ()
    request_id: str | None = None

    def as_assistant_message(self) -> Message:
        return Message(role="assistant", text=self.text, raw=self.raw)


@dataclass(frozen=True)
class Structured[T]:
    value: T
    model: str
    usage: Usage
    request_id: str | None = None


@dataclass(frozen=True)
class TextDelta:
    text: str
    type: Literal["text"] = "text"


@dataclass(frozen=True)
class StreamDone:
    completion: Completion
    type: Literal["done"] = "done"


StreamEvent = TextDelta | StreamDone


@dataclass(frozen=True)
class ModelChoice:
    id: str
    display_name: str
    max_input_tokens: int | None = None
    max_output_tokens: int | None = None
    extra: dict[str, Any] = field(default_factory=dict)
