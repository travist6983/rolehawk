"""Following up on quiet applications, and closing ones that never got a reply.

The usual practice is a short, polite note one to two weeks after applying, at most twice.
`quiet()` lists applications that qualify; `draft()` writes a 60-120 word note whose every
claim comes from what the user actually sent (the CV and cover letter on file), never from
the wider profile: a follow-up that introduces new claims is a fabrication vector. It's a
draft only; nothing is ever sent. `log()` records one the user sent, so the quiet-days clock
restarts and a third is never suggested.

`stale()` lists applications quiet for 60+ days (two follow-ups or not), and `close_stale()`
moves the ones the user picks to Ghosted, which keeps the funnel honest. No cutoff is
imposed: the user decides.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from rolehawk.apply.style import CLICHES, plain_dashes
from rolehawk.apply.truth import numbers_missing_from
from rolehawk.db.models import (
    Application,
    FollowUp,
    FollowUpChannel,
    Job,
    Stage,
    StageEvent,
    StageEventSource,
)
from rolehawk.db.types import utcnow
from rolehawk.llm.prompting import UNTRUSTED_RULES, tagged, untrusted
from rolehawk.llm.service import LLMService
from rolehawk.llm.types import Message, SystemBlock, Task
from rolehawk.rendering.model import CoverLetter, CvDocument

FOLLOW_UP_DAYS = 10
MAX_FOLLOW_UPS = 2
STALE_DAYS = 60
WAITING: tuple[Stage, ...] = (Stage.APPLIED, Stage.SCREEN, Stage.INTERVIEW)
Channel = FollowUpChannel

FOLLOW_UP_RULES = f"""You write one short follow-up note for a job application that has gone
quiet. The candidate sends it themselves; you only draft it.

- 60 to 120 words. Greet the contact the user names, or the hiring team.
- One sentence restating interest in this specific role. One concrete reminder of value,
  taken from the documents they already sent. One polite question about the timeline.
- Use only what's in <sent_documents>: no new skills, experience, or numbers. A follow-up
  that adds claims the application didn't make reads as invented.
- Warm but direct. No pressure, no guilt, no "just checking in" or "touching base", no
  clichés, no em dashes.
- Match the cover letter's language and register.
- email: include a short subject line reusing the role title. linkedin: shorter, no
  subject. portal: plain text, no subject.

{UNTRUSTED_RULES}"""


class FollowUpDraftOut(BaseModel):
    subject: str = Field(description="Email subject line; empty for LinkedIn and portals")
    body: str = Field(description="The note, 60-120 words")


class QuietApplication(BaseModel):
    model_config = ConfigDict(json_schema_serialization_defaults_required=True)

    application_id: int
    job_id: int
    title: str
    company: str
    stage: Stage
    applied_at: datetime | None
    quiet_days: int
    follow_ups: int
    last_follow_up_at: datetime | None


class FollowUpIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    channel: Channel = FollowUpChannel.EMAIL
    subject: str | None = Field(default=None, max_length=300)
    body: str = Field(min_length=1, max_length=5_000)


class FollowUpDraft(BaseModel):
    channel: Channel
    subject: str | None
    body: str
    issues: list[str] = Field(description="Claims or phrases worth a second look before sending")


class FollowUpView(BaseModel):
    id: int
    application_id: int
    channel: Channel
    subject: str | None
    body: str
    sent_at: datetime


class CloseStaleIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    application_ids: list[int] = Field(min_length=1, max_length=200)


class ClosedStale(BaseModel):
    closed: int


class FollowUpLimitError(ValueError):
    user_message = (
        f"You've already sent {MAX_FOLLOW_UPS} follow-ups for this application. If it stays "
        "quiet, consider closing it as no response."
    )


class NotWaitingError(ValueError):
    user_message = "Follow-ups are for applications you've sent and are waiting on."


class NoDocumentsError(ValueError):
    user_message = "This application has no CV or cover letter on file to draw from."


BundleDocs = Callable[[int], tuple[CvDocument, CoverLetter] | None]


class FollowUpService:
    def __init__(
        self, sessions: sessionmaker[Session], llm: LLMService, documents: BundleDocs
    ) -> None:
        self._sessions = sessions
        self._llm = llm
        self._documents = documents

    # --- who's quiet --------------------------------------------------------------------

    def _rows(self, session: Session) -> list[QuietApplication]:
        counts = (
            select(
                FollowUp.application_id,
                func.count(FollowUp.id).label("n"),
                func.max(FollowUp.sent_at).label("last"),
            )
            .group_by(FollowUp.application_id)
            .subquery()
        )
        stmt = (
            select(Application, Job, counts.c.n, counts.c.last)
            .join(Job, Job.id == Application.job_id)
            .outerjoin(counts, counts.c.application_id == Application.id)
            .where(Application.stage.in_(WAITING))
        )
        now = utcnow()
        rows: list[QuietApplication] = []
        for app, job, n, last in session.execute(stmt).all():
            since = max(d for d in (app.applied_at, app.stage_changed_at, last) if d is not None)
            rows.append(
                QuietApplication(
                    application_id=app.id,
                    job_id=job.id,
                    title=job.title,
                    company=job.company,
                    stage=app.stage,
                    applied_at=app.applied_at,
                    quiet_days=max((now - since).days, 0),
                    follow_ups=n or 0,
                    last_follow_up_at=last,
                )
            )
        return sorted(rows, key=lambda r: r.quiet_days, reverse=True)

    def quiet(self, days: int = FOLLOW_UP_DAYS) -> list[QuietApplication]:
        """Waiting applications quiet for `days` with fewer than two follow-ups sent."""
        with self._sessions() as session:
            rows = self._rows(session)
        return [r for r in rows if r.quiet_days >= days and r.follow_ups < MAX_FOLLOW_UPS]

    def stale(self, days: int = STALE_DAYS) -> list[QuietApplication]:
        with self._sessions() as session:
            rows = self._rows(session)
        return [r for r in rows if r.quiet_days >= days]

    def history(self, application_id: int) -> list[FollowUpView]:
        with self._sessions() as session:
            rows = session.scalars(
                select(FollowUp)
                .where(FollowUp.application_id == application_id)
                .order_by(FollowUp.sent_at)
            ).all()
            return [_view(f) for f in rows]

    # --- drafting -----------------------------------------------------------------------

    def _waiting(self, session: Session, application_id: int) -> tuple[Application, Job, int]:
        app = session.get(Application, application_id)
        if app is None:
            raise KeyError(application_id)
        if app.stage not in WAITING:
            raise NotWaitingError(app.stage.value)
        sent = (
            session.scalar(
                select(func.count(FollowUp.id)).where(FollowUp.application_id == application_id)
            )
            or 0
        )
        job = session.get(Job, app.job_id)
        assert job is not None  # noqa: S101 - applications.job_id is a RESTRICT foreign key
        return app, job, sent

    async def draft(
        self,
        application_id: int,
        channel: Channel = FollowUpChannel.EMAIL,
        task_id: str | None = None,
    ) -> FollowUpDraft:
        with self._sessions() as session:
            _app, job, sent = self._waiting(session, application_id)
            title, company = job.title, job.company
        if sent >= MAX_FOLLOW_UPS:
            raise FollowUpLimitError(application_id)
        docs = self._documents(application_id)
        if docs is None:
            raise NoDocumentsError(application_id)
        cv, letter = docs
        sent_text = _sent_text(cv, letter)
        prompt = (
            untrusted("job", f"{title} at {company}")
            + "\n\n"
            + tagged("sent_documents", sent_text)
            + f"\n\nChannel: {channel.value}. This is follow-up {sent + 1} of at most "
            f"{MAX_FOLLOW_UPS}."
            " Write the note."
        )
        out = await self._llm.structured(
            command="followup-draft",
            task=Task.WRITE,
            system=[SystemBlock(FOLLOW_UP_RULES)],
            messages=[Message(role="user", text=prompt)],
            schema=FollowUpDraftOut,
            task_id=task_id,
        )
        body = plain_dashes(out.body.strip())
        subject = plain_dashes(out.subject.strip()) if channel is FollowUpChannel.EMAIL else ""
        return FollowUpDraft(
            channel=channel,
            subject=subject or None,
            body=body,
            issues=_issues(body, sent_text),
        )

    def log(self, application_id: int, note: FollowUpIn) -> FollowUpView:
        """Record a follow-up the user sent (they confirm; the app never sends anything)."""
        with self._sessions.begin() as session:
            _app, _job, sent = self._waiting(session, application_id)
            if sent >= MAX_FOLLOW_UPS:
                raise FollowUpLimitError(application_id)
            row = FollowUp(
                application_id=application_id,
                channel=note.channel,
                subject=(note.subject or "").strip() or None,
                body=note.body.strip(),
                sent_at=utcnow(),
            )
            session.add(row)
            session.flush()
            return _view(row)

    # --- closing --------------------------------------------------------------------

    def close_stale(self, application_ids: Sequence[int], days: int = STALE_DAYS) -> ClosedStale:
        """Move the chosen quiet applications to Ghosted (only ones still quiet for `days`)."""
        eligible = {r.application_id: r for r in self.stale(days)}
        closed = 0
        now = utcnow()
        with self._sessions.begin() as session:
            for app_id in dict.fromkeys(application_ids):
                row = eligible.get(app_id)
                app = session.get(Application, app_id)
                if row is None or app is None:
                    continue
                session.add(
                    StageEvent(
                        application_id=app.id,
                        from_stage=app.stage,
                        to_stage=Stage.GHOSTED,
                        source=StageEventSource.USER,
                        evidence=f"No reply in {row.quiet_days} days "
                        f"({row.follow_ups} follow-up{'s' if row.follow_ups != 1 else ''} sent)",
                    )
                )
                app.stage = Stage.GHOSTED
                app.stage_changed_at = now
                closed += 1
        return ClosedStale(closed=closed)


def _view(row: FollowUp) -> FollowUpView:
    return FollowUpView(
        id=row.id,
        application_id=row.application_id,
        channel=row.channel,
        subject=row.subject,
        body=row.body,
        sent_at=row.sent_at,
    )


def _sent_text(cv: CvDocument, letter: CoverLetter) -> str:
    lines = [f"Cover letter:\n{letter.greeting}", *letter.paragraphs, ""]
    lines += ["CV:", cv.headline or "", cv.summary or ""]
    for role in cv.experience:
        lines.append(f"{role.title}, {role.organization or ''}".strip(", "))
        lines += [f"- {b}" for b in role.bullets]
    if cv.skills:
        lines.append("Skills: " + ", ".join(cv.skills))
    return "\n".join(line for line in lines if line)


_FILLER = re.compile(
    r"\b(?:just checking in|touching base|circling back|following up again)\b", re.I
)


def _issues(body: str, sent: str) -> list[str]:
    """Numbers the sent documents don't contain, clichés, and filler, for a look first."""
    issues: list[str] = []
    new = numbers_missing_from(body, sent)
    if new:
        issues.append(f"{', '.join(new)} isn't in the documents you sent")
    lowered = body.casefold()
    issues += [f'"{c}" is a cliché' for c in CLICHES if c in lowered]
    if _FILLER.search(body):
        issues.append('It has filler like "just checking in"')
    words = len(body.split())
    if words > 140:
        issues.append(f"It's {words} words; aim for under 120")
    return issues
