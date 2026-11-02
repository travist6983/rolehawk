"""Adding jobs that no /scrape source found: one from a link or pasted posting (any site), or a
batch Claude Code found through the user's Indeed connector (jobs/intake.py)."""

from __future__ import annotations

import asyncio
from typing import Any

from rolehawk.commands.registry import CommandContext, CommandRegistry, CommandSpec, NoParams
from rolehawk.jobs.intake import ImportIn, LinkIn, PostingIn
from rolehawk.portals.scrape import load_queries


async def _job_add(ctx: CommandContext, params: PostingIn) -> dict[str, Any]:
    added = await asyncio.to_thread(ctx.runtime.intake.add, params)
    return added.model_dump(mode="json")


async def _job_read_link(ctx: CommandContext, params: LinkIn) -> dict[str, Any]:
    draft = await ctx.runtime.intake.read_link(params.url)
    return draft.model_dump(mode="json")


async def _jobs_import(ctx: CommandContext, params: ImportIn) -> dict[str, Any]:
    summary = await asyncio.to_thread(ctx.runtime.intake.import_jobs, params)
    return summary.model_dump(mode="json")


def _targets(ctx: CommandContext) -> list[dict[str, Any]]:
    with ctx.runtime.sessions() as session:
        queries = load_queries(session, ctx.runtime.settings.search.country)
    return [
        {
            "title": q.title,
            "keywords": list(q.keywords),
            "locations": list(q.locations),
            "country": q.country,
            "remote_only": q.remote_only,
        }
        for q in queries
    ]


async def _search_targets(ctx: CommandContext, _params: NoParams) -> list[dict[str, Any]]:
    return await asyncio.to_thread(_targets, ctx)


def register_intake(registry: CommandRegistry) -> None:
    registry.register(
        CommandSpec(
            "job-add",
            "Add one job the user found (any site, LinkedIn and Indeed included): link, title, "
            "company, and the posting's text. Adding the same link again returns the stored job.",
            _job_add,
            PostingIn,
            read_only=False,
            untrusted_output=True,
        )
    )
    registry.register(
        CommandSpec(
            "job-read-link",
            "Read one job posting page to fill in job-add (nothing is stored). Sites whose "
            "robots.txt asks tools not to read them (LinkedIn) are refused: paste the text.",
            _job_read_link,
            LinkIn,
            chat_allowed=False,  # fetches a URL: never on the say-so of text chat is reading
            untrusted_output=True,
        )
    )
    registry.register(
        CommandSpec(
            "jobs-import",
            "Store jobs found through the user's Indeed connector in Claude. Only jobs that "
            "match a search target (title and country) are kept; duplicates are skipped.",
            _jobs_import,
            ImportIn,
            read_only=False,
            chat_allowed=False,
        )
    )
    registry.register(
        CommandSpec(
            "search-targets",
            "The active search targets: job titles, keywords, locations, country, remote only.",
            _search_targets,
        )
    )
