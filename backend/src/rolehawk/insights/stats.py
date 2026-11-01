"""Insights: the funnel, response rate by source, weekly activity, and AI spend.

A stage counts as "reached" if the application is there now or ever moved there, so a
rejection after an interview still counts the interview. A "response" is any employer
reply after applying: a screen, an interview, an offer, or a rejection."""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from rolehawk.db.models import Application, Job, LLMCall, Portal, Stage, StageEvent
from rolehawk.db.types import utcnow
from rolehawk.insights.board import ACTIVE, CLOSED, LABELS
from rolehawk.llm.meter import month_start

FUNNEL: tuple[Stage, ...] = ACTIVE
RESPONSE_STAGES = {Stage.SCREEN, Stage.INTERVIEW, Stage.OFFER, Stage.REJECTED}
WEEKS = 12


class FunnelStep(BaseModel):
    stage: Stage
    label: str
    count: int
    rate_from_previous: float | None  # 0..1


class SourceRate(BaseModel):
    source: str
    applied: int
    responses: int
    rate: float  # 0..1


class WeekCount(BaseModel):
    week_start: str  # ISO date (Monday)
    applied: int
    jobs_found: int


class SpendLine(BaseModel):
    command: str
    cost_usd: float
    calls: int


class Spend(BaseModel):
    month_to_date_usd: float
    cap_usd: float | None
    by_command: list[SpendLine]


class Totals(BaseModel):
    jobs: int
    applications: int
    active: int
    applied: int
    responses: int
    response_rate: float | None
    interviews: int
    offers: int


class Insights(BaseModel):
    generated_at: datetime
    totals: Totals
    funnel: list[FunnelStep]
    by_source: list[SourceRate]
    weekly: list[WeekCount]
    spend: Spend


def _week_start(moment: datetime) -> datetime:
    day = moment.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    return day - timedelta(days=day.weekday())


class InsightsService:
    def __init__(self, sessions: sessionmaker[Session], cap: Callable[[], float | None]) -> None:
        self._sessions = sessions
        self._cap = cap

    def insights(self, now: datetime | None = None) -> Insights:
        now = now or utcnow()
        with self._sessions() as session:
            apps = session.execute(
                select(Application.id, Application.stage, Application.applied_at, Portal.name)
                .join(Job, Job.id == Application.job_id)
                .outerjoin(Portal, Portal.id == Job.portal_id)
            ).all()
            reached: dict[int, set[Stage]] = defaultdict(set)
            for app_id, stage in session.execute(
                select(StageEvent.application_id, StageEvent.to_stage)
            ):
                reached[app_id].add(stage)
            jobs_total = session.scalar(select(func.count()).select_from(Job)) or 0
            since = _week_start(now) - timedelta(weeks=WEEKS - 1)
            found = Counter(
                _week_start(scraped).date().isoformat()
                for (scraped,) in session.execute(
                    select(Job.scraped_at).where(Job.scraped_at >= since)
                )
            )
            spend_rows = session.execute(
                select(LLMCall.command, func.sum(LLMCall.cost_usd), func.count())
                .where(LLMCall.created_at >= month_start(now))
                .group_by(LLMCall.command)
            ).all()

        order = {stage: i for i, stage in enumerate(FUNNEL)}
        furthest: dict[int, int] = {}
        responded: dict[int, bool] = {}
        for app_id, stage, applied_at, _source in apps:
            stages = reached[app_id] | {stage}
            if applied_at is not None:
                stages.add(Stage.APPLIED)
            furthest[app_id] = max((order[s] for s in stages if s in order), default=0)
            responded[app_id] = bool(stages & RESPONSE_STAGES)

        funnel: list[FunnelStep] = []
        previous: int | None = None
        for i, stage in enumerate(FUNNEL):
            count = sum(1 for f in furthest.values() if f >= i)
            funnel.append(
                FunnelStep(
                    stage=stage,
                    label=LABELS[stage.value],
                    count=count,
                    rate_from_previous=(count / previous) if previous else None,
                )
            )
            previous = count

        applied_index = order[Stage.APPLIED]
        per_source: dict[str, list[int]] = defaultdict(lambda: [0, 0])
        for app_id, _stage, _applied_at, source in apps:
            if furthest[app_id] >= applied_index or responded[app_id]:
                row = per_source[source or "Other"]
                row[0] += 1
                row[1] += int(responded[app_id])
        by_source = sorted(
            (
                SourceRate(source=name, applied=a, responses=r, rate=r / a if a else 0.0)
                for name, (a, r) in per_source.items()
            ),
            key=lambda s: (-s.rate, -s.applied, s.source),
        )

        applied_weeks = Counter(
            _week_start(applied_at).date().isoformat()
            for _id, _stage, applied_at, _source in apps
            if applied_at is not None and applied_at >= since
        )
        weekly = [
            WeekCount(
                week_start=(week := (since + timedelta(weeks=i)).date().isoformat()),
                applied=applied_weeks.get(week, 0),
                jobs_found=found.get(week, 0),
            )
            for i in range(WEEKS)
        ]

        applied_total = sum(s.applied for s in by_source)
        responses = sum(s.responses for s in by_source)
        by_command = sorted(
            (
                SpendLine(command=command, cost_usd=round(float(cost or 0), 4), calls=calls)
                for command, cost, calls in spend_rows
            ),
            key=lambda line: -line.cost_usd,
        )
        return Insights(
            generated_at=now,
            totals=Totals(
                jobs=jobs_total,
                applications=len(apps),
                active=sum(1 for _id, stage, *_ in apps if stage not in CLOSED),
                applied=applied_total,
                responses=responses,
                response_rate=(responses / applied_total) if applied_total else None,
                interviews=sum(1 for f in furthest.values() if f >= order[Stage.INTERVIEW]),
                offers=sum(1 for f in furthest.values() if f >= order[Stage.OFFER]),
            ),
            funnel=funnel,
            by_source=by_source,
            weekly=weekly,
            spend=Spend(
                month_to_date_usd=round(sum(line.cost_usd for line in by_command), 4),
                cap_usd=self._cap(),
                by_command=by_command,
            ),
        )
