"""Job deadlines: the application closing date, from the source or read from the posting

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-31 20:40:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Plain ALTER TABLE (SQLite 3.35+), not batch mode, as in 0005.


def upgrade() -> None:
    op.add_column("jobs", sa.Column("closes_at", sa.Date(), nullable=True))
    op.create_index("ix_jobs_closes_at", "jobs", ["closes_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_jobs_closes_at", table_name="jobs")
    op.execute("ALTER TABLE jobs DROP COLUMN closes_at")
