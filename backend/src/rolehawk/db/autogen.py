"""Alembic autogenerate hooks, shared by migrations/env.py and the schema-drift test."""

from __future__ import annotations

from typing import Any, Literal

import sqlalchemy as sa

from rolehawk.db.types import UTCDateTime

# Tables and views created by raw SQL in migrations, invisible to the ORM metadata.
RAW_SQL_PREFIXES = ("jobs_fts", "v_")


def include_object(
    obj: Any, name: str | None, type_: str, reflected: bool, compare_to: Any
) -> bool:
    return not (type_ == "table" and name is not None and name.startswith(RAW_SQL_PREFIXES))


def render_item(type_: str, obj: Any, autogen_context: Any) -> str | Literal[False]:
    """Render app-specific column types as plain SQLAlchemy types so migration files never
    import application code (models change; migrations must not)."""
    if type_ == "type":
        if isinstance(obj, UTCDateTime):
            return "sa.DateTime()"
        if isinstance(obj, sa.Enum) and not obj.native_enum:
            return f"sa.String(length={obj.length})"
    return False
