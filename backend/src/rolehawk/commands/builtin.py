"""Commands available from chunk 3 on. Feature commands (setup, scrape, rank, apply, ...)
register themselves in later chunks."""

from __future__ import annotations

import asyncio
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from rolehawk.commands.registry import CommandContext, CommandRegistry, CommandSpec, NoParams
from rolehawk.memory.context import build_context_pack
from rolehawk.memory.proposals import ProposalIn


class SelftestParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    steps: int = Field(default=5, ge=1, le=50)
    delay_s: float = Field(default=0.2, ge=0, le=5)


async def _selftest(ctx: CommandContext, params: SelftestParams) -> dict[str, int]:
    for step in range(1, params.steps + 1):
        await asyncio.sleep(params.delay_s)
        await ctx.progress(step / params.steps, f"Step {step} of {params.steps}")
    return {"steps": params.steps}


class ContextParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    for_command: str = Field(default="chat", description="Command the pack is for.")
    job_ids: list[int] = Field(default_factory=list)
    application_ids: list[int] = Field(default_factory=list)


async def _context(ctx: CommandContext, params: ContextParams) -> dict[str, Any]:
    rt = ctx.runtime
    pack = await asyncio.to_thread(
        build_context_pack,
        rt.memory,
        rt.sessions,
        params.for_command,
        job_ids=params.job_ids,
        application_ids=params.application_ids,
    )
    return {
        "pack": pack.to_json(),
        "memory_text": pack.memory_text(),
        "rows_text": pack.rows_text(),
    }


async def _memory(ctx: CommandContext, _params: NoParams) -> dict[str, Any]:
    rt = ctx.runtime
    snapshot = await asyncio.to_thread(rt.memory.snapshot)
    pending = await asyncio.to_thread(rt.memory.list_proposals)
    return {
        "memory": snapshot.model_dump(),
        "pending_proposals": [p.model_dump(mode="json") for p in pending],
    }


async def _spend(ctx: CommandContext, _params: NoParams) -> dict[str, Any]:
    rt = ctx.runtime
    spent = await asyncio.to_thread(rt.llm.meter.month_to_date)
    return {"month_to_date_usd": spent, "monthly_cap_usd": rt.settings.llm.monthly_cap_usd}


async def _propose(ctx: CommandContext, params: ProposalIn) -> dict[str, Any]:
    """Skills suggest memory edits this way; the user accepts them in the dashboard."""
    view = await asyncio.to_thread(ctx.runtime.memory.propose, params, "skill")
    return view.model_dump(mode="json")


def register_builtin(registry: CommandRegistry) -> None:
    registry.register(
        CommandSpec(
            "selftest",
            "Run a short background task to check progress streaming.",
            _selftest,
            SelftestParams,
            background=True,
        )
    )
    registry.register(
        CommandSpec(
            "context",
            "Export the context pack (memory files plus requested jobs/applications) that "
            "commands send to Claude. Skills use it to work from the same facts.",
            _context,
            ContextParams,
        )
    )
    registry.register(CommandSpec("memory", "Show memory files and pending proposals.", _memory))
    registry.register(CommandSpec("spend", "Show AI spend this month and the cap.", _spend))
    registry.register(
        CommandSpec(
            "propose",
            "Propose a memory edit (target, op, section, text, old_text, reason). It stays "
            "pending until the user accepts it in the dashboard.",
            _propose,
            ProposalIn,
            read_only=False,
        )
    )
