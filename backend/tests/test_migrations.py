from datetime import UTC, datetime, timedelta, timezone

import pytest
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from sqlalchemy import Engine, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from rolehawk.db import fts, migrate
from rolehawk.db.autogen import include_object
from rolehawk.db.engine import make_engine
from rolehawk.db.models import Application, Base, Job, Portal, PortalKind, RiskLevel, Stage
from rolehawk.paths import DataPaths
from rolehawk.services import backup

CORE_TABLES = {
    "profile_items",
    "search_targets",
    "portals",
    "jobs",
    "job_scores",
    "applications",
    "stage_events",
    "interviews",
    "outcomes",
    "llm_calls",
    "chat_messages",
    "tasks",
}


def _portal() -> Portal:
    return Portal(id="greenhouse", name="Greenhouse", kind=PortalKind.ATS, risk_level=RiskLevel.LOW)


def _add_portal(sessions: sessionmaker[Session]) -> None:
    with sessions.begin() as session:
        session.add(_portal())


def _job(n: int, **overrides: object) -> Job:
    values: dict[str, object] = {
        "portal_id": "greenhouse",
        "external_id": f"ext-{n}",
        "url": f"https://example.com/{n}",
        "company": "Acme",
        "title": "Engineer",
        "description": "",
        "hash": f"hash-{n}",
    }
    values.update(overrides)
    return Job(**values)


def test_upgrade_creates_every_table_and_fts(engine: Engine) -> None:
    tables = set(inspect(engine).get_table_names())
    assert tables >= CORE_TABLES | {"jobs_fts", "alembic_version"}
    assert migrate.current_revision(engine) == migrate.head_revision()
    assert not migrate.needs_upgrade(engine)


def test_models_match_migrations(engine: Engine) -> None:
    """Fails if a model changed without a migration."""
    with engine.connect() as connection:
        context = MigrationContext.configure(
            connection, opts={"include_object": include_object, "compare_type": True}
        )
        assert compare_metadata(context, Base.metadata) == []


def test_downgrade_to_base_removes_everything(engine: Engine) -> None:
    migrate.downgrade(engine, "base")
    assert set(inspect(engine).get_table_names()) <= {"alembic_version"}
    migrate.upgrade(engine)
    assert set(inspect(engine).get_table_names()) >= CORE_TABLES


def test_wal_and_foreign_keys_enabled(engine: Engine) -> None:
    with engine.connect() as connection:
        assert connection.execute(text("PRAGMA journal_mode")).scalar() == "wal"
        assert connection.execute(text("PRAGMA foreign_keys")).scalar() == 1


def test_foreign_keys_enforced(sessions: sessionmaker[Session]) -> None:
    with pytest.raises(IntegrityError), sessions.begin() as session:
        session.add(_job(1, portal_id="missing"))


def test_job_dedupe_constraints(sessions: sessionmaker[Session]) -> None:
    _add_portal(sessions)
    with sessions.begin() as session:
        session.add(_job(1))
    with pytest.raises(IntegrityError), sessions.begin() as session:
        session.add(_job(2, external_id="ext-1"))  # same portal + external_id
    with pytest.raises(IntegrityError), sessions.begin() as session:
        session.add(_job(3, hash="hash-1"))  # same cross-portal hash


def test_fts_tracks_insert_update_delete(sessions: sessionmaker[Session]) -> None:
    _add_portal(sessions)
    with sessions.begin() as session:
        session.add(_job(1, title="Senior Frontend Engineer", company="Stripe"))
        session.add(_job(2, title="Data Analyst", description="SQL dashboards"))
    with sessions() as session:
        assert [j.company for j in fts.search_jobs(session, "frontend")] == ["Stripe"]
        assert [j.external_id for j in fts.search_jobs(session, "dashboard")] == ["ext-2"]
        assert fts.search_jobs(session, "   ") == []
        assert fts.search_jobs(session, 'NEAR( AND "') == []  # operators can't break the query

    with sessions.begin() as session:
        job = session.query(Job).filter_by(external_id="ext-1").one()
        job.title = "Backend Engineer"
    with sessions() as session:
        assert fts.search_jobs(session, "frontend") == []
        assert len(fts.search_jobs(session, "backend")) == 1

    with sessions.begin() as session:
        session.delete(session.query(Job).filter_by(external_id="ext-1").one())
    with sessions() as session:
        assert fts.search_jobs(session, "backend") == []


def test_fts_query_quotes_operators() -> None:
    assert fts.to_match_query('react AND "node"') == '"react"* "AND"* "node"*'
    assert fts.to_match_query("!!!") is None


def test_datetimes_round_trip_as_aware_utc(sessions: sessionmaker[Session]) -> None:
    eastern = timezone(timedelta(hours=-5))
    applied = datetime(2026, 10, 1, 9, 30, tzinfo=eastern)
    _add_portal(sessions)
    with sessions.begin() as session:
        session.add(_job(1))
        session.flush()
        job_id = session.query(Job.id).scalar()
        session.add(Application(job_id=job_id, stage=Stage.APPLIED, applied_at=applied))
    with sessions() as session:
        app = session.query(Application).one()
        assert app.applied_at == applied
        assert app.applied_at is not None
        assert app.applied_at.tzinfo == UTC
        assert app.stage is Stage.APPLIED


def test_naive_datetimes_rejected(sessions: sessionmaker[Session]) -> None:
    _add_portal(sessions)
    with pytest.raises(Exception, match="naive datetime"), sessions.begin() as session:
        session.add(_job(1, posted_at=datetime(2026, 1, 1)))


def test_migrate_skips_backup_for_new_database(paths: DataPaths) -> None:
    eng = make_engine(paths.db)
    try:
        assert migrate.migrate(paths, eng) is None
        assert migrate.migrate(paths, eng) is None  # already at head
        assert backup.list_backups(paths) == []
    finally:
        eng.dispose()


def test_migrate_backs_up_before_upgrading_existing_database(
    paths: DataPaths, engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    upgraded: list[str] = []
    monkeypatch.setattr(migrate, "head_revision", lambda: "9999_future")
    monkeypatch.setattr(migrate, "upgrade", lambda eng, revision="head": upgraded.append(revision))
    backup_path = migrate.migrate(paths, engine)
    assert backup_path is not None
    assert backup_path.exists()
    assert "pre-migrate" in backup_path.name
    assert upgraded == ["head"]
