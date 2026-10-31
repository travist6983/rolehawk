from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field

from offerbound.api.deps import RuntimeDep
from offerbound.commands.runner import CommandStarted, run_command
from offerbound.portals.registry import get_portal
from offerbound.portals.scrape import CompanyCheck, ScrapeSummary
from offerbound.portals.state import SLUG_PATTERN, CompanyIn, CompanyView, PortalView

router = APIRouter(tags=["sources"])


class PortalPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool


class CredentialsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    secrets: dict[str, str] = Field(default_factory=dict)
    config: dict[str, str] = Field(default_factory=dict)


class ScrapeIn(BaseModel):
    portal_ids: list[str] | None = None


class TaskRef(BaseModel):
    task_id: str


class CompaniesIn(BaseModel):
    ats: str
    companies: list[CompanyIn] = Field(min_length=1, max_length=500)


class CompanyPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool


class CheckIn(BaseModel):
    ats: str
    slug: str = Field(min_length=1, max_length=128, pattern=SLUG_PATTERN)


def _known(portal_id: str) -> None:
    try:
        get_portal(portal_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Unknown source") from None


@router.get("/api/portals")
async def list_portals(runtime: RuntimeDep) -> list[PortalView]:
    return await asyncio.to_thread(runtime.portals.views)


@router.patch("/api/portals/{portal_id}")
async def patch_portal(portal_id: str, body: PortalPatch, runtime: RuntimeDep) -> PortalView:
    _known(portal_id)
    return await asyncio.to_thread(runtime.portals.set_enabled, portal_id, body.enabled)


@router.put("/api/portals/{portal_id}/credentials")
async def put_credentials(portal_id: str, body: CredentialsIn, runtime: RuntimeDep) -> PortalView:
    """API keys go to the OS keychain; non-secret settings (e.g. the USAJOBS email) to the
    database."""
    _known(portal_id)
    try:
        return await asyncio.to_thread(
            runtime.portals.set_credentials, portal_id, body.secrets, body.config
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None


@router.delete("/api/portals/{portal_id}/credentials")
async def delete_credentials(portal_id: str, runtime: RuntimeDep) -> PortalView:
    _known(portal_id)
    return await asyncio.to_thread(runtime.portals.clear_credentials, portal_id)


@router.post("/api/scrape", status_code=202)
async def scrape(runtime: RuntimeDep, body: ScrapeIn | None = None) -> TaskRef:
    """Starts a background search; follow progress over /api/events."""
    spec = runtime.commands.get("scrape")
    started = await run_command(runtime, spec, (body or ScrapeIn()).model_dump())
    assert isinstance(started, CommandStarted)  # noqa: S101 - scrape is a background command
    return TaskRef(task_id=started.task_id)


@router.get("/api/scrape/last")
async def last_scrape(runtime: RuntimeDep) -> ScrapeSummary | None:
    """Results of the most recent successful search, or null if none has run."""
    return await asyncio.to_thread(runtime.scraper.last_summary)


@router.get("/api/companies")
async def list_companies(runtime: RuntimeDep, ats: str | None = None) -> list[CompanyView]:
    return await asyncio.to_thread(runtime.portals.companies, ats)


@router.post("/api/companies", status_code=201)
async def add_companies(body: CompaniesIn, runtime: RuntimeDep) -> list[CompanyView]:
    try:
        return await asyncio.to_thread(runtime.portals.add_companies, body.ats, body.companies)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None


@router.patch("/api/companies/{company_id}")
async def patch_company(company_id: int, body: CompanyPatch, runtime: RuntimeDep) -> CompanyView:
    try:
        return await asyncio.to_thread(
            runtime.portals.set_company_enabled, company_id, body.enabled
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="Unknown company") from None


@router.delete("/api/companies/{company_id}", status_code=204)
async def delete_company(company_id: int, runtime: RuntimeDep) -> Response:
    try:
        await asyncio.to_thread(runtime.portals.remove_company, company_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Unknown company") from None
    return Response(status_code=204)


@router.post("/api/companies/check")
async def check_company(body: CheckIn, runtime: RuntimeDep) -> CompanyCheck:
    """Look the company up on its ATS before adding it (one public request)."""
    try:
        return await runtime.scraper.check_company(body.ats, body.slug)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
