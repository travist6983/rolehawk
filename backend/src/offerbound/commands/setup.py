"""/setup commands. The dashboard uses the REST routes; these serve chat and skills."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from offerbound.commands.registry import CommandContext, CommandRegistry, CommandSpec, NoParams
from offerbound.profile.extraction import ExtractedSetup
from offerbound.profile.interview import AnswerValue
from offerbound.profile.service import completeness


class _Params(BaseModel):
    model_config = ConfigDict(extra="forbid")


async def _overview(ctx: CommandContext, _params: NoParams) -> dict[str, Any]:
    rt = ctx.runtime
    profile = await asyncio.to_thread(rt.profiles.load_profile)
    prefs = await asyncio.to_thread(rt.profiles.load_preferences)
    state = await asyncio.to_thread(rt.setup.interview_state)
    draft = await asyncio.to_thread(rt.setup.get_draft)
    return {
        "completeness": completeness(profile, prefs).model_dump(),
        "interview": state.model_dump(mode="json"),
        "has_draft": draft is not None,
        "next_step": (
            "Review and apply the setup draft"
            if draft
            else "Answer the next interview question"
            if not state.complete
            else "Profile set up; choose job sources next"
        ),
    }


class ImportParams(_Params):
    path: str = Field(description="Local path to a PDF, DOCX, TXT, or LinkedIn export ZIP.")


def _import_file(ctx: CommandContext, raw_path: str) -> dict[str, Any]:
    path = Path(raw_path).expanduser()
    view = ctx.runtime.setup.add_document(path.name, path.read_bytes())
    return view.model_dump(mode="json")


async def _import(ctx: CommandContext, params: ImportParams) -> dict[str, Any]:
    return await asyncio.to_thread(_import_file, ctx, params.path)


class ExtractParams(_Params):
    document_ids: list[int] = Field(min_length=1)


async def _extract(ctx: CommandContext, params: ExtractParams) -> dict[str, Any]:
    await ctx.progress(None, "Reading your documents")
    draft = await ctx.runtime.setup.extract(
        params.document_ids, task_id=ctx.task.task_id if ctx.task else None
    )
    await ctx.progress(1.0, "Draft ready for review")
    return draft.model_dump(mode="json")


async def _store_draft(ctx: CommandContext, params: ExtractedSetup) -> dict[str, Any]:
    draft = await asyncio.to_thread(ctx.runtime.setup.store_draft, params)
    return draft.model_dump(mode="json")


async def _apply(ctx: CommandContext, _params: NoParams) -> dict[str, Any]:
    result = await asyncio.to_thread(ctx.runtime.setup.apply_draft)
    return result.model_dump(mode="json")


async def _interview(ctx: CommandContext, _params: NoParams) -> dict[str, Any]:
    state = await asyncio.to_thread(ctx.runtime.setup.interview_state)
    return state.model_dump(mode="json")


class AnswerParams(_Params):
    question_id: str
    value: AnswerValue


async def _answer(ctx: CommandContext, params: AnswerParams) -> dict[str, Any]:
    state = await asyncio.to_thread(ctx.runtime.setup.answer, params.question_id, params.value)
    return state.model_dump(mode="json")


class SkipParams(_Params):
    question_id: str


async def _skip(ctx: CommandContext, params: SkipParams) -> dict[str, Any]:
    state = await asyncio.to_thread(ctx.runtime.setup.skip, params.question_id)
    return state.model_dump(mode="json")


def register_setup(registry: CommandRegistry) -> None:
    for spec in [
        CommandSpec(
            "setup",
            "Show profile setup progress: completeness, the next interview question, and "
            "whether an imported draft is waiting for review.",
            _overview,
        ),
        CommandSpec(
            "setup-import",
            "Import a resume, CV, or LinkedIn export from a local file path.",
            _import,
            ImportParams,
            read_only=False,
            chat_allowed=False,  # reads local files; for the CLI and skills only
        ),
        CommandSpec(
            "setup-extract",
            "Read imported documents with Claude and prepare a profile draft for review.",
            _extract,
            ExtractParams,
            read_only=False,
            background=True,
        ),
        CommandSpec(
            "setup-draft",
            "Store a profile draft extracted elsewhere (e.g. by Claude Code) for review.",
            _store_draft,
            ExtractedSetup,
            read_only=False,
            chat_allowed=False,
        ),
        CommandSpec(
            "setup-apply",
            "Merge the reviewed setup draft into profile.md and preferences.md.",
            _apply,
            read_only=False,
        ),
        CommandSpec(
            "setup-interview",
            "Show the next gap-interview question.",
            _interview,
        ),
        CommandSpec(
            "setup-answer",
            "Answer a gap-interview question with the user's own words.",
            _answer,
            AnswerParams,
            read_only=False,
            chat_allowed=False,
        ),
        CommandSpec(
            "setup-skip",
            "Skip an optional gap-interview question.",
            _skip,
            SkipParams,
            read_only=False,
            chat_allowed=False,
        ),
    ]:
        registry.register(spec)
