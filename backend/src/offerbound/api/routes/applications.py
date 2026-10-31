from __future__ import annotations

import asyncio
from typing import Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

from offerbound.api.deps import RuntimeDep
from offerbound.api.routes.portals import TaskRef
from offerbound.apply.autofill import AutofillReport, AutofillUnavailableError
from offerbound.apply.drafts import Section
from offerbound.apply.service import (
    ApplicationDetail,
    ApplyParams,
    ApplyPlan,
    DocumentsIn,
    StagePatch,
    UnknownJobError,
)
from offerbound.commands.runner import CommandStarted, run_command
from offerbound.rendering.service import MEDIA_TYPES

router = APIRouter(tags=["applications"])


class PlanIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    job_id: int


class RegenerateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    section: Section
    instruction: str | None = Field(default=None, max_length=1_000)


async def _start(runtime: RuntimeDep, name: str, params: dict[str, object]) -> TaskRef:
    started = await run_command(runtime, runtime.commands.get(name), params)
    assert isinstance(started, CommandStarted)  # noqa: S101 - background commands
    return TaskRef(task_id=started.task_id)


@router.post("/api/apply/plan")
async def apply_plan(body: PlanIn, runtime: RuntimeDep) -> ApplyPlan:
    """Fit, threshold, existing application, and estimated cost, before /apply runs."""
    try:
        return await asyncio.to_thread(runtime.applications.plan, body.job_id)
    except UnknownJobError:
        raise HTTPException(status_code=404, detail=UnknownJobError.user_message) from None


@router.post("/api/apply", status_code=202)
async def apply(body: ApplyParams, runtime: RuntimeDep) -> TaskRef:
    """Starts /apply in the background; follow progress over /api/events."""
    return await _start(runtime, "apply", body.model_dump())


def _not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="Unknown application")


@router.get("/api/applications/{application_id}")
async def get_application(application_id: int, runtime: RuntimeDep) -> ApplicationDetail:
    try:
        return await asyncio.to_thread(runtime.applications.detail, application_id)
    except KeyError:
        raise _not_found() from None


@router.patch("/api/applications/{application_id}")
async def update_application(
    application_id: int, body: StagePatch, runtime: RuntimeDep
) -> ApplicationDetail:
    try:
        return await asyncio.to_thread(runtime.applications.update, application_id, body)
    except KeyError:
        raise _not_found() from None


@router.put("/api/applications/{application_id}/documents")
async def save_documents(
    application_id: int, body: DocumentsIn, runtime: RuntimeDep
) -> ApplicationDetail:
    """Hand edits to the CV or cover letter: fact-checked and re-rendered."""
    try:
        return await runtime.applications.save_documents(application_id, body)
    except KeyError:
        raise _not_found() from None


@router.post("/api/applications/{application_id}/regenerate", status_code=202)
async def regenerate(application_id: int, body: RegenerateIn, runtime: RuntimeDep) -> TaskRef:
    if await asyncio.to_thread(runtime.applications.load_bundle, application_id) is None:
        raise _not_found()
    return await _start(
        runtime,
        "application-regenerate",
        {"application_id": application_id, **body.model_dump()},
    )


@router.get(
    "/api/applications/{application_id}/files/{document}.{format}",
    response_class=FileResponse,
    responses={200: {"content": {MEDIA_TYPES["pdf"]: {}, MEDIA_TYPES["docx"]: {}}}},
)
async def application_file(
    application_id: int,
    document: Literal["cv", "cover_letter"],
    format: Literal["pdf", "docx"],
    runtime: RuntimeDep,
    download: bool = False,
) -> FileResponse:
    try:
        path = await asyncio.to_thread(
            runtime.applications.file_path, application_id, document, format
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="File not found") from None
    return FileResponse(
        path,
        media_type=MEDIA_TYPES[format],
        filename=path.name,
        content_disposition_type="attachment" if download or format == "docx" else "inline",
        headers={"Cache-Control": "no-store"},
    )


@router.post("/api/applications/{application_id}/autofill")
async def autofill(application_id: int, runtime: RuntimeDep) -> AutofillReport:
    """Opens the application form in a visible browser and fills what it can. Never submits."""
    try:
        return await runtime.applications.autofill(application_id, runtime.autofill)
    except KeyError:
        raise _not_found() from None
    except AutofillUnavailableError as exc:
        raise HTTPException(status_code=503, detail=exc.user_message) from None
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
