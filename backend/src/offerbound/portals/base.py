from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

from pydantic import BaseModel

from offerbound.db.models import PortalKind, RiskLevel
from offerbound.portals.http import PoliteClient
from offerbound.portals.integrity import PostingIntegrity


@dataclass(frozen=True)
class SearchQuery:
    """One active search target, as portals see it."""

    title: str
    keywords: tuple[str, ...] = ()
    locations: tuple[str, ...] = ()
    country: str = "US"
    remote_only: bool = False


@dataclass(frozen=True)
class CompanyRef:
    slug: str
    name: str


@dataclass(frozen=True)
class RawJob:
    """A job exactly as the source returned it, plus where it came from."""

    external_id: str
    data: dict[str, Any]
    company: CompanyRef | None = None


class NormalizedJob(BaseModel):
    external_id: str
    url: str
    company: str
    title: str
    location: str | None = None
    remote: bool | None = None
    salary_text: str | None = None
    description: str = ""
    posted_at: datetime | None = None
    # What the integrity check removed or found (portals/integrity.py); None if not run.
    integrity: PostingIntegrity | None = None


class PortalError(Exception):
    """A source failed in a way worth showing on its card (bad key, endpoint gone)."""


@dataclass
class PortalContext:
    http: PoliteClient
    queries: Sequence[SearchQuery]
    companies: Sequence[CompanyRef] = ()
    secrets: dict[str, str] = field(default_factory=dict)
    config: dict[str, Any] = field(default_factory=dict)
    # Per-company failures are reported here instead of failing the whole source.
    report_company_error: Callable[[CompanyRef, str], None] = lambda _c, _e: None
    report_company_count: Callable[[CompanyRef, int], None] = lambda _c, _n: None


class Portal(Protocol):
    id: str
    name: str
    kind: PortalKind
    countries: tuple[str, ...]  # ISO codes, or ("*",)
    risk_level: RiskLevel
    requires: tuple[str, ...]  # e.g. ("secret:adzuna_app_id", "watchlist")
    default_enabled: bool
    host: str  # for rate limiting
    min_interval_s: float  # minimum gap between requests to `host`
    docs_url: str

    def search(self, ctx: PortalContext, since: datetime | None) -> AsyncIterator[RawJob]: ...

    def normalize(self, raw: RawJob) -> NormalizedJob: ...
