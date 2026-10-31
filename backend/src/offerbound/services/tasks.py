"""Background task runner for long commands (scrape, rank, apply).

Each task is an asyncio task whose state is persisted to the `tasks` table and broadcast on
the event bus as `task.updated`. Task functions receive a TaskContext for progress reports.
Cancellation uses asyncio cancellation, so task code should not swallow CancelledError.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict
from sqlalchemy import select, update
from sqlalchemy.orm import Session, sessionmaker

from offerbound.db.models import Task, TaskStatus
from offerbound.db.types import utcnow
from offerbound.services.events import EventBus

log = logging.getLogger(__name__)

TASK_EVENT = "task.updated"
INTERRUPTED = "Interrupted: the app stopped while this task was running."


class TaskNotFoundError(LookupError):
    pass


class TaskView(BaseModel):
    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: str
    kind: str
    status: TaskStatus
    progress: float | None
    message: str | None
    params: dict[str, Any]
    result: Any
    error: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None

    @classmethod
    def from_row(cls, row: Task) -> TaskView:
        return cls.model_validate(row)

    def to_json(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class TaskContext:
    def __init__(self, runner: TaskRunner, task_id: str) -> None:
        self._runner = runner
        self.task_id = task_id

    async def progress(self, fraction: float | None = None, message: str | None = None) -> None:
        """Report progress. `fraction` is clamped to 0..1; None means indeterminate."""
        if fraction is not None:
            fraction = min(max(fraction, 0.0), 1.0)
        await self._runner._update(self.task_id, progress=fraction, message=message)


TaskFn = Callable[[TaskContext], Awaitable[Any]]


class TaskRunner:
    def __init__(
        self, session_factory: sessionmaker[Session], bus: EventBus, max_concurrency: int = 4
    ) -> None:
        self._sessions = session_factory
        self._bus = bus
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._running: dict[str, asyncio.Task[None]] = {}

    # --- queries (sync; safe to call from route handlers) ----------------------------

    def get(self, task_id: str) -> TaskView:
        with self._sessions() as session:
            row = session.get(Task, task_id)
            if row is None:
                raise TaskNotFoundError(task_id)
            return TaskView.from_row(row)

    def list_tasks(self, limit: int = 50, kind: str | None = None) -> list[TaskView]:
        with self._sessions() as session:
            stmt = select(Task).order_by(Task.created_at.desc()).limit(limit)
            if kind is not None:
                stmt = stmt.where(Task.kind == kind)
            return [TaskView.from_row(row) for row in session.scalars(stmt)]

    def recover_interrupted(self) -> int:
        """Mark tasks left queued/running by a previous process as failed. Call at startup."""
        with self._sessions.begin() as session:
            result = session.execute(
                update(Task)
                .where(Task.status.in_([TaskStatus.QUEUED, TaskStatus.RUNNING]))
                .values(status=TaskStatus.FAILED, error=INTERRUPTED, finished_at=utcnow())
            )
            return int(getattr(result, "rowcount", 0) or 0)

    # --- lifecycle -------------------------------------------------------------------

    async def submit(self, kind: str, fn: TaskFn, params: dict[str, Any] | None = None) -> str:
        task_id = uuid.uuid4().hex
        row = await asyncio.to_thread(self._insert, task_id, kind, params or {})
        self._bus.publish(TASK_EVENT, row.to_json())
        handle = asyncio.create_task(self._run(task_id, fn), name=f"offerbound:{kind}:{task_id}")
        self._running[task_id] = handle
        handle.add_done_callback(lambda _: self._running.pop(task_id, None))
        return task_id

    async def cancel(self, task_id: str) -> bool:
        handle = self._running.get(task_id)
        if handle is None or handle.done():
            return False
        handle.cancel()
        return True

    async def wait(self, task_id: str) -> TaskView:
        handle = self._running.get(task_id)
        if handle is not None:
            await asyncio.gather(handle, return_exceptions=True)
        return await asyncio.to_thread(self.get, task_id)

    async def shutdown(self) -> None:
        handles = list(self._running.values())
        for handle in handles:
            handle.cancel()
        await asyncio.gather(*handles, return_exceptions=True)

    # --- internals -------------------------------------------------------------------

    async def _run(self, task_id: str, fn: TaskFn) -> None:
        try:
            async with self._semaphore:
                await self._update(task_id, status=TaskStatus.RUNNING, started_at=utcnow())
                result = await fn(TaskContext(self, task_id))
        except asyncio.CancelledError:
            await self._finish(task_id, TaskStatus.CANCELLED)
            raise
        except Exception as exc:
            log.exception("task %s failed", task_id)
            await self._finish(task_id, TaskStatus.FAILED, error=f"{type(exc).__name__}: {exc}")
        else:
            await self._finish(task_id, TaskStatus.SUCCEEDED, result=result, progress=1.0)

    async def _finish(self, task_id: str, status: TaskStatus, **values: Any) -> None:
        # Shielded so a cancellation can still record its terminal state.
        await asyncio.shield(self._update(task_id, status=status, finished_at=utcnow(), **values))

    async def _update(self, task_id: str, **values: Any) -> None:
        view = await asyncio.to_thread(self._write, task_id, values)
        self._bus.publish(TASK_EVENT, view.to_json())

    def _insert(self, task_id: str, kind: str, params: dict[str, Any]) -> TaskView:
        with self._sessions.begin() as session:
            row = Task(id=task_id, kind=kind, params=params, status=TaskStatus.QUEUED)
            session.add(row)
            session.flush()
            return TaskView.from_row(row)

    def _write(self, task_id: str, values: dict[str, Any]) -> TaskView:
        with self._sessions.begin() as session:
            row = session.get(Task, task_id)
            if row is None:
                raise TaskNotFoundError(task_id)
            for key, value in values.items():
                setattr(row, key, value)
            session.flush()
            return TaskView.from_row(row)
