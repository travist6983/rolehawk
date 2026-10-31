from pathlib import Path

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from offerbound.chat.pipeline_query import QueryRejectedError, run_query
from offerbound.db.models import Application, Job, Portal, PortalKind, RiskLevel, Stage
from offerbound.paths import DataPaths


@pytest.fixture
def db(paths: DataPaths, engine: Engine, sessions: sessionmaker[Session]) -> Path:
    with sessions.begin() as session:
        session.add(
            Portal(id="gh", name="Greenhouse", kind=PortalKind.ATS, risk_level=RiskLevel.LOW)
        )
        session.flush()
        for n, company in enumerate(["Stripe", "Ramp", "Plaid"]):
            session.add(
                Job(
                    portal_id="gh",
                    external_id=str(n),
                    url=f"https://x/{n}",
                    company=company,
                    title="Engineer",
                    description="secret description",
                    hash=f"h{n}",
                )
            )
        session.flush()
        session.add(Application(job_id=1, stage=Stage.APPLIED))
        session.add(Application(job_id=2, stage=Stage.INTERVIEW))
    return paths.db


def test_select_from_views(db: Path) -> None:
    result = run_query(db, "SELECT company, stage FROM v_applications ORDER BY company")
    assert result.columns == ["company", "stage"]
    assert result.rows == [["Ramp", "interview"], ["Stripe", "applied"]]
    jobs = run_query(db, "select count(*) from v_jobs where has_application = 0;")
    assert jobs.rows == [[1]]


def test_cte_and_functions_allowed(db: Path) -> None:
    sql = "WITH a AS (SELECT * FROM v_applications) SELECT lower(company) FROM a LIMIT 1"
    assert len(run_query(db, sql).rows) == 1


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT description FROM jobs",  # base tables are off limits
        "SELECT * FROM chat_messages",
        "SELECT name FROM sqlite_master",
        "DELETE FROM jobs",
        "UPDATE applications SET stage = 'offer'",
        "PRAGMA table_info(jobs)",
        "ATTACH DATABASE 'x.db' AS x",
        "SELECT 1; DELETE FROM jobs",
        "SELECT * FROM v_jobs JOIN jobs USING (company)",
    ],
)
def test_rejected(db: Path, sql: str) -> None:
    with pytest.raises(QueryRejectedError):
        run_query(db, sql)
    assert len(run_query(db, "SELECT * FROM v_jobs").rows) == 3  # nothing changed


def test_views_hide_descriptions(db: Path) -> None:
    result = run_query(db, "SELECT * FROM v_jobs")
    assert "description" not in result.columns
    assert all("secret" not in str(cell) for row in result.rows for cell in row)


def test_row_cap(db: Path) -> None:
    result = run_query(db, "SELECT company FROM v_jobs", max_rows=2)
    assert len(result.rows) == 2
    assert result.truncated


def test_runaway_query_times_out(db: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from offerbound.chat import pipeline_query

    monkeypatch.setattr(pipeline_query, "TIME_LIMIT_S", 0.05)
    sql = (
        "WITH RECURSIVE n(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM n) "
        "SELECT count(*) FROM n, v_jobs"
    )
    with pytest.raises(QueryRejectedError, match="interrupt"):
        run_query(db, sql)
