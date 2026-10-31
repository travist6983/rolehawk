"""Applicant tracking systems with public job board APIs. They list jobs per company, so they
walk the company watchlist. Endpoints verified 2026-10-31 (see SOURCES.md)."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import datetime
from typing import Any

from offerbound.db.models import PortalKind, RiskLevel
from offerbound.portals.base import CompanyRef, NormalizedJob, PortalContext, RawJob
from offerbound.portals.http import HttpError
from offerbound.portals.text import (
    html_to_text,
    looks_remote,
    parse_datetime,
    salary_range,
)

FetchCompany = Callable[[PortalContext, CompanyRef], Awaitable[list[RawJob]]]


async def walk_companies(
    ctx: PortalContext, fetch: FetchCompany, concurrency: int = 4
) -> AsyncIterator[RawJob]:
    """Fetch every company concurrently; a failing company is reported, never fatal."""
    queue: asyncio.Queue[list[RawJob] | None] = asyncio.Queue()
    slots = asyncio.Semaphore(concurrency)

    async def one(company: CompanyRef) -> None:
        async with slots:
            try:
                jobs = await fetch(ctx, company)
            except HttpError as exc:
                message = "not found on this ATS" if exc.status == 404 else str(exc)
                ctx.report_company_error(company, message)
                jobs = []
            except (KeyError, TypeError, ValueError) as exc:
                ctx.report_company_error(company, f"unexpected response: {exc}")
                jobs = []
            else:
                ctx.report_company_count(company, len(jobs))
        await queue.put(jobs)

    tasks = [asyncio.create_task(one(c)) for c in ctx.companies]
    try:
        for _ in tasks:
            batch = await queue.get()
            for job in batch or []:
                yield job
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


class AtsPortal:
    """Base for sources that list jobs per company from the watchlist."""

    kind = PortalKind.ATS
    countries: tuple[str, ...] = ("*",)
    risk_level = RiskLevel.LOW
    requires: tuple[str, ...] = ("watchlist",)
    default_enabled = True
    min_interval_s = 0.2

    async def fetch_company(self, ctx: PortalContext, company: CompanyRef) -> list[RawJob]:
        raise NotImplementedError

    def search(self, ctx: PortalContext, since: datetime | None) -> AsyncIterator[RawJob]:
        return walk_companies(ctx, self.fetch_company)


class Greenhouse(AtsPortal):
    id = "greenhouse"
    name = "Greenhouse"
    host = "boards-api.greenhouse.io"
    docs_url = "https://developers.greenhouse.io/job-board.html"

    async def fetch_company(self, ctx: PortalContext, company: CompanyRef) -> list[RawJob]:
        data = await ctx.http.json(
            f"https://{self.host}/v1/boards/{company.slug}/jobs", params={"content": "true"}
        )
        return [RawJob(str(job["id"]), job, company) for job in data.get("jobs", [])]

    def normalize(self, raw: RawJob) -> NormalizedJob:
        job = raw.data
        location = (job.get("location") or {}).get("name")
        return NormalizedJob(
            external_id=raw.external_id,
            url=job["absolute_url"],
            company=job.get("company_name") or (raw.company.name if raw.company else ""),
            title=job["title"].strip(),
            location=location,
            remote=looks_remote(location),
            description=html_to_text(job.get("content")),
            posted_at=parse_datetime(job.get("first_published") or job.get("updated_at")),
        )


class Lever(AtsPortal):
    id = "lever"
    name = "Lever"
    host = "api.lever.co"
    docs_url = "https://github.com/lever/postings-api"

    async def fetch_company(self, ctx: PortalContext, company: CompanyRef) -> list[RawJob]:
        try:
            data = await ctx.http.json(
                f"https://{self.host}/v0/postings/{company.slug}", params={"mode": "json"}
            )
        except HttpError as exc:
            if exc.status != 404:
                raise
            # Some companies live on Lever's EU instance.
            data = await ctx.http.json(
                f"https://api.eu.lever.co/v0/postings/{company.slug}", params={"mode": "json"}
            )
        return [RawJob(str(job["id"]), job, company) for job in data]

    def normalize(self, raw: RawJob) -> NormalizedJob:
        job = raw.data
        categories = job.get("categories") or {}
        location = categories.get("location")
        workplace = (job.get("workplaceType") or "").lower()
        salary = job.get("salaryRange") or {}
        sections = [job.get("descriptionPlain") or html_to_text(job.get("description"))]
        for block in job.get("lists") or []:
            sections.append(f"{block.get('text', '')}\n{html_to_text(block.get('content'))}")
        sections.append(job.get("additionalPlain") or "")
        return NormalizedJob(
            external_id=raw.external_id,
            url=job["hostedUrl"],
            company=raw.company.name if raw.company else "",
            title=job["text"].strip(),
            location=location,
            remote=True if workplace == "remote" else looks_remote(location),
            salary_text=salary_range(
                salary.get("min"),
                salary.get("max"),
                salary.get("currency"),
                (salary.get("interval") or "").replace("per-", "") or None,
            ),
            description="\n\n".join(s.strip() for s in sections if s and s.strip()),
            posted_at=parse_datetime(job.get("createdAt")),
        )


class Ashby(AtsPortal):
    id = "ashby"
    name = "Ashby"
    host = "api.ashbyhq.com"
    docs_url = "https://developers.ashbyhq.com/docs/public-job-posting-api"

    async def fetch_company(self, ctx: PortalContext, company: CompanyRef) -> list[RawJob]:
        data = await ctx.http.json(
            f"https://{self.host}/posting-api/job-board/{company.slug}",
            params={"includeCompensation": "true"},
        )
        jobs = [j for j in data.get("jobs", []) if j.get("isListed", True)]
        # Ashby documents no id field; use it when present, else the stable job URL.
        return [RawJob(str(j.get("id") or j["jobUrl"]), j, company) for j in jobs]

    def normalize(self, raw: RawJob) -> NormalizedJob:
        job = raw.data
        compensation: dict[str, Any] = job.get("compensation") or {}
        workplace = (job.get("workplaceType") or "").lower()
        return NormalizedJob(
            external_id=raw.external_id,
            url=job.get("jobUrl") or job["applyUrl"],
            company=raw.company.name if raw.company else "",
            title=job["title"].strip(),
            location=job.get("location"),
            remote=True
            if workplace == "remote"
            else (None if workplace else looks_remote(job.get("location"))),
            salary_text=compensation.get("scrapeableCompensationSalarySummary")
            or compensation.get("compensationTierSummary"),
            description=job.get("descriptionPlain") or html_to_text(job.get("descriptionHtml")),
            posted_at=parse_datetime(job.get("publishedAt")),
        )


class Workable(AtsPortal):
    id = "workable"
    name = "Workable"
    host = "apply.workable.com"
    # The help center documents www.workable.com/api/accounts/{subdomain}, which redirects here.
    docs_url = "https://help.workable.com/hc/en-us/articles/115012771647"

    async def fetch_company(self, ctx: PortalContext, company: CompanyRef) -> list[RawJob]:
        data = await ctx.http.json(
            f"https://{self.host}/api/v1/widget/accounts/{company.slug}",
            params={"details": "true"},
        )
        name = data.get("name") or company.name
        ref = CompanyRef(company.slug, name)
        return [RawJob(str(j["shortcode"]), j, ref) for j in data.get("jobs", [])]

    def normalize(self, raw: RawJob) -> NormalizedJob:
        job = raw.data
        location = ", ".join(
            p for p in [job.get("city"), job.get("state"), job.get("country")] if p
        )
        return NormalizedJob(
            external_id=raw.external_id,
            url=job["url"],
            company=raw.company.name if raw.company else "",
            title=job["title"].strip(),
            location=location or None,
            remote=True if job.get("telecommuting") else looks_remote(location),
            description=html_to_text(job.get("description")),
            posted_at=parse_datetime(job.get("published_on") or job.get("created_at")),
        )
