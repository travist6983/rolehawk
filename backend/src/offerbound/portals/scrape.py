"""/scrape: run every enabled, ready source concurrently, keep jobs matching a search target,
normalize, and dedupe (by source + external id, then by company/title/location hash).
One failing source never fails the run."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Sequence
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from offerbound.db.models import (
    Company,
    Job,
    Portal,
    RemotePolicy,
    SearchTarget,
    Task,
    TaskStatus,
)
from offerbound.db.types import utcnow
from offerbound.portals.ats import AtsPortal
from offerbound.portals.base import (
    CompanyRef,
    NormalizedJob,
    PortalContext,
    PortalError,
    SearchQuery,
)
from offerbound.portals.base import Portal as PortalImpl
from offerbound.portals.http import HttpError, PoliteClient
from offerbound.portals.integrity import clean_posting
from offerbound.portals.matching import title_matches
from offerbound.portals.registry import ATS_IDS, BUILTIN
from offerbound.portals.state import missing_requirements, stored_secrets
from offerbound.portals.text import job_hash

log = logging.getLogger(__name__)

PORTAL_TIMEOUT_S = 300
MAX_JOBS_PER_PORTAL = 2_000

Progress = Callable[[float | None, str | None], Awaitable[None]]


class NoSearchTargetsError(ValueError):
    user_message = "Add the job titles you're looking for (Profile > Preferences) first."


class PortalRun(BaseModel):
    model_config = ConfigDict(json_schema_serialization_defaults_required=True)

    portal_id: str
    name: str
    status: str  # ok | error | skipped
    found: int = 0
    matched: int = 0
    new: int = 0
    duplicates: int = 0
    errors: list[str] = Field(default_factory=list)
    detail: str | None = None


class CompanyCheck(BaseModel):
    ok: bool
    jobs: int
    company: str | None = Field(description="The name the ATS reports, when it differs")
    detail: str | None


class ScrapeSummary(BaseModel):
    started_at: datetime
    finished_at: datetime
    queries: list[str]
    portals: list[PortalRun]
    found: int
    new: int
    duplicates: int


def load_queries(session: Session, default_country: str) -> list[SearchQuery]:
    targets = session.scalars(select(SearchTarget).where(SearchTarget.active.is_(True)))
    return [
        SearchQuery(
            title=t.title,
            keywords=tuple(t.keywords or ()),
            locations=tuple(t.locations or ()),
            country=(t.country or default_country).upper(),
            remote_only=t.remote_policy is RemotePolicy.REMOTE,
        )
        for t in targets
    ]


def _checked(job: NormalizedJob) -> NormalizedJob:
    """A last integrity pass over the final text, for sources that send plain text (and so
    invisible characters and lines addressed to AI tools are caught whatever the source)."""
    final = clean_posting(job.description, html_input=False)
    found = final.integrity.merge(job.integrity) if job.integrity else final.integrity
    return job.model_copy(update={"description": final.text, "integrity": found})


def _integrity(job: NormalizedJob) -> dict[str, object] | None:
    return job.integrity.stored() if job.integrity else None


class Scraper:
    def __init__(
        self,
        sessions: sessionmaker[Session],
        default_country: Callable[[], str],
        http_factory: Callable[[], PoliteClient] = PoliteClient,
        portals: Sequence[PortalImpl] = BUILTIN,
        extra: Callable[[], Sequence[PortalImpl]] = lambda: (),
    ) -> None:
        self._sessions = sessions
        self._default_country = default_country
        self.http_factory = http_factory  # swapped in tests for a recorded transport
        self._builtin = list(portals)
        self._extra = extra  # custom sources added with /add-portal
        self._write_lock = asyncio.Lock()

    @property
    def _portals(self) -> list[PortalImpl]:
        return [*self._builtin, *self._extra()]

    async def run(
        self, progress: Progress, portal_ids: Sequence[str] | None = None
    ) -> ScrapeSummary:
        started = utcnow()
        with self._sessions() as session:
            queries = load_queries(session, self._default_country())
            rows = {p.id: p for p in session.scalars(select(Portal))}
            companies: dict[str, list[CompanyRef]] = {ats: [] for ats in ATS_IDS}
            for company in session.scalars(select(Company).where(Company.enabled.is_(True))):
                companies.setdefault(company.ats, []).append(CompanyRef(company.slug, company.name))
        if not queries:
            raise NoSearchTargetsError("no active search targets")

        countries = {q.country for q in queries}
        portals = self._portals
        selected = [p for p in portals if portal_ids is None or p.id in portal_ids]
        runs: list[PortalRun] = []
        jobs_to_run: list[tuple[PortalImpl, PortalContext]] = []
        http = self.http_factory()
        for impl in selected:
            row = rows.get(impl.id)
            config = dict(row.config) if row else {}
            secrets = stored_secrets(impl.id)
            portal_companies = companies.get(impl.id, [])
            if row is None or (not row.enabled and portal_ids is None):
                runs.append(
                    PortalRun(portal_id=impl.id, name=impl.name, status="skipped", detail="off")
                )
                continue
            if "*" not in impl.countries and not countries & set(impl.countries):
                runs.append(
                    PortalRun(
                        portal_id=impl.id,
                        name=impl.name,
                        status="skipped",
                        detail="not available in your search country",
                    )
                )
                continue
            missing = missing_requirements(impl, config, secrets, len(portal_companies))
            if missing:
                runs.append(
                    PortalRun(
                        portal_id=impl.id,
                        name=impl.name,
                        status="skipped",
                        detail="needs " + ", ".join(missing),
                    )
                )
                continue
            http.pace(impl.host, impl.min_interval_s)
            jobs_to_run.append(
                (
                    impl,
                    PortalContext(
                        http=http,
                        queries=queries,
                        companies=portal_companies,
                        secrets=secrets,
                        config=config,
                    ),
                )
            )

        done = 0
        total = len(jobs_to_run)
        await progress(0.0 if total else None, f"Searching {total} sources")

        async def run_one(impl: PortalImpl, ctx: PortalContext) -> PortalRun:
            nonlocal done
            result = await self._run_portal(impl, ctx)
            done += 1
            await progress(
                done / total,
                f"{impl.name}: {result.new} new"
                + (f", {len(result.errors)} issues" if result.errors else ""),
            )
            return result

        try:
            runs += await asyncio.gather(*(run_one(impl, ctx) for impl, ctx in jobs_to_run))
        finally:
            await http.aclose()

        order = {p.id: i for i, p in enumerate(portals)}
        runs.sort(key=lambda r: order.get(r.portal_id, 99))
        return ScrapeSummary(
            started_at=started,
            finished_at=utcnow(),
            queries=[q.title for q in queries],
            portals=runs,
            found=sum(r.found for r in runs),
            new=sum(r.new for r in runs),
            duplicates=sum(r.duplicates for r in runs),
        )

    def last_summary(self) -> ScrapeSummary | None:
        """The most recent successful run's results, for the Sources screen."""
        with self._sessions() as session:
            row = session.scalar(
                select(Task)
                .where(Task.kind == "scrape", Task.status == TaskStatus.SUCCEEDED)
                .order_by(Task.finished_at.desc())
                .limit(1)
            )
            result = row.result if row else None
        if not isinstance(result, dict):
            return None
        try:
            return ScrapeSummary.model_validate(result)
        except ValueError:  # an older result shape
            return None

    async def check_company(self, ats: str, slug: str) -> CompanyCheck:
        """Look a company up on its ATS before adding it to the watchlist (one request)."""
        impl = next((p for p in self._portals if p.id == ats), None)
        if not isinstance(impl, AtsPortal):
            raise ValueError(f"{ats!r} is not an ATS source")
        http = self.http_factory()
        http.pace(impl.host, impl.min_interval_s)
        try:
            jobs = await impl.fetch_company(
                PortalContext(http=http, queries=()), CompanyRef(slug, slug)
            )
        except HttpError as exc:
            detail = "No job board with that name on this ATS." if exc.status == 404 else str(exc)
            return CompanyCheck(ok=False, jobs=0, company=None, detail=detail)
        except (KeyError, TypeError, ValueError):
            return CompanyCheck(
                ok=False, jobs=0, company=None, detail="The ATS sent an unexpected response."
            )
        finally:
            await http.aclose()
        name: str | None = None
        if jobs:  # Greenhouse and Workable report the company's own name on each job
            try:
                name = impl.normalize(jobs[0]).company
            except (KeyError, TypeError, ValueError):
                name = None
        return CompanyCheck(
            ok=True, jobs=len(jobs), company=name if name and name != slug else None, detail=None
        )

    async def _run_portal(self, impl: PortalImpl, ctx: PortalContext) -> PortalRun:
        run = PortalRun(portal_id=impl.id, name=impl.name, status="ok")
        company_errors: dict[str, str] = {}
        company_counts: dict[str, int] = {}
        ctx.report_company_error = lambda c, e: company_errors.__setitem__(c.slug, e)
        ctx.report_company_count = lambda c, n: company_counts.__setitem__(c.slug, n)
        matched: list[NormalizedJob] = []
        try:
            async with asyncio.timeout(PORTAL_TIMEOUT_S):
                async for raw in impl.search(ctx, None):
                    run.found += 1
                    try:
                        job = impl.normalize(raw)
                    except (KeyError, TypeError, ValueError) as exc:
                        run.errors.append(f"skipped a malformed job: {exc}")
                        continue
                    if not job.title or not job.url.startswith(("https://", "http://")):
                        continue  # no title, or a link that isn't a web page
                    if title_matches(job.title, ctx.queries):
                        matched.append(job)
                        if len(matched) >= MAX_JOBS_PER_PORTAL:
                            run.errors.append(f"stopped at {MAX_JOBS_PER_PORTAL} matching jobs")
                            break
        except TimeoutError:
            run.errors.append(f"timed out after {PORTAL_TIMEOUT_S}s; kept what was found")
        except (PortalError, HttpError) as exc:
            run.status = "error"
            run.errors.append(str(exc))
        except Exception as exc:  # isolate: one broken source never fails the run
            log.exception("source %s failed", impl.id)
            run.status = "error"
            run.errors.append(f"{type(exc).__name__}: {exc}")

        run.matched = len(matched)
        run.errors += [f"{slug}: {err}" for slug, err in sorted(company_errors.items())]
        async with self._write_lock:
            run.new, run.duplicates = await asyncio.to_thread(self._store, impl.id, matched)
            await asyncio.to_thread(self._record, impl.id, run, company_counts, company_errors)
        return run

    def _store(self, portal_id: str, jobs: list[NormalizedJob]) -> tuple[int, int]:
        new = duplicates = 0
        now = utcnow()
        with self._sessions.begin() as session:
            for job in map(_checked, jobs):
                existing = session.scalar(
                    select(Job).where(
                        Job.portal_id == portal_id, Job.external_id == job.external_id
                    )
                )
                if existing is not None:
                    existing.scraped_at = now
                    existing.url = job.url
                    if job.description:
                        existing.description = job.description
                        existing.integrity = _integrity(job)
                    duplicates += 1
                    continue
                digest = job_hash(job.company, job.title, job.location)
                if session.scalar(select(Job.id).where(Job.hash == digest)) is not None:
                    duplicates += 1  # the same job from another source
                    continue
                session.add(
                    Job(
                        portal_id=portal_id,
                        external_id=job.external_id,
                        url=job.url,
                        company=job.company,
                        title=job.title,
                        location=job.location,
                        remote=job.remote,
                        salary_text=job.salary_text,
                        description=job.description,
                        posted_at=job.posted_at,
                        scraped_at=now,
                        hash=digest,
                        integrity=_integrity(job),
                    )
                )
                session.flush()
                new += 1
        return new, duplicates

    def _record(
        self,
        portal_id: str,
        run: PortalRun,
        counts: dict[str, int],
        errors: dict[str, str],
    ) -> None:
        with self._sessions.begin() as session:
            row = session.get(Portal, portal_id)
            if row is not None:
                row.status = run.status
                row.last_run_at = utcnow()
                row.last_error = run.errors[0] if run.status == "error" and run.errors else None
            if counts or errors:
                for company in session.scalars(select(Company).where(Company.ats == portal_id)):
                    if company.slug in counts:
                        company.last_job_count = counts[company.slug]
                        company.last_error = None
                    elif company.slug in errors:
                        company.last_error = errors[company.slug]
