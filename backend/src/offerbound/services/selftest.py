"""A harmless background task that exercises the runner, progress events, and SSE end to end.
Used by `offerbound doctor` and by the frontend while developing progress UI."""

from __future__ import annotations

import asyncio
from typing import Any

from offerbound.services.tasks import TaskContext

KIND = "selftest"


def make_selftest(steps: int = 5, delay_s: float = 0.2) -> Any:
    async def run(ctx: TaskContext) -> dict[str, int]:
        for step in range(1, steps + 1):
            await asyncio.sleep(delay_s)
            await ctx.progress(step / steps, f"Step {step} of {steps}")
        return {"steps": steps}

    return run
