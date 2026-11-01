from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict

from rolehawk.api.deps import RuntimeDep
from rolehawk.apply.followup import (
    FOLLOW_UP_DAYS,
    STALE_DAYS,
    Channel,
    ClosedStale,
    CloseStaleIn,
    FollowUpDraft,
    FollowUpIn,
    FollowUpLimitError,
    FollowUpView,
    NoDocumentsError,
    NotWaitingError,
    QuietApplication,
)
from rolehawk.db.models import FollowUpChannel

router = APIRouter(tags=["followups"])


class DraftIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    channel: Channel = FollowUpChannel.EMAIL


def _refused(exc: Exception) -> HTTPException:
    message = getattr(exc, "user_message", str(exc))
    return HTTPException(status_code=409, detail=message)


@router.get("/api/followups")
async def quiet(
    runtime: RuntimeDep, days: int = Query(default=FOLLOW_UP_DAYS, ge=1, le=365)
) -> list[QuietApplication]:
    """Waiting applications quiet long enough for a follow-up (at most two each)."""
    return await asyncio.to_thread(runtime.followups.quiet, days)


@router.get("/api/followups/stale")
async def stale(
    runtime: RuntimeDep, days: int = Query(default=STALE_DAYS, ge=7, le=730)
) -> list[QuietApplication]:
    return await asyncio.to_thread(runtime.followups.stale, days)


@router.post("/api/followups/close-stale")
async def close_stale(body: CloseStaleIn, runtime: RuntimeDep) -> ClosedStale:
    """Move the chosen long-quiet applications to Ghosted."""
    return await asyncio.to_thread(runtime.followups.close_stale, body.application_ids)


@router.get("/api/applications/{application_id}/followups")
async def history(application_id: int, runtime: RuntimeDep) -> list[FollowUpView]:
    return await asyncio.to_thread(runtime.followups.history, application_id)


@router.post("/api/applications/{application_id}/followups/draft")
async def draft(application_id: int, body: DraftIn, runtime: RuntimeDep) -> FollowUpDraft:
    """A draft from the documents already sent. Nothing is sent."""
    try:
        return await runtime.followups.draft(application_id, body.channel)
    except (FollowUpLimitError, NotWaitingError, NoDocumentsError) as exc:
        raise _refused(exc) from None
    except KeyError:
        raise HTTPException(status_code=404, detail="Unknown application") from None


@router.post("/api/applications/{application_id}/followups", status_code=201)
async def log(application_id: int, body: FollowUpIn, runtime: RuntimeDep) -> FollowUpView:
    """Record a follow-up the user sent."""
    try:
        return await asyncio.to_thread(runtime.followups.log, application_id, body)
    except (FollowUpLimitError, NotWaitingError) as exc:
        raise _refused(exc) from None
    except KeyError:
        raise HTTPException(status_code=404, detail="Unknown application") from None
