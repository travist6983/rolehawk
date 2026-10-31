"""/rank and the job triage commands. Same services as the Discover screen."""

from __future__ import annotations

import asyncio
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from offerbound.commands.registry import CommandContext, CommandRegistry, CommandSpec
from offerbound.fit.ranker import BATCH_SIZE, RankParams
from offerbound.fit.rubric import FIT_RUBRIC, RUBRIC_VERSION, JobFit
from offerbound.jobs.store import DismissIn, JobQuery, SaveIn

EXTERNAL_MODEL = "claude-code"


class JobParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    job_id: int


class CandidatesParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    limit: int = Field(default=BATCH_SIZE, ge=1, le=50, description="Jobs per batch")
    rescore: bool = False


class SaveScoresParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scores: list[JobFit] = Field(min_length=1, max_length=200)


async def _rank(ctx: CommandContext, params: RankParams) -> dict[str, Any]:
    summary = await ctx.runtime.ranker.run(params, ctx.progress, ctx.task_id)
    return summary.model_dump(mode="json")


async def _rank_plan(ctx: CommandContext, params: RankParams) -> dict[str, Any]:
    plan = await asyncio.to_thread(ctx.runtime.ranker.plan, params)
    return plan.model_dump(mode="json")


async def _rank_candidates(ctx: CommandContext, params: CandidatesParams) -> dict[str, Any]:
    """For the /rank skill: Claude Code scores in its own session, then calls rank-save."""
    runtime = ctx.runtime
    plan_params = RankParams(rescore=params.rescore)
    jobs, counts, remaining = await asyncio.to_thread(runtime.ranker.select, plan_params)
    batch = jobs[: params.limit]
    return {
        "rubric_version": RUBRIC_VERSION,
        "rubric": FIT_RUBRIC,
        "jobs": [runtime.ranker.job_payload(job) for job in batch],
        "left_after_this_batch": len(jobs) - len(batch) + remaining,
        "filtered": counts.model_dump(),
    }


async def _rank_save(ctx: CommandContext, params: SaveScoresParams) -> dict[str, int]:
    saved = await asyncio.to_thread(ctx.runtime.ranker.save_external, params.scores, EXTERNAL_MODEL)
    return {"saved": saved}


async def _jobs(ctx: CommandContext, params: JobQuery) -> dict[str, Any]:
    page = await asyncio.to_thread(ctx.runtime.jobs.list, params)
    return page.model_dump(mode="json")


async def _job(ctx: CommandContext, params: JobParams) -> dict[str, Any]:
    detail = await asyncio.to_thread(ctx.runtime.jobs.get, params.job_id)
    return detail.model_dump(mode="json")


async def _jobs_save(ctx: CommandContext, params: SaveIn) -> dict[str, Any]:
    changed = await asyncio.to_thread(ctx.runtime.jobs.set_saved, params.job_ids, params.saved)
    return changed.model_dump()


async def _jobs_dismiss(ctx: CommandContext, params: DismissIn) -> dict[str, Any]:
    changed = await asyncio.to_thread(
        ctx.runtime.jobs.set_dismissed, params.job_ids, params.dismissed
    )
    return changed.model_dump()


def register_rank(registry: CommandRegistry) -> None:
    registry.register(
        CommandSpec(
            "rank",
            "Score new jobs against the profile with the fit rubric (after hard filters for "
            "location, salary, and excluded words). Uses the in-app Claude key; see rank-plan "
            "for the cost first.",
            _rank,
            RankParams,
            read_only=False,
            background=True,
        )
    )
    registry.register(
        CommandSpec(
            "rank-plan",
            "How many jobs /rank would score, what the hard filters skipped, and the "
            "estimated cost.",
            _rank_plan,
            RankParams,
        )
    )
    registry.register(
        CommandSpec(
            "rank-candidates",
            "The next batch of jobs to score plus the fit rubric, for scoring outside the app "
            "(the /rank skill in Claude Code). Save results with rank-save.",
            _rank_candidates,
            CandidatesParams,
            chat_allowed=False,
            untrusted_output=True,
        )
    )
    registry.register(
        CommandSpec(
            "rank-save",
            "Save fit scores computed outside the app (job_id, score 0-100, reasons, "
            "must_have_gaps).",
            _rank_save,
            SaveScoresParams,
            read_only=False,
            chat_allowed=False,
        )
    )
    registry.register(
        CommandSpec(
            "jobs",
            "List scraped jobs with their latest fit score; filter by text, status, minimum "
            "score, source, or remote.",
            _jobs,
            JobQuery,
            untrusted_output=True,
        )
    )
    registry.register(
        CommandSpec(
            "job",
            "One job with its full posting, score, reasons, and gaps.",
            _job,
            JobParams,
            untrusted_output=True,
        )
    )
    registry.register(
        CommandSpec(
            "jobs-save",
            "Save jobs to the pipeline (stage Saved), or unsave them with saved=false.",
            _jobs_save,
            SaveIn,
            read_only=False,
        )
    )
    registry.register(
        CommandSpec(
            "jobs-dismiss",
            "Dismiss jobs (hidden from Discover and future ranking), or restore them with "
            "dismissed=false.",
            _jobs_dismiss,
            DismissIn,
            read_only=False,
        )
    )
