"""Context packs: everything a Claude call needs to know about the candidate, plus the rows
the command works on (docs/SPEC.md "Memory strategy")."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from offerbound.db.models import Application, Job
from offerbound.llm.prompting import tagged, untrusted
from offerbound.llm.types import SystemBlock
from offerbound.memory.proposals import MemoryService, MemorySnapshot


class JobContext(BaseModel):
    id: int
    company: str
    title: str
    location: str | None
    remote: bool | None
    salary_text: str | None
    url: str
    description: str  # third-party text: rendered only inside <untrusted_content>


class ApplicationContext(BaseModel):
    id: int
    job_id: int
    stage: str
    notes: str | None


class ContextPack(BaseModel):
    command: str
    memory: MemorySnapshot
    jobs: list[JobContext] = []
    applications: list[ApplicationContext] = []

    def memory_text(self) -> str:
        """The candidate's own memory. Stable across calls, so it is cached."""
        parts = [
            tagged("profile", self.memory.profile),
            tagged("preferences", self.memory.preferences),
            tagged("facts", self.memory.facts),
        ]
        if self.memory.latest_session:
            parts.append(tagged("last_session_summary", self.memory.latest_session))
        return tagged("memory", "\n\n".join(parts))

    def memory_block(self) -> SystemBlock:
        return SystemBlock(self.memory_text(), cache=True)

    def rows_text(self) -> str | None:
        """Requested rows for the user turn. Job descriptions are untrusted."""
        if not self.jobs and not self.applications:
            return None
        parts: list[str] = []
        for job in self.jobs:
            header = (
                f"Job {job.id}: {job.title} at {job.company}"
                f" | location: {job.location or 'n/a'} | remote: {job.remote}"
                f" | salary: {job.salary_text or 'n/a'} | {job.url}"
            )
            parts.append(header + "\n" + untrusted("job_posting", job.description, job_id=job.id))
        for app in self.applications:
            parts.append(
                f"Application {app.id} for job {app.job_id}: stage {app.stage}"
                + (f"\nNotes: {app.notes}" if app.notes else "")
            )
        return "\n\n".join(parts)

    @property
    def has_untrusted(self) -> bool:
        return bool(self.jobs)

    def to_json(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


def build_context_pack(
    memory: MemoryService,
    sessions: sessionmaker[Session],
    command: str,
    *,
    job_ids: Sequence[int] = (),
    application_ids: Sequence[int] = (),
) -> ContextPack:
    with sessions() as session:
        apps = (
            list(session.scalars(select(Application).where(Application.id.in_(application_ids))))
            if application_ids
            else []
        )
        wanted_jobs = list(dict.fromkeys([*job_ids, *(a.job_id for a in apps)]))
        jobs = (
            list(session.scalars(select(Job).where(Job.id.in_(wanted_jobs)))) if wanted_jobs else []
        )
    by_id = {job.id: job for job in jobs}
    return ContextPack(
        command=command,
        memory=memory.snapshot(),
        jobs=[
            JobContext(
                id=j.id,
                company=j.company,
                title=j.title,
                location=j.location,
                remote=j.remote,
                salary_text=j.salary_text,
                url=j.url,
                description=j.description,
            )
            for j in (by_id[i] for i in wanted_jobs if i in by_id)
        ],
        applications=[
            ApplicationContext(id=a.id, job_id=a.job_id, stage=a.stage.value, notes=a.notes)
            for a in apps
        ],
    )
