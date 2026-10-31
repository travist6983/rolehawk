"""Keyword or whole-market feeds. Endpoints and terms verified 2026-10-31 (see SOURCES.md)."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from collections.abc import AsyncIterator
from datetime import datetime

from offerbound.db.models import PortalKind, RiskLevel
from offerbound.portals.base import NormalizedJob, PortalContext, PortalError, RawJob
from offerbound.portals.http import HttpError
from offerbound.portals.integrity import clean_posting
from offerbound.portals.text import (
    html_to_text,
    looks_remote,
    parse_datetime,
    salary_range,
)


def _safe_xml(text: str) -> ET.Element:
    """RSS from the network: refuse DTDs/entities (XXE, entity expansion) before parsing."""
    head = text[:2048].upper()
    if "<!DOCTYPE" in head or "<!ENTITY" in text.upper():
        raise PortalError("feed contains a DTD; refusing to parse it")
    return ET.fromstring(text)  # noqa: S314 - DTDs refused above


class RemoteOK:
    """Terms (from the API's own `legal` field): link back to the Remote OK job URL and
    mention Remote OK as the source. We store and show the remoteok.com URL for each job."""

    id = "remoteok"
    name = "Remote OK"
    kind = PortalKind.FEED
    countries: tuple[str, ...] = ("*",)
    risk_level = RiskLevel.LOW
    requires: tuple[str, ...] = ()
    default_enabled = True
    host = "remoteok.com"
    min_interval_s = 2.0
    docs_url = "https://remoteok.com/api"

    async def search(self, ctx: PortalContext, since: datetime | None) -> AsyncIterator[RawJob]:
        data = await ctx.http.json(f"https://{self.host}/api")
        for job in data:
            if isinstance(job, dict) and job.get("id") and job.get("position"):  # skip `legal`
                yield RawJob(str(job["id"]), job)

    def normalize(self, raw: RawJob) -> NormalizedJob:
        job = raw.data
        desc = clean_posting(job.get("description"))
        return NormalizedJob(
            external_id=raw.external_id,
            url=job.get("url") or f"https://remoteok.com/remote-jobs/{raw.external_id}",
            company=html_to_text(job.get("company")),
            title=html_to_text(job["position"]),  # titles arrive entity-encoded
            location=job.get("location") or "Remote",
            remote=True,
            salary_text=salary_range(job.get("salary_min"), job.get("salary_max"), "USD", "year"),
            description=desc.text,
            integrity=desc.integrity,
            posted_at=parse_datetime(job.get("date") or job.get("epoch")),
        )


class WeWorkRemotely:
    id = "weworkremotely"
    name = "We Work Remotely"
    kind = PortalKind.FEED
    countries: tuple[str, ...] = ("*",)
    risk_level = RiskLevel.LOW
    requires: tuple[str, ...] = ()
    default_enabled = True
    host = "weworkremotely.com"
    min_interval_s = 2.0
    docs_url = "https://weworkremotely.com/remote-jobs.rss"
    DEFAULT_FEEDS: tuple[str, ...] = (
        "remote-jobs.rss",
    )  # everything; categories like categories/<slug>.rss

    async def search(self, ctx: PortalContext, since: datetime | None) -> AsyncIterator[RawJob]:
        feeds = ctx.config.get("feeds") or self.DEFAULT_FEEDS
        for feed in feeds:
            root = _safe_xml(await ctx.http.text(f"https://{self.host}/{feed}"))
            for item in root.iter("item"):
                data = {child.tag: (child.text or "").strip() for child in item}
                key = data.get("guid") or data.get("link")
                if key and data.get("title"):
                    yield RawJob(key.rstrip("/").rsplit("/", 1)[-1], data)

    def normalize(self, raw: RawJob) -> NormalizedJob:
        item = raw.data
        company, _, title = item["title"].partition(": ")
        if not title:  # no "Company: " prefix
            company, title = "", item["title"]
        region = item.get("region") or "Remote"
        desc = clean_posting(item.get("description"))
        return NormalizedJob(
            external_id=raw.external_id,
            url=item.get("link") or item.get("guid") or "",
            company=html_to_text(company),
            title=html_to_text(title),
            location=region,
            remote=True,
            description=desc.text,
            integrity=desc.integrity,
            posted_at=parse_datetime(item.get("pubDate")),
        )


class Adzuna:
    """Free API key (app_id + app_key). Terms: personal job search is a permitted use; show
    "Adzuna" with a link on listings. Country list is Adzuna's published markets."""

    id = "adzuna"
    name = "Adzuna"
    kind = PortalKind.FEED
    countries: tuple[str, ...] = (
        "GB", "US", "AT", "AU", "BE", "BR", "CA", "CH", "DE", "ES",
        "FR", "IN", "IT", "MX", "NL", "NZ", "PL", "SG", "ZA",
    )  # fmt: skip
    risk_level = RiskLevel.LOW
    requires: tuple[str, ...] = ("secret:adzuna_app_id", "secret:adzuna_app_key")
    default_enabled = True
    host = "api.adzuna.com"
    min_interval_s = 1.0
    docs_url = "https://developer.adzuna.com/docs/search"
    PAGES = 2
    PER_PAGE = 50

    async def search(self, ctx: PortalContext, since: datetime | None) -> AsyncIterator[RawJob]:
        for query in ctx.queries:
            country = query.country.lower()
            if query.country.upper() not in self.countries:
                continue
            for page in range(1, self.PAGES + 1):
                params: dict[str, str | int] = {
                    "app_id": ctx.secrets["adzuna_app_id"],
                    "app_key": ctx.secrets["adzuna_app_key"],
                    "what": query.title,
                    "results_per_page": self.PER_PAGE,
                    "max_days_old": 30,
                    "content-type": "application/json",
                }
                if query.locations and not query.remote_only:
                    params["where"] = query.locations[0]
                try:
                    data = await ctx.http.json(
                        f"https://{self.host}/v1/api/jobs/{country}/search/{page}", params=params
                    )
                except HttpError as exc:
                    if exc.status in (401, 403):
                        raise PortalError("Adzuna rejected the app ID or key") from exc
                    raise
                results = data.get("results", [])
                for job in results:
                    yield RawJob(str(job["id"]), job)
                if len(results) < self.PER_PAGE:
                    break

    def normalize(self, raw: RawJob) -> NormalizedJob:
        job = raw.data
        location = (job.get("location") or {}).get("display_name")
        salary = salary_range(job.get("salary_min"), job.get("salary_max"))
        if salary and job.get("salary_is_predicted") in (1, "1", True):
            salary = f"{salary} (Adzuna estimate)"
        desc = clean_posting(job.get("description"))
        return NormalizedJob(
            external_id=raw.external_id,
            url=job["redirect_url"],
            company=(job.get("company") or {}).get("display_name") or "",
            title=html_to_text(job["title"]),
            location=location,
            remote=looks_remote(location, job.get("title")),
            salary_text=salary,
            description=desc.text,
            integrity=desc.integrity,
            posted_at=parse_datetime(job.get("created")),
        )


class USAJobs:
    """US federal jobs. Needs a free API key and the email it was issued to (sent as the
    User-Agent, as the API requires)."""

    id = "usajobs"
    name = "USAJOBS"
    kind = PortalKind.FEED
    countries: tuple[str, ...] = ("US",)
    risk_level = RiskLevel.LOW
    requires: tuple[str, ...] = ("secret:usajobs_api_key", "config:email")
    default_enabled = True
    host = "data.usajobs.gov"
    min_interval_s = 1.0
    docs_url = "https://developer.usajobs.gov/api-reference/get-api-search"

    async def search(self, ctx: PortalContext, since: datetime | None) -> AsyncIterator[RawJob]:
        headers = {
            "Host": self.host,
            "User-Agent": str(ctx.config["email"]),
            "Authorization-Key": ctx.secrets["usajobs_api_key"],
        }
        for query in ctx.queries:
            if query.country.upper() != "US":
                continue
            params: dict[str, str | int] = {
                "Keyword": query.title,
                "ResultsPerPage": 100,
                "DatePosted": 30,
            }
            if query.remote_only:
                params["RemoteIndicator"] = "True"
            elif query.locations:
                params["LocationName"] = ";".join(query.locations)
            try:
                data = await ctx.http.json(
                    f"https://{self.host}/api/search", params=params, headers=headers
                )
            except HttpError as exc:
                if exc.status in (401, 403):
                    raise PortalError("USAJOBS rejected the API key or email") from exc
                raise
            for item in (data.get("SearchResult") or {}).get("SearchResultItems", []):
                yield RawJob(str(item.get("MatchedObjectId")), item)

    def normalize(self, raw: RawJob) -> NormalizedJob:
        job = raw.data.get("MatchedObjectDescriptor") or {}
        pay = (job.get("PositionRemuneration") or [{}])[0]
        details = ((job.get("UserArea") or {}).get("Details")) or {}
        location = job.get("PositionLocationDisplay")
        return NormalizedJob(
            external_id=raw.external_id,
            url=job.get("PositionURI") or "",
            company=job.get("OrganizationName") or job.get("DepartmentName") or "",
            title=job.get("PositionTitle", "").strip(),
            location=location,
            remote=True if details.get("RemoteIndicator") else looks_remote(location),
            salary_text=salary_range(
                pay.get("MinimumRange"),
                pay.get("MaximumRange"),
                "USD",
                (pay.get("Description") or "").lower().replace("per ", "") or None,
            ),
            description=details.get("JobSummary") or job.get("QualificationSummary") or "",
            posted_at=parse_datetime(job.get("PublicationStartDate")),
        )
