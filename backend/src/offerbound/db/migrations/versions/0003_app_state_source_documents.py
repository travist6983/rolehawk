"""app_state key-value table and uploaded source documents

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-31 11:30:13.664741
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:

    op.create_table(
        "app_state",
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("value", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("key", name=op.f("pk_app_state")),
    )
    op.create_table(
        "source_documents",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_source_documents")),
    )
    with op.batch_alter_table("source_documents", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_source_documents_sha256"), ["sha256"], unique=False)


def downgrade() -> None:

    with op.batch_alter_table("source_documents", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_source_documents_sha256"))

    op.drop_table("source_documents")
    op.drop_table("app_state")
