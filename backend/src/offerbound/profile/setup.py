"""/setup: import documents, extract a reviewable draft, apply it, and run the gap interview."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from offerbound.db.models import SourceDocument
from offerbound.db.types import utcnow
from offerbound.llm.service import LLMService
from offerbound.paths import DataPaths
from offerbound.profile import interview
from offerbound.profile.documents import DocumentError, DocumentKind, parse_document
from offerbound.profile.extraction import ExtractedSetup, extract_setup
from offerbound.profile.interview import AnswerValue, InterviewProgress, InterviewState
from offerbound.profile.merge import merge_preferences, merge_profile
from offerbound.profile.model import Preferences, Profile
from offerbound.profile.service import Completeness, ProfileService, completeness
from offerbound.services.app_state import AppStateStore

DRAFT_KEY = "setup.draft"
INTERVIEW_KEY = "setup.interview"
MAX_PASTED_CHARS = 100_000


class DocumentView(BaseModel):
    id: int
    filename: str
    kind: str
    size: int
    chars: int
    created_at: datetime


class Draft(BaseModel):
    profile: Profile
    preferences: Preferences
    document_ids: list[int] = Field(default_factory=list)
    created_at: datetime


class ApplyResult(BaseModel):
    profile: Profile
    preferences: Preferences
    added: dict[str, int]
    updated: dict[str, int]
    completeness: Completeness


class NoDraftError(LookupError):
    pass


def _safe_name(filename: str) -> str:
    stem = re.sub(r"[^\w.\-]+", "_", Path(filename).name).strip("._") or "document"
    return stem[:100]


class SetupService:
    def __init__(
        self,
        paths: DataPaths,
        sessions: sessionmaker[Session],
        profiles: ProfileService,
        state: AppStateStore,
        llm: LLMService,
    ) -> None:
        self._paths = paths
        self._sessions = sessions
        self._profiles = profiles
        self._state = state
        self._llm = llm

    # --- documents --------------------------------------------------------------------

    def add_document(self, filename: str, data: bytes) -> DocumentView:
        """Parse and keep an uploaded file. The same file uploaded twice is stored once."""
        parsed = parse_document(filename, data)  # raises DocumentError
        digest = hashlib.sha256(data).hexdigest()
        with self._sessions.begin() as session:
            existing = session.scalar(select(SourceDocument).where(SourceDocument.sha256 == digest))
            if existing is not None:
                return self._view(existing)
            row = SourceDocument(
                filename=Path(filename).name[:255] or "document",
                kind=parsed.kind.value,
                path="",
                sha256=digest,
                size=len(data),
                text=parsed.text,
            )
            session.add(row)
            session.flush()
            target = self._paths.source_documents / f"{row.id}-{_safe_name(filename)}"
            target.write_bytes(data)
            row.path = str(target.relative_to(self._paths.root).as_posix())
            return self._view(row)

    def add_text(self, text: str) -> DocumentView:
        if not text.strip():
            raise DocumentError("Paste some text first.")
        if len(text) > MAX_PASTED_CHARS:
            raise DocumentError("That's too much text; paste just your CV.")
        return self.add_document("pasted-cv.txt", text.encode("utf-8"))

    def list_documents(self) -> list[DocumentView]:
        with self._sessions() as session:
            rows = session.scalars(select(SourceDocument).order_by(SourceDocument.id.desc()))
            return [self._view(row) for row in rows]

    @staticmethod
    def _view(row: SourceDocument) -> DocumentView:
        return DocumentView(
            id=row.id,
            filename=row.filename,
            kind=row.kind,
            size=row.size,
            chars=len(row.text),
            created_at=row.created_at,
        )

    # --- drafts -----------------------------------------------------------------------

    async def extract(self, document_ids: list[int], task_id: str | None = None) -> Draft:
        """Build a draft from documents: LinkedIn exports map directly, other text goes
        through Claude. Nothing is written to the profile until the draft is applied."""
        with self._sessions() as session:
            rows = list(
                session.scalars(select(SourceDocument).where(SourceDocument.id.in_(document_ids)))
            )
        if not rows:
            raise DocumentError("Add a document first.")
        draft_profile = Profile()
        draft_prefs = Preferences()
        texts: list[tuple[str, str]] = []
        for row in rows:
            if row.kind == DocumentKind.LINKEDIN.value:
                data = (self._paths.root / row.path).read_bytes()
                linked = parse_document(row.filename, data).profile
                if linked is not None:
                    draft_profile, _ = merge_profile(draft_profile, linked)
            elif row.text.strip():
                texts.append((row.filename, row.text))
        if texts:
            extracted = await extract_setup(self._llm, texts, task_id=task_id)
            draft_profile, _ = merge_profile(draft_profile, extracted.profile)
            draft_prefs = merge_preferences(draft_prefs, extracted.preferences)
        draft = Draft(
            profile=draft_profile,
            preferences=draft_prefs,
            document_ids=[row.id for row in rows],
            created_at=utcnow(),
        )
        self._state.set(DRAFT_KEY, draft.model_dump(mode="json"))
        return draft

    def store_draft(self, extracted: ExtractedSetup) -> Draft:
        """Skills (Claude Code) extract in their own session and store the result here."""
        draft = Draft(
            profile=extracted.profile, preferences=extracted.preferences, created_at=utcnow()
        )
        self._state.set(DRAFT_KEY, draft.model_dump(mode="json"))
        return draft

    def get_draft(self) -> Draft | None:
        raw: Any = self._state.get(DRAFT_KEY)
        return Draft.model_validate(raw) if raw else None

    def discard_draft(self) -> None:
        self._state.delete(DRAFT_KEY)

    def apply_draft(self, edited: ExtractedSetup | None = None) -> ApplyResult:
        """Merge the (optionally user-edited) draft into the profile. Existing facts win;
        re-running setup updates entries instead of duplicating them."""
        draft = self.get_draft()
        source = edited or (
            ExtractedSetup(profile=draft.profile, preferences=draft.preferences) if draft else None
        )
        if source is None:
            raise NoDraftError
        with self._profiles.lock:
            profile, report = merge_profile(self._profiles.load_profile(), source.profile)
            prefs = merge_preferences(self._profiles.load_preferences(), source.preferences)
            self._profiles.save_profile(profile)
            self._profiles.save_preferences(prefs)
        self.discard_draft()
        return ApplyResult(
            profile=profile,
            preferences=prefs,
            added=report.added,
            updated=report.updated,
            completeness=completeness(profile, prefs),
        )

    # --- interview --------------------------------------------------------------------

    def _progress(self) -> InterviewProgress:
        return InterviewProgress.model_validate(self._state.get(INTERVIEW_KEY) or {})

    def interview_state(self) -> InterviewState:
        return interview.state(
            self._profiles.load_profile(), self._profiles.load_preferences(), self._progress()
        )

    def answer(self, question_id: str, value: AnswerValue) -> InterviewState:
        with self._profiles.lock:
            profile = self._profiles.load_profile()
            prefs = self._profiles.load_preferences()
            new_profile, new_prefs, progress = interview.apply_answer(
                question_id, value, profile, prefs, self._progress()
            )
            if new_profile != profile:
                self._profiles.save_profile(new_profile)
            if new_prefs != prefs:
                self._profiles.save_preferences(new_prefs)
            self._state.set(INTERVIEW_KEY, progress.model_dump())
        return interview.state(new_profile, new_prefs, progress)

    def skip(self, question_id: str) -> InterviewState:
        current = self.interview_state()
        open_ids = {
            q.id: q
            for q in interview.open_questions(
                self._profiles.load_profile(), self._profiles.load_preferences(), self._progress()
            )
        }
        question = open_ids.get(question_id)
        if question is None:
            return current
        progress = interview.skip(question_id, self._progress(), required=not question.optional)
        self._state.set(INTERVIEW_KEY, progress.model_dump())
        return self.interview_state()

    def restart_interview(self) -> InterviewState:
        """Forget skipped questions (answers stay in the profile)."""
        self._state.delete(INTERVIEW_KEY)
        return self.interview_state()
