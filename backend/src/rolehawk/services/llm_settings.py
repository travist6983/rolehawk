"""Claude connection settings: API key in the keychain, model choices in config.toml."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Literal

from pydantic import BaseModel

from rolehawk import keychain
from rolehawk.config import update_settings
from rolehawk.keychain import SecretName
from rolehawk.llm import errors as llm_errors
from rolehawk.llm import models
from rolehawk.llm.routing import chosen_model, route_table
from rolehawk.llm.types import Effort, ModelChoice, Task
from rolehawk.llm.typical_cost import TypicalCost, typical_cost
from rolehawk.logging_setup import register_secret
from rolehawk.services.runtime import Runtime

log = logging.getLogger(__name__)


class RouteView(BaseModel):
    task: Task
    model: str
    effort: Effort | None


class LLMStatus(BaseModel):
    configured: bool
    key_source: str
    provider: str
    model: str
    smart_routing: bool
    routes: list[RouteView]
    monthly_cap_usd: float | None
    month_to_date_usd: float
    typical_cost: TypicalCost


def status(runtime: Runtime) -> LLMStatus:
    settings = runtime.settings.llm
    return LLMStatus(
        configured=runtime.llm.configured,
        key_source=str(runtime.providers.key_source()),
        provider=settings.provider.value,
        model=chosen_model(settings),
        smart_routing=settings.smart_routing,
        routes=[
            RouteView(task=r.task, model=r.model, effort=r.effort)
            for r in route_table(settings).values()
        ],
        monthly_cap_usd=settings.monthly_cap_usd,
        month_to_date_usd=runtime.llm.meter.month_to_date(),
        typical_cost=typical_cost(settings),
    )


KeyProblem = Literal[
    "bad_key",
    "permission",
    "no_credit",
    "account_limit",
    "rate_limit",
    "overloaded",
    "network",
    "not_configured",
    "unknown",
]
FixLink = Literal["keys", "billing"]


class KeyTest(BaseModel):
    """The result of one tiny real call, in words a non-developer can act on."""

    ok: bool
    problem: KeyProblem | None
    key_accepted: bool = False  # Anthropic recognized the key, even if the call failed
    title: str
    fix: str
    fix_link: FixLink | None = None


class KeyConnect(BaseModel):
    saved: bool
    test: KeyTest
    status: LLMStatus


_PASSED = KeyTest(
    ok=True,
    problem=None,
    key_accepted=True,
    title="Your key works",
    fix="Claude answered a test message, so ranking jobs and writing applications are ready.",
)

# Most specific first: the error classes form a hierarchy.
_PROBLEMS: list[tuple[type[llm_errors.LLMError], KeyTest]] = [
    (
        llm_errors.LLMPermissionError,
        KeyTest(
            ok=False,
            problem="permission",
            title="This key isn't allowed to use Claude",
            fix="Create a new key in the Default workspace on the API keys page, then paste it "
            "here.",
            fix_link="keys",
        ),
    ),
    (
        llm_errors.LLMAuthError,
        KeyTest(
            ok=False,
            problem="bad_key",
            title="Anthropic didn't accept this key",
            fix="Check you copied the whole key, starting with sk-ant-. If it still fails, the "
            "key may have been turned off: create a new one on the API keys page and paste it "
            "here.",
            fix_link="keys",
        ),
    ),
    (
        llm_errors.LLMNotConfiguredError,
        KeyTest(
            ok=False,
            problem="not_configured",
            title="No key saved yet",
            fix="Paste your key first, then test it.",
        ),
    ),
    (
        llm_errors.LLMBillingError,
        KeyTest(
            ok=False,
            problem="no_credit",
            key_accepted=True,
            title="Your key works, but the account has no credit",
            fix="Open Billing and buy some credit, then test again. New credit can take a minute "
            "or two to show up.",
            fix_link="billing",
        ),
    ),
    (
        llm_errors.LLMAccountLimitError,
        KeyTest(
            ok=False,
            problem="account_limit",
            key_accepted=True,
            title="Your account reached its spend limit",
            fix="Open Billing and raise the limit under Spend limits, or wait until next month "
            "when it resets.",
            fix_link="billing",
        ),
    ),
    (
        llm_errors.LLMRateLimitError,
        KeyTest(
            ok=False,
            problem="rate_limit",
            key_accepted=True,
            title="Anthropic is limiting requests right now",
            fix="Wait a minute and test again. New accounts start with low limits that go up as "
            "you use them.",
        ),
    ),
    (
        llm_errors.LLMConnectionError,
        KeyTest(
            ok=False,
            problem="network",
            title="Couldn't reach Anthropic",
            fix="Check your internet connection. On a work network or VPN, a firewall may be "
            "blocking api.anthropic.com.",
        ),
    ),
    (
        llm_errors.LLMUnavailableError,
        KeyTest(
            ok=False,
            problem="overloaded",
            key_accepted=True,
            title="Claude is busy right now",
            fix="This isn't a problem with your key. Test again in a few minutes.",
        ),
    ),
]

_UNKNOWN = KeyTest(
    ok=False,
    problem="unknown",
    title="The test didn't go through",
    fix="Try again. If it keeps failing, sign in to the Claude Platform and check your account.",
)


def explain(error: llm_errors.LLMError) -> KeyTest:
    return next((result for kind, result in _PROBLEMS if isinstance(error, kind)), _UNKNOWN)


async def check_api_key(runtime: Runtime, api_key: str | None = None) -> KeyTest:
    """Send one tiny real message with `api_key` (or the stored key) and explain the result.

    Uses the cheapest model and one output token, so it costs a tiny fraction of a cent. It is
    recorded in the spend meter like any other call. Never raises for an API problem.
    """
    key = api_key.strip() if api_key is not None else None
    if key:
        register_secret(key)
    try:
        usage = await runtime.providers.probe_key(key)
    except llm_errors.LLMError as error:
        log.info("key test failed: %s", type(error).__name__)
        return explain(error)
    await asyncio.to_thread(
        runtime.llm.meter.record,
        command="key_test",
        provider=runtime.providers.provider_name(),
        model=models.PROBE_MODEL,
        usage=usage,
    )
    return _PASSED


async def set_api_key(runtime: Runtime, api_key: str) -> KeyConnect:
    """Test the key, then store it in the keychain if Anthropic accepted it.

    A recognized key is saved even when the account can't run requests yet (no credit, a
    spend limit, a busy moment), so the person fixes that on the Claude Platform and tests
    again instead of pasting the key a second time.
    """
    key = api_key.strip()
    test = await check_api_key(runtime, key)
    if test.key_accepted:
        await asyncio.to_thread(keychain.set_secret, SecretName.ANTHROPIC_API_KEY, key)
        runtime.providers.invalidate()
    return KeyConnect(
        saved=test.key_accepted, test=test, status=await asyncio.to_thread(status, runtime)
    )


async def clear_api_key(runtime: Runtime) -> LLMStatus:
    await asyncio.to_thread(keychain.delete_secret, SecretName.ANTHROPIC_API_KEY)
    runtime.providers.invalidate()
    return await asyncio.to_thread(status, runtime)


def update_llm_settings(runtime: Runtime, changes: dict[str, Any]) -> LLMStatus:
    """Apply `changes` (model, smart_routing, monthly_cap_usd; None clears) to config.toml."""
    update_settings(runtime.paths.config_file, "llm", changes)
    runtime.reload_settings()
    return status(runtime)


async def list_models(runtime: Runtime) -> list[ModelChoice]:
    """Live models from the Models API, filtered to Claude chat models."""
    models = await runtime.llm.provider().list_models()
    return [m for m in models if m.id.startswith("claude-")]
