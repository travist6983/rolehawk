"""Score breakdown and gates: the four parts behind a fit score, and the eligibility and
language gates (fit/rubric.py)

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-31 20:20:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Plain ALTER TABLE (SQLite 3.35+), not batch mode, as in 0005.


def upgrade() -> None:
    op.add_column("job_scores", sa.Column("breakdown", sa.JSON(), nullable=True))
    op.add_column("job_scores", sa.Column("gates", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.execute("ALTER TABLE job_scores DROP COLUMN gates")
    op.execute("ALTER TABLE job_scores DROP COLUMN breakdown")
