"""/reset: clear part (or all) of the user's data, after a zipped backup.

The user types the scope's name to confirm. Settings (config.toml), API keys in the
keychain, job source settings, and backups are never touched. Jobs that have an
application are kept by "jobs and scores": the application history needs them."""

from __future__ import annotations

import shutil
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, exists, update
from sqlalchemy.orm import Session, sessionmaker

from offerbound.db.models import (
    Application,
    AppState,
    ChatSession,
    Company,
    Job,
    JobScore,
    LLMCall,
    MemoryProposal,
    ProfileItem,
    SearchTarget,
    SourceDocument,
    Task,
    TaskStatus,
)
from offerbound.memory.files import TEMPLATES, MemoryFiles, MemoryTarget
from offerbound.paths import DataPaths
from offerbound.portals.state import PortalStore
from offerbound.services.backup import create_backup


class ResetScope(StrEnum):
    PROFILE = "profile"
    DOCUMENTS = "documents"
    JOBS = "jobs"
    APPLICATIONS = "applications"
    EVERYTHING = "everything"


SCOPES: dict[ResetScope, tuple[str, str]] = {
    ResetScope.PROFILE: (
        "Profile only",
        "profile.md, preferences.md, facts.md, search targets, imported documents, and "
        "pending memory proposals.",
    ),
    ResetScope.DOCUMENTS: (
        "Documents only",
        "Uploaded resumes and every generated CV and cover letter.",
    ),
    ResetScope.JOBS: (
        "Jobs and scores",
        "Scraped jobs and fit scores. Jobs you applied to are kept.",
    ),
    ResetScope.APPLICATIONS: (
        "Application history",
        "Every application, its stage history, and its documents.",
    ),
    ResetScope.EVERYTHING: (
        "Everything",
        "All of the above plus chat history, task history, AI spend history, and reports. "
        "Settings, API keys, and backups stay.",
    ),
}


class ResetIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scope: ResetScope
    confirm: str = Field(description="Must be the scope's name, e.g. 'profile'")


class ResetResult(BaseModel):
    scope: ResetScope
    backup: str
    removed: dict[str, int]


class ScopeView(BaseModel):
    id: ResetScope
    label: str
    description: str


class ConfirmationError(ValueError):
    pass


def scopes() -> list[ScopeView]:
    return [ScopeView(id=s, label=label, description=d) for s, (label, d) in SCOPES.items()]


def _clear_folder(folder: Path) -> int:
    """Delete everything inside `folder` (not the folder). Returns files removed."""
    if not folder.is_dir():
        return 0
    removed = 0
    for child in folder.iterdir():
        if child.is_dir():
            removed += sum(1 for f in child.rglob("*") if f.is_file())
            shutil.rmtree(child)
        else:
            child.unlink()
            removed += 1
    return removed


class ResetService:
    def __init__(
        self,
        paths: DataPaths,
        sessions: sessionmaker[Session],
        files: MemoryFiles,
        portals: PortalStore,
    ) -> None:
        self._paths = paths
        self._sessions = sessions
        self._files = files
        self._portals = portals

    def reset(self, request: ResetIn) -> ResetResult:
        scope = request.scope
        if request.confirm.strip().casefold() != scope.value:
            raise ConfirmationError(f'Type "{scope.value}" to confirm.')
        backup = create_backup(self._paths, f"reset-{scope.value}")
        everything = scope is ResetScope.EVERYTHING
        removed: dict[str, int] = {}

        def count(name: str, result: object) -> None:
            removed[name] = removed.get(name, 0) + int(getattr(result, "rowcount", 0) or 0)

        with self._sessions.begin() as session:
            if everything or scope is ResetScope.APPLICATIONS:
                count("applications", session.execute(delete(Application)))  # cascades history
            if everything or scope is ResetScope.JOBS:
                count("job scores", session.execute(delete(JobScore)))
                has_application = exists().where(Application.job_id == Job.id)
                count("jobs", session.execute(delete(Job).where(~has_application)))
            if everything or scope is ResetScope.PROFILE:
                count("profile items", session.execute(delete(ProfileItem)))
                count("search targets", session.execute(delete(SearchTarget)))
                count("memory proposals", session.execute(delete(MemoryProposal)))
                count("setup state", session.execute(delete(AppState)))
            if everything or scope in (ResetScope.PROFILE, ResetScope.DOCUMENTS):
                count("imported documents", session.execute(delete(SourceDocument)))
            if scope is ResetScope.DOCUMENTS:
                session.execute(update(Application).values(cv_path=None, cover_path=None))
            if everything:
                count("chats", session.execute(delete(ChatSession)))
                count("AI calls", session.execute(delete(LLMCall)))
                finished = Task.status.in_(
                    [TaskStatus.SUCCEEDED, TaskStatus.FAILED, TaskStatus.CANCELLED]
                )
                count("tasks", session.execute(delete(Task).where(finished)))  # not running ones
                count("added companies", session.execute(delete(Company).where(
                    Company.source == "user"
                )))  # fmt: skip
                session.execute(update(Company).values(enabled=True, last_error=None))

        if everything or scope is ResetScope.PROFILE:
            for target in MemoryTarget:
                self._files.write(target, TEMPLATES[target])
            removed["files"] = removed.get("files", 0) + _clear_folder(self._paths.source_documents)
        if scope is ResetScope.DOCUMENTS:
            removed["files"] = _clear_folder(self._paths.source_documents) + _clear_folder(
                self._paths.generated_documents
            )
        if everything or scope is ResetScope.APPLICATIONS:
            removed["files"] = removed.get("files", 0) + _clear_folder(
                self._paths.generated_documents
            )
        if everything:
            removed["files"] += _clear_folder(self._paths.reports) + _clear_folder(
                self._paths.sessions
            )
            self._portals.seed_watchlist()
        return ResetResult(scope=scope, backup=str(backup), removed=removed)
