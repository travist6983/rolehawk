"""/rank: hard filters, then batched structured scoring with the shared fit rubric.

Batches of up to 20 jobs go to Claude concurrently (4 at a time), so 200 jobs (10 batches)
take about three rounds of one call each. A failed batch is reported and skipped; only
problems that would fail every batch (no key, bad key, spend cap) stop the run."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Sequence
from datetime import date

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from rolehawk.db.models import Job, JobScore, SearchTarget
from rolehawk.fit.filters import FilterCounts, build_rules, candidates
from rolehawk.fit.rubric import FIT_RUBRIC, FitBatch, Gates, JobFit
from rolehawk.llm.errors import (
    LLMError,
    LLMNotConfiguredError,
    LLMOutputError,
    SpendCapExceededError,
)
from rolehawk.llm.meter import estimate_tokens
from rolehawk.llm.prompting import untrusted
from rolehawk.llm.service import LLMService
from rolehawk.llm.types import Message, SystemBlock, Task
from rolehawk.memory.context import ContextPack
from rolehawk.memory.proposals import MemoryService
from rolehawk.profile.model import Preferences

log = logging.getLogger(__name__)

BATCH_SIZE = 20
CONCURRENCY = 4
MAX_JOBS_PER_RUN = 1_000
DESCRIPTION_CHARS = 5_000  # per job; postings rarely put requirements past this
OUTPUT_TOKENS_PER_JOB = 320  # four parts, two gates with quotes, reasons, concerns, gaps

Progress = Callable[[float | None, str | None], Awaitable[None]]


class RankParams(BaseModel):
    job_ids: list[int] | None = Field(
        default=None, max_length=MAX_JOBS_PER_RUN, description="Only these jobs (default: all)"
    )
    rescore: bool = Field(default=False, description="Score jobs again even if already ranked")


class RankPlan(BaseModel):
    """What a run would do, shown before it starts."""

    candidates: int
    remaining: int = Field(description="Matching jobs beyond this run's limit")
    filtered: FilterCounts
    batches: int
    model: str
    estimated_cost_usd: float
    month_to_date_usd: float
    cap_usd: float | None
    exceeds_cap: bool
    configured: bool


class RankedJob(BaseModel):
    job_id: int
    title: str
    company: str
    score: int


class RankSummary(BaseModel):
    ranked: int
    failed: int
    remaining: int
    filtered: FilterCounts
    model: str | None
    top: list[RankedJob]
    errors: list[str]


class NothingToRankError(ValueError):
    user_message = "No new jobs to rank. Run a search first, or rank again to rescore."


def job_text(job: Job) -> str:
    header = (
        f"Job {job.id}: {job.title} at {job.company}"
        f" | location: {job.location or 'not stated'}"
        f" | remote: {'yes' if job.remote else 'not stated'}"
        f" | salary: {job.salary_text or 'not stated'}"
    )
    description = job.description[:DESCRIPTION_CHARS]
    if len(job.description) > DESCRIPTION_CHARS:
        description += "\n[posting truncated]"
    return header + "\n" + untrusted("job_posting", description, job_id=job.id)


def batch_prompt(jobs: Sequence[Job]) -> str:
    listing = "\n\n".join(job_text(job) for job in jobs)
    return (
        f"Score these {len(jobs)} jobs for me with the rubric. Return exactly one entry per "
        "job, using the job ids given.\n\n" + listing
    )


class Ranker:
    def __init__(
        self,
        sessions: sessionmaker[Session],
        llm: LLMService,
        memory: MemoryService,
        preferences: Callable[[], Preferences],
    ) -> None:
        self._sessions = sessions
        self._llm = llm
        self._memory = memory
        self._preferences = preferences

    # --- planning -----------------------------------------------------------------------

    def select(self, params: RankParams) -> tuple[list[Job], FilterCounts, int]:
        prefs = self._preferences()
        with self._sessions() as session:
            active = select(SearchTarget).where(SearchTarget.active.is_(True))
            rules = build_rules(list(session.scalars(active)), prefs)
            jobs, counts = candidates(
                session, rules, job_ids=params.job_ids, rescore=params.rescore
            )
        return jobs[:MAX_JOBS_PER_RUN], counts, max(len(jobs) - MAX_JOBS_PER_RUN, 0)

    @staticmethod
    def job_payload(job: Job) -> dict[str, object]:
        """A job as data for scoring outside the app. The description is third-party text."""
        return {
            "job_id": job.id,
            "title": job.title,
            "company": job.company,
            "location": job.location,
            "remote": job.remote,
            "salary_text": job.salary_text,
            "url": job.url,
            "description": job.description[:DESCRIPTION_CHARS],
        }

    def _system(self) -> list[SystemBlock]:
        pack = ContextPack(command="rank", memory=self._memory.snapshot())
        # Rubric then memory: both stable across batches, cached after the first call.
        return [SystemBlock(FIT_RUBRIC), pack.memory_block()]

    def plan(self, params: RankParams) -> RankPlan:
        jobs, counts, remaining = self.select(params)
        batches = [jobs[i : i + BATCH_SIZE] for i in range(0, len(jobs), BATCH_SIZE)]
        system_tokens = sum(estimate_tokens(b.text) for b in self._system())
        input_tokens = sum(system_tokens + estimate_tokens(batch_prompt(b)) for b in batches)
        output_tokens = OUTPUT_TOKENS_PER_JOB * len(jobs)
        calls = max(len(batches), 1)
        estimate = self._llm.estimate(
            Task.RANK,
            input_tokens=input_tokens // calls,
            output_tokens=output_tokens // calls,
            calls=len(batches),
        )
        return RankPlan(
            candidates=len(jobs),
            remaining=remaining,
            filtered=counts,
            batches=len(batches),
            model=estimate.model,
            estimated_cost_usd=estimate.cost_usd,
            month_to_date_usd=estimate.month_to_date_usd,
            cap_usd=estimate.cap_usd,
            exceeds_cap=estimate.exceeds_cap,
            configured=self._llm.configured,
        )

    # --- running ------------------------------------------------------------------------

    async def run(
        self, params: RankParams, progress: Progress, task_id: str | None = None
    ) -> RankSummary:
        jobs, counts, remaining = await asyncio.to_thread(self.select, params)
        if not jobs:
            raise NothingToRankError("no candidates")
        if not self._llm.configured:
            raise LLMNotConfiguredError("ranking needs Claude")
        plan = await asyncio.to_thread(self.plan, params)
        if plan.exceeds_cap and plan.cap_usd is not None:
            raise SpendCapExceededError(plan.month_to_date_usd, plan.cap_usd)

        system = self._system()
        batches = [jobs[i : i + BATCH_SIZE] for i in range(0, len(jobs), BATCH_SIZE)]
        slots = asyncio.Semaphore(CONCURRENCY)
        scored: list[tuple[JobFit, str]] = []
        errors: list[str] = []
        failed = 0
        done = 0
        await progress(0.0, f"Ranking {len(jobs)} jobs in {len(batches)} batches")

        async def one(batch: list[Job]) -> None:
            nonlocal failed, done
            async with slots:
                try:
                    fits, model = await self._score(batch, system, task_id)
                except (LLMNotConfiguredError, SpendCapExceededError):
                    raise  # every other batch would fail the same way
                except LLMError as exc:
                    log.warning("rank batch failed: %s", exc)
                    errors.append(exc.user_message)
                    failed += len(batch)
                else:
                    await asyncio.to_thread(self._store, fits, model, task_id)
                    scored.extend((fit, model) for fit in fits)
                    failed += len(batch) - len(fits)
            done += len(batch)
            await progress(done / len(jobs), f"Ranked {done} of {len(jobs)} jobs")

        await asyncio.gather(*(one(b) for b in batches))

        by_id = {job.id: job for job in jobs}
        best = sorted(scored, key=lambda pair: pair[0].score, reverse=True)[:5]
        return RankSummary(
            ranked=len(scored),
            failed=failed,
            remaining=remaining,
            filtered=counts,
            model=scored[0][1] if scored else None,
            top=[
                RankedJob(
                    job_id=fit.job_id,
                    title=by_id[fit.job_id].title,
                    company=by_id[fit.job_id].company,
                    score=fit.score,
                )
                for fit, _ in best
            ],
            errors=list(dict.fromkeys(errors)),
        )

    async def _score(
        self, batch: list[Job], system: list[SystemBlock], task_id: str | None
    ) -> tuple[list[JobFit], str]:
        result = await self._llm.structured_result(
            command="rank",
            task=Task.RANK,
            system=system,
            messages=[Message(role="user", text=batch_prompt(batch))],
            schema=FitBatch,
            task_id=task_id,
        )
        wanted = {job.id for job in batch}
        fits: dict[int, JobFit] = {}
        for fit in result.value.jobs:
            if fit.job_id in wanted and fit.job_id not in fits:  # ignore unknown or repeated ids
                fits[fit.job_id] = fit.clamped()
        return list(fits.values()), result.model

    def _store(self, fits: list[JobFit], model: str, task_id: str | None) -> None:
        with self._sessions.begin() as session:
            for fit in fits:
                job = session.get(Job, fit.job_id)
                if job is not None and job.closes_at is None and fit.deadline:
                    job.closes_at = date.fromisoformat(fit.deadline)  # the source's date wins
                session.add(
                    JobScore(
                        job_id=fit.job_id,
                        run_id=task_id,
                        score=fit.score,
                        reasons=fit.reasons,
                        concerns=fit.concerns,
                        must_have_gaps=fit.must_have_gaps,
                        breakdown=fit.breakdown.model_dump(),
                        gates=Gates.of(fit).model_dump(),
                        model=model,
                    )
                )

    async def score_one(self, job_id: int, task_id: str | None = None) -> JobFit:
        """Score a single job now (the /apply fit gate), with the same rubric as /rank."""
        with self._sessions() as session:
            job = session.get(Job, job_id)
        if job is None:
            raise KeyError(job_id)
        fits, model = await self._score([job], self._system(), task_id)
        if not fits:
            raise LLMOutputError("the fit check returned no score")
        await asyncio.to_thread(self._store, fits, model, task_id)
        return fits[0]

    # --- scores from elsewhere (Claude Code skills) -------------------------------------

    def save_external(self, fits: Sequence[JobFit], model: str) -> int:
        """Scores computed outside the app (the /rank skill in Claude Code). Unknown job
        ids are ignored."""
        clean = {f.job_id: f.clamped() for f in fits}
        with self._sessions() as session:
            known = set(session.scalars(select(Job.id).where(Job.id.in_(clean))))
        self._store([f for i, f in clean.items() if i in known], model, None)
        return len(known)
