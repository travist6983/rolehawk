from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from rolehawk.api.deps import RuntimeDep
from rolehawk.services.tasks import TaskNotFoundError, TaskView

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


class CancelOut(BaseModel):
    cancelled: bool


@router.get("")
def list_tasks(
    runtime: RuntimeDep, limit: int = Query(50, ge=1, le=500), kind: str | None = None
) -> list[TaskView]:
    return runtime.tasks.list_tasks(limit=limit, kind=kind)


@router.get("/{task_id}")
def get_task(task_id: str, runtime: RuntimeDep) -> TaskView:
    try:
        return runtime.tasks.get(task_id)
    except TaskNotFoundError:
        raise HTTPException(status_code=404, detail="Task not found") from None


@router.post("/{task_id}/cancel")
async def cancel_task(task_id: str, runtime: RuntimeDep) -> CancelOut:
    try:
        await asyncio.to_thread(runtime.tasks.get, task_id)
    except TaskNotFoundError:
        raise HTTPException(status_code=404, detail="Task not found") from None
    return CancelOut(cancelled=await runtime.tasks.cancel(task_id))
