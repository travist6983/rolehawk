"""Learning from results: resolved applications are compared and preference edits come back
as pending proposals; nothing changes until the user accepts."""

from __future__ import annotations

from datetime import timedelta

import pytest
from pydantic import BaseModel

from offerbound.db.models import Application, ProposalOp, Stage, StageEvent, StageEventSource
from offerbound.db.types import utcnow
from offerbound.insights.calibration import (
    CalibrationOut,
    Finding,
    NotEnoughResultsError,
    PreferenceEdit,
)
from offerbound.llm.fake import FakeProvider
from offerbound.llm.types import LLMRequest
from offerbound.memory.files import MemoryTarget
from offerbound.services.runtime import Runtime
from tests.test_rank import add_jobs

pytestmark = pytest.mark.anyio


def application(runtime: Runtime, job_id: int, stage: Stage, *history: Stage) -> int:
    applied = utcnow() - timedelta(days=30)
    with runtime.sessions.begin() as session:
        app = Application(job_id=job_id, stage=stage, applied_at=applied, stage_changed_at=applied)
        session.add(app)
        session.flush()
        for i, to_stage in enumerate(history):
            session.add(
                StageEvent(
                    application_id=app.id,
                    to_stage=to_stage,
                    source=StageEventSource.USER,
                    created_at=applied + timedelta(days=5 + i),
                )
            )
        return app.id


def seed(runtime: Runtime) -> list[int]:
    jobs = add_jobs(runtime, 5)
    return [
        application(runtime, jobs[0], Stage.INTERVIEW, Stage.APPLIED, Stage.INTERVIEW),
        application(runtime, jobs[1], Stage.REJECTED, Stage.APPLIED, Stage.SCREEN, Stage.REJECTED),
        application(runtime, jobs[2], Stage.REJECTED, Stage.APPLIED, Stage.REJECTED),
        application(runtime, jobs[3], Stage.GHOSTED, Stage.APPLIED, Stage.GHOSTED),
        application(runtime, jobs[4], Stage.APPLIED, Stage.APPLIED),  # still waiting
    ]


async def test_results_are_counted_from_the_furthest_stage_reached(runtime: Runtime) -> None:
    ids = seed(runtime)
    rows = {r.application_id: r for r in runtime.calibration.resolved()}
    assert set(rows) == set(ids[:4])
    assert [rows[i].result for i in ids[:4]] == ["interview", "interview", "rejected", "no reply"]
    assert rows[ids[0]].days_to_reply == 6  # applied, then the interview invite
    status = runtime.calibration.status()
    assert (status.resolved, status.positive, status.negative, status.ready) == (4, 2, 2, True)


async def test_too_few_results_is_a_clear_error(runtime: Runtime) -> None:
    jobs = add_jobs(runtime, 2)
    application(runtime, jobs[0], Stage.REJECTED)
    assert runtime.calibration.status().ready is False
    with pytest.raises(NotEnoughResultsError):
        await runtime.calibration.run()


async def test_patterns_and_preference_proposals(runtime: Runtime, fake: FakeProvider) -> None:
    ids = seed(runtime)
    prompts: list[str] = []

    def handler(request: LLMRequest, schema: type[BaseModel]) -> BaseModel:
        assert schema is CalibrationOut
        prompts.append(request.messages[-1].text)
        return CalibrationOut(
            findings=[
                Finding(
                    pattern="Both interviews came from hybrid roles in Denver.",
                    application_ids=[ids[0], ids[1], 999],
                    strength="worth watching",
                )
            ],
            edits=[
                PreferenceEdit(
                    op=ProposalOp.ADD,
                    section="Target titles",
                    text="Analytics Engineer",
                    old_text=None,
                    reason="Your two interviews were analytics engineering roles.",
                ),
                PreferenceEdit(
                    op=ProposalOp.REPLACE,
                    section=None,
                    text="x",
                    old_text=None,
                    reason="missing old line",
                ),
            ],
        )

    fake.structured_handler = handler
    before = runtime.memory.files.read(MemoryTarget.PREFERENCES)
    result = await runtime.calibration.run()

    assert '<untrusted_content source="resolved_applications">' in prompts[0]
    assert "Result: interview after 6 days" in prompts[0]
    assert result.resolved == 4
    assert result.findings[0].application_ids == [ids[0], ids[1]]
    assert [(p.text, p.source, p.status) for p in result.proposals] == [
        ("Analytics Engineer", "calibration", "pending")
    ]
    assert runtime.memory.files.read(MemoryTarget.PREFERENCES) == before  # until accepted
