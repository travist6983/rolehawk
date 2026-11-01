"""Model catalog: pricing for cost tracking and per-model API capabilities.

Prices are USD per million tokens from Anthropic's published pricing (checked 2026-10-31).
Verify at https://platform.claude.com/docs/en/about-claude/pricing when adding models. The
Settings screen lists live models from the Models API; this table only needs to cover
pricing and request-shape differences.
"""

from __future__ import annotations

from dataclasses import dataclass

from rolehawk.llm.types import Usage

DEFAULT_MODEL = "claude-opus-5-5"  # best model: writing, review, chat
SMALL_MODEL = "claude-haiku-5-5"  # smart routing: ranking and extraction


@dataclass(frozen=True)
class Pricing:
    input: float
    output: float
    cache_read: float
    cache_write: float  # 5-minute TTL writes


@dataclass(frozen=True)
class ModelInfo:
    id: str
    label: str
    pricing: Pricing
    # Above this prompt size (input incl. cache tokens) `long_pricing` applies.
    long_context_threshold: int | None = None
    long_pricing: Pricing | None = None
    supports_effort: bool = True
    # Server-side refusal fallback (`fallbacks="default"`); Haiku 5.5 has none.
    server_fallback: bool = False


CATALOG: dict[str, ModelInfo] = {
    m.id: m
    for m in [
        ModelInfo(
            "claude-fable-5-1",
            "Claude Fable 5.1",
            Pricing(10.0, 50.0, 0.25, 12.5),
            server_fallback=True,
        ),
        ModelInfo(
            "claude-opus-5-5",
            "Claude Opus 5.5",
            Pricing(4.0, 20.0, 0.20, 5.0),
            server_fallback=True,
        ),
        ModelInfo(
            "claude-opus-5",
            "Claude Opus 5",
            Pricing(5.0, 25.0, 0.50, 6.25),
            server_fallback=True,
        ),
        ModelInfo(
            "claude-sonnet-5-5",
            "Claude Sonnet 5.5",
            Pricing(2.0, 10.0, 0.20, 2.5),
            server_fallback=True,
        ),
        ModelInfo(
            "claude-haiku-5-5",
            "Claude Haiku 5.5",
            Pricing(0.10, 0.50, 0.01, 0.125),
            long_context_threshold=100_000,
            long_pricing=Pricing(0.50, 2.50, 0.05, 0.625),
        ),
    ]
}

# Unknown models are costed at the most expensive tier so a spend cap can't be bypassed.
_CONSERVATIVE = CATALOG["claude-fable-5-1"].pricing


def get(model_id: str) -> ModelInfo | None:
    return CATALOG.get(model_id)


def pricing_for(model_id: str, prompt_tokens: int = 0) -> Pricing:
    info = CATALOG.get(model_id)
    if info is None:
        return _CONSERVATIVE
    if (
        info.long_pricing is not None
        and info.long_context_threshold is not None
        and prompt_tokens > info.long_context_threshold
    ):
        return info.long_pricing
    return info.pricing


def cost_usd(model_id: str, usage: Usage) -> float:
    prompt_tokens = usage.input_tokens + usage.cache_read_tokens + usage.cache_write_tokens
    price = pricing_for(model_id, prompt_tokens)
    total = (
        usage.input_tokens * price.input
        + usage.output_tokens * price.output
        + usage.cache_read_tokens * price.cache_read
        + usage.cache_write_tokens * price.cache_write
    ) / 1_000_000
    return round(total, 6)


def supports_effort(model_id: str) -> bool:
    info = CATALOG.get(model_id)
    return True if info is None else info.supports_effort


def has_server_fallback(model_id: str) -> bool:
    info = CATALOG.get(model_id)
    return info is not None and info.server_fallback
