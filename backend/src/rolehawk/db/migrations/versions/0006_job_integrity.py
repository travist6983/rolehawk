"""Job integrity findings: what the posting check removed or found (portals/integrity.py)

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-31 19:49:06.577514
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Plain ALTER TABLE (SQLite 3.35+), not batch mode: batch mode rebuilds `jobs`, which the
# v_* views reference.


def upgrade() -> None:
    op.add_column("jobs", sa.Column("integrity", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.execute("ALTER TABLE jobs DROP COLUMN integrity")
