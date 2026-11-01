"""AnthropicProvider against a mocked HTTP transport: real SDK, no network."""

import json
from collections.abc import Callable
from typing import Any

import httpx2
import pytest
from pydantic import BaseModel

from rolehawk.llm.anthropic_provider import FALLBACK_BETA, AnthropicProvider, resolve_api_key
from rolehawk.llm.errors import (
    LLMAccountLimitError,
    LLMAuthError,
    LLMBillingError,
    LLMConnectionError,
    LLMError,
    LLMModelNotFoundError,
    LLMOverloadedError,
    LLMPermissionError,
    LLMRateLimitError,
    LLMRefusalError,
    LLMRequestError,
    LLMTooLargeError,
    LLMTruncatedError,
    LLMUnavailableError,
)
from rolehawk.llm.models import PROBE_MODEL
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


def _error(status: int, kind: str, message: str, **extra: Any) -> Handler:
    payload = {"type": "error", "error": {"type": kind, "message": message, **extra}}
    return lambda _r: httpx2.Response(status, json=payload)


@pytest.mark.parametrize(
    ("handler", "error"),
    [
        (_error(401, "authentication_error", "invalid x-api-key"), LLMAuthError),
        (_error(403, "permission_error", "not allowed"), LLMPermissionError),
        (_error(402, "billing_error", "check your payment details"), LLMBillingError),
        (
            _error(400, "invalid_request_error", "Your credit balance is too low"),
            LLMBillingError,
        ),
        (
            _error(
                400, "invalid_request_error", "You have reached your specified API usage limits"
            ),
            LLMAccountLimitError,
        ),
        (
            _error(429, "rate_limit_error", "cap", error_code="enforced_spend_limit_reached"),
            LLMAccountLimitError,
        ),
        (_error(429, "rate_limit_error", "slow down"), LLMRateLimitError),
        (_error(529, "overloaded_error", "busy"), LLMOverloadedError),
        (_error(500, "api_error", "oops"), LLMOverloadedError),
        (_error(404, "not_found_error", "model: claude-x"), LLMModelNotFoundError),
        (_error(413, "request_too_large", "too big"), LLMTooLargeError),
        (_error(400, "invalid_request_error", "prompt is too long: 2M tokens"), LLMTooLargeError),
        (
            _error(400, "invalid_request_error", "Schema is too complex for compilation."),
            LLMRequestError,
        ),
        (_error(418, "x", "teapot"), LLMError),
    ],
)
async def test_key_check_sorts_errors_into_explainable_kinds(
    handler: Handler, error: type[Exception]
) -> None:
    provider, _ = _provider(handler)
    with pytest.raises(error) as caught:
        await provider.check()
    assert type(caught.value) is error


async def test_error_messages_say_what_claude_said() -> None:
    provider, _ = _provider(
        _error(400, "invalid_request_error", "Schema is too complex for compilation.")
    )
    with pytest.raises(LLMRequestError) as caught:
        await provider.check()
    assert '"Schema is too complex for compilation."' in caught.value.user_message
    assert "Error code" not in caught.value.user_message  # the API text, not the SDK repr

    provider, _ = _provider(_error(418, "x", "teapot"))
    with pytest.raises(LLMError) as other:
        await provider.check()
    assert other.value.user_message == "Claude returned an error (418): teapot"


async def test_key_check_network_failure() -> None:
    def fail(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("no route", request=request)

    provider, _ = _provider(fail)
    with pytest.raises(LLMConnectionError):
        await provider.check()


async def test_key_check_is_one_token_on_the_cheapest_model() -> None:
    provider, recorder = _provider(
        lambda _r: httpx2.Response(200, json=_message([{"type": "text", "text": "H"}]))
    )
    usage = await provider.check()
    assert usage.input_tokens == 10
    assert recorder.requests[-1].url.path == "/v1/messages"
    assert recorder.body["model"] == PROBE_MODEL == "claude-haiku-5-5"
    assert recorder.body["max_tokens"] == 1
    assert recorder.body["thinking"] == {"type": "disabled"}


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
