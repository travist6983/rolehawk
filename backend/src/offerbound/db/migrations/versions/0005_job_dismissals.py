"""Job dismissals: hide a job from Discover and from future ranking runs

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-31 12:43:58.627147
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Plain ALTER TABLE (SQLite 3.35+), not batch mode: batch mode rebuilds `jobs`, which the
# v_* views reference.


def upgrade() -> None:
    op.add_column("jobs", sa.Column("dismissed_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.execute("ALTER TABLE jobs DROP COLUMN dismissed_at")
