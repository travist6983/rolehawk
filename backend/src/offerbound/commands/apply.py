"""/apply and application commands. The API, chat, and skills all go through these."""

from __future__ import annotations

import asyncio
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from offerbound.apply.drafts import (
    SECTIONS,
    WRITER_RULES,
    ApplicationDraft,
    Section,
    build_cv,
    build_letter,
    indexed_profile,
)
from offerbound.apply.review import REVIEW_RULES
from offerbound.apply.service import ApplyParams, DocumentsIn, StagePatch
from offerbound.apply.style import check_style, polish
from offerbound.apply.truth import check_cv, check_letter
from offerbound.commands.registry import CommandContext, CommandRegistry, CommandSpec

EXTERNAL_MODEL = "claude-code"


class JobRef(BaseModel):
    model_config = ConfigDict(extra="forbid")
    job_id: int


class ApplicationRef(BaseModel):
    model_config = ConfigDict(extra="forbid")
    application_id: int


class UpdateParams(StagePatch):
    model_config = ConfigDict(extra="forbid")
    application_id: int


class DocumentsParams(DocumentsIn):
    model_config = ConfigDict(extra="forbid")
    application_id: int


class RegenerateParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    application_id: int
    section: Section = Field(description=f"One of: {', '.join(SECTIONS)}")
    instruction: str | None = Field(default=None, max_length=1_000)


class SaveDraftParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    job_id: int
    draft: ApplicationDraft


async def _apply(ctx: CommandContext, params: ApplyParams) -> dict[str, Any]:
    result = await ctx.runtime.applications.apply(params, ctx.progress, ctx.task_id)
    return result.model_dump(mode="json")


async def _plan(ctx: CommandContext, params: JobRef) -> dict[str, Any]:
    plan = await asyncio.to_thread(ctx.runtime.applications.plan, params.job_id)
    return plan.model_dump(mode="json")


async def _application(ctx: CommandContext, params: ApplicationRef) -> dict[str, Any]:
    detail = await asyncio.to_thread(ctx.runtime.applications.detail, params.application_id)
    return detail.model_dump(mode="json")


async def _update(ctx: CommandContext, params: UpdateParams) -> dict[str, Any]:
    patch = StagePatch(stage=params.stage, notes=params.notes)
    detail = await asyncio.to_thread(ctx.runtime.applications.update, params.application_id, patch)
    return detail.model_dump(mode="json")


async def _documents(ctx: CommandContext, params: DocumentsParams) -> dict[str, Any]:
    edits = DocumentsIn(cv=params.cv, cover_letter=params.cover_letter)
    detail = await ctx.runtime.applications.save_documents(params.application_id, edits)
    return detail.model_dump(mode="json")


async def _regenerate(ctx: CommandContext, params: RegenerateParams) -> dict[str, Any]:
    result = await ctx.runtime.applications.regenerate(
        params.application_id, params.section, params.instruction, ctx.progress, ctx.task_id
    )
    return result.model_dump(mode="json")


async def _autofill(ctx: CommandContext, params: ApplicationRef) -> dict[str, Any]:
    report = await ctx.runtime.applications.autofill(params.application_id, ctx.runtime.autofill)
    return report.model_dump(mode="json")


async def _apply_context(ctx: CommandContext, params: JobRef) -> dict[str, Any]:
    """For the /apply skill: everything Claude Code needs to draft in its own session."""
    runtime = ctx.runtime
    detail = await asyncio.to_thread(runtime.jobs.get, params.job_id)
    profile = await asyncio.to_thread(runtime.profiles.load_profile)
    plan = await asyncio.to_thread(runtime.applications.plan, params.job_id)
    return {
        "job": detail.model_dump(mode="json"),
        "fit": plan.fit.model_dump() if plan.fit else None,
        "threshold": plan.threshold,
        "writer_rules": WRITER_RULES,
        "review_rules": REVIEW_RULES,
        "profile_index": indexed_profile(profile),
        "draft_schema": ApplicationDraft.model_json_schema(),
    }


async def _apply_save(ctx: CommandContext, params: SaveDraftParams) -> dict[str, Any]:
    """A draft written by Claude Code. Structured facts still come from the profile by
    index, and the fact and style checks run exactly as in the app."""
    service = ctx.runtime.applications
    profile = await asyncio.to_thread(ctx.runtime.profiles.load_profile)
    job = await asyncio.to_thread(service.job, params.job_id)
    cv, letter = polish(
        build_cv(profile, params.draft.cv), build_letter(profile, job, params.draft.cover_letter)
    )
    flags = (
        check_cv(cv, profile)
        + check_letter(letter, profile, job.description)
        + check_style(cv, letter)
    )
    application_id = await asyncio.to_thread(service.ensure_application, job.id)
    fit = await asyncio.to_thread(service.latest_fit, job.id)
    bundle = await service.render_documents(
        application_id, job.id, cv, letter, flags, fit, EXTERNAL_MODEL
    )
    return {
        "application_id": application_id,
        "status": "needs_review" if bundle.flags else "ready",
        "flags": [f.model_dump() for f in bundle.flags],
        "files": bundle.files.model_dump(),
    }


def register_apply(registry: CommandRegistry) -> None:
    registry.register(
        CommandSpec(
            "apply",
            "Fit-check a job, draft a tailored CV and cover letter, fact-check them against "
            "the profile, and create Word and PDF files plus an application at Applying.",
            _apply,
            ApplyParams,
            read_only=False,
            background=True,
        )
    )
    registry.register(
        CommandSpec(
            "apply-plan",
            "Before /apply: the job's fit score, the threshold, and the estimated cost.",
            _plan,
            JobRef,
        )
    )
    registry.register(
        CommandSpec(
            "application",
            "One application: stage, history, the job, documents, and review flags.",
            _application,
            ApplicationRef,
            untrusted_output=True,
        )
    )
    registry.register(
        CommandSpec(
            "application-update",
            "Move an application to a stage (e.g. applied) or set its notes.",
            _update,
            UpdateParams,
            read_only=False,
        )
    )
    registry.register(
        CommandSpec(
            "application-documents",
            "Replace an application's CV or cover letter data (hand edits); re-checks facts "
            "and re-renders the files.",
            _documents,
            DocumentsParams,
            read_only=False,
        )
    )
    registry.register(
        CommandSpec(
            "application-regenerate",
            "Rewrite one part of an application (summary, experience, skills, cover_letter), "
            "optionally following an instruction.",
            _regenerate,
            RegenerateParams,
            read_only=False,
            background=True,
        )
    )
    registry.register(
        CommandSpec(
            "autofill",
            "Open the job's application form in a visible browser, fill the contact fields, "
            "and attach the CV and cover letter. Never submits.",
            _autofill,
            ApplicationRef,
            read_only=False,
        )
    )
    registry.register(
        CommandSpec(
            "apply-context",
            "For drafting outside the app (the /apply skill): the job, fit, indexed profile, "
            "rules, and the draft schema.",
            _apply_context,
            JobRef,
            chat_allowed=False,
            untrusted_output=True,
        )
    )
    registry.register(
        CommandSpec(
            "apply-save",
            "Save a draft written outside the app: builds the documents from the profile, "
            "fact-checks them, renders files, and creates the application.",
            _apply_save,
            SaveDraftParams,
            read_only=False,
            chat_allowed=False,
        )
    )
