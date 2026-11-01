"""Claude connection settings: API key in the keychain, model choices in config.toml."""

from __future__ import annotations

import asyncio
from typing import Any

from pydantic import BaseModel

from rolehawk import keychain
from rolehawk.config import update_settings
from rolehawk.keychain import SecretName
from rolehawk.llm.routing import chosen_model, route_table
from rolehawk.llm.types import Effort, ModelChoice, Task
from rolehawk.logging_setup import register_secret
from rolehawk.services.runtime import Runtime


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
    )


async def set_api_key(runtime: Runtime, api_key: str) -> LLMStatus:
    key = api_key.strip()
    register_secret(key)
    await runtime.providers.validate_key(key)  # raises LLMAuthError for a bad key
    await asyncio.to_thread(keychain.set_secret, SecretName.ANTHROPIC_API_KEY, key)
    runtime.providers.invalidate()
    return await asyncio.to_thread(status, runtime)


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
