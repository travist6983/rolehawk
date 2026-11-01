"""AnthropicProvider against a mocked HTTP transport: real SDK, no network."""

import json
from collections.abc import Callable
from typing import Any

import httpx2
import pytest
from pydantic import BaseModel

from rolehawk.llm.anthropic_provider import FALLBACK_BETA, AnthropicProvider, resolve_api_key
from rolehawk.llm.errors import (
    LLMAuthError,
    LLMRefusalError,
    LLMTruncatedError,
    LLMUnavailableError,
)
from rolehawk.llm.types import (
    LLMRequest,
    Message,
    StreamDone,
    SystemBlock,
    TextDelta,
    ToolDef,
    ToolResult,
)

pytestmark = pytest.mark.anyio

Handler = Callable[[httpx2.Request], httpx2.Response]


def _message(content: list[dict[str, Any]], **overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "id": "msg_1",
        "type": "message",
        "role": "assistant",
        "model": "claude-opus-5-5",
        "content": content,
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": {
            "input_tokens": 10,
            "output_tokens": 5,
            "cache_read_input_tokens": 3,
            "cache_creation_input_tokens": 2,
        },
    }
    body.update(overrides)
    return body


class Recorder:
    def __init__(self, handler: Handler) -> None:
        self.handler = handler
        self.requests: list[httpx2.Request] = []

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        return self.handler(request)

    @property
    def body(self) -> dict[str, Any]:
        result: dict[str, Any] = json.loads(self.requests[-1].content)
        return result


def _provider(handler: Handler) -> tuple[AnthropicProvider, Recorder]:
    recorder = Recorder(handler)
    client = httpx2.AsyncClient(transport=httpx2.MockTransport(recorder))
    return AnthropicProvider("sk-ant-test-key", http_client=client, max_retries=0), recorder


def _request(model: str = "claude-opus-5-5", **kwargs: Any) -> LLMRequest:
    return LLMRequest(
        model=model,
        system=[SystemBlock("rules"), SystemBlock("memory", cache=True)],
        messages=[Message(role="user", text="hi")],
        effort="medium",
        **kwargs,
    )


async def test_request_shape_for_opus() -> None:
    thinking = {"type": "thinking", "thinking": "", "signature": "sig"}
    provider, rec = _provider(
        lambda r: httpx2.Response(200, json=_message([thinking, {"type": "text", "text": "Hi"}]))
    )
    completion = await provider.complete(_request())

    body, headers = rec.body, rec.requests[-1].headers
    assert body["model"] == "claude-opus-5-5"
    assert body["fallbacks"] == "default"
    assert FALLBACK_BETA in headers["anthropic-beta"]
    assert body["output_config"] == {"effort": "medium"}
    assert "thinking" not in body  # adaptive by default
    assert body["system"][1]["cache_control"] == {"type": "ephemeral"}
    assert "cache_control" not in body["system"][0]
    sent_key = headers.get("x-api-key") or headers.get("authorization", "").removeprefix("Bearer ")
    assert sent_key == "sk-ant-test-key"

    assert completion.text == "Hi"
    assert completion.stop_reason == "end_turn"
    assert completion.usage.cache_read_tokens == 3
    assert completion.usage.cache_write_tokens == 2
    assert completion.raw[0]["type"] == "thinking"  # kept verbatim for replay


async def test_haiku_gets_no_fallbacks() -> None:
    provider, rec = _provider(
        lambda r: httpx2.Response(200, json=_message([{"type": "text", "text": "x"}]))
    )
    await provider.complete(_request("claude-haiku-5-5"))
    assert "fallbacks" not in rec.body
    assert FALLBACK_BETA not in rec.requests[-1].headers.get("anthropic-beta", "")


async def test_tools_are_strict_and_tool_round_trip_replays_raw() -> None:
    tool_use = {"type": "tool_use", "id": "tu_1", "name": "lookup", "input": {"q": "x"}}
    provider, rec = _provider(
        lambda r: httpx2.Response(200, json=_message([tool_use], stop_reason="tool_use"))
    )
    tool = ToolDef("lookup", "Look up", {"type": "object", "properties": {}})
    first = await provider.complete(_request(tools=[tool]))
    assert rec.body["tools"][0]["strict"] is True
    assert first.tool_calls[0].name == "lookup"
    assert first.tool_calls[0].input == {"q": "x"}

    follow_up = LLMRequest(
        model="claude-opus-5-5",
        system=[SystemBlock("rules")],
        messages=[
            Message(role="user", text="hi"),
            first.as_assistant_message(),
            Message(role="user", tool_results=[ToolResult("tu_1", "result", False)]),
        ],
        tools=[tool],
    )
    await provider.complete(follow_up)
    messages = rec.body["messages"]
    assert messages[1]["content"][0]["type"] == "tool_use"
    assert messages[2]["content"][0] == {
        "type": "tool_result",
        "tool_use_id": "tu_1",
        "content": "result",
        "is_error": False,
    }


async def test_refusal_raises_with_category() -> None:
    body = _message(
        [], stop_reason="refusal", stop_details={"type": "refusal", "category": "cyber"}
    )
    provider, _ = _provider(lambda r: httpx2.Response(200, json=body))
    with pytest.raises(LLMRefusalError) as caught:
        await provider.complete(_request())
    assert caught.value.category == "cyber"


async def test_truncated_tool_input_raises() -> None:
    tool_use = {"type": "tool_use", "id": "tu_1", "name": "lookup", "input": {}}
    provider, _ = _provider(
        lambda r: httpx2.Response(200, json=_message([tool_use], stop_reason="max_tokens"))
    )
    with pytest.raises(LLMTruncatedError):
        await provider.complete(_request())


@pytest.mark.parametrize(
    ("status", "error"),
    [
        (401, LLMAuthError),
        (403, LLMAuthError),
        (429, LLMUnavailableError),
        (529, LLMUnavailableError),
    ],
)
async def test_http_errors_are_mapped(status: int, error: type[Exception]) -> None:
    payload = {"type": "error", "error": {"type": "x", "message": "nope"}}
    provider, _ = _provider(lambda r: httpx2.Response(status, json=payload))
    with pytest.raises(error):
        await provider.complete(_request())


class Verdict(BaseModel):
    score: int
    reasons: list[str]


async def test_structured_output_parses_and_sends_schema_with_effort() -> None:
    text = json.dumps({"score": 82, "reasons": ["React", "remote"]})
    provider, rec = _provider(
        lambda r: httpx2.Response(200, json=_message([{"type": "text", "text": text}]))
    )
    result = await provider.structured(_request(), Verdict)
    assert result.value == Verdict(score=82, reasons=["React", "remote"])
    output_config = rec.body["output_config"]
    assert output_config["effort"] == "medium"
    assert output_config["format"]["type"] == "json_schema"


def _sse(events: list[tuple[str, Any]]) -> bytes:
    return "".join(f"event: {name}\ndata: {json.dumps(data)}\n\n" for name, data in events).encode()


async def test_stream_yields_text_then_completion() -> None:
    start = _message([], stop_reason=None)
    start["usage"] = {"input_tokens": 10, "output_tokens": 1}
    events = [
        ("message_start", {"type": "message_start", "message": start}),
        (
            "content_block_start",
            {
                "type": "content_block_start",
                "index": 0,
                "content_block": {"type": "text", "text": ""},
            },
        ),
        (
            "content_block_delta",
            {
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "text_delta", "text": "Hel"},
            },
        ),
        (
            "content_block_delta",
            {
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "text_delta", "text": "lo"},
            },
        ),
        ("content_block_stop", {"type": "content_block_stop", "index": 0}),
        (
            "message_delta",
            {
                "type": "message_delta",
                "delta": {"stop_reason": "end_turn", "stop_sequence": None},
                "usage": {"output_tokens": 7},
            },
        ),
        ("message_stop", {"type": "message_stop"}),
    ]
    provider, _ = _provider(
        lambda r: httpx2.Response(
            200, content=_sse(events), headers={"content-type": "text/event-stream"}
        )
    )
    out = [e async for e in provider.stream(_request())]
    assert [e.text for e in out if isinstance(e, TextDelta)] == ["Hel", "lo"]
    done = out[-1]
    assert isinstance(done, StreamDone)
    assert done.completion.text == "Hello"
    assert done.completion.usage.output_tokens == 7


def test_key_resolution_prefers_keychain(monkeypatch: pytest.MonkeyPatch) -> None:
    from rolehawk import keychain
    from rolehawk.keychain import SecretName

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert resolve_api_key() == (None, "none")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-env-key")
    assert resolve_api_key() == ("sk-ant-env-key", "env")
    keychain.set_secret(SecretName.ANTHROPIC_API_KEY, "sk-ant-chain-key")
    assert resolve_api_key() == ("sk-ant-chain-key", "keychain")
