from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from offerbound.api.deps import RuntimeDep
from offerbound.services import selftest
from offerbound.services.tasks import TaskNotFoundError, TaskView

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


class SelftestIn(BaseModel):
    steps: int = Field(default=5, ge=1, le=50)
    delay_s: float = Field(default=0.2, ge=0, le=5)


class TaskRef(BaseModel):
    id: str


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


@router.post("/selftest", status_code=202)
async def start_selftest(runtime: RuntimeDep, body: SelftestIn | None = None) -> TaskRef:
    body = body or SelftestIn()
    task_id = await runtime.tasks.submit(
        selftest.KIND, selftest.make_selftest(body.steps, body.delay_s), body.model_dump()
    )
    return TaskRef(id=task_id)
