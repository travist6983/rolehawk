from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from rolehawk.api.deps import RuntimeDep
from rolehawk.insights.board import Board
from rolehawk.insights.calibration import (
    CalibrationResult,
    CalibrationStatus,
    NotEnoughResultsError,
)
from rolehawk.insights.service import ReportFile
from rolehawk.insights.stats import Insights
from rolehawk.services.reset import ConfirmationError, ResetIn, ResetResult, ScopeView, scopes

router = APIRouter(tags=["insights"])


@router.get("/api/pipeline")
async def pipeline(runtime: RuntimeDep) -> Board:
    """Applications by stage. Move one with PATCH /api/applications/{id}."""
    return await asyncio.to_thread(runtime.board.board)


@router.get("/api/insights")
async def insights(runtime: RuntimeDep) -> Insights:
    return await asyncio.to_thread(runtime.insights.insights)


@router.get("/api/calibration")
async def calibration_status(runtime: RuntimeDep) -> CalibrationStatus:
    """Applications with a result, and whether there are enough to learn from."""
    return await asyncio.to_thread(runtime.calibration.status)


@router.post("/api/calibration")
async def calibrate(runtime: RuntimeDep) -> CalibrationResult:
    """Patterns in what got interviews, with preference edits as pending proposals."""
    try:
        return await runtime.calibration.run()
    except NotEnoughResultsError:
        raise HTTPException(status_code=409, detail=NotEnoughResultsError.user_message) from None


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
