"""Rolling chat summaries in memory/sessions/YYYY-MM-DD.md and chat retention.

A session is summarized once it has 40 unsummarized messages, or when it has gone quiet
since an earlier UTC day ("nightly"). Only summarized messages are ever purged."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, sessionmaker

from rolehawk.db.models import ChatMessage, ChatSession
from rolehawk.db.types import utcnow
from rolehawk.llm.service import LLMService
from rolehawk.llm.types import Message, SystemBlock, Task
from rolehawk.memory.files import MemoryFiles

SUMMARIZE_AT = 40

SUMMARY_PROMPT = """\
Summarize this chat between a job seeker and their assistant for future sessions. Keep
decisions, preferences the user expressed, applications discussed, and open follow-ups.
Write 3-10 short bullets. Do not add anything that was not said."""


class SessionSummary(BaseModel):
    bullets: list[str] = Field(description="3-10 short bullets.")
    open_threads: list[str] = Field(description="Follow-ups still pending; may be empty.")


class SessionMaintenance:
    def __init__(
        self, llm: LLMService, files: MemoryFiles, sessions: sessionmaker[Session]
    ) -> None:
        self._llm = llm
        self._files = files
        self._sessions = sessions

    def _pending_messages(self, session_id: str) -> tuple[ChatSession, list[ChatMessage]]:
        with self._sessions() as session:
            chat = session.get(ChatSession, session_id)
            if chat is None:
                raise LookupError(session_id)
            rows = list(
                session.scalars(
                    select(ChatMessage)
                    .where(
                        ChatMessage.session_id == session_id,
                        ChatMessage.id > chat.summarized_through_id,
                    )
                    .order_by(ChatMessage.id)
                )
            )
            return chat, rows

    def needs_summary(self, session_id: str, now: datetime | None = None) -> bool:
        _, rows = self._pending_messages(session_id)
        if not rows:
            return False
        if len(rows) >= SUMMARIZE_AT:
            return True
        today = (now or datetime.now(UTC)).date()
        return rows[-1].created_at.date() < today

    async def summarize(self, session_id: str) -> bool:
        chat, rows = self._pending_messages(session_id)
        if not rows:
            return False
        transcript = "\n".join(f"{row.role.value}: {row.content}" for row in rows)
        summary = await self._llm.structured(
            command="chat",
            task=Task.EXTRACT,
            system=[SystemBlock(SUMMARY_PROMPT)],
            messages=[Message(role="user", text=transcript)],
            schema=SessionSummary,
        )
        body = "\n".join(f"- {b}" for b in summary.bullets)
        if summary.open_threads:
            body += "\n\nOpen threads:\n" + "\n".join(f"- {t}" for t in summary.open_threads)
        day = rows[-1].created_at.date()
        heading = (
            f"{chat.title or 'Chat'} ({rows[0].created_at:%H:%M}-{rows[-1].created_at:%H:%M} UTC)"
        )
        self._files.append_session_summary(day, heading, body)
        with self._sessions.begin() as session:
            row = session.get(ChatSession, session_id)
            if row is not None:
                row.summarized_through_id = rows[-1].id
        return True

    async def summarize_stale(self, now: datetime | None = None) -> int:
        """Summarize every session that went quiet before today. Run at startup."""
        with self._sessions() as session:
            ids = list(session.scalars(select(ChatSession.id)))
        count = 0
        for session_id in ids:
            if self.needs_summary(session_id, now) and await self.summarize(session_id):
                count += 1
        return count

    def purge(self, retention_days: int, now: datetime | None = None) -> int:
        cutoff = (now or utcnow()) - timedelta(days=retention_days)
        with self._sessions.begin() as session:
            summarized = (
                select(ChatSession.summarized_through_id)
                .where(ChatSession.id == ChatMessage.session_id)
                .scalar_subquery()
            )
            result = session.execute(
                delete(ChatMessage).where(
                    ChatMessage.created_at < cutoff, ChatMessage.id <= func.coalesce(summarized, 0)
                )
            )
            return int(getattr(result, "rowcount", 0) or 0)
