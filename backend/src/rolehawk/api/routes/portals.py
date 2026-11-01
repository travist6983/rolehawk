from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field

from rolehawk.api.deps import RuntimeDep
from rolehawk.commands.runner import CommandStarted, run_command
from rolehawk.portals.custom.definition import PortalDefinition, UnsafeUrlError
from rolehawk.portals.custom.detect import Candidate, Inspection
from rolehawk.portals.custom.generate import DraftError
from rolehawk.portals.custom.service import NotEnoughJobsError, TestResult
from rolehawk.portals.custom.store import portal_id
from rolehawk.portals.scrape import CompanyCheck, ScrapeSummary
from rolehawk.portals.state import SLUG_PATTERN, CompanyIn, CompanyView, PortalView
from rolehawk.services.runtime import Runtime

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


def _known(runtime: Runtime, portal_id: str) -> None:
    if not runtime.portals.known(portal_id):
        raise HTTPException(status_code=404, detail="Unknown source")


@router.get("/api/portals")
async def list_portals(runtime: RuntimeDep) -> list[PortalView]:
    return await asyncio.to_thread(runtime.portals.views)


@router.patch("/api/portals/{portal_id}")
async def patch_portal(portal_id: str, body: PortalPatch, runtime: RuntimeDep) -> PortalView:
    _known(runtime, portal_id)
    return await asyncio.to_thread(runtime.portals.set_enabled, portal_id, body.enabled)


@router.put("/api/portals/{portal_id}/credentials")
async def put_credentials(portal_id: str, body: CredentialsIn, runtime: RuntimeDep) -> PortalView:
    """API keys go to the OS keychain; non-secret settings (e.g. the USAJOBS email) to the
    database."""
    _known(runtime, portal_id)
    try:
        return await asyncio.to_thread(
            runtime.portals.set_credentials, portal_id, body.secrets, body.config
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None


@router.delete("/api/portals/{portal_id}/credentials")
async def delete_credentials(portal_id: str, runtime: RuntimeDep) -> PortalView:
    _known(runtime, portal_id)
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


# --- /add-portal --------------------------------------------------------------------------


class InspectIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    url: str = Field(max_length=2_000)
    name: str | None = Field(default=None, max_length=80)


class DefinitionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    definition: PortalDefinition


@router.post("/api/portals/inspect")
async def inspect_portal(body: InspectIn, runtime: RuntimeDep) -> Inspection:
    """Finds how to read a careers URL: known ATS, RSS, JSON-LD, or a JSON list."""
    return await runtime.add_portal.inspect(body.url)


@router.post("/api/portals/draft")
async def draft_portal(body: InspectIn, runtime: RuntimeDep) -> Candidate:
    """Claude proposes a definition when detection found nothing (uses the API key)."""
    try:
        return await runtime.add_portal.draft(body.url, body.name)
    except (DraftError, UnsafeUrlError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None


@router.post("/api/portals/test")
async def test_portal(body: DefinitionIn, runtime: RuntimeDep) -> TestResult:
    """Runs the definition in the sandbox. ok needs at least 3 jobs."""
    return await runtime.add_portal.test(body.definition)


@router.post("/api/portals/custom", status_code=201)
async def add_custom_portal(body: DefinitionIn, runtime: RuntimeDep) -> PortalView:
    try:
        await runtime.add_portal.add(body.definition)
    except NotEnoughJobsError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    return await asyncio.to_thread(runtime.portals.view, portal_id(body.definition.id))


@router.delete("/api/portals/custom/{definition_id}", status_code=204)
async def remove_custom_portal(definition_id: str, runtime: RuntimeDep) -> Response:
    if not await asyncio.to_thread(runtime.add_portal.remove, definition_id):
        raise HTTPException(status_code=404, detail="Unknown custom source")
    return Response(status_code=204)
