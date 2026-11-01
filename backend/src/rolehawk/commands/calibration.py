"""Learn from results: patterns in what got interviews, as preference proposals."""

from __future__ import annotations

import asyncio
from typing import Any

from rolehawk.commands.registry import CommandContext, CommandRegistry, CommandSpec, NoParams


async def _status(ctx: CommandContext, _params: NoParams) -> dict[str, Any]:
    status = await asyncio.to_thread(ctx.runtime.calibration.status)
    return status.model_dump(mode="json")


async def _calibrate(ctx: CommandContext, _params: NoParams) -> dict[str, Any]:
    result = await ctx.runtime.calibration.run(ctx.task_id)
    return result.model_dump(mode="json")


def register_calibration(registry: CommandRegistry) -> None:
    registry.register(
        CommandSpec(
            "calibration-status",
            "How many applications have a result (interview, offer, rejected, no reply) and "
            "whether there are enough to learn from.",
            _status,
        )
    )
    registry.register(
        CommandSpec(
            "calibrate",
            "Compare applications that got interviews with ones that didn't, and propose "
            "preference edits (pending until the user accepts each).",
            _calibrate,
            read_only=False,
            untrusted_output=True,
        )
    )
