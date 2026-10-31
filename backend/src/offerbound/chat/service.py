"""Chat turns: stream a reply, run tools, persist, then propose memory facts.

History contract (keeps the API's preserved-thinking check and the prompt cache happy):
- Within one user turn, the system prompt and tool list are fixed, and assistant content is
  replayed verbatim (thinking blocks included) between tool rounds.
- Across turns, history is rebuilt from stored text only, in order, so it is append-only and
  replays no thinking blocks from earlier turns.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import AsyncIterator
from datetime import datetime
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from offerbound.chat.tools import ChatTool, ToolContext, chat_tools, execute
from offerbound.db.models import ChatMessage, ChatRole, ChatSession
from offerbound.llm.errors import LLMError
from offerbound.llm.prompting import TRUTHFULNESS_RULES, UNTRUSTED_RULES, tagged
from offerbound.llm.types import (
    Completion,
    Message,
    StreamDone,
    SystemBlock,
    Task,
    TextDelta,
    ToolResult,
)
from offerbound.memory.context import build_context_pack
from offerbound.memory.extraction import extract_proposals

if TYPE_CHECKING:
    from offerbound.services.runtime import Runtime

log = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 8
HISTORY_MESSAGES = 40

CHAT_PROMPT = f"""\
You are Offerbound, a job search copilot that runs on the user's own computer. You help them
find, rank, and apply to jobs, prepare for interviews, and track outcomes.

- Answer pipeline questions ("who did I apply to last month?") with query_pipeline. Never
  guess counts, dates, or statuses.
- When the user states a durable fact about themselves, call propose_memory_update. It only
  proposes; the user accepts or rejects it.
- Use run_command for app actions. Commands that change data become a confirmation card.
- {TRUTHFULNESS_RULES}
- {UNTRUSTED_RULES}
- Be concise. Use short paragraphs or bullets; no headings for short answers.
"""


class ViewContext(BaseModel):
    """What the user is looking at, shown as the context chip."""

    model_config = ConfigDict(extra="forbid")
    label: str | None = Field(default=None, description='e.g. "Stripe, Senior Frontend"')
    route: str | None = None
    job_ids: list[int] = Field(default_factory=list)
    application_ids: list[int] = Field(default_factory=list)


class ChatEvent(BaseModel):
    type: Literal["text", "tool_call", "tool_result", "card", "memory_proposals", "error", "done"]
    data: dict[str, Any]


class ChatMessageView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    session_id: str
    role: ChatRole
    content: str
    context: dict[str, Any] | None
    cards: list[dict[str, Any]]
    created_at: datetime


class ChatSessionView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    title: str | None
    created_at: datetime
    updated_at: datetime


class ChatSessionNotFoundError(LookupError):
    pass


def _event(type_: str, **data: Any) -> ChatEvent:
    return ChatEvent.model_validate({"type": type_, "data": data})


class ChatService:
    def __init__(self, runtime: Runtime) -> None:
        self._rt = runtime
        self._tools: dict[str, ChatTool] = {tool.name: tool for tool in chat_tools()}

    # --- sessions ------------------------------------------------------------------

    def create_session(self, title: str | None = None) -> ChatSessionView:
        with self._rt.sessions.begin() as session:
            row = ChatSession(id=uuid.uuid4().hex, title=title)
            session.add(row)
            session.flush()
            return ChatSessionView.model_validate(row)

    def list_sessions(self, limit: int = 50) -> list[ChatSessionView]:
        with self._rt.sessions() as session:
            rows = session.scalars(
                select(ChatSession).order_by(ChatSession.updated_at.desc()).limit(limit)
            )
            return [ChatSessionView.model_validate(row) for row in rows]

    def messages(self, session_id: str) -> list[ChatMessageView]:
        with self._rt.sessions() as session:
            if session.get(ChatSession, session_id) is None:
                raise ChatSessionNotFoundError(session_id)
            rows = session.scalars(
                select(ChatMessage)
                .where(ChatMessage.session_id == session_id)
                .order_by(ChatMessage.id)
            )
            return [ChatMessageView.model_validate(row) for row in rows]

    def _history(self, session_id: str) -> list[Message]:
        with self._rt.sessions() as session:
            rows = list(
                session.scalars(
                    select(ChatMessage)
                    .where(ChatMessage.session_id == session_id)
                    .order_by(ChatMessage.id.desc())
                    .limit(HISTORY_MESSAGES)
                )
            )
        rows.reverse()
        while rows and rows[0].role is not ChatRole.USER:
            rows.pop(0)
        history: list[Message] = []
        for row in rows:
            if row.role is ChatRole.USER:
                prompt = (row.context or {}).get("prompt_text") or row.content
                history.append(Message(role="user", text=prompt))
            elif row.role is ChatRole.ASSISTANT and row.content:
                history.append(Message(role="assistant", text=row.content))
        return history

    def _save(
        self,
        session_id: str,
        role: ChatRole,
        content: str,
        context: dict[str, Any] | None = None,
        cards: list[dict[str, Any]] | None = None,
    ) -> int:
        with self._rt.sessions.begin() as session:
            chat = session.get(ChatSession, session_id)
            if chat is None:
                raise ChatSessionNotFoundError(session_id)
            if chat.title is None and role is ChatRole.USER:
                chat.title = content.strip().splitlines()[0][:60] if content.strip() else None
            chat.updated_at = datetime.now(chat.updated_at.tzinfo)
            row = ChatMessage(
                session_id=session_id,
                role=role,
                content=content,
                context=context,
                cards=cards or [],
            )
            session.add(row)
            session.flush()
            return row.id

    # --- a turn ----------------------------------------------------------------------

    def _system(self, memory_block: SystemBlock) -> list[SystemBlock]:
        commands = "\n".join(
            f"- {c.name}{'' if c.read_only else ' (needs confirmation)'}: {c.description}"
            for c in self._rt.commands.all()
            if c.chat_allowed
        )
        return [SystemBlock(CHAT_PROMPT + "\nCommands:\n" + commands), memory_block]

    async def send(
        self, session_id: str, text: str, view: ViewContext | None = None
    ) -> AsyncIterator[ChatEvent]:
        rt = self._rt
        view = view or ViewContext()
        pack = await asyncio.to_thread(
            build_context_pack,
            rt.memory,
            rt.sessions,
            "chat",
            job_ids=view.job_ids,
            application_ids=view.application_ids,
        )
        prompt_parts = []
        if view.label:
            prompt_parts.append(tagged("viewing", view.label))
        rows = pack.rows_text()
        if rows:
            prompt_parts.append(tagged("context_rows", rows))
        prompt_parts.append(text)
        prompt_text = "\n\n".join(prompt_parts)

        history = await asyncio.to_thread(self._history, session_id)
        await asyncio.to_thread(
            self._save,
            session_id,
            ChatRole.USER,
            text,
            {"view": view.model_dump(), "prompt_text": prompt_text},
        )

        system = self._system(pack.memory_block())
        tool_defs = [tool.definition() for tool in self._tools.values()]
        messages: list[Message] = [*history, Message(role="user", text=prompt_text)]
        ctx = ToolContext(runtime=rt, session_id=session_id, tainted=pack.has_untrusted)
        texts: list[str] = []
        cards: list[dict[str, Any]] = []

        try:
            for _round in range(MAX_TOOL_ROUNDS):
                completion: Completion | None = None
                async for event in rt.llm.stream(
                    command="chat",
                    task=Task.CHAT,
                    system=system,
                    messages=messages,
                    tools=tool_defs,
                ):
                    if isinstance(event, TextDelta):
                        yield _event("text", text=event.text)
                    elif isinstance(event, StreamDone):
                        completion = event.completion
                if completion is None:  # pragma: no cover - providers always finish
                    break
                if completion.text:
                    texts.append(completion.text)
                messages.append(completion.as_assistant_message())
                if not completion.tool_calls:
                    break
                results: list[ToolResult] = []
                for call in completion.tool_calls:
                    yield _event("tool_call", id=call.id, name=call.name, input=call.input)
                    tool = self._tools.get(call.name)
                    if tool is None:
                        outcome_text, is_error, new_cards, tainting = (
                            f"Unknown tool {call.name}",
                            True,
                            [],
                            False,
                        )
                    else:
                        outcome = await execute(tool, ctx, call.input)
                        outcome_text, is_error = outcome.content, outcome.is_error
                        new_cards, tainting = outcome.cards, outcome.untrusted
                    ctx.tainted = ctx.tainted or tainting
                    for card in new_cards:
                        cards.append(card)
                        yield _event("card", card=card)
                    yield _event("tool_result", id=call.id, name=call.name, is_error=is_error)
                    results.append(ToolResult(call.id, outcome_text, is_error))
                messages.append(Message(role="user", tool_results=results))
            else:
                texts.append("(Stopped after too many tool steps. Ask me to continue.)")
        except LLMError as exc:
            log.warning("chat turn failed: %s", exc)
            yield _event("error", message=exc.user_message, kind=type(exc).__name__)
            return

        reply = "\n\n".join(t.strip() for t in texts if t.strip())
        message_id = await asyncio.to_thread(
            self._save, session_id, ChatRole.ASSISTANT, reply, None, cards
        )
        yield _event("done", message_id=message_id)

        proposals = await self._extract(session_id, text, reply)
        if proposals:
            yield _event("memory_proposals", proposals=proposals)
        await self._maintain(session_id)

    async def _extract(self, session_id: str, user_text: str, reply: str) -> list[dict[str, Any]]:
        rt = self._rt
        try:
            snapshot = await asyncio.to_thread(rt.memory.snapshot)
            found = await extract_proposals(rt.llm, snapshot, user_text, reply)
            views = [
                await asyncio.to_thread(rt.memory.propose, p, "extraction", session_id)
                for p in found
            ]
        except LLMError as exc:
            log.info("fact extraction skipped: %s", exc)
            return []
        return [v.model_dump(mode="json") for v in views if v.status.value == "pending"]

    async def _maintain(self, session_id: str) -> None:
        maintenance = self._rt.session_maintenance
        try:
            if await asyncio.to_thread(maintenance.needs_summary, session_id):
                await maintenance.summarize(session_id)
        except LLMError as exc:
            log.info("session summary skipped: %s", exc)
