"""Learn from results: which kinds of jobs got interviews, and which went nowhere.

Once a few applications are resolved, Claude compares the ones that reached a screen,
interview, or offer with the ones that were rejected or never answered, using what RoleHawk
already knows about each (the fit score and its parts, reasons, gaps, source, and how long
the reply took). It returns the patterns it sees and suggested edits to preferences.md, and
those edits are memory proposals: nothing changes until the user accepts each one. Ranking
reads preferences, so accepted edits calibrate every future score.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from rolehawk.db.models import (
    Application,
    Job,
    JobScore,
    Portal,
    ProposalOp,
    Stage,
    StageEvent,
)
from rolehawk.db.types import utcnow
from rolehawk.llm.prompting import TRUTHFULNESS_RULES, UNTRUSTED_RULES, untrusted
from rolehawk.llm.service import LLMService
from rolehawk.llm.types import Message, SystemBlock, Task
from rolehawk.memory.context import ContextPack
from rolehawk.memory.files import MemoryTarget
from rolehawk.memory.proposals import MemoryService, ProposalIn, ProposalView

MIN_RESOLVED = 3
POSITIVE: tuple[Stage, ...] = (Stage.SCREEN, Stage.INTERVIEW, Stage.OFFER)
NEGATIVE: tuple[Stage, ...] = (Stage.REJECTED, Stage.GHOSTED)
Result = Literal["interview", "offer", "rejected", "no reply"]

CALIBRATION_RULES = f"""You help one job seeker learn from their own results. You get their
memory (profile and preferences) and their resolved applications: the ones that reached a
screen, interview, or offer, and the ones rejected or never answered, with each job's fit
score, the score's parts, the reasons and gaps found when it was ranked, the source, and how
long a reply took.

Find patterns that would change which jobs they should go after. Only patterns the data
supports: say how many applications show each one and cite their ids. With a handful of
applications, prefer "worth watching" over firm rules, and say so.

Then suggest edits to preferences.md that encode the strongest patterns, for example a target
title to add, a deal breaker the rejections share, or a seniority that keeps getting
interviews. One fact per edit, quoting existing lines exactly for replace and remove. No more
than 4. Never edit the profile's facts, and suggest nothing when the data is too thin.

{TRUTHFULNESS_RULES}

{UNTRUSTED_RULES}"""


class Finding(BaseModel):
    pattern: str = Field(description="One sentence, written to the job seeker")
    application_ids: list[int] = Field(description="The applications that show it")
    strength: Literal["firm", "worth watching"]


class PreferenceEdit(BaseModel):
    op: ProposalOp = Field(description="add, replace, or remove")
    section: str | None = Field(description="Heading for add, e.g. 'Target titles'; else null")
    text: str | None = Field(description="New text for add/replace; else null")
    old_text: str | None = Field(description="Exact existing line for replace/remove; else null")
    reason: str = Field(description="One sentence citing the pattern")


class CalibrationOut(BaseModel):
    findings: list[Finding]
    edits: list[PreferenceEdit]


class ResolvedApplication(BaseModel):
    application_id: int
    title: str
    company: str
    source: str
    result: Result
    fit_score: int | None
    breakdown: dict[str, int] | None
    reasons: list[str]
    concerns: list[str]
    gaps: list[str]
    days_to_reply: int | None


class CalibrationStatus(BaseModel):
    resolved: int
    positive: int
    negative: int
    needed: int = Field(description="Results needed before patterns mean much")
    ready: bool


class CalibrationResult(BaseModel):
    findings: list[Finding]
    proposals: list[ProposalView]
    resolved: int
    ran_at: datetime


class NotEnoughResultsError(ValueError):
    user_message = (
        f"Calibration needs at least {MIN_RESOLVED} applications that reached an interview, "
        "were rejected, or got no reply."
    )


class CalibrationService:
    def __init__(
        self, sessions: sessionmaker[Session], llm: LLMService, memory: MemoryService
    ) -> None:
        self._sessions = sessions
        self._llm = llm
        self._memory = memory

    def resolved(self) -> list[ResolvedApplication]:
        """Applications with a result: reached a screen or later (ever), or closed without."""
        latest = (
            select(JobScore.job_id, func.max(JobScore.id).label("score_id"))
            .group_by(JobScore.job_id)
            .subquery()
        )
        stmt = (
            select(Application, Job, Portal.name, JobScore)
            .join(Job, Job.id == Application.job_id)
            .outerjoin(Portal, Portal.id == Job.portal_id)
            .outerjoin(latest, latest.c.job_id == Job.id)
            .outerjoin(JobScore, JobScore.id == latest.c.score_id)
            .order_by(Application.id)
        )
        out: list[ResolvedApplication] = []
        with self._sessions() as session:
            for app, job, source, score in session.execute(stmt).all():
                events = session.scalars(
                    select(StageEvent)
                    .where(StageEvent.application_id == app.id)
                    .order_by(StageEvent.created_at)
                ).all()
                reached = [e for e in events if e.to_stage in POSITIVE]
                result: Result | None
                if app.stage is Stage.OFFER or any(e.to_stage is Stage.OFFER for e in events):
                    result = "offer"
                elif app.stage in POSITIVE or reached:
                    result = "interview"
                elif app.stage is Stage.REJECTED:
                    result = "rejected"
                elif app.stage is Stage.GHOSTED:
                    result = "no reply"
                else:
                    result = None
                if result is None:
                    continue
                reply = reached[0].created_at if reached else None
                if reply is None and app.stage is Stage.REJECTED:
                    reply = app.stage_changed_at
                days = (reply - app.applied_at).days if reply and app.applied_at else None
                out.append(
                    ResolvedApplication(
                        application_id=app.id,
                        title=job.title,
                        company=job.company,
                        source=source or job.portal_id,
                        result=result,
                        fit_score=score.score if score else None,
                        breakdown=score.breakdown if score else None,
                        reasons=list(score.reasons) if score else [],
                        concerns=list(score.concerns or []) if score else [],
                        gaps=list(score.must_have_gaps) if score else [],
                        days_to_reply=max(days, 0) if days is not None else None,
                    )
                )
        return out

    def status(self) -> CalibrationStatus:
        rows = self.resolved()
        positive = sum(1 for r in rows if r.result in ("interview", "offer"))
        return CalibrationStatus(
            resolved=len(rows),
            positive=positive,
            negative=len(rows) - positive,
            needed=MIN_RESOLVED,
            ready=len(rows) >= MIN_RESOLVED,
        )

    async def run(self, task_id: str | None = None) -> CalibrationResult:
        rows = self.resolved()
        if len(rows) < MIN_RESOLVED:
            raise NotEnoughResultsError(len(rows))
        listing = "\n\n".join(_describe(r) for r in rows)
        pack = ContextPack(command="calibrate", memory=self._memory.snapshot())
        out = await self._llm.structured(
            command="calibrate",
            task=Task.REVIEW,
            system=[SystemBlock(CALIBRATION_RULES), pack.memory_block()],
            messages=[
                Message(
                    role="user",
                    text=untrusted("resolved_applications", listing)
                    + "\n\nWhat do my results say, and what should change in my preferences?",
                )
            ],
            schema=CalibrationOut,
            task_id=task_id,
        )
        known = {r.application_id for r in rows}
        findings = [
            f.model_copy(update={"application_ids": [i for i in f.application_ids if i in known]})
            for f in out.findings
            if f.pattern.strip()
        ][:6]
        proposals: list[ProposalView] = []
        for edit in out.edits[:4]:
            try:
                proposal = ProposalIn(
                    target=MemoryTarget.PREFERENCES,
                    op=edit.op,
                    section=edit.section,
                    text=edit.text,
                    old_text=edit.old_text,
                    reason=edit.reason,
                )
            except ValueError:
                continue  # an edit missing its text or old line: skip it, don't guess
            proposals.append(self._memory.propose(proposal, source="calibration"))
        return CalibrationResult(
            findings=findings, proposals=proposals, resolved=len(rows), ran_at=utcnow()
        )


def _describe(r: ResolvedApplication) -> str:
    parts = ", ".join(f"{k} {v}" for k, v in (r.breakdown or {}).items())
    lines = [
        f"Application {r.application_id}: {r.title} at {r.company} (via {r.source})",
        f"Result: {r.result}"
        + (f" after {r.days_to_reply} days" if r.days_to_reply is not None else ""),
        f"Fit score: {r.fit_score if r.fit_score is not None else 'not ranked'}"
        + (f" ({parts})" if parts else ""),
    ]
    if r.reasons:
        lines.append("Reasons: " + "; ".join(r.reasons))
    if r.concerns:
        lines.append("Concerns: " + "; ".join(r.concerns))
    if r.gaps:
        lines.append("Gaps: " + "; ".join(r.gaps))
    return "\n".join(lines)
