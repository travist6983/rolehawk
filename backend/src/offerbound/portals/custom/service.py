"""/add-portal: inspect a careers URL, optionally have Claude propose a definition, test it
in the sandbox (3+ jobs required), and save it as a plugin the Scraper runs."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from datetime import datetime

from pydantic import BaseModel, Field
from sqlalchemy import delete, exists, select
from sqlalchemy.orm import Session, sessionmaker

from offerbound.db.models import Application, Job, Portal, PortalKind, RiskLevel
from offerbound.llm.service import LLMService
from offerbound.llm.types import Message, SystemBlock, Task
from offerbound.paths import DataPaths
from offerbound.portals.base import NormalizedJob, PortalContext, PortalError, RawJob
from offerbound.portals.custom.definition import (
    PortalDefinition,
    RssDefinition,
    UnsafeUrlError,
    check_url,
    guess_company_in_title,
    site_domain,
    split_company,
)
from offerbound.portals.custom.detect import Candidate, Inspection, inspect, page_sample
from offerbound.portals.custom.generate import RULES, AiDraft, draft_prompt, to_definition
from offerbound.portals.custom.sandbox import Definition, run_in_sandbox
from offerbound.portals.custom.store import (
    PluginFiles,
    definition_json,
    plugin_source,
    portal_id,
)

MIN_JOBS = 3
SAMPLES = 5


class TestResult(BaseModel):
    ok: bool = Field(description="At least 3 jobs came back")
    count: int
    samples: list[NormalizedJob]
    errors: list[str]
    error: str | None
    plugin_source: str
    definition_json: str
    definition: PortalDefinition = Field(
        description="What was tested, with anything the run settled (how titles carry the"
        " company) filled in. Add this one."
    )


class NotEnoughJobsError(ValueError):
    pass


def _settle_company(
    definition: RssDefinition, jobs: list[NormalizedJob]
) -> tuple[RssDefinition, list[NormalizedJob]]:
    """Feeds that list many companies often put the company in the title. Guess the pattern
    from this run's titles and save it, so later runs split the same way (no guessing)."""
    how = "none" if definition.company else guess_company_in_title([j.title for j in jobs])
    definition = definition.model_copy(update={"company_in_title": how})
    split = []
    for job in jobs:
        company, title = split_company(job.title, how)
        split.append(
            job.model_copy(update={"company": company, "title": title}) if company else job
        )
    return definition, split


class CustomPortal:
    """Adapter so the Scraper runs a custom source like a built-in one (in the sandbox)."""

    kind = PortalKind.PLUGIN
    countries: tuple[str, ...] = ("*",)
    requires: tuple[str, ...] = ()
    default_enabled = True
    min_interval_s = 1.0

    def __init__(self, definition: Definition, allow_private: bool = False) -> None:
        self.definition = definition
        self.id = portal_id(definition.id)
        self.name = definition.name
        self.host = site_domain(definition.domain)
        self.docs_url = definition.source_url
        self.risk_level = RiskLevel.MEDIUM if definition.kind == "html" else RiskLevel.LOW
        self.allow_private = allow_private

    async def search(self, ctx: PortalContext, since: datetime | None) -> AsyncIterator[RawJob]:
        result = await run_in_sandbox(self.definition, allow_private=self.allow_private)
        if not result.ok:
            raise PortalError(result.error or "the source failed")
        for job in result.jobs:
            yield RawJob(job.external_id, job.model_dump(mode="json"))

    def normalize(self, raw: RawJob) -> NormalizedJob:
        return NormalizedJob.model_validate(raw.data)


class AddPortalService:
    def __init__(
        self,
        paths: DataPaths,
        sessions: sessionmaker[Session],
        llm: LLMService,
        allow_private: Callable[[], bool] = lambda: False,
    ) -> None:
        self.files = PluginFiles(paths.portals)
        self._sessions = sessions
        self._llm = llm
        self.allow_private = allow_private

    # --- discovery ----------------------------------------------------------------------

    async def inspect(self, url: str) -> Inspection:
        return await asyncio.to_thread(inspect, url, allow_private=self.allow_private())

    async def draft(self, url: str, name: str | None = None) -> Candidate:
        """Claude proposes a definition from the page (when detection found nothing)."""
        domain = site_domain(_host(url))
        check_url(url, domain, allow_private=self.allow_private())
        sample = await asyncio.to_thread(page_sample, url, allow_private=self.allow_private())
        draft = await self._llm.structured(
            command="add-portal",
            task=Task.EXTRACT,
            system=[SystemBlock(RULES)],
            messages=[Message(role="user", text=draft_prompt(sample))],
            schema=AiDraft,
        )
        definition = to_definition(draft, url, name or _host(url).removeprefix("www."))
        return Candidate(
            kind=definition.kind,
            title="JSON job list" if definition.kind == "json_api" else "Page layout (CSS)",
            detail=draft.reason,
            definition=definition,
        )

    async def test(self, definition: Definition) -> TestResult:
        result = await run_in_sandbox(definition, allow_private=self.allow_private(), limit=200)
        jobs = result.jobs
        if isinstance(definition, RssDefinition) and definition.company_in_title is None:
            definition, jobs = _settle_company(definition, jobs)
        return TestResult(
            ok=result.ok and len(jobs) >= MIN_JOBS,
            count=len(jobs),
            samples=jobs[:SAMPLES],
            errors=result.errors,
            error=result.error
            or (
                None
                if len(result.jobs) >= MIN_JOBS
                else f"Found {len(result.jobs)} jobs; a source needs at least {MIN_JOBS}."
            ),
            plugin_source=plugin_source(definition),
            definition_json=definition_json(definition),
            definition=definition,
        )

    # --- saved sources ------------------------------------------------------------------

    async def add(self, definition: Definition) -> TestResult:
        """Test again (the client's result isn't trusted), then save and enable."""
        result = await self.test(definition)
        if not result.ok:
            raise NotEnoughJobsError(result.error or "the test run failed")
        await asyncio.to_thread(self._save, result.definition)
        return result

    def _save(self, definition: Definition) -> None:
        self.files.save(definition)
        with self._sessions.begin() as session:
            row = session.get(Portal, portal_id(definition.id))
            risk = RiskLevel.MEDIUM if definition.kind == "html" else RiskLevel.LOW
            if row is None:
                session.add(
                    Portal(
                        id=portal_id(definition.id),
                        name=definition.name,
                        kind=PortalKind.PLUGIN,
                        countries=["*"],
                        enabled=True,
                        risk_level=risk,
                        config={},
                    )
                )
            else:
                row.name, row.enabled, row.risk_level = definition.name, True, risk

    def portals(self) -> list[CustomPortal]:
        return [CustomPortal(d, self.allow_private()) for d in self.files.load_all()]

    def remove(self, definition_id: str) -> bool:
        """Delete the plugin, its row, and its jobs (jobs you applied to keep the row)."""
        removed = self.files.remove(definition_id)
        pid = portal_id(definition_id)
        with self._sessions.begin() as session:
            has_application = exists().where(Application.job_id == Job.id)
            session.execute(delete(Job).where(Job.portal_id == pid, ~has_application))
            still_used = session.scalar(select(Job.id).where(Job.portal_id == pid).limit(1))
            row = session.get(Portal, pid)
            if row is not None:
                if still_used is None:
                    session.delete(row)
                else:
                    row.enabled = False
        return removed


def _host(url: str) -> str:
    from urllib.parse import urlsplit

    host = urlsplit(url).hostname
    if not host:
        raise UnsafeUrlError("not a web URL")
    return host
