"""Pipeline, Insights, the HTML report, and /reset."""

from __future__ import annotations

import asyncio
from typing import Any

from rolehawk.commands.registry import CommandContext, CommandRegistry, CommandSpec, NoParams
from rolehawk.services.reset import ResetIn


async def _pipeline(ctx: CommandContext, _params: NoParams) -> dict[str, Any]:
    board = await asyncio.to_thread(ctx.runtime.board.board)
    return board.model_dump(mode="json")


async def _insights(ctx: CommandContext, _params: NoParams) -> dict[str, Any]:
    insights = await asyncio.to_thread(ctx.runtime.insights.insights)
    return insights.model_dump(mode="json")


async def _report(ctx: CommandContext, _params: NoParams) -> dict[str, Any]:
    report = await asyncio.to_thread(ctx.runtime.reports.generate)
    return report.model_dump(mode="json")


async def _reset(ctx: CommandContext, params: ResetIn) -> dict[str, Any]:
    result = await asyncio.to_thread(ctx.runtime.reset.reset, params)
    return result.model_dump(mode="json")


def register_insights(registry: CommandRegistry) -> None:
    registry.register(
        CommandSpec(
            "pipeline",
            "The Pipeline board: applications by stage with days in stage and next action.",
            _pipeline,
            untrusted_output=True,
        )
    )
    registry.register(
        CommandSpec(
            "insights",
            "Funnel, response rate by source, weekly activity, and AI spend this month.",
            _insights,
            untrusted_output=True,
        )
    )
    registry.register(
        CommandSpec(
            "html-report",
            "Write a self-contained HTML report (charts and a searchable table, no network "
            "requests) to the reports folder.",
            _report,
            read_only=False,
        )
    )
    registry.register(
        CommandSpec(
            "reset",
            "Delete part of your data after a zipped backup. scope: profile, documents, jobs, "
            "applications, or everything; confirm must repeat the scope.",
            _reset,
            ResetIn,
            read_only=False,
            chat_allowed=False,  # destructive: only from the Settings screen or a terminal
        )
    )
