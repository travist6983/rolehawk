"""The Pipeline board: applications by stage, with what to do next."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import date, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from offerbound.db.models import Application, Job, JobScore, Portal, Stage
from offerbound.db.types import utcnow
from offerbound.jobs.store import CLOSING_SOON_DAYS

ACTIVE: tuple[Stage, ...] = (
    Stage.SAVED,
    Stage.APPLYING,
    Stage.APPLIED,
    Stage.SCREEN,
    Stage.INTERVIEW,
    Stage.OFFER,
)
CLOSED: tuple[Stage, ...] = (Stage.REJECTED, Stage.WITHDRAWN, Stage.GHOSTED)
FOLLOW_UP_DAYS = 7


class Card(BaseModel):
    model_config = ConfigDict(json_schema_serialization_defaults_required=True)

    application_id: int
    job_id: int
    title: str
    company: str
    location: str | None
    source: str
    stage: Stage
    score: int | None
    days_in_stage: int
    applied_at: datetime | None
    has_documents: bool
    flags: int
    closes_at: date | None
    next_action: str | None


class Column(BaseModel):
    id: str  # a stage, or "closed"
    label: str
    stages: list[Stage]
    cards: list[Card]


class Board(BaseModel):
    columns: list[Column]
    total: int


LABELS = {
    "saved": "Saved",
    "applying": "Applying",
    "applied": "Applied",
    "screen": "Screen",
    "interview": "Interview",
    "offer": "Offer",
    "closed": "Closed",
}


def _day(value: date) -> str:
    return f"{value:%b} {value.day}"


def next_action(
    stage: Stage,
    days: int,
    has_documents: bool,
    flags: int,
    closes_at: date | None = None,
    today: date | None = None,
) -> str | None:
    if stage in (Stage.SAVED, Stage.APPLYING) and closes_at and today:
        if closes_at < today:
            return f"The posting closed {_day(closes_at)}: check it's still open"
        before = f" by {_day(closes_at)}" if (closes_at - today).days <= CLOSING_SOON_DAYS else ""
    else:
        before = ""
    if stage is Stage.SAVED:
        return f"Write your application{before}"
    if stage is Stage.APPLYING:
        if not has_documents:
            return f"Write your CV and cover letter{before}"
        if flags:
            return f"Check {flags} flagged line{'s' if flags != 1 else ''}, then submit{before}"
        return f"Submit{before}, then mark as applied"
    if stage is Stage.APPLIED:
        return "Send a follow-up" if days >= FOLLOW_UP_DAYS else "Wait for a reply"
    if stage is Stage.SCREEN:
        return "Prepare for the screen"
    if stage is Stage.INTERVIEW:
        return "Prepare for interviews"
    if stage is Stage.OFFER:
        return "Review the offer"
    return None


class BoardService:
    def __init__(self, sessions: sessionmaker[Session], bundle_path: Callable[[int], Path]) -> None:
        self._sessions = sessions
        self._bundle_path = bundle_path

    def _documents(self, application_id: int) -> tuple[bool, int]:
        path = self._bundle_path(application_id)
        if not path.is_file():
            return False, 0
        try:
            flags = json.loads(path.read_text(encoding="utf-8")).get("flags", [])
        except (OSError, ValueError):
            return True, 0
        return True, len(flags) if isinstance(flags, list) else 0

    def board(self) -> Board:
        latest = (
            select(JobScore.score)
            .where(JobScore.job_id == Job.id)
            .order_by(JobScore.id.desc())
            .limit(1)
            .scalar_subquery()
        )
        stmt = (
            select(Application, Job, Portal.name, latest)
            .join(Job, Job.id == Application.job_id)
            .outerjoin(Portal, Portal.id == Job.portal_id)
            .order_by(Application.stage_changed_at.desc(), Application.id.desc())
        )
        now = utcnow()
        cards: list[Card] = []
        with self._sessions() as session:
            for app, job, source, score in session.execute(stmt).all():
                has_documents, flags = self._documents(app.id)
                days = max((now - app.stage_changed_at).days, 0)
                cards.append(
                    Card(
                        application_id=app.id,
                        job_id=job.id,
                        title=job.title,
                        company=job.company,
                        location=job.location,
                        source=source or job.portal_id,
                        stage=app.stage,
                        score=score,
                        days_in_stage=days,
                        applied_at=app.applied_at,
                        has_documents=has_documents,
                        flags=flags,
                        closes_at=job.closes_at,
                        next_action=next_action(
                            app.stage, days, has_documents, flags, job.closes_at, now.date()
                        ),
                    )
                )
        columns = [
            Column(
                id=stage.value,
                label=LABELS[stage.value],
                stages=[stage],
                cards=[c for c in cards if c.stage is stage],
            )
            for stage in ACTIVE
        ]
        columns.append(
            Column(
                id="closed",
                label=LABELS["closed"],
                stages=list(CLOSED),
                cards=[c for c in cards if c.stage in CLOSED],
            )
        )
        return Board(columns=columns, total=len(cards))
