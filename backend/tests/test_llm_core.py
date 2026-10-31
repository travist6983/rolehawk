from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session, sessionmaker

from offerbound.config import LLMSettings
from offerbound.db.models import LLMCall
from offerbound.llm import models
from offerbound.llm.errors import LLMNotConfiguredError, SpendCapExceededError
from offerbound.llm.fake import FakeProvider, FakeReply
from offerbound.llm.meter import SpendMeter, estimate_tokens, month_start
from offerbound.llm.routing import route, route_table
from offerbound.llm.service import LLMService
from offerbound.llm.types import Message, StreamDone, SystemBlock, Task, TextDelta, Usage


def test_cost_uses_model_pricing_and_cache_rates() -> None:
    usage = Usage(input_tokens=1_000_000, output_tokens=100_000, cache_read_tokens=1_000_000)
    # Opus 5.5: $4 in, $20 out, $0.20 cache read per MTok
    assert models.cost_usd("claude-opus-5-5", usage) == pytest.approx(4.0 + 2.0 + 0.2)


def test_haiku_long_context_tier() -> None:
    short = Usage(input_tokens=50_000, output_tokens=1_000)
    long = Usage(input_tokens=150_000, output_tokens=1_000)
    assert models.cost_usd("claude-haiku-5-5", short) == pytest.approx(0.005 + 0.0005)
    assert models.cost_usd("claude-haiku-5-5", long) == pytest.approx(0.075 + 0.0025)


def test_unknown_model_is_costed_conservatively() -> None:
    usage = Usage(input_tokens=1_000_000)
    assert models.cost_usd("claude-future-9", usage) == models.cost_usd("claude-fable-5-1", usage)


def test_server_fallback_flags() -> None:
    assert models.has_server_fallback("claude-opus-5-5")
    assert models.has_server_fallback("claude-sonnet-5-5")
    assert not models.has_server_fallback("claude-haiku-5-5")
    assert not models.has_server_fallback("unknown")


def test_smart_routing_uses_small_model_for_cheap_tasks() -> None:
    settings = LLMSettings()
    assert route(Task.RANK, settings).model == models.SMALL_MODEL
    assert route(Task.EXTRACT, settings).model == models.SMALL_MODEL
    assert route(Task.WRITE, settings).model == models.DEFAULT_MODEL
    assert route(Task.WRITE, settings).effort == "high"
    assert route(Task.RANK, settings).effort == "low"


def test_routing_off_uses_chosen_model_everywhere() -> None:
    settings = LLMSettings(model="claude-sonnet-5-5", smart_routing=False)
    assert {r.model for r in route_table(settings).values()} == {"claude-sonnet-5-5"}


def test_estimate_tokens_is_conservative() -> None:
    assert estimate_tokens("") == 1
    assert estimate_tokens("x" * 300) == 100


def test_month_start_is_utc() -> None:
    eastern = datetime(2026, 11, 1, 1, 0, tzinfo=UTC) - timedelta(hours=5)  # Oct 31 local
    assert month_start(eastern) == datetime(2026, 10, 1, tzinfo=UTC)


def test_meter_records_and_sums_this_month_only(sessions: sessionmaker[Session]) -> None:
    meter = SpendMeter(sessions)
    cost = meter.record(
        command="rank", provider="fake", model="claude-opus-5-5", usage=Usage(1_000_000, 0)
    )
    assert cost == pytest.approx(4.0)
    with sessions.begin() as session:
        session.add(
            LLMCall(
                command="old",
                provider="fake",
                model="m",
                cost_usd=99.0,
                created_at=datetime.now(UTC) - timedelta(days=62),
            )
        )
    assert meter.month_to_date() == pytest.approx(4.0)


def test_cap_blocks_when_reached_or_estimate_exceeds(sessions: sessionmaker[Session]) -> None:
    meter = SpendMeter(sessions)
    meter.check_cap(None)
    meter.check_cap(5.0)
    meter.record(command="x", provider="fake", model="claude-opus-5-5", usage=Usage(1_000_000, 0))
    meter.check_cap(5.0)  # $4 of $5
    with pytest.raises(SpendCapExceededError):
        meter.check_cap(5.0, upcoming_usd=2.0)
    with pytest.raises(SpendCapExceededError) as caught:
        meter.check_cap(4.0)
    assert "$4.00" in caught.value.user_message


def _service(
    sessions: sessionmaker[Session], provider: FakeProvider | None, settings: LLMSettings
) -> LLMService:
    return LLMService(lambda: provider, lambda: settings, SpendMeter(sessions))


SYSTEM = [SystemBlock("You help.")]
HELLO = [Message(role="user", text="hi")]


@pytest.mark.anyio
async def test_service_routes_records_cost_and_streams(sessions: sessionmaker[Session]) -> None:
    fake = FakeProvider([FakeReply(text="hello there"), FakeReply(text="ok")])
    service = _service(sessions, fake, LLMSettings())

    events = [
        e
        async for e in service.stream(command="chat", task=Task.CHAT, system=SYSTEM, messages=HELLO)
    ]
    assert "".join(e.text for e in events if isinstance(e, TextDelta)) == "hello there"
    assert isinstance(events[-1], StreamDone)
    assert fake.requests[0].model == models.DEFAULT_MODEL
    assert fake.requests[0].effort == "medium"

    await service.complete(command="rank", task=Task.RANK, system=SYSTEM, messages=HELLO)
    assert fake.requests[1].model == models.SMALL_MODEL
    with sessions() as session:
        calls = session.query(LLMCall).order_by(LLMCall.id).all()
    assert [(c.command, c.model) for c in calls] == [
        ("chat", models.DEFAULT_MODEL),
        ("rank", models.SMALL_MODEL),
    ]
    assert all(c.cost_usd > 0 for c in calls)


@pytest.mark.anyio
async def test_service_enforces_cap_before_calling(sessions: sessionmaker[Session]) -> None:
    fake = FakeProvider([FakeReply(text="never")])
    SpendMeter(sessions).record(
        command="x", provider="fake", model="claude-opus-5-5", usage=Usage(1_000_000, 0)
    )
    service = _service(sessions, fake, LLMSettings(monthly_cap_usd=1.0))
    with pytest.raises(SpendCapExceededError):
        await service.complete(command="chat", task=Task.CHAT, system=SYSTEM, messages=HELLO)
    assert fake.requests == []


@pytest.mark.anyio
async def test_service_without_provider(sessions: sessionmaker[Session]) -> None:
    service = _service(sessions, None, LLMSettings())
    assert service.configured is False
    with pytest.raises(LLMNotConfiguredError):
        await service.complete(command="chat", task=Task.CHAT, system=SYSTEM, messages=HELLO)


def test_estimate_flags_cap(sessions: sessionmaker[Session]) -> None:
    service = _service(sessions, FakeProvider(), LLMSettings(monthly_cap_usd=0.01))
    estimate = service.estimate(Task.RANK, input_tokens=20_000, output_tokens=2_000, calls=10)
    assert estimate.model == models.SMALL_MODEL
    assert estimate.calls == 10
    assert estimate.input_tokens == 200_000
    assert estimate.cost_usd == pytest.approx(10 * (0.002 + 0.001))
    assert estimate.exceeds_cap
