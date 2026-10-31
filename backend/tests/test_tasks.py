import asyncio

import pytest
from sqlalchemy.orm import Session, sessionmaker

from offerbound.db.models import Task, TaskStatus
from offerbound.services.events import EventBus
from offerbound.services.selftest import make_selftest
from offerbound.services.tasks import (
    INTERRUPTED,
    TASK_EVENT,
    TaskContext,
    TaskNotFoundError,
    TaskRunner,
)

pytestmark = pytest.mark.anyio


async def test_success_records_progress_result_and_events(
    sessions: sessionmaker[Session],
) -> None:
    bus = EventBus()
    runner = TaskRunner(sessions, bus)
    async with bus.subscribe() as queue:
        task_id = await runner.submit("selftest", make_selftest(steps=3, delay_s=0), {"steps": 3})
        view = await runner.wait(task_id)
        events = [queue.get_nowait() for _ in range(queue.qsize())]

    assert view.status is TaskStatus.SUCCEEDED
    assert view.result == {"steps": 3}
    assert view.progress == 1.0
    assert view.started_at is not None
    assert view.finished_at is not None
    assert view.params == {"steps": 3}

    assert {e.type for e in events} == {TASK_EVENT}
    statuses = [e.data["status"] for e in events]
    assert statuses[0] == "queued"
    assert statuses[1] == "running"
    assert statuses[-1] == "succeeded"
    messages = [e.data["message"] for e in events if e.data["message"]]
    assert "Step 3 of 3" in messages
    assert [e.id for e in events] == sorted(e.id for e in events)


async def test_failure_is_isolated_and_recorded(sessions: sessionmaker[Session]) -> None:
    runner = TaskRunner(sessions, EventBus())

    async def boom(ctx: TaskContext) -> None:
        raise RuntimeError("portal exploded")

    failed = await runner.wait(await runner.submit("scrape", boom))
    ok = await runner.wait(await runner.submit("selftest", make_selftest(1, 0)))
    assert failed.status is TaskStatus.FAILED
    assert failed.error == "RuntimeError: portal exploded"
    assert ok.status is TaskStatus.SUCCEEDED


async def test_cancel(sessions: sessionmaker[Session]) -> None:
    runner = TaskRunner(sessions, EventBus())
    started = asyncio.Event()

    async def forever(ctx: TaskContext) -> None:
        started.set()
        await asyncio.sleep(3600)

    task_id = await runner.submit("rank", forever)
    await started.wait()
    assert await runner.cancel(task_id) is True
    view = await runner.wait(task_id)
    assert view.status is TaskStatus.CANCELLED
    assert view.finished_at is not None
    assert await runner.cancel(task_id) is False


async def test_concurrency_limit(sessions: sessionmaker[Session]) -> None:
    runner = TaskRunner(sessions, EventBus(), max_concurrency=2)
    active = peak = 0

    async def work(ctx: TaskContext) -> None:
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.02)
        active -= 1

    ids = [await runner.submit("x", work) for _ in range(5)]
    views = [await runner.wait(i) for i in ids]
    assert peak == 2
    assert all(v.status is TaskStatus.SUCCEEDED for v in views)


async def test_progress_is_clamped(sessions: sessionmaker[Session]) -> None:
    runner = TaskRunner(sessions, EventBus())
    seen: list[float | None] = []

    async def report(ctx: TaskContext) -> None:
        await ctx.progress(5.0)
        seen.append(runner.get(ctx.task_id).progress)
        await ctx.progress(-1.0, "rewind")
        seen.append(runner.get(ctx.task_id).progress)

    await runner.wait(await runner.submit("x", report))
    assert seen == [1.0, 0.0]


async def test_shutdown_cancels_running(sessions: sessionmaker[Session]) -> None:
    runner = TaskRunner(sessions, EventBus())

    async def forever(ctx: TaskContext) -> None:
        await asyncio.sleep(3600)

    task_id = await runner.submit("x", forever)
    await asyncio.sleep(0.05)
    await runner.shutdown()
    assert runner.get(task_id).status is TaskStatus.CANCELLED


def test_recover_interrupted_and_queries(sessions: sessionmaker[Session]) -> None:
    with sessions.begin() as session:
        session.add(Task(id="a" * 32, kind="scrape", status=TaskStatus.RUNNING, params={}))
        session.add(Task(id="b" * 32, kind="rank", status=TaskStatus.SUCCEEDED, params={}))
    runner = TaskRunner(sessions, EventBus())
    assert runner.recover_interrupted() == 1
    recovered = runner.get("a" * 32)
    assert recovered.status is TaskStatus.FAILED
    assert recovered.error == INTERRUPTED
    assert runner.get("b" * 32).status is TaskStatus.SUCCEEDED
    assert [t.kind for t in runner.list_tasks(kind="rank")] == ["rank"]
    assert len(runner.list_tasks()) == 2
    with pytest.raises(TaskNotFoundError):
        runner.get("missing")
