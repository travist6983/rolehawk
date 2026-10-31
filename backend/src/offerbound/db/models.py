"""Core tables (docs/SPEC.md "Data model and memory"). Change a model, then add a migration:
`uv run offerbound db revision -m "..."` and review the generated file."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Float,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from offerbound.db.types import UTCDateTime, str_enum, utcnow

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)


# --- Enums -----------------------------------------------------------------------------


class ProfileItemKind(StrEnum):
    EXPERIENCE = "experience"
    EDUCATION = "education"
    SKILL = "skill"
    PROJECT = "project"
    CERT = "cert"
    ACHIEVEMENT = "achievement"


class RemotePolicy(StrEnum):
    ONSITE = "onsite"
    HYBRID = "hybrid"
    REMOTE = "remote"
    ANY = "any"


class PortalKind(StrEnum):
    ATS = "ats"
    FEED = "feed"
    SCRAPER = "scraper"
    PLUGIN = "plugin"


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Stage(StrEnum):
    SAVED = "saved"
    APPLYING = "applying"
    APPLIED = "applied"
    SCREEN = "screen"
    INTERVIEW = "interview"
    OFFER = "offer"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"
    GHOSTED = "ghosted"


class ApplyMethod(StrEnum):
    MANUAL = "manual"
    AUTOFILL = "autofill"
    AUTOSUBMIT = "autosubmit"


class StageEventSource(StrEnum):
    USER = "user"
    GMAIL = "gmail"
    OUTCOME = "outcome"


class ProposalStatus(StrEnum):
    PENDING = "pending"
    APPLIED = "applied"
    DISMISSED = "dismissed"


class InterviewStage(StrEnum):
    RECRUITER_SCREEN = "recruiter_screen"
    HIRING_MANAGER = "hiring_manager"
    TECHNICAL = "technical"
    BEHAVIORAL = "behavioral"
    FINAL = "final"


class ChatRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class ProposalOp(StrEnum):
    ADD = "add"
    REPLACE = "replace"
    REMOVE = "remove"


class MemoryProposalStatus(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    CONFLICT = "conflict"  # the file changed and the edit no longer applies


class TaskStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @property
    def is_terminal(self) -> bool:
        return self in {TaskStatus.SUCCEEDED, TaskStatus.FAILED, TaskStatus.CANCELLED}


# --- Tables ----------------------------------------------------------------------------


class ProfileItem(TimestampMixin, Base):
    __tablename__ = "profile_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[ProfileItemKind] = mapped_column(str_enum(ProfileItemKind), index=True)
    data: Mapped[dict[str, Any]] = mapped_column(JSON)
    source: Mapped[str | None] = mapped_column(String(255))
    confidence: Mapped[float | None] = mapped_column(Float)


class SearchTarget(TimestampMixin, Base):
    __tablename__ = "search_targets"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(255))
    seniority: Mapped[str | None] = mapped_column(String(64))
    locations: Mapped[list[str]] = mapped_column(JSON, default=list)
    remote_policy: Mapped[RemotePolicy] = mapped_column(
        str_enum(RemotePolicy), default=RemotePolicy.ANY
    )
    country: Mapped[str] = mapped_column(String(2))
    salary_min: Mapped[int | None] = mapped_column(Integer)
    keywords: Mapped[list[str]] = mapped_column(JSON, default=list)
    exclude: Mapped[list[str]] = mapped_column(JSON, default=list)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Portal(TimestampMixin, Base):
    __tablename__ = "portals"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    kind: Mapped[PortalKind] = mapped_column(str_enum(PortalKind))
    countries: Mapped[list[str]] = mapped_column(JSON, default=list)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    risk_level: Mapped[RiskLevel] = mapped_column(str_enum(RiskLevel))
    config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    status: Mapped[str | None] = mapped_column(String(64))
    last_run_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    last_error: Mapped[str | None] = mapped_column(Text)


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (UniqueConstraint("portal_id", "external_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    portal_id: Mapped[str] = mapped_column(ForeignKey("portals.id"), index=True)
    external_id: Mapped[str] = mapped_column(String(255))
    url: Mapped[str] = mapped_column(Text)
    company: Mapped[str] = mapped_column(String(255), index=True)
    title: Mapped[str] = mapped_column(String(255))
    location: Mapped[str | None] = mapped_column(String(255))
    remote: Mapped[bool | None] = mapped_column(Boolean)
    salary_text: Mapped[str | None] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    posted_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    scraped_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    hash: Mapped[str] = mapped_column(String(64), unique=True)


class Task(Base):
    """A background run (scrape, rank, apply, ...). Named `tasks` because `jobs` holds postings."""

    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    kind: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[TaskStatus] = mapped_column(str_enum(TaskStatus), default=TaskStatus.QUEUED)
    progress: Mapped[float | None] = mapped_column(Float)
    message: Mapped[str | None] = mapped_column(Text)
    params: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    result: Mapped[Any | None] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class JobScore(Base):
    __tablename__ = "job_scores"
    __table_args__ = (
        UniqueConstraint("job_id", "run_id"),
        CheckConstraint("score >= 0 AND score <= 100", name="score_range"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("tasks.id", ondelete="SET NULL"))
    score: Mapped[int] = mapped_column(Integer)
    must_have_gaps: Mapped[list[str]] = mapped_column(JSON, default=list)
    reasons: Mapped[list[str]] = mapped_column(JSON, default=list)
    model: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class Application(TimestampMixin, Base):
    __tablename__ = "applications"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="RESTRICT"), index=True)
    stage: Mapped[Stage] = mapped_column(str_enum(Stage), default=Stage.SAVED, index=True)
    stage_changed_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    applied_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    method: Mapped[ApplyMethod | None] = mapped_column(str_enum(ApplyMethod))
    cv_path: Mapped[str | None] = mapped_column(Text)
    cover_path: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)


class StageEvent(Base):
    __tablename__ = "stage_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), index=True
    )
    from_stage: Mapped[Stage | None] = mapped_column(str_enum(Stage))
    to_stage: Mapped[Stage] = mapped_column(str_enum(Stage))
    source: Mapped[StageEventSource] = mapped_column(str_enum(StageEventSource))
    status: Mapped[ProposalStatus] = mapped_column(
        str_enum(ProposalStatus), default=ProposalStatus.APPLIED, index=True
    )
    evidence: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class Interview(TimestampMixin, Base):
    __tablename__ = "interviews"
    __table_args__ = (
        CheckConstraint(
            "self_rating IS NULL OR (self_rating >= 1 AND self_rating <= 5)", name="rating_range"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), index=True
    )
    stage: Mapped[InterviewStage] = mapped_column(str_enum(InterviewStage))
    scheduled_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    prep_pack_path: Mapped[str | None] = mapped_column(Text)
    mock_transcript_path: Mapped[str | None] = mapped_column(Text)
    self_rating: Mapped[int | None] = mapped_column(Integer)


class Outcome(Base):
    __tablename__ = "outcomes"

    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), index=True
    )
    result: Mapped[str] = mapped_column(String(64))
    feedback: Mapped[str | None] = mapped_column(Text)
    follow_up_draft: Mapped[str | None] = mapped_column(Text)
    archived_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class LLMCall(Base):
    __tablename__ = "llm_calls"

    id: Mapped[int] = mapped_column(primary_key=True)
    command: Mapped[str] = mapped_column(String(64), index=True)
    provider: Mapped[str] = mapped_column(String(32))
    model: Mapped[str] = mapped_column(String(128))
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cache_read_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cache_write_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    task_id: Mapped[str | None] = mapped_column(ForeignKey("tasks.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)


class ChatSession(TimestampMixin, Base):
    __tablename__ = "chat_sessions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    title: Mapped[str | None] = mapped_column(String(255))
    # Messages with id <= this are folded into memory/sessions/*.md and may be purged.
    summarized_through_id: Mapped[int] = mapped_column(Integer, default=0)


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("chat_sessions.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[ChatRole] = mapped_column(str_enum(ChatRole))
    content: Mapped[str] = mapped_column(Text)
    # What the user was viewing when they sent it ("Viewing: Stripe, Senior Frontend").
    context: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    # Rich cards rendered with an assistant message (proposals, command suggestions).
    cards: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)


class MemoryProposal(Base):
    __tablename__ = "memory_proposals"

    id: Mapped[int] = mapped_column(primary_key=True)
    target: Mapped[str] = mapped_column(String(32))
    op: Mapped[ProposalOp] = mapped_column(str_enum(ProposalOp))
    section: Mapped[str | None] = mapped_column(String(255))
    text: Mapped[str | None] = mapped_column(Text)
    old_text: Mapped[str | None] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(String(32))
    session_id: Mapped[str | None] = mapped_column(
        ForeignKey("chat_sessions.id", ondelete="SET NULL")
    )
    status: Mapped[MemoryProposalStatus] = mapped_column(
        str_enum(MemoryProposalStatus), default=MemoryProposalStatus.PENDING, index=True
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class AppState(Base):
    """Small JSON values keyed by name: setup drafts, interview progress, UI flags."""

    __tablename__ = "app_state"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[Any] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)


class SourceDocument(Base):
    """An uploaded resume, CV, or LinkedIn export kept in documents/source/."""

    __tablename__ = "source_documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    filename: Mapped[str] = mapped_column(String(255))
    kind: Mapped[str] = mapped_column(String(32))
    path: Mapped[str] = mapped_column(Text)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    size: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
