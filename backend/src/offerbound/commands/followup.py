"""Follow-ups on quiet applications and closing stale ones (apply/followup.py)."""

from __future__ import annotations

import asyncio
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from offerbound.apply.followup import (
    FOLLOW_UP_DAYS,
    STALE_DAYS,
    Channel,
    CloseStaleIn,
    FollowUpIn,
)
from offerbound.commands.registry import CommandContext, CommandRegistry, CommandSpec
from offerbound.db.models import FollowUpChannel


class QuietParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    days: int = Field(default=FOLLOW_UP_DAYS, ge=1, le=365, description="Quiet for at least")


class StaleParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    days: int = Field(default=STALE_DAYS, ge=7, le=730, description="Quiet for at least")


class DraftParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    application_id: int
    channel: Channel = FollowUpChannel.EMAIL


class LogParams(FollowUpIn):
    application_id: int


class CloseParams(CloseStaleIn):
    days: int = Field(default=STALE_DAYS, ge=7, le=730)


async def _quiet(ctx: CommandContext, params: QuietParams) -> dict[str, Any]:
    rows = await asyncio.to_thread(ctx.runtime.followups.quiet, params.days)
    return {"applications": [r.model_dump(mode="json") for r in rows]}


async def _stale(ctx: CommandContext, params: StaleParams) -> dict[str, Any]:
    rows = await asyncio.to_thread(ctx.runtime.followups.stale, params.days)
    return {"applications": [r.model_dump(mode="json") for r in rows]}


async def _draft(ctx: CommandContext, params: DraftParams) -> dict[str, Any]:
    draft = await ctx.runtime.followups.draft(params.application_id, params.channel, ctx.task_id)
    return draft.model_dump(mode="json")


async def _log(ctx: CommandContext, params: LogParams) -> dict[str, Any]:
    note = FollowUpIn(channel=params.channel, subject=params.subject, body=params.body)
    view = await asyncio.to_thread(ctx.runtime.followups.log, params.application_id, note)
    return view.model_dump(mode="json")


async def _close(ctx: CommandContext, params: CloseParams) -> dict[str, Any]:
    result = await asyncio.to_thread(
        ctx.runtime.followups.close_stale, params.application_ids, params.days
    )
    return result.model_dump()


def register_followup(registry: CommandRegistry) -> None:
    registry.register(
        CommandSpec(
            "followups",
            "Applications quiet long enough for a follow-up (default 10 days, at most two "
            "follow-ups each).",
            _quiet,
            QuietParams,
            untrusted_output=True,
        )
    )
    registry.register(
        CommandSpec(
            "followup-draft",
            "Draft a short follow-up note for a quiet application from the documents already "
            "sent (email, linkedin, or portal). A draft only: nothing is sent.",
            _draft,
            DraftParams,
            untrusted_output=True,
        )
    )
    registry.register(
        CommandSpec(
            "followup-log",
            "Record a follow-up the user has sent, so the quiet-days count restarts.",
            _log,
            LogParams,
            read_only=False,
        )
    )
    registry.register(
        CommandSpec(
            "stale-applications",
            "Applications with no reply for a long time (default 60 days).",
            _stale,
            StaleParams,
            untrusted_output=True,
        )
    )
    registry.register(
        CommandSpec(
            "close-stale",
            "Move chosen long-quiet applications to Ghosted (no response).",
            _close,
            CloseParams,
            read_only=False,
        )
    )
