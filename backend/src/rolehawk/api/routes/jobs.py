from __future__ import annotations

import asyncio
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from rolehawk.api.deps import RuntimeDep
from rolehawk.api.routes.portals import TaskRef
from rolehawk.commands.runner import CommandStarted, run_command
from rolehawk.fit.ranker import RankParams, RankPlan
from rolehawk.jobs.intake import Added, IntakeError, LinkDraft, LinkIn, PostingIn
from rolehawk.jobs.store import Changed, DismissIn, JobDetail, JobPage, JobQuery, SaveIn

router = APIRouter(tags=["jobs"])


@router.get("/api/jobs")
async def list_jobs(runtime: RuntimeDep, query: Annotated[JobQuery, Query()]) -> JobPage:
    """Scraped jobs with their latest fit score (best fit first by default)."""
    return await asyncio.to_thread(runtime.jobs.list, query)


@router.post("/api/jobs")
async def add_job(body: PostingIn, runtime: RuntimeDep) -> Added:
    """Add a job the user found anywhere (LinkedIn, Indeed, a company site)."""
    return await asyncio.to_thread(runtime.intake.add, body)


@router.post("/api/jobs/read-link")
async def read_link(body: LinkIn, runtime: RuntimeDep) -> LinkDraft:
    """Read a posting page to fill in the Add a job form. Nothing is stored."""
    try:
        return await runtime.intake.read_link(body.url)
    except IntakeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None


@router.get("/api/jobs/{job_id}")
async def get_job(job_id: int, runtime: RuntimeDep) -> JobDetail:
    try:
        return await asyncio.to_thread(runtime.jobs.get, job_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Unknown job") from None


@router.post("/api/jobs/save")
async def save_jobs(body: SaveIn, runtime: RuntimeDep) -> Changed:
    return await asyncio.to_thread(runtime.jobs.set_saved, body.job_ids, body.saved)


@router.post("/api/jobs/dismiss")
async def dismiss_jobs(body: DismissIn, runtime: RuntimeDep) -> Changed:
    return await asyncio.to_thread(runtime.jobs.set_dismissed, body.job_ids, body.dismissed)


@router.post("/api/rank/plan")
async def rank_plan(runtime: RuntimeDep, body: RankParams | None = None) -> RankPlan:
    """What /rank would do and cost. Shown before the user starts it."""
    return await asyncio.to_thread(runtime.ranker.plan, body or RankParams())


@router.post("/api/rank", status_code=202)
async def rank(runtime: RuntimeDep, body: RankParams | None = None) -> TaskRef:
    """Starts ranking in the background; follow progress over /api/events."""
    spec = runtime.commands.get("rank")
    started = await run_command(runtime, spec, (body or RankParams()).model_dump())
    assert isinstance(started, CommandStarted)  # noqa: S101 - rank is a background command
    return TaskRef(task_id=started.task_id)
