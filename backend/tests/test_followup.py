"""Follow-ups on quiet applications (drafts only, at most two, from what was sent) and
closing long-quiet ones as no response."""

from __future__ import annotations

from datetime import timedelta
from typing import cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel
from sqlalchemy import select

from offerbound.apply.followup import (
    FollowUpDraftOut,
    FollowUpIn,
    FollowUpLimitError,
    NotWaitingError,
)
from offerbound.apply.service import ApplyParams
from offerbound.db.models import Application, FollowUpChannel, Stage, StageEvent
from offerbound.db.types import utcnow
from offerbound.llm.fake import FakeProvider
from offerbound.llm.types import LLMRequest
from offerbound.services.runtime import Runtime
from tests.test_api_setup import wait_for_task
from tests.test_apply import Scripted, noop_progress, ready

pytestmark = pytest.mark.anyio


async def applied(runtime: Runtime, fake: FakeProvider, days_ago: int) -> int:
    """An application with documents, sent `days_ago` days ago."""
    job_id = ready(runtime, fake, Scripted())
    result = await runtime.applications.apply(ApplyParams(job_id=job_id), noop_progress)
    assert result.application_id is not None
    back_date(runtime, result.application_id, days_ago)
    return result.application_id


def back_date(runtime: Runtime, application_id: int, days_ago: int) -> None:
    when = utcnow() - timedelta(days=days_ago)
    with runtime.sessions.begin() as session:
        app = session.get(Application, application_id)
        assert app is not None
        app.stage, app.applied_at, app.stage_changed_at = Stage.APPLIED, when, when


def note(body: str = "Thanks again; any news on timing?") -> FollowUpIn:
    return FollowUpIn(channel=FollowUpChannel.EMAIL, subject="Frontend Engineer", body=body)


async def test_quiet_applications_and_the_two_follow_up_limit(
    runtime: Runtime, fake: FakeProvider
) -> None:
    quiet_id = await applied(runtime, fake, 12)
    recent_id = await applied(runtime, fake, 4)
    followups = runtime.followups

    rows = followups.quiet()
    assert [r.application_id for r in rows] == [quiet_id]
    assert rows[0].quiet_days == 12
    assert recent_id not in [r.application_id for r in followups.quiet()]

    followups.log(quiet_id, note())
    assert followups.quiet() == []  # the clock restarted
    assert [r.follow_ups for r in followups.quiet(days=0) if r.application_id == quiet_id] == [1]
    followups.log(quiet_id, note("One more nudge on timing?"))
    with pytest.raises(FollowUpLimitError):
        followups.log(quiet_id, note())
    assert [f.body for f in followups.history(quiet_id)] == [
        "Thanks again; any news on timing?",
        "One more nudge on timing?",
    ]

    card = next(
        c
        for col in runtime.board.board().columns
        for c in col.cards
        if c.application_id == quiet_id
    )
    assert card.follow_ups == 2
    assert card.follow_up_due is False
    assert card.next_action == "Wait for a reply"  # the last note went out today


async def test_drafts_use_only_what_was_sent_and_say_what_to_check(
    runtime: Runtime, fake: FakeProvider
) -> None:
    app_id = await applied(runtime, fake, 14)
    prompts: list[str] = []

    def handler(request: LLMRequest, schema: type[BaseModel]) -> BaseModel:
        assert schema is FollowUpDraftOut
        prompts.append(request.messages[-1].text)
        return FollowUpDraftOut(
            subject="Frontend Engineer \N{EM DASH} following up",
            body="Just checking in \N{EM DASH} I lifted conversion 40% at Northwind. Any news?",
        )

    fake.structured_handler = handler
    draft = await runtime.followups.draft(app_id, FollowUpChannel.EMAIL)

    assert "<sent_documents>" in prompts[0]
    assert "Lifted checkout conversion 12% with a redesign" in prompts[0]
    assert '<untrusted_content source="job">' in prompts[0]
    assert draft.subject == "Frontend Engineer, following up"
    assert "\N{EM DASH}" not in draft.body
    assert draft.issues == [
        "40% isn't in the documents you sent",
        'It has filler like "just checking in"',
    ]

    linked = await runtime.followups.draft(app_id, FollowUpChannel.LINKEDIN)
    assert linked.subject is None


async def test_only_waiting_applications_get_follow_ups(
    runtime: Runtime, fake: FakeProvider
) -> None:
    app_id = await applied(runtime, fake, 20)
    with runtime.sessions.begin() as session:
        app = session.get(Application, app_id)
        assert app is not None
        app.stage = Stage.APPLYING
    with pytest.raises(NotWaitingError):
        runtime.followups.log(app_id, note())
    with pytest.raises(NotWaitingError):
        await runtime.followups.draft(app_id)


async def test_long_quiet_applications_close_as_no_response(
    runtime: Runtime, fake: FakeProvider
) -> None:
    old = await applied(runtime, fake, 75)
    newer = await applied(runtime, fake, 20)
    assert [r.application_id for r in runtime.followups.stale()] == [old]

    result = runtime.followups.close_stale([old, newer, 99_999])
    assert result.closed == 1
    with runtime.sessions() as session:
        stages = dict((a.id, a.stage) for a in session.scalars(select(Application)))
        event = session.scalars(
            select(StageEvent)
            .where(StageEvent.application_id == old)
            .order_by(StageEvent.id.desc())
        ).first()
    assert stages[old] is Stage.GHOSTED
    assert stages[newer] is Stage.APPLIED
    assert event is not None
    assert event.evidence == "No reply in 75 days (0 follow-ups sent)"


def test_follow_up_api(client: TestClient, fake: FakeProvider) -> None:
    runtime: Runtime = cast(FastAPI, client.app).state.runtime
    job_id = ready(runtime, fake, Scripted())
    started = client.post("/api/apply", json={"job_id": job_id}).json()
    result = cast(dict[str, int], wait_for_task(client, started["task_id"])["result"])
    app_id = result["application_id"]
    back_date(runtime, app_id, 30)
    assert [r["application_id"] for r in client.get("/api/followups").json()] == [app_id]

    fake.structured_handler = lambda _r, _s: FollowUpDraftOut(subject="", body="Any news?")
    drafted = client.post(f"/api/applications/{app_id}/followups/draft", json={"channel": "portal"})
    assert drafted.status_code == 200
    assert drafted.json()["body"] == "Any news?"

    for _ in range(2):
        sent = client.post(
            f"/api/applications/{app_id}/followups", json={"channel": "portal", "body": "Any news?"}
        )
        assert sent.status_code == 201
    third = client.post(f"/api/applications/{app_id}/followups", json={"body": "Again?"})
    assert third.status_code == 409
    assert "already sent 2 follow-ups" in third.json()["detail"]
    assert len(client.get(f"/api/applications/{app_id}/followups").json()) == 2

    closed = client.post("/api/followups/close-stale", json={"application_ids": [app_id]})
    assert closed.json() == {"closed": 0}  # quiet for 0 days since the last note
