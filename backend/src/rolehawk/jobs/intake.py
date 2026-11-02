"""Jobs that don't come from a /scrape source:

- One job the user adds from a link or a pasted posting, from any site (LinkedIn and Indeed
  included). It's kept whatever its title, so /rank and /apply work on it.
- A batch Claude Code found through the user's own Claude connector (Indeed's official one,
  which only Claude's apps can use). Those must match a target, like scraped jobs.

Both are cleaned (portals/integrity.py) and deduped exactly like scraped jobs. Reading a link
to a Greenhouse, Lever, Ashby, or Workable job asks that board's public API (the one /scrape
uses). Any other link fetches that one page through the custom-source Fetcher: public
addresses only, the same site, and its robots.txt respected (LinkedIn's asks tools not to, so
the user pastes the text)."""

from __future__ import annotations

import asyncio
import re
from collections.abc import Callable
from datetime import date, datetime
from typing import Literal
from urllib.parse import parse_qsl, urlsplit, urlunsplit

import httpx2
from bs4 import BeautifulSoup, Tag
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.orm import Session, sessionmaker

from rolehawk.db.models import PortalKind
from rolehawk.db.types import utcnow
from rolehawk.portals.ats import AtsPortal
from rolehawk.portals.base import CompanyRef, NormalizedJob, PortalContext, PortalError
from rolehawk.portals.custom.definition import UnsafeUrlError
from rolehawk.portals.custom.detect import ats_link
from rolehawk.portals.custom.engine import (
    EngineError,
    Fetcher,
    RobotsBlockedError,
    from_posting,
    postings_in,
)
from rolehawk.portals.http import HttpError, PoliteClient
from rolehawk.portals.integrity import clean_posting
from rolehawk.portals.matching import job_matches
from rolehawk.portals.registry import BUILTIN
from rolehawk.portals.scrape import MANUAL_SOURCE, ensure_source, load_queries, store_job
from rolehawk.portals.text import html_to_text, looks_remote

# Sources Claude Code can import from, as (portal id, name shown on jobs).
CONNECTOR_SOURCES: dict[str, str] = {"indeed": "Indeed"}
MANUAL_NAME = "Added by you"
MAX_IMPORT = 200
MAX_PAGE_TEXT = 30_000
_HTML_TAG = re.compile(r"<(p|br|li|ul|ol|div|h[1-6]|strong|b|em|span)\b", re.IGNORECASE)


class IntakeError(ValueError):
    """Something the user can fix: a link that can't be read, or a bad posting."""


class PostingIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    url: str = Field(min_length=1, max_length=2000, description="Link to the posting")
    title: str = Field(min_length=1, max_length=255)
    company: str = Field(min_length=1, max_length=255)
    location: str | None = Field(default=None, max_length=255)
    remote: bool | None = None
    salary_text: str | None = Field(default=None, max_length=255)
    description: str = Field(default="", max_length=100_000, description="The posting's text")
    posted_at: datetime | None = None
    closes_at: date | None = Field(default=None, description="Application deadline, if stated")
    external_id: str | None = Field(
        default=None, max_length=255, description="The source's id for the job, when known"
    )

    @field_validator("url")
    @classmethod
    def _web_link(cls, value: str) -> str:
        if not value.startswith(("https://", "http://")) or not urlsplit(value).hostname:
            raise ValueError("Links must start with http:// or https://")
        return value


class Added(BaseModel):
    job_id: int
    created: bool = Field(description="False when the job was already in your list")
    title: str
    company: str


class ImportIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: Literal["indeed"] = Field(description="Where the jobs came from")
    jobs: list[PostingIn] = Field(max_length=MAX_IMPORT)


class ImportSummary(BaseModel):
    model_config = ConfigDict(json_schema_serialization_defaults_required=True)

    received: int
    matched: int = Field(description="Jobs that match a search target (title and country)")
    new: int
    duplicates: int


class LinkIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    url: str = Field(min_length=1, max_length=2000)


class LinkDraft(BaseModel):
    """What a link's page says, to fill the Add a job form. The user checks it before saving."""

    model_config = ConfigDict(json_schema_serialization_defaults_required=True)

    url: str
    found: Literal["posting", "page"] = Field(
        description="posting: the page describes the job in structured data; page: only its text"
    )
    title: str | None
    company: str | None
    location: str | None
    remote: bool | None
    description: str
    posted_at: datetime | None
    closes_at: date | None


def _draft(url: str, job: NormalizedJob) -> LinkDraft:
    return LinkDraft(
        url=url,
        found="posting",
        title=job.title,
        company=job.company or None,
        location=job.location,
        remote=job.remote,
        description=job.description,
        posted_at=job.posted_at,
        closes_at=job.closes_at,
    )


def _link_ids(url: str) -> set[str]:
    """Every path segment and query value of a link: one of them is the board's job id."""
    parts = urlsplit(url)
    return {p for p in parts.path.split("/") if p} | {v for _k, v in parse_qsl(parts.query)}


def link_id(url: str) -> str:
    """A stable id for a link: no query or fragment (tracking parameters vary per visit)."""
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc.lower(), parts.path.rstrip("/"), "", ""))[:255]


def _normalized(posting: PostingIn, external_id: str) -> NormalizedJob:
    cleaned = clean_posting(
        posting.description, html_input=bool(_HTML_TAG.search(posting.description))
    )
    return NormalizedJob(
        external_id=external_id,
        url=posting.url,
        company=posting.company,
        title=posting.title,
        location=posting.location or None,
        remote=posting.remote
        if posting.remote is not None
        else looks_remote(posting.location, posting.title),
        salary_text=posting.salary_text or None,
        description=cleaned.text,
        integrity=cleaned.integrity,
        posted_at=posting.posted_at,
        closes_at=posting.closes_at,
    )


class JobIntake:
    def __init__(
        self,
        sessions: sessionmaker[Session],
        default_country: Callable[[], str],
        fetcher: Callable[[str], Fetcher] = Fetcher,
        http_factory: Callable[[], PoliteClient] = PoliteClient,
    ) -> None:
        self._sessions = sessions
        self._default_country = default_country
        self.fetcher = fetcher  # tests swap in a fake site
        self.http_factory = http_factory  # and a recorded transport for job boards

    def add(self, posting: PostingIn) -> Added:
        """Add one job the user found. Adding the same link again returns the stored job."""
        job = _normalized(posting, posting.external_id or link_id(posting.url))
        with self._sessions.begin() as session:
            ensure_source(session, MANUAL_SOURCE, MANUAL_NAME, PortalKind.MANUAL)
            job_id, created = store_job(session, MANUAL_SOURCE, job, utcnow())
        return Added(job_id=job_id, created=created, title=job.title, company=job.company)

    def import_jobs(self, params: ImportIn) -> ImportSummary:
        """Store jobs Claude Code found through a connector, keeping those that match a target."""
        now = utcnow()
        new = matched = 0
        with self._sessions.begin() as session:
            queries = load_queries(session, self._default_country())
            ensure_source(
                session, params.source, CONNECTOR_SOURCES[params.source], PortalKind.CONNECTOR
            )
            for posting in params.jobs:
                if not job_matches(posting.title, posting.location, queries):
                    continue
                matched += 1
                job = _normalized(posting, posting.external_id or link_id(posting.url))
                new += store_job(session, params.source, job, now)[1]
        return ImportSummary(
            received=len(params.jobs), matched=matched, new=new, duplicates=matched - new
        )

    async def read_link(self, url: str) -> LinkDraft:
        """Read what a posting link says, to fill in the Add a job form. Nothing is stored."""
        host = (urlsplit(url).hostname or "").lower()
        if not url.startswith(("https://", "http://")) or not host:
            raise IntakeError("Links must start with http:// or https://")
        board = await self._from_board(url)
        if board is not None:
            return board
        return await asyncio.to_thread(self._from_page, url, host)

    async def _from_board(self, url: str) -> LinkDraft | None:
        """A job on a Greenhouse, Lever, Ashby, or Workable board, from the board's public API:
        it names the company and location, which the job page often doesn't."""
        found = ats_link(url)
        impl = next((p for p in BUILTIN if found and p.id == found[0]), None)
        if found is None or not isinstance(impl, AtsPortal):
            return None
        http = self.http_factory()
        try:
            raws = await impl.fetch_company(
                PortalContext(http=http, queries=()), CompanyRef(found[1], found[1])
            )
            ids = _link_ids(url)
            raw = next((r for r in raws if r.external_id in ids), None)
            return _draft(url, impl.normalize(raw)) if raw else None
        except (PortalError, HttpError, httpx2.HTTPError, KeyError, TypeError, ValueError):
            return None  # read the page instead
        finally:
            await http.aclose()

    def _from_page(self, url: str, host: str) -> LinkDraft:
        fetch = self.fetcher(host.removeprefix("www."))
        try:
            page = fetch.get(url)
        except RobotsBlockedError:
            raise IntakeError(
                f"{host} doesn't allow tools to read its pages. Copy the posting's text into "
                "the form instead."
            ) from None
        except UnsafeUrlError as exc:
            raise IntakeError(f"Couldn't open that link: {exc}.") from None
        except (EngineError, httpx2.HTTPError) as exc:
            raise IntakeError(
                f"Couldn't read that page ({exc}). Copy the posting's text into the form instead."
            ) from None
        finally:
            fetch.close()
        page_url = str(page.url)
        for posting in postings_in(page.text):
            job = from_posting(posting, page_url, None)
            if job is not None:
                return _draft(url, job)
        return _page_draft(url, page.text)


def _page_draft(url: str, markup: str) -> LinkDraft:
    """No structured data: the page's title and visible text, for the user to tidy up."""
    soup = BeautifulSoup(markup, "html.parser")
    meta = soup.find("meta", attrs={"property": "og:title"})
    title = meta.get("content") if isinstance(meta, Tag) else None
    if not isinstance(title, str) or not title.strip():
        title = soup.title.get_text() if soup.title else None
    body = soup.find("main") or soup.body or soup
    for tag in body.find_all(["script", "style", "nav", "header", "footer", "noscript"]):
        tag.decompose()
    text = clean_posting(str(body)).text[:MAX_PAGE_TEXT]
    return LinkDraft(
        url=url,
        found="page",
        title=(html_to_text(title).strip() or None) if title else None,
        company=None,
        location=None,
        remote=None,
        description=text,
        posted_at=None,
        closes_at=None,
    )
