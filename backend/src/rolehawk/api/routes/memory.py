from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException

from rolehawk.api.deps import RuntimeDep
from rolehawk.db.models import MemoryProposalStatus
from rolehawk.memory.edits import EditConflictError
from rolehawk.memory.proposals import (
    MemorySnapshot,
    ProposalNotFoundError,
    ProposalStateError,
    ProposalView,
)

router = APIRouter(prefix="/api/memory", tags=["memory"])


@router.get("")
async def get_memory(runtime: RuntimeDep) -> MemorySnapshot:
    return await asyncio.to_thread(runtime.memory.snapshot)


@router.get("/proposals")
async def list_proposals(
    runtime: RuntimeDep, status: MemoryProposalStatus | None = MemoryProposalStatus.PENDING
) -> list[ProposalView]:
    return await asyncio.to_thread(runtime.memory.list_proposals, status)


@router.post("/proposals/{proposal_id}/accept")
async def accept_proposal(proposal_id: int, runtime: RuntimeDep) -> ProposalView:
    try:
        return await asyncio.to_thread(runtime.memory.accept, proposal_id)
    except ProposalNotFoundError:
        raise HTTPException(status_code=404, detail="Proposal not found") from None
    except ProposalStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    except EditConflictError as exc:
        detail = f"The file changed since this was proposed ({exc}). Edit it by hand instead."
        raise HTTPException(status_code=409, detail=detail) from None


@router.post("/proposals/{proposal_id}/reject")
async def reject_proposal(proposal_id: int, runtime: RuntimeDep) -> ProposalView:
    try:
        return await asyncio.to_thread(runtime.memory.reject, proposal_id)
    except ProposalNotFoundError:
        raise HTTPException(status_code=404, detail="Proposal not found") from None
    except ProposalStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
