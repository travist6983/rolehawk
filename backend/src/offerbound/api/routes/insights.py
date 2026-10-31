from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from offerbound.api.deps import RuntimeDep
from offerbound.insights.board import Board
from offerbound.insights.service import ReportFile
from offerbound.insights.stats import Insights
from offerbound.services.reset import ConfirmationError, ResetIn, ResetResult, ScopeView, scopes

router = APIRouter(tags=["insights"])


@router.get("/api/pipeline")
async def pipeline(runtime: RuntimeDep) -> Board:
    """Applications by stage. Move one with PATCH /api/applications/{id}."""
    return await asyncio.to_thread(runtime.board.board)


@router.get("/api/insights")
async def insights(runtime: RuntimeDep) -> Insights:
    return await asyncio.to_thread(runtime.insights.insights)


@router.post("/api/reports")
async def create_report(runtime: RuntimeDep) -> ReportFile:
    """Writes a self-contained HTML report to the reports folder."""
    return await asyncio.to_thread(runtime.reports.generate)


@router.get("/api/reports/{filename}", response_class=FileResponse)
async def download_report(filename: str, runtime: RuntimeDep) -> FileResponse:
    try:
        path = await asyncio.to_thread(runtime.reports.path_for, filename)
    except KeyError:
        raise HTTPException(status_code=404, detail="Report not found") from None
    return FileResponse(path, media_type="text/html", filename=path.name)


@router.get("/api/reset/scopes")
async def reset_scopes() -> list[ScopeView]:
    return scopes()


@router.post("/api/reset")
async def reset(body: ResetIn, runtime: RuntimeDep) -> ResetResult:
    """Backs up the data folder, then deletes the chosen scope."""
    try:
        return await asyncio.to_thread(runtime.reset.reset, body)
    except ConfirmationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
