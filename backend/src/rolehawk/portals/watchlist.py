"""Adding companies to the watchlist from a skill or chat: check each board, keep the real ones."""

from __future__ import annotations

import asyncio

from pydantic import BaseModel

from rolehawk.portals.scrape import Scraper
from rolehawk.portals.state import CompanyIn, CompanyView, PortalStore

CHECK_CONCURRENCY = 3


class NotAdded(BaseModel):
    slug: str
    detail: str


class WatchlistAddResult(BaseModel):
    added: list[CompanyView]
    not_added: list[NotAdded]


async def add_checked(
    scraper: Scraper, store: PortalStore, ats: str, slugs: list[str]
) -> WatchlistAddResult:
    slots = asyncio.Semaphore(CHECK_CONCURRENCY)

    async def check(slug: str) -> tuple[str, str | None, str | None]:
        async with slots:
            result = await scraper.check_company(ats, slug)
        if not result.ok:
            return slug, None, result.detail or "not found"
        return slug, result.company or slug, None

    unique = list(dict.fromkeys(s.strip() for s in slugs if s.strip()))
    results = await asyncio.gather(*(check(slug) for slug in unique))
    found = [CompanyIn(slug=slug, name=name) for slug, name, error in results if not error]
    added = await asyncio.to_thread(store.add_companies, ats, found) if found else []
    return WatchlistAddResult(
        added=added,
        not_added=[NotAdded(slug=s, detail=e) for s, _, e in results if e],
    )
