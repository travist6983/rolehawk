"""Alembic environment. Driven programmatically from rolehawk.db.migrate (no alembic.ini)."""

from __future__ import annotations

from alembic import context
from sqlalchemy import Connection

from rolehawk.db.autogen import include_object, render_item
from rolehawk.db.models import Base


def run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=Base.metadata,
        render_as_batch=True,  # SQLite can't ALTER most things; batch mode rebuilds tables.
        include_object=include_object,
        render_item=render_item,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


connection: Connection | None = context.config.attributes.get("connection")
if connection is None:
    raise RuntimeError("Run migrations through rolehawk.db.migrate, not the alembic CLI.")
run_migrations(connection)
