from __future__ import annotations

import asyncio
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field

from rolehawk.commands.registry import CommandContext, CommandRegistry, CommandSpec, NoParams
from rolehawk.portals.state import SLUG_PATTERN
from rolehawk.portals.watchlist import add_checked


class ScrapeParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    portal_ids: list[str] | None = Field(
        default=None, description="Only these sources (runs them even if switched off)."
    )


async def _scrape(ctx: CommandContext, params: ScrapeParams) -> dict[str, Any]:
    async def progress(fraction: float | None, message: str | None) -> None:
        await ctx.progress(fraction, message)

    summary = await ctx.runtime.scraper.run(progress, params.portal_ids)
    return summary.model_dump(mode="json")


class WatchlistAddParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ats: str = Field(description="greenhouse, lever, ashby, workable, or smartrecruiters")
    slugs: list[Annotated[str, Field(pattern=SLUG_PATTERN, max_length=128)]] = Field(
        min_length=1,
        max_length=50,
        description="Board names, e.g. 'stripe' from boards.greenhouse.io/stripe",
    )


async def _sources(ctx: CommandContext, _params: NoParams) -> dict[str, Any]:
    runtime = ctx.runtime
    views, last = await asyncio.gather(
        asyncio.to_thread(runtime.portals.views),
        asyncio.to_thread(runtime.scraper.last_summary),
    )
    return {
        "sources": [v.model_dump(mode="json") for v in views],
        "last_search": last.model_dump(mode="json") if last else None,
    }


async def _watchlist(ctx: CommandContext, _params: NoParams) -> list[dict[str, Any]]:
    companies = await asyncio.to_thread(ctx.runtime.portals.companies)
    return [c.model_dump(mode="json") for c in companies]


async def _watchlist_add(ctx: CommandContext, params: WatchlistAddParams) -> dict[str, Any]:
    result = await add_checked(ctx.runtime.scraper, ctx.runtime.portals, params.ats, params.slugs)
    return result.model_dump(mode="json")


def register_scrape(registry: CommandRegistry) -> None:
    registry.register(
        CommandSpec(
            "scrape",
            "Search every enabled job source for the active search targets, keeping new "
            "matching jobs and skipping duplicates.",
            _scrape,
            ScrapeParams,
            read_only=False,
            background=True,
        )
    )
    registry.register(
        CommandSpec(
            "sources",
            "List job sources with status, readiness (what each still needs), jobs found, and "
            "the last search's per-source results.",
            _sources,
            untrusted_output=True,  # error text and names from job sites
        )
    )
    registry.register(
        CommandSpec(
            "watchlist",
            "List the companies whose job boards are searched.",
            _watchlist,
            untrusted_output=True,
        )
    )
    registry.register(
        CommandSpec(
            "watchlist-add",
            "Add companies to the watchlist by ATS board name. Each is looked up on its ATS "
            "first; only real boards are added.",
            _watchlist_add,
            WatchlistAddParams,
            read_only=False,
        )
    )
