"""chat sessions, memory proposals, read-only pipeline views

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-31 10:10:32.272821
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Read-only views for chat's query_pipeline tool. The tool may read only these; columns
# with long third-party text (descriptions, email bodies) are deliberately left out.
VIEWS = {
    "v_applications": """
        SELECT a.id AS application_id, j.id AS job_id, j.company, j.title, j.location,
               j.remote, j.salary_text, a.stage, a.method, a.applied_at, a.stage_changed_at,
               a.created_at, p.name AS source, p.kind AS source_kind, j.url,
               (SELECT s.score FROM job_scores s WHERE s.job_id = j.id
                ORDER BY s.created_at DESC LIMIT 1) AS score
        FROM applications a
        JOIN jobs j ON j.id = a.job_id
        JOIN portals p ON p.id = j.portal_id
    """,
    "v_jobs": """
        SELECT j.id AS job_id, j.company, j.title, j.location, j.remote, j.salary_text,
               j.posted_at, j.scraped_at, p.name AS source, p.kind AS source_kind, j.url,
               (SELECT s.score FROM job_scores s WHERE s.job_id = j.id
                ORDER BY s.created_at DESC LIMIT 1) AS score,
               EXISTS (SELECT 1 FROM applications a WHERE a.job_id = j.id) AS has_application
        FROM jobs j
        JOIN portals p ON p.id = j.portal_id
    """,
    "v_stage_history": """
        SELECT e.application_id, j.company, j.title, e.from_stage, e.to_stage, e.source,
               e.status, e.created_at
        FROM stage_events e
        JOIN applications a ON a.id = e.application_id
        JOIN jobs j ON j.id = a.job_id
    """,
    "v_interviews": """
        SELECT i.application_id, j.company, j.title, i.stage, i.scheduled_at, i.self_rating
        FROM interviews i
        JOIN applications a ON a.id = i.application_id
        JOIN jobs j ON j.id = a.job_id
    """,
    "v_spend": """
        SELECT command, model, input_tokens, output_tokens, cost_usd, created_at
        FROM llm_calls
    """,
}


def upgrade() -> None:
    op.create_table(
        "chat_sessions",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("summarized_through_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_chat_sessions")),
    )
    op.create_table(
        "memory_proposals",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("target", sa.String(length=32), nullable=False),
        sa.Column("op", sa.String(length=32), nullable=False),
        sa.Column("section", sa.String(length=255), nullable=True),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column("old_text", sa.Text(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("session_id", sa.String(length=32), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["chat_sessions.id"],
            name=op.f("fk_memory_proposals_session_id_chat_sessions"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_memory_proposals")),
    )
    with op.batch_alter_table("memory_proposals", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_memory_proposals_status"), ["status"], unique=False)

    with op.batch_alter_table("chat_messages", schema=None) as batch_op:
        batch_op.add_column(sa.Column("context", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("cards", sa.JSON(), nullable=False, server_default="[]"))
        batch_op.alter_column(
            "session_id",
            existing_type=sa.VARCHAR(length=64),
            type_=sa.String(length=32),
            existing_nullable=False,
        )
        batch_op.create_foreign_key(
            batch_op.f("fk_chat_messages_session_id_chat_sessions"),
            "chat_sessions",
            ["session_id"],
            ["id"],
            ondelete="CASCADE",
        )

    for name, body in VIEWS.items():
        op.execute(f"CREATE VIEW {name} AS {body.strip()}")


def downgrade() -> None:
    for name in VIEWS:
        op.execute(f"DROP VIEW IF EXISTS {name}")
    with op.batch_alter_table("chat_messages", schema=None) as batch_op:
        batch_op.drop_constraint(
            batch_op.f("fk_chat_messages_session_id_chat_sessions"), type_="foreignkey"
        )
        batch_op.alter_column(
            "session_id",
            existing_type=sa.String(length=32),
            type_=sa.VARCHAR(length=64),
            existing_nullable=False,
        )
        batch_op.drop_column("cards")
        batch_op.drop_column("context")

    with op.batch_alter_table("memory_proposals", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_memory_proposals_status"))

    op.drop_table("memory_proposals")
    op.drop_table("chat_sessions")
