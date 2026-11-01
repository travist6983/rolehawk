"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-10-31 09:53:15.804543
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "chat_messages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_chat_messages")),
    )
    with op.batch_alter_table("chat_messages", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_chat_messages_created_at"), ["created_at"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_chat_messages_session_id"), ["session_id"], unique=False
        )

    op.create_table(
        "portals",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("countries", sa.JSON(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("risk_level", sa.String(length=32), nullable=False),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=True),
        sa.Column("last_run_at", sa.DateTime(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_portals")),
    )
    op.create_table(
        "profile_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("source", sa.String(length=255), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_profile_items")),
    )
    with op.batch_alter_table("profile_items", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_profile_items_kind"), ["kind"], unique=False)

    op.create_table(
        "search_targets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("seniority", sa.String(length=64), nullable=True),
        sa.Column("locations", sa.JSON(), nullable=False),
        sa.Column("remote_policy", sa.String(length=32), nullable=False),
        sa.Column("country", sa.String(length=2), nullable=False),
        sa.Column("salary_min", sa.Integer(), nullable=True),
        sa.Column("keywords", sa.JSON(), nullable=False),
        sa.Column("exclude", sa.JSON(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_search_targets")),
    )
    op.create_table(
        "tasks",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("progress", sa.Float(), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("params", sa.JSON(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tasks")),
    )
    with op.batch_alter_table("tasks", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_tasks_created_at"), ["created_at"], unique=False)
        batch_op.create_index(batch_op.f("ix_tasks_kind"), ["kind"], unique=False)

    op.create_table(
        "jobs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("portal_id", sa.String(length=64), nullable=False),
        sa.Column("external_id", sa.String(length=255), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("company", sa.String(length=255), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("location", sa.String(length=255), nullable=True),
        sa.Column("remote", sa.Boolean(), nullable=True),
        sa.Column("salary_text", sa.String(length=255), nullable=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("posted_at", sa.DateTime(), nullable=True),
        sa.Column("scraped_at", sa.DateTime(), nullable=False),
        sa.Column("hash", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(
            ["portal_id"], ["portals.id"], name=op.f("fk_jobs_portal_id_portals")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_jobs")),
        sa.UniqueConstraint("hash", name=op.f("uq_jobs_hash")),
        sa.UniqueConstraint("portal_id", "external_id", name=op.f("uq_jobs_portal_id_external_id")),
    )
    with op.batch_alter_table("jobs", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_jobs_company"), ["company"], unique=False)
        batch_op.create_index(batch_op.f("ix_jobs_portal_id"), ["portal_id"], unique=False)

    op.create_table(
        "llm_calls",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("command", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("cache_read_tokens", sa.Integer(), nullable=False),
        sa.Column("cache_write_tokens", sa.Integer(), nullable=False),
        sa.Column("cost_usd", sa.Float(), nullable=False),
        sa.Column("task_id", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["task_id"], ["tasks.id"], name=op.f("fk_llm_calls_task_id_tasks"), ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_llm_calls")),
    )
    with op.batch_alter_table("llm_calls", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_llm_calls_command"), ["command"], unique=False)
        batch_op.create_index(batch_op.f("ix_llm_calls_created_at"), ["created_at"], unique=False)

    op.create_table(
        "applications",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("job_id", sa.Integer(), nullable=False),
        sa.Column("stage", sa.String(length=32), nullable=False),
        sa.Column("stage_changed_at", sa.DateTime(), nullable=False),
        sa.Column("applied_at", sa.DateTime(), nullable=True),
        sa.Column("method", sa.String(length=32), nullable=True),
        sa.Column("cv_path", sa.Text(), nullable=True),
        sa.Column("cover_path", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["job_id"], ["jobs.id"], name=op.f("fk_applications_job_id_jobs"), ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_applications")),
    )
    with op.batch_alter_table("applications", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_applications_job_id"), ["job_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_applications_stage"), ["stage"], unique=False)

    op.create_table(
        "job_scores",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("job_id", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.String(length=32), nullable=True),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("must_have_gaps", sa.JSON(), nullable=False),
        sa.Column("reasons", sa.JSON(), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("score >= 0 AND score <= 100", name=op.f("ck_job_scores_score_range")),
        sa.ForeignKeyConstraint(
            ["job_id"], ["jobs.id"], name=op.f("fk_job_scores_job_id_jobs"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["run_id"], ["tasks.id"], name=op.f("fk_job_scores_run_id_tasks"), ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_job_scores")),
        sa.UniqueConstraint("job_id", "run_id", name=op.f("uq_job_scores_job_id_run_id")),
    )
    with op.batch_alter_table("job_scores", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_job_scores_job_id"), ["job_id"], unique=False)

    op.create_table(
        "interviews",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("application_id", sa.Integer(), nullable=False),
        sa.Column("stage", sa.String(length=32), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(), nullable=True),
        sa.Column("prep_pack_path", sa.Text(), nullable=True),
        sa.Column("mock_transcript_path", sa.Text(), nullable=True),
        sa.Column("self_rating", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "self_rating IS NULL OR (self_rating >= 1 AND self_rating <= 5)",
            name=op.f("ck_interviews_rating_range"),
        ),
        sa.ForeignKeyConstraint(
            ["application_id"],
            ["applications.id"],
            name=op.f("fk_interviews_application_id_applications"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_interviews")),
    )
    with op.batch_alter_table("interviews", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_interviews_application_id"), ["application_id"], unique=False
        )

    op.create_table(
        "outcomes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("application_id", sa.Integer(), nullable=False),
        sa.Column("result", sa.String(length=64), nullable=False),
        sa.Column("feedback", sa.Text(), nullable=True),
        sa.Column("follow_up_draft", sa.Text(), nullable=True),
        sa.Column("archived_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["application_id"],
            ["applications.id"],
            name=op.f("fk_outcomes_application_id_applications"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_outcomes")),
    )
    with op.batch_alter_table("outcomes", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_outcomes_application_id"), ["application_id"], unique=False
        )

    op.create_table(
        "stage_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("application_id", sa.Integer(), nullable=False),
        sa.Column("from_stage", sa.String(length=32), nullable=True),
        sa.Column("to_stage", sa.String(length=32), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("evidence", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["application_id"],
            ["applications.id"],
            name=op.f("fk_stage_events_application_id_applications"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_stage_events")),
    )
    with op.batch_alter_table("stage_events", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_stage_events_application_id"), ["application_id"], unique=False
        )
        batch_op.create_index(batch_op.f("ix_stage_events_status"), ["status"], unique=False)

    # Full-text search over jobs. External-content FTS5 table kept in sync by triggers.
    op.execute(
        "CREATE VIRTUAL TABLE jobs_fts USING fts5("
        "title, company, description, content='jobs', content_rowid='id', "
        "tokenize='porter unicode61')"
    )
    op.execute(
        "CREATE TRIGGER jobs_fts_ai AFTER INSERT ON jobs BEGIN "
        "INSERT INTO jobs_fts(rowid, title, company, description) "
        "VALUES (new.id, new.title, new.company, new.description); END"
    )
    op.execute(
        "CREATE TRIGGER jobs_fts_ad AFTER DELETE ON jobs BEGIN "
        "INSERT INTO jobs_fts(jobs_fts, rowid, title, company, description) "
        "VALUES ('delete', old.id, old.title, old.company, old.description); END"
    )
    op.execute(
        "CREATE TRIGGER jobs_fts_au AFTER UPDATE ON jobs BEGIN "
        "INSERT INTO jobs_fts(jobs_fts, rowid, title, company, description) "
        "VALUES ('delete', old.id, old.title, old.company, old.description); "
        "INSERT INTO jobs_fts(rowid, title, company, description) "
        "VALUES (new.id, new.title, new.company, new.description); END"
    )


def downgrade() -> None:
    for trigger in ("jobs_fts_au", "jobs_fts_ad", "jobs_fts_ai"):
        op.execute(f"DROP TRIGGER IF EXISTS {trigger}")
    op.execute("DROP TABLE IF EXISTS jobs_fts")
    with op.batch_alter_table("stage_events", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_stage_events_status"))
        batch_op.drop_index(batch_op.f("ix_stage_events_application_id"))

    op.drop_table("stage_events")
    with op.batch_alter_table("outcomes", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_outcomes_application_id"))

    op.drop_table("outcomes")
    with op.batch_alter_table("interviews", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_interviews_application_id"))

    op.drop_table("interviews")
    with op.batch_alter_table("job_scores", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_job_scores_job_id"))

    op.drop_table("job_scores")
    with op.batch_alter_table("applications", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_applications_stage"))
        batch_op.drop_index(batch_op.f("ix_applications_job_id"))

    op.drop_table("applications")
    with op.batch_alter_table("llm_calls", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_llm_calls_created_at"))
        batch_op.drop_index(batch_op.f("ix_llm_calls_command"))

    op.drop_table("llm_calls")
    with op.batch_alter_table("jobs", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_jobs_portal_id"))
        batch_op.drop_index(batch_op.f("ix_jobs_company"))

    op.drop_table("jobs")
    with op.batch_alter_table("tasks", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_tasks_kind"))
        batch_op.drop_index(batch_op.f("ix_tasks_created_at"))

    op.drop_table("tasks")
    op.drop_table("search_targets")
    with op.batch_alter_table("profile_items", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_profile_items_kind"))

    op.drop_table("profile_items")
    op.drop_table("portals")
    with op.batch_alter_table("chat_messages", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_chat_messages_session_id"))
        batch_op.drop_index(batch_op.f("ix_chat_messages_created_at"))

    op.drop_table("chat_messages")
