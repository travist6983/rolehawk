"""Score concerns: why a job might not fit, next to the reasons it does (fit/rubric.py).
Null for scores from before the rubric asked.

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-01 21:06:10.391530
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Plain ALTER TABLE (SQLite 3.35+), not batch mode, as in 0005.


def upgrade() -> None:
    op.add_column("job_scores", sa.Column("concerns", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.execute("ALTER TABLE job_scores DROP COLUMN concerns")
