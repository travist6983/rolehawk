"""Browsing and triaging scraped jobs (the Discover screen): ranked listing with filters,
detail, save to the pipeline, dismiss."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Select, delete, false, func, select, text, update
from sqlalchemy.orm import Session, sessionmaker

from offerbound.db.fts import to_match_query
from offerbound.db.models import (
    Application,
    Job,
    JobScore,
    Portal,
    Stage,
    StageEvent,
    StageEventSource,
)
from offerbound.db.types import utcnow
from offerbound.fit.rubric import Breakdown, Gates
from offerbound.portals.integrity import IntegrityView, Verdict

MAX_PAGE = 500


class JobQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    q: str | None = Field(default=None, max_length=200, description="Words in title/company/text")
    status: Literal["all", "ranked", "unranked"] = "all"
    show: Literal["active", "saved", "dismissed"] = Field(
        default="active", description="active hides dismissed jobs"
    )
    min_score: int | None = Field(default=None, ge=0, le=100)
    portal_id: str | None = None
    remote: bool = Field(default=False, description="Only jobs marked remote")
    sort: Literal["score", "newest"] = "score"
    limit: int = Field(default=100, ge=1, le=MAX_PAGE)
    offset: int = Field(default=0, ge=0)


class JobRow(BaseModel):
    model_config = ConfigDict(json_schema_serialization_defaults_required=True)

    id: int
    title: str
    company: str
    location: str | None
    remote: bool | None
    salary_text: str | None
    portal_id: str
    source: str
    url: str
    posted_at: datetime | None
    scraped_at: datetime
    score: int | None
    reasons: list[str]
    must_have_gaps: list[str]
    scored_at: datetime | None
    score_model: str | None
    breakdown: Breakdown | None = Field(description="The four parts behind the score")
    gates: Gates | None = Field(description="Eligibility and language gates, deal breaker")
    stage: Stage | None
    dismissed: bool
    integrity: Verdict = Field(description="clean, cleaned (hidden text removed), or warning")


class JobDetail(JobRow):
    description: str = Field(description="Third-party text from the posting")
    application_id: int | None
    integrity_report: IntegrityView | None = Field(
        description="What the integrity check removed or found; null when nothing"
    )


class JobStats(BaseModel):
    """Counts over every job that isn't dismissed (dismissed counted separately)."""

    jobs: int
    ranked: int
    unranked: int
    saved: int
    dismissed: int


class JobPage(BaseModel):
    items: list[JobRow]
    total: int
    stats: JobStats


class JobIds(BaseModel):
    model_config = ConfigDict(extra="forbid")
    job_ids: list[int] = Field(min_length=1, max_length=MAX_PAGE)


class DismissIn(JobIds):
    dismissed: bool = True


class SaveIn(JobIds):
    saved: bool = True


class Changed(BaseModel):
    changed: int


def _latest_scores() -> Any:
    """One row per job: its most recent score."""
    latest = (
        select(JobScore.job_id, func.max(JobScore.id).label("score_id"))
        .group_by(JobScore.job_id)
        .subquery()
    )
    return select(JobScore).join(latest, JobScore.id == latest.c.score_id).subquery("latest_score")


class JobStore:
    def __init__(self, sessions: sessionmaker[Session]) -> None:
        self._sessions = sessions

    def _base(self) -> tuple[Select[Any], Any]:
        score = _latest_scores()
        stmt = (
            select(
                Job,
                score.c.score,
                score.c.reasons,
                score.c.must_have_gaps,
                score.c.created_at,
                score.c.model,
                score.c.breakdown,
                score.c.gates,
                Application.stage,
                Application.id,
                Portal.name,
            )
            .outerjoin(score, score.c.job_id == Job.id)
            .outerjoin(Application, Application.job_id == Job.id)
            .outerjoin(Portal, Portal.id == Job.portal_id)
        )
        return stmt, score

    @staticmethod
    def _row(values: Any) -> dict[str, Any]:
        job, score, reasons, gaps, scored_at, model, breakdown, gates, stage, app_id, source = (
            values
        )
        report = IntegrityView.of(job.integrity)
        return {
            "id": job.id,
            "title": job.title,
            "company": job.company,
            "location": job.location,
            "remote": job.remote,
            "salary_text": job.salary_text,
            "portal_id": job.portal_id,
            "source": source or job.portal_id,
            "url": job.url,
            "posted_at": job.posted_at,
            "scraped_at": job.scraped_at,
            "score": score,
            "reasons": reasons or [],
            "must_have_gaps": gaps or [],
            "scored_at": scored_at,
            "score_model": model,
            "breakdown": Breakdown.model_validate(breakdown) if breakdown else None,
            "gates": Gates.model_validate(gates) if gates else None,
            "stage": stage,
            "dismissed": job.dismissed_at is not None,
            "integrity": report.verdict if report else "clean",
            "integrity_report": report,
            "description": job.description,
            "application_id": app_id,
        }

    def list(self, query: JobQuery) -> JobPage:
        stmt, score = self._base()
        if query.show == "dismissed":
            stmt = stmt.where(Job.dismissed_at.is_not(None))
        else:
            stmt = stmt.where(Job.dismissed_at.is_(None))
        if query.show == "saved":
            stmt = stmt.where(Application.id.is_not(None))
        if query.status == "ranked":
            stmt = stmt.where(score.c.score.is_not(None))
        elif query.status == "unranked":
            stmt = stmt.where(score.c.score.is_(None))
        if query.min_score is not None:
            stmt = stmt.where(score.c.score >= query.min_score)
        if query.portal_id:
            stmt = stmt.where(Job.portal_id == query.portal_id)
        if query.remote:
            stmt = stmt.where(Job.remote.is_(True))
        match = to_match_query(query.q) if query.q else None
        if query.q and match is None:
            stmt = stmt.where(false())  # punctuation only: nothing can match
        elif match:
            stmt = stmt.where(
                text("jobs.id IN (SELECT rowid FROM jobs_fts WHERE jobs_fts MATCH :match)")
            ).params(match=match)

        newest = (func.coalesce(Job.posted_at, Job.scraped_at).desc(), Job.id.desc())
        if query.sort == "score":
            stmt = stmt.order_by(score.c.score.desc().nulls_last(), *newest)
        else:
            stmt = stmt.order_by(*newest)

        with self._sessions() as session:
            total = session.scalar(select(func.count()).select_from(stmt.order_by(None).subquery()))
            rows = session.execute(stmt.limit(query.limit).offset(query.offset)).all()
            items = [JobRow.model_validate(self._row(r)) for r in rows]
            stats = self._stats(session)
        return JobPage(items=items, total=total or 0, stats=stats)

    def _stats(self, session: Session) -> JobStats:
        scored = select(JobScore.job_id).distinct().subquery()
        active = Job.dismissed_at.is_(None)
        jobs = session.scalar(select(func.count()).select_from(Job).where(active)) or 0
        ranked = (
            session.scalar(
                select(func.count()).select_from(Job).where(active, Job.id.in_(select(scored)))
            )
            or 0
        )
        saved = (
            session.scalar(
                select(func.count())
                .select_from(Application)
                .join(Job, Job.id == Application.job_id)
                .where(active)
            )
            or 0
        )
        dismissed = session.scalar(select(func.count()).select_from(Job).where(~active)) or 0
        return JobStats(
            jobs=jobs, ranked=ranked, unranked=jobs - ranked, saved=saved, dismissed=dismissed
        )

    def get(self, job_id: int) -> JobDetail:
        stmt, _ = self._base()
        with self._sessions() as session:
            row = session.execute(stmt.where(Job.id == job_id)).first()
        if row is None:
            raise KeyError(job_id)
        return JobDetail.model_validate(self._row(row))

    def set_saved(self, job_ids: Sequence[int], saved: bool = True) -> Changed:
        """Saving puts a job in the pipeline at Saved (and un-dismisses it). Unsaving only
        removes applications still at Saved; anything further along is real history."""
        changed = 0
        with self._sessions.begin() as session:
            known = set(session.scalars(select(Job.id).where(Job.id.in_(job_ids))))
            has_app = set(
                session.scalars(select(Application.job_id).where(Application.job_id.in_(known)))
            )
            if saved:
                for job_id in sorted(known - has_app):
                    app = Application(job_id=job_id, stage=Stage.SAVED)
                    session.add(app)
                    session.flush()
                    session.add(
                        StageEvent(
                            application_id=app.id,
                            from_stage=None,
                            to_stage=Stage.SAVED,
                            source=StageEventSource.USER,
                        )
                    )
                    changed += 1
                session.execute(update(Job).where(Job.id.in_(known)).values(dismissed_at=None))
            else:
                result = session.execute(
                    delete(Application).where(
                        Application.job_id.in_(known), Application.stage == Stage.SAVED
                    )
                )
                changed = int(getattr(result, "rowcount", 0) or 0)
        return Changed(changed=changed)

    def set_dismissed(self, job_ids: Sequence[int], dismissed: bool = True) -> Changed:
        """Dismissing hides a job from Discover and future ranking. Jobs already in the
        pipeline (beyond Saved) can't be dismissed; saved ones are unsaved."""
        with self._sessions.begin() as session:
            in_pipeline = set(
                session.scalars(
                    select(Application.job_id).where(
                        Application.job_id.in_(job_ids), Application.stage != Stage.SAVED
                    )
                )
            )
            ids = [i for i in job_ids if i not in in_pipeline]
            if dismissed:
                session.execute(
                    delete(Application).where(
                        Application.job_id.in_(ids), Application.stage == Stage.SAVED
                    )
                )
            result = session.execute(
                update(Job)
                .where(Job.id.in_(ids))
                .values(dismissed_at=utcnow() if dismissed else None)
            )
            return Changed(changed=int(getattr(result, "rowcount", 0) or 0))
