from __future__ import annotations

import asyncio

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field, SecretStr

from offerbound.api.deps import RuntimeDep
from offerbound.llm import models as catalog
from offerbound.llm.types import ModelChoice, Task
from offerbound.services import llm_settings
from offerbound.services.llm_settings import LLMStatus

router = APIRouter(prefix="/api/llm", tags=["llm"])


class ApiKeyIn(BaseModel):
    api_key: SecretStr = Field(min_length=10)


class LLMSettingsIn(BaseModel):
    """Partial update; send null for monthly_cap_usd to remove the cap."""

    model_config = ConfigDict(extra="forbid")
    model: str | None = Field(default=None, min_length=3, max_length=128)
    smart_routing: bool | None = None
    monthly_cap_usd: float | None = Field(default=None, ge=0)


class EstimateIn(BaseModel):
    task: Task
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    calls: int = Field(default=1, ge=1, le=100_000)


class EstimateOut(BaseModel):
    model: str
    calls: int
    input_tokens: int
    output_tokens: int
    cost_usd: float
    month_to_date_usd: float
    cap_usd: float | None
    exceeds_cap: bool


@router.get("/status")
async def get_status(runtime: RuntimeDep) -> LLMStatus:
    return await asyncio.to_thread(llm_settings.status, runtime)


@router.put("/key")
async def put_key(body: ApiKeyIn, runtime: RuntimeDep) -> LLMStatus:
    """Validates the key with one cheap call, then stores it in the OS keychain."""
    return await llm_settings.set_api_key(runtime, body.api_key.get_secret_value())


@router.delete("/key")
async def delete_key(runtime: RuntimeDep) -> LLMStatus:
    return await llm_settings.clear_api_key(runtime)


@router.patch("/settings")
async def patch_settings(body: LLMSettingsIn, runtime: RuntimeDep) -> LLMStatus:
    changes = {name: getattr(body, name) for name in body.model_fields_set}
    return await asyncio.to_thread(llm_settings.update_llm_settings, runtime, changes)


@router.get("/models")
async def get_models(runtime: RuntimeDep) -> list[ModelChoice]:
    if not runtime.llm.configured:
        return [ModelChoice(id=m.id, display_name=m.label) for m in catalog.CATALOG.values()]
    return await llm_settings.list_models(runtime)


@router.post("/estimate")
async def post_estimate(body: EstimateIn, runtime: RuntimeDep) -> EstimateOut:
    estimate = await asyncio.to_thread(
        runtime.llm.estimate,
        body.task,
        input_tokens=body.input_tokens,
        output_tokens=body.output_tokens,
        calls=body.calls,
    )
    return EstimateOut(
        model=estimate.model,
        calls=estimate.calls,
        input_tokens=estimate.input_tokens,
        output_tokens=estimate.output_tokens,
        cost_usd=estimate.cost_usd,
        month_to_date_usd=estimate.month_to_date_usd,
        cap_usd=estimate.cap_usd,
        exceeds_cap=estimate.exceeds_cap,
    )
