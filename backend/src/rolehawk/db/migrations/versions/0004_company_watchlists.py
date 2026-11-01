"""ATS company watchlists

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-31 12:12:10.472490
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:

    op.create_table(
        "companies",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("ats", sa.String(length=32), nullable=False),
        sa.Column("slug", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("industry", sa.String(length=64), nullable=True),
        sa.Column("country", sa.String(length=8), nullable=True),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("last_job_count", sa.Integer(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_companies")),
        sa.UniqueConstraint("ats", "slug", name=op.f("uq_companies_ats_slug")),
    )
    with op.batch_alter_table("companies", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_companies_ats"), ["ats"], unique=False)


def downgrade() -> None:

    with op.batch_alter_table("companies", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_companies_ats"))

    op.drop_table("companies")
