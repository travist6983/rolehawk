from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Response, UploadFile
from pydantic import BaseModel, Field

from offerbound.api.deps import RuntimeDep
from offerbound.commands.runner import CommandStarted, run_command
from offerbound.profile.documents import MAX_UPLOAD_BYTES, DocumentError
from offerbound.profile.extraction import ExtractedSetup
from offerbound.profile.interview import AnswerError, AnswerValue, InterviewState
from offerbound.profile.setup import ApplyResult, DocumentView, Draft, NoDraftError

router = APIRouter(prefix="/api/setup", tags=["setup"])


class TextIn(BaseModel):
    text: str = Field(min_length=1, max_length=100_000)


class ExtractIn(BaseModel):
    document_ids: list[int] = Field(min_length=1)


class TaskRef(BaseModel):
    task_id: str


class AnswerIn(BaseModel):
    question_id: str
    value: AnswerValue


class SkipIn(BaseModel):
    question_id: str


@router.post("/documents", status_code=201)
async def upload_document(file: UploadFile, runtime: RuntimeDep) -> DocumentView:
    """PDF, DOCX, TXT/MD, or a LinkedIn data export ZIP, up to 10 MB."""
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    try:
        return await asyncio.to_thread(
            runtime.setup.add_document, file.filename or "document", data
        )
    except DocumentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None


@router.post("/documents/text", status_code=201)
async def paste_text(body: TextIn, runtime: RuntimeDep) -> DocumentView:
    try:
        return await asyncio.to_thread(runtime.setup.add_text, body.text)
    except DocumentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None


@router.get("/documents")
async def list_documents(runtime: RuntimeDep) -> list[DocumentView]:
    return await asyncio.to_thread(runtime.setup.list_documents)


@router.post("/extract", status_code=202)
async def extract(body: ExtractIn, runtime: RuntimeDep) -> TaskRef:
    """Starts a background task; follow it over /api/events. Its result is the draft."""
    spec = runtime.commands.get("setup-extract")
    started = await run_command(runtime, spec, {"document_ids": body.document_ids})
    assert isinstance(started, CommandStarted)  # noqa: S101 - setup-extract is a background command
    return TaskRef(task_id=started.task_id)


@router.get("/draft")
async def get_draft(runtime: RuntimeDep) -> Draft:
    draft = await asyncio.to_thread(runtime.setup.get_draft)
    if draft is None:
        raise HTTPException(status_code=404, detail="No setup draft")
    return draft


@router.delete("/draft", status_code=204)
async def discard_draft(runtime: RuntimeDep) -> Response:
    await asyncio.to_thread(runtime.setup.discard_draft)
    return Response(status_code=204)


@router.post("/draft/apply")
async def apply_draft(runtime: RuntimeDep, body: ExtractedSetup | None = None) -> ApplyResult:
    """Applies the stored draft, or the edited version the user reviewed."""
    try:
        return await asyncio.to_thread(runtime.setup.apply_draft, body)
    except NoDraftError:
        raise HTTPException(status_code=404, detail="No setup draft to apply") from None


@router.get("/interview")
async def get_interview(runtime: RuntimeDep) -> InterviewState:
    return await asyncio.to_thread(runtime.setup.interview_state)


@router.post("/interview/answer")
async def answer(body: AnswerIn, runtime: RuntimeDep) -> InterviewState:
    try:
        return await asyncio.to_thread(runtime.setup.answer, body.question_id, body.value)
    except AnswerError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None


@router.post("/interview/skip")
async def skip(body: SkipIn, runtime: RuntimeDep) -> InterviewState:
    try:
        return await asyncio.to_thread(runtime.setup.skip, body.question_id)
    except AnswerError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None


@router.post("/interview/restart")
async def restart(runtime: RuntimeDep) -> InterviewState:
    return await asyncio.to_thread(runtime.setup.restart_interview)
