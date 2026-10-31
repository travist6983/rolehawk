"""Proposed memory edits. Anything the model wants to change becomes a pending proposal;
only `accept()` (a user action) writes to the markdown files."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from offerbound.db.models import MemoryProposal, MemoryProposalStatus, ProposalOp
from offerbound.db.types import utcnow
from offerbound.memory import edits
from offerbound.memory.files import MemoryFiles, MemoryTarget

ProposalSource = Literal["chat", "extraction", "setup", "expand", "skill"]


class ProposalNotFoundError(LookupError):
    pass


class ProposalStateError(ValueError):
    pass


class ProposalIn(BaseModel):
    """A suggested edit. Shared by chat's propose_memory_update tool and fact extraction."""

    model_config = ConfigDict(extra="forbid")

    target: MemoryTarget = Field(description="Which memory file to edit.")
    op: ProposalOp = Field(description="add a line, replace old_text with text, or remove.")
    section: str | None = Field(
        description="Heading to add under, e.g. 'Skills' (add only). Null for end of file."
    )
    text: str | None = Field(description="New text (add/replace). One fact per proposal.")
    old_text: str | None = Field(description="Exact existing text (replace/remove).")
    reason: str = Field(description="One short sentence citing what the user said.")

    @model_validator(mode="after")
    def _fields_match_op(self) -> Self:
        if self.op in (ProposalOp.ADD, ProposalOp.REPLACE) and not (self.text or "").strip():
            raise ValueError(f"{self.op.value} needs text")
        if self.op in (ProposalOp.REPLACE, ProposalOp.REMOVE) and not (self.old_text or "").strip():
            raise ValueError(f"{self.op.value} needs old_text")
        return self


class ProposalView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    target: MemoryTarget
    op: ProposalOp
    section: str | None
    text: str | None
    old_text: str | None
    reason: str
    source: str
    session_id: str | None
    status: MemoryProposalStatus
    created_at: datetime
    resolved_at: datetime | None


class MemorySnapshot(BaseModel):
    profile: str
    preferences: str
    facts: str
    latest_session: str | None


def apply_edit(document: str, proposal: ProposalIn | ProposalView) -> str:
    if proposal.op is ProposalOp.ADD:
        return edits.add(document, proposal.text or "", proposal.section)
    if proposal.op is ProposalOp.REPLACE:
        return edits.replace(document, proposal.old_text or "", proposal.text or "")
    return edits.remove(document, proposal.old_text or "")


class MemoryService:
    def __init__(self, files: MemoryFiles, sessions: sessionmaker[Session]) -> None:
        self.files = files
        self._sessions = sessions

    def snapshot(self) -> MemorySnapshot:
        return MemorySnapshot(
            profile=self.files.read(MemoryTarget.PROFILE),
            preferences=self.files.read(MemoryTarget.PREFERENCES),
            facts=self.files.read(MemoryTarget.FACTS),
            latest_session=self.files.latest_session_summary(),
        )

    def propose(
        self, proposal: ProposalIn, source: ProposalSource, session_id: str | None = None
    ) -> ProposalView:
        """Record a pending proposal. Identical pending proposals are not duplicated, and an
        add whose text is already in the file is dropped (returned as accepted, unchanged)."""
        with self._sessions.begin() as session:
            existing = session.scalar(
                select(MemoryProposal).where(
                    MemoryProposal.status == MemoryProposalStatus.PENDING,
                    MemoryProposal.target == proposal.target.value,
                    MemoryProposal.op == proposal.op,
                    MemoryProposal.text.is_(None)
                    if proposal.text is None
                    else MemoryProposal.text == proposal.text,
                    MemoryProposal.old_text.is_(None)
                    if proposal.old_text is None
                    else MemoryProposal.old_text == proposal.old_text,
                )
            )
            if existing is not None:
                return ProposalView.model_validate(existing)
            row = MemoryProposal(
                target=proposal.target.value,
                op=proposal.op,
                section=proposal.section,
                text=proposal.text,
                old_text=proposal.old_text,
                reason=proposal.reason,
                source=source,
                session_id=session_id,
            )
            session.add(row)
            session.flush()
            return ProposalView.model_validate(row)

    def list_proposals(
        self, status: MemoryProposalStatus | None = MemoryProposalStatus.PENDING
    ) -> list[ProposalView]:
        with self._sessions() as session:
            stmt = select(MemoryProposal).order_by(MemoryProposal.id)
            if status is not None:
                stmt = stmt.where(MemoryProposal.status == status)
            return [ProposalView.model_validate(row) for row in session.scalars(stmt)]

    def get(self, proposal_id: int) -> ProposalView:
        with self._sessions() as session:
            row = session.get(MemoryProposal, proposal_id)
            if row is None:
                raise ProposalNotFoundError(proposal_id)
            return ProposalView.model_validate(row)

    def accept(self, proposal_id: int) -> ProposalView:
        """Apply the edit to the file. Raises EditConflictError (and marks the proposal
        `conflict`) if the file no longer contains the text the proposal expected."""
        with self._sessions.begin() as session:
            row = self._pending(session, proposal_id)
            view = ProposalView.model_validate(row)
            document = self.files.read(view.target)
            try:
                updated = apply_edit(document, view)
            except edits.EditConflictError:
                row.status = MemoryProposalStatus.CONFLICT
                row.resolved_at = utcnow()
                session.flush()
                session.commit()
                raise
            if updated != document:
                self.files.write(view.target, updated)
            row.status = MemoryProposalStatus.ACCEPTED
            row.resolved_at = utcnow()
            session.flush()
            return ProposalView.model_validate(row)

    def reject(self, proposal_id: int) -> ProposalView:
        with self._sessions.begin() as session:
            row = self._pending(session, proposal_id)
            row.status = MemoryProposalStatus.REJECTED
            row.resolved_at = utcnow()
            session.flush()
            return ProposalView.model_validate(row)

    @staticmethod
    def _pending(session: Session, proposal_id: int) -> MemoryProposal:
        row = session.get(MemoryProposal, proposal_id)
        if row is None:
            raise ProposalNotFoundError(proposal_id)
        if row.status is not MemoryProposalStatus.PENDING:
            raise ProposalStateError(f"proposal {proposal_id} is already {row.status.value}")
        return row
