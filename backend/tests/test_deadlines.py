"""Application deadlines and stale postings: read from sources and postings, shown in
Discover and the pipeline, and closed jobs kept out of ranking (never deleted)."""

from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace

import pytest
from pydantic import BaseModel
from sqlalchemy import select

from rolehawk.db.models import Job, JobScore, Stage
from rolehawk.db.types import utcnow
from rolehawk.fit.ranker import RankParams
from rolehawk.fit.rubric import FitBatch
from rolehawk.insights.board import next_action
from rolehawk.jobs.store import JobQuery, deadline_status
from rolehawk.llm.fake import FakeProvider
from rolehawk.llm.types import LLMRequest
from rolehawk.portals.base import RawJob
from rolehawk.portals.custom.definition import JsonLdDefinition
from rolehawk.portals.custom.engine import postings_in, run_jsonld
from rolehawk.portals.feeds import USAJobs
from rolehawk.portals.text import parse_date
from rolehawk.services.runtime import Runtime
from tests.fits import fit_of
from tests.portal_web import fixture_json
from tests.test_rank import add_jobs, set_prefs

TODAY = date(2026, 10, 31)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2026-11-15", date(2026, 11, 15)),
        ("2026-11-10T23:59:59.9970", date(2026, 11, 10)),
        ("Sun, 15 Nov 2026 00:00:00 GMT", date(2026, 11, 15)),
        ("ASAP", None),
        ("rolling", None),
        ("2026-13-40", None),
        ("0001-01-01", None),
        ("", None),
        (None, None),
    ],
)
def test_deadlines_parse_defensively(value: object, expected: date | None) -> None:
    assert parse_date(value) == expected


def test_deadline_status() -> None:
    assert deadline_status(None, TODAY) is None
    assert deadline_status(TODAY - timedelta(days=1), TODAY) == "closed"
    assert deadline_status(TODAY, TODAY) == "soon"
    assert deadline_status(TODAY + timedelta(days=7), TODAY) == "soon"
    assert deadline_status(TODAY + timedelta(days=8), TODAY) is None


def test_usajobs_and_jsonld_deadlines() -> None:
    usajobs = fixture_json("usajobs.json")["SearchResult"]["SearchResultItems"][0]
    job = USAJobs().normalize(RawJob("1", usajobs))
    assert job.closes_at == date(2026, 11, 10)

    page = (
        '<script type="application/ld+json">{"@type": "JobPosting", "title": "Analyst",'
        ' "url": "https://jobs.example/1", "validThrough": "2026-12-01T00:00:00Z",'
        ' "hiringOrganization": {"name": "Contoso"}}</script>'
    )
    assert postings_in(page)[0]["validThrough"] == "2026-12-01T00:00:00Z"

    definition = JsonLdDefinition(
        id="ct", name="Contoso", source_url="https://jobs.example", list_url="https://jobs.example"
    )
    fetcher = SimpleNamespace(
        get=lambda _url: SimpleNamespace(text=page, url="https://jobs.example")
    )
    jobs, _ = run_jsonld(definition, fetcher)  # type: ignore[arg-type]  # a minimal fake Fetcher
    assert jobs[0].closes_at == date(2026, 12, 1)


def test_next_actions_mention_deadlines() -> None:
    soon, later, passed = TODAY + timedelta(days=3), TODAY + timedelta(days=30), TODAY
    assert next_action(Stage.SAVED, 0, False, 0, soon, TODAY) == "Write your application by Nov 3"
    assert next_action(Stage.SAVED, 0, False, 0, later, TODAY) == "Write your application"
    assert next_action(Stage.APPLYING, 0, True, 0, soon, TODAY) == (
        "Submit by Nov 3, then mark as applied"
    )
    assert next_action(Stage.SAVED, 0, False, 0, passed - timedelta(days=1), TODAY) == (
        "The posting closed Oct 30: check it's still open"
    )


pytestmark = pytest.mark.anyio


def _set(runtime: Runtime, job_id: int, **values: object) -> None:
    with runtime.sessions.begin() as session:
        job = session.get(Job, job_id)
        assert job is not None
        for key, value in values.items():
            setattr(job, key, value)


async def test_listing_flags_deadlines_and_age_and_hides_closed_jobs(runtime: Runtime) -> None:
    today = utcnow().date()
    soon, closed, old, plain = add_jobs(runtime, 4)
    _set(runtime, soon, closes_at=today + timedelta(days=2))
    _set(runtime, closed, closes_at=today - timedelta(days=1))
    _set(runtime, old, posted_at=utcnow() - timedelta(days=45))

    page = runtime.jobs.list(JobQuery())
    rows = {r.id: r for r in page.items}
    assert closed not in rows
    assert rows[soon].deadline == "soon"
    assert rows[old].stale_days == 45
    assert rows[plain].deadline is None
    assert rows[plain].stale_days is None
    assert page.stats.closed == 1

    shown = runtime.jobs.list(JobQuery(show="closed")).items
    assert [r.id for r in shown] == [closed]
    assert shown[0].deadline == "closed"


async def test_ranking_skips_closed_jobs_and_reads_stated_deadlines(
    runtime: Runtime, fake: FakeProvider
) -> None:
    set_prefs(runtime)
    today = utcnow().date()
    open_job, closed, stated = add_jobs(runtime, 3)
    _set(runtime, closed, closes_at=today - timedelta(days=3))
    _set(runtime, stated, closes_at=today + timedelta(days=20))  # from the source: it wins

    plan = runtime.ranker.plan(RankParams())
    assert plan.candidates == 2
    assert plan.filtered.closed == 1

    deadline = (today + timedelta(days=5)).isoformat()

    def handler(_request: LLMRequest, _schema: type[BaseModel]) -> BaseModel:
        return FitBatch(
            jobs=[
                fit_of(open_job, 80).model_copy(update={"deadline": deadline}),
                fit_of(stated, 80).model_copy(update={"deadline": deadline}),
            ]
        )

    async def progress(_f: float | None, _m: str | None) -> None:
        return None

    fake.structured_handler = handler
    await runtime.ranker.run(RankParams(), progress)
    with runtime.sessions() as session:
        closes = {i: c for i, c in session.execute(select(Job.id, Job.closes_at)).all()}
        assert session.scalar(select(JobScore.id).where(JobScore.job_id == closed)) is None
    assert closes[open_job] == date.fromisoformat(deadline)
    assert closes[stated] == today + timedelta(days=20)


def test_model_deadlines_are_kept_only_when_they_are_dates() -> None:
    assert fit_of(1, 50).model_copy(update={"deadline": "ASAP"}).clamped().deadline == ""
    assert fit_of(1, 50).model_copy(update={"deadline": "2026-11-15"}).clamped().deadline == (
        "2026-11-15"
    )
