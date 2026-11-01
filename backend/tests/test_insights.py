"""Pipeline board, Insights stats, the self-contained HTML report, and /reset."""

from __future__ import annotations

import itertools
import json
import re
import zipfile
from datetime import timedelta
from pathlib import Path
from typing import cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from rolehawk.db.models import (
    Application,
    ChatSession,
    Company,
    Job,
    JobScore,
    LLMCall,
    Stage,
    StageEvent,
    StageEventSource,
    Task,
    TaskStatus,
)
from rolehawk.db.types import utcnow
from rolehawk.insights.board import next_action
from rolehawk.memory.files import MemoryTarget
from rolehawk.services.reset import ConfirmationError, ResetIn, ResetScope
from rolehawk.services.runtime import Runtime

pytestmark = pytest.mark.anyio
_ids = itertools.count()


def job(runtime: Runtime, company: str = "Globex", portal: str = "greenhouse") -> int:
    n = next(_ids)
    with runtime.sessions.begin() as session:
        row = Job(
            portal_id=portal,
            external_id=f"j{n}",
            url=f"https://example.com/{n}",
            company=company,
            title=f"Engineer {n}",
            location="Remote",
            description="Build things.",
            scraped_at=utcnow(),
            hash=f"h{n}",
        )
        session.add(row)
        session.flush()
        return row.id


def application(
    runtime: Runtime,
    path: list[Stage],
    *,
    portal: str = "greenhouse",
    company: str = "Globex",
    days_ago: int = 0,
    score: int | None = None,
) -> int:
    """An application that moved through `path` (its current stage is the last one)."""
    job_id = job(runtime, company, portal)
    when = utcnow() - timedelta(days=days_ago)
    with runtime.sessions.begin() as session:
        if score is not None:
            session.add(
                JobScore(job_id=job_id, score=score, reasons=[], must_have_gaps=[], model="m")
            )
        app = Application(job_id=job_id, stage=path[-1], stage_changed_at=when)
        if Stage.APPLIED in path:
            app.applied_at = when
        session.add(app)
        session.flush()
        previous = None
        for stage in path:
            session.add(
                StageEvent(
                    application_id=app.id,
                    from_stage=previous,
                    to_stage=stage,
                    source=StageEventSource.USER,
                    created_at=when,
                )
            )
            previous = stage
        return app.id


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _exists(path: Path) -> bool:
    return path.is_file()


# --- board --------------------------------------------------------------------------------


def test_next_actions() -> None:
    assert next_action(Stage.SAVED, 0, False, 0) == "Write your application"
    assert next_action(Stage.APPLYING, 0, False, 0) == "Write your CV and cover letter"
    assert next_action(Stage.APPLYING, 0, True, 2) == "Check 2 flagged lines, then submit"
    assert next_action(Stage.APPLYING, 0, True, 0) == "Submit, then mark as applied"
    assert next_action(Stage.APPLIED, 3, True, 0) == "Wait for a reply"
    assert next_action(Stage.APPLIED, 9, True, 0) == "Wait for a reply"
    assert next_action(Stage.APPLIED, 10, True, 0) == "Send a follow-up"
    assert next_action(Stage.APPLIED, 12, True, 0, follow_ups=1) == "Send a second follow-up"
    assert next_action(Stage.APPLIED, 12, True, 0, follow_ups=2) == (
        "No reply after two follow-ups: close it as no response?"
    )
    assert next_action(Stage.REJECTED, 9, True, 0) is None


async def test_board_groups_by_stage_with_details(runtime: Runtime) -> None:
    saved = application(runtime, [Stage.SAVED], score=72)
    applying = application(runtime, [Stage.SAVED, Stage.APPLYING])
    folder = runtime.paths.generated_documents / str(applying)
    folder.mkdir(parents=True)
    (folder / "application.json").write_text(json.dumps({"flags": [{}, {}]}))
    applied = application(runtime, [Stage.APPLIED], days_ago=10)
    rejected = application(runtime, [Stage.APPLIED, Stage.INTERVIEW, Stage.REJECTED])

    board = runtime.board.board()
    columns = {c.id: c for c in board.columns}
    assert list(columns) == [
        "saved",
        "applying",
        "applied",
        "screen",
        "interview",
        "offer",
        "closed",
    ]
    assert board.total == 4
    (saved_card,) = columns["saved"].cards
    assert (saved_card.application_id, saved_card.score) == (saved, 72)
    (applying_card,) = columns["applying"].cards
    assert (applying_card.application_id, applying_card.has_documents, applying_card.flags) == (
        applying,
        True,
        2,
    )
    (applied_card,) = columns["applied"].cards
    assert applied_card.application_id == applied
    assert applied_card.days_in_stage == 10
    assert applied_card.next_action == "Send a follow-up"
    assert [c.application_id for c in columns["closed"].cards] == [rejected]
    assert columns["closed"].stages == [Stage.REJECTED, Stage.WITHDRAWN, Stage.GHOSTED]


# --- stats --------------------------------------------------------------------------------


async def test_insights_funnel_sources_weeks_and_spend(runtime: Runtime) -> None:
    application(runtime, [Stage.SAVED])
    application(runtime, [Stage.SAVED, Stage.APPLYING])
    application(runtime, [Stage.APPLIED], portal="lever", days_ago=2)
    application(runtime, [Stage.APPLIED, Stage.SCREEN], portal="lever", days_ago=9)
    application(runtime, [Stage.APPLIED, Stage.INTERVIEW, Stage.REJECTED], days_ago=9)
    application(runtime, [Stage.APPLIED, Stage.REJECTED], portal="ashby", days_ago=20)
    application(runtime, [Stage.APPLIED, Stage.GHOSTED], portal="ashby", days_ago=40)
    with runtime.sessions.begin() as session:
        for command, cost in [("rank", 0.05), ("rank", 0.03), ("apply", 0.4)]:
            session.add(
                LLMCall(command=command, provider="fake", model="m", input_tokens=1,
                        output_tokens=1, cost_usd=cost)
            )  # fmt: skip

    data = runtime.insights.insights()
    funnel = {s.stage: s.count for s in data.funnel}
    assert funnel == {
        Stage.SAVED: 7,
        Stage.APPLYING: 6,
        Stage.APPLIED: 5,
        Stage.SCREEN: 2,
        Stage.INTERVIEW: 1,
        Stage.OFFER: 0,
    }
    assert data.funnel[2].rate_from_previous == pytest.approx(5 / 6)
    sources = {s.source: (s.applied, s.responses) for s in data.by_source}
    assert sources == {"Lever": (2, 1), "Greenhouse": (1, 1), "Ashby": (2, 1)}
    assert data.by_source[0].source == "Greenhouse"  # 100% first
    t = data.totals
    assert (t.applications, t.active, t.applied, t.responses, t.interviews) == (7, 4, 5, 3, 1)
    assert t.response_rate == pytest.approx(3 / 5)
    assert len(data.weekly) == 12
    assert sum(w.applied for w in data.weekly) == 5  # 12 weeks reach back past 40 days
    assert sum(w.jobs_found for w in data.weekly) == 7
    assert data.weekly[-1].week_start <= utcnow().date().isoformat()
    assert [(line.command, line.cost_usd, line.calls) for line in data.spend.by_command] == [
        ("apply", 0.4, 1),
        ("rank", 0.08, 2),
    ]
    assert data.spend.month_to_date_usd == pytest.approx(0.48)


async def test_insights_with_no_data(runtime: Runtime) -> None:
    data = runtime.insights.insights()
    assert data.totals.response_rate is None
    assert [s.count for s in data.funnel] == [0] * 6
    assert data.by_source == []


# --- the HTML report ----------------------------------------------------------------------


async def test_report_is_self_contained_and_escaped(runtime: Runtime) -> None:
    application(runtime, [Stage.APPLIED, Stage.SCREEN], company='<img src="https://x.test/p">')
    application(runtime, [Stage.SAVED], company="Initech")
    report = runtime.reports.generate()
    path = Path(report.path)
    assert path.parent == runtime.paths.reports
    html = _text(path)

    assert "Content-Security-Policy" in html
    assert "default-src 'none'" in html
    assert '<img src="https://x.test' not in html
    assert "&lt;img src=&quot;https://x.test/p&quot;&gt;" in html
    # Nothing in the markup can make a request.
    assert not re.search(r"""(src|href)\s*=\s*["']?(https?:)?//""", html)
    assert "@import" not in html
    assert html.count("<svg") == 4
    assert "Initech" in html
    assert 'id="apps"' in html
    assert runtime.reports.path_for(report.filename) == path
    with pytest.raises(KeyError):
        runtime.reports.path_for("../rolehawk.db")


# --- reset --------------------------------------------------------------------------------


async def test_reset_needs_the_scope_typed(runtime: Runtime) -> None:
    with pytest.raises(ConfirmationError, match='Type "everything"'):
        runtime.reset.reset(ResetIn(scope=ResetScope.EVERYTHING, confirm="yes"))
    assert not any(runtime.paths.backups.glob("*reset*"))


async def test_reset_jobs_keeps_applied_jobs(runtime: Runtime) -> None:
    applied = application(runtime, [Stage.APPLIED], score=80)
    job(runtime)
    result = runtime.reset.reset(ResetIn(scope=ResetScope.JOBS, confirm="Jobs "))
    assert _exists(Path(result.backup))
    assert "reset-jobs" in Path(result.backup).name
    assert result.removed == {"job scores": 1, "jobs": 1}
    with runtime.sessions() as session:
        app = session.get(Application, applied)
        assert app is not None
        assert session.get(Job, app.job_id) is not None
        assert session.scalar(select(func.count()).select_from(JobScore)) == 0


async def test_reset_profile(runtime: Runtime) -> None:
    runtime.profiles.save_preferences(
        runtime.profiles.load_preferences().model_copy(update={"target_titles": ["Data Analyst"]})
    )
    runtime.memory.files.write(MemoryTarget.FACTS, "# Facts\n\n- Speaks Klingon\n")
    (runtime.paths.source_documents / "cv.pdf").write_bytes(b"%PDF")
    application(runtime, [Stage.APPLIED])

    result = runtime.reset.reset(ResetIn(scope=ResetScope.PROFILE, confirm="profile"))
    assert result.removed["search targets"] == 1
    assert result.removed["files"] == 1
    assert "Klingon" not in runtime.memory.files.read(MemoryTarget.FACTS)
    assert runtime.profiles.load_preferences().target_titles == []
    with runtime.sessions() as session:
        assert session.scalar(select(func.count()).select_from(Application)) == 1  # untouched


async def test_reset_applications_and_documents(runtime: Runtime) -> None:
    app_id = application(runtime, [Stage.APPLIED, Stage.SCREEN])
    folder = runtime.paths.generated_documents / str(app_id)
    folder.mkdir(parents=True)
    (folder / "cv.pdf").write_bytes(b"%PDF")

    docs = runtime.reset.reset(ResetIn(scope=ResetScope.DOCUMENTS, confirm="documents"))
    assert docs.removed["files"] == 1
    assert not folder.exists()
    with runtime.sessions() as session:
        assert session.get(Application, app_id) is not None

    apps = runtime.reset.reset(ResetIn(scope=ResetScope.APPLICATIONS, confirm="applications"))
    assert apps.removed["applications"] == 1
    with runtime.sessions() as session:
        assert session.scalar(select(func.count()).select_from(StageEvent)) == 0  # cascaded
        assert session.scalar(select(func.count()).select_from(Job)) == 1  # jobs stay


async def test_reset_everything_keeps_settings_and_sources(runtime: Runtime) -> None:
    application(runtime, [Stage.APPLIED])
    runtime.portals.add_companies("greenhouse", [])
    with runtime.sessions.begin() as session:
        session.add(ChatSession(id="c1", title="hi"))
        session.add(Task(id="t-done", kind="scrape", status=TaskStatus.SUCCEEDED))
        session.add(Task(id="t-run", kind="scrape", status=TaskStatus.RUNNING))
        session.add(LLMCall(command="rank", provider="fake", model="m", input_tokens=1,
                            output_tokens=1, cost_usd=0.1))  # fmt: skip
        first = session.scalars(select(Company)).first()
        assert first is not None
        first.enabled = False
    config = runtime.paths.config_file.read_text(encoding="utf-8")

    result = runtime.reset.reset(ResetIn(scope=ResetScope.EVERYTHING, confirm="everything"))
    with zipfile.ZipFile(result.backup) as backup:
        assert "rolehawk.db" in backup.namelist()
    with runtime.sessions() as session:
        for model in (Application, Job, ChatSession, LLMCall):
            assert session.scalar(select(func.count()).select_from(model)) == 0
        assert [t.id for t in session.scalars(select(Task))] == ["t-run"]
        assert (
            session.scalar(select(func.count()).select_from(Company).where(~Company.enabled)) == 0
        )
    assert runtime.portals.views()  # sources untouched
    assert runtime.paths.config_file.read_text(encoding="utf-8") == config


# --- API ----------------------------------------------------------------------------------


def runtime_of(client: TestClient) -> Runtime:
    runtime: Runtime = cast(FastAPI, client.app).state.runtime
    return runtime


def test_insights_api(client: TestClient) -> None:
    runtime = runtime_of(client)
    app_id = application(runtime, [Stage.SAVED, Stage.APPLYING])

    board = client.get("/api/pipeline").json()
    assert [c["id"] for c in board["columns"]][:2] == ["saved", "applying"]
    assert board["columns"][1]["cards"][0]["application_id"] == app_id
    moved = client.patch(f"/api/applications/{app_id}", json={"stage": "applied"})
    assert moved.status_code == 200
    board = client.get("/api/pipeline").json()
    assert board["columns"][2]["cards"][0]["application_id"] == app_id

    assert client.get("/api/insights").json()["totals"]["applied"] == 1

    report = client.post("/api/reports").json()
    download = client.get(f"/api/reports/{report['filename']}")
    assert download.status_code == 200
    assert download.headers["content-type"].startswith("text/html")
    assert "attachment" in download.headers["content-disposition"]
    assert client.get("/api/reports/..%2Frolehawk.db").status_code == 404

    assert [s["id"] for s in client.get("/api/reset/scopes").json()] == [
        "profile",
        "documents",
        "jobs",
        "applications",
        "everything",
    ]
    bad = client.post("/api/reset", json={"scope": "jobs", "confirm": "nope"})
    assert bad.status_code == 422
    assert bad.json()["detail"] == 'Type "jobs" to confirm.'
    ok = client.post("/api/reset", json={"scope": "applications", "confirm": "applications"})
    assert ok.json()["removed"]["applications"] == 1


def test_reset_is_not_offered_to_chat(client: TestClient) -> None:
    commands = {c["name"]: c for c in client.get("/api/commands").json()}
    assert commands["reset"]["chat_allowed"] is False
