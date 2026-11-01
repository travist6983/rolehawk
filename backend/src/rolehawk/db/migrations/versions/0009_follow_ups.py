"""Follow-ups: notes the user sent on quiet applications (apply/followup.py)

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-31 20:22:56.720008
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "follow_ups",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("application_id", sa.Integer(), nullable=False),
        sa.Column("channel", sa.String(length=32), nullable=False),
        sa.Column("subject", sa.String(length=300), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("sent_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["application_id"],
            ["applications.id"],
            name=op.f("fk_follow_ups_application_id_applications"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_follow_ups")),
    )
    op.create_index(
        op.f("ix_follow_ups_application_id"), "follow_ups", ["application_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_follow_ups_application_id"), table_name="follow_ups")
    op.drop_table("follow_ups")
