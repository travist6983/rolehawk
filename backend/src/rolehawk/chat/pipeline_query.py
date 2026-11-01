"""Read-only SQL over the v_* views for chat's query_pipeline tool.

Defense in depth: a separate read-only connection (mode=ro, query_only), an authorizer that
permits only SELECT and reads that go through an allowed view, one statement per call, a
row cap, and a time limit."""

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ALLOWED_VIEWS: dict[str, str] = {
    "v_applications": (
        "application_id, job_id, company, title, location, remote, salary_text, stage, method, "
        "applied_at, stage_changed_at, created_at, source, source_kind, url, score"
    ),
    "v_jobs": (
        "job_id, company, title, location, remote, salary_text, posted_at, scraped_at, source, "
        "source_kind, url, score, has_application"
    ),
    "v_stage_history": (
        "application_id, company, title, from_stage, to_stage, source, status, created_at"
    ),
    "v_interviews": "application_id, company, title, stage, scheduled_at, self_rating",
    "v_spend": "command, model, input_tokens, output_tokens, cost_usd, created_at",
}

MAX_ROWS = 200
TIME_LIMIT_S = 2.0
_ALLOWED_ACTIONS = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_FUNCTION, sqlite3.SQLITE_RECURSIVE}


class QueryRejectedError(ValueError):
    pass


@dataclass(frozen=True)
class QueryResult:
    columns: list[str]
    rows: list[list[Any]]
    truncated: bool

    def to_json(self) -> dict[str, Any]:
        return {"columns": self.columns, "rows": self.rows, "truncated": self.truncated}


def schema_description() -> str:
    lines = [f"- {name}({columns})" for name, columns in ALLOWED_VIEWS.items()]
    return (
        "SQLite views (read-only). Timestamps are UTC text 'YYYY-MM-DD HH:MM:SS'. Stages: "
        "saved, applying, applied, screen, interview, offer, rejected, withdrawn, ghosted.\n"
        + "\n".join(lines)
    )


def _authorizer(
    action: int, arg1: str | None, arg2: str | None, db: str | None, source: str | None
) -> int:
    if action in _ALLOWED_ACTIONS:
        return sqlite3.SQLITE_OK
    if action == sqlite3.SQLITE_READ:
        # arg1 = table, arg2 = column, source = the view responsible for the access.
        through_view = arg1 in ALLOWED_VIEWS or source in ALLOWED_VIEWS
        cte = db is None  # WITH-clause tables are not real tables
        no_data = arg2 == ""  # count(*) over a flattened view reads no column values
        if through_view or cte or no_data:
            return sqlite3.SQLITE_OK
    return sqlite3.SQLITE_DENY


def run_query(db_path: Path, sql: str, max_rows: int = MAX_ROWS) -> QueryResult:
    statement = sql.strip().rstrip(";").strip()
    if not statement.lower().startswith(("select", "with")):
        raise QueryRejectedError("only SELECT queries over the v_* views are allowed")
    connection = sqlite3.connect(f"{db_path.resolve().as_uri()}?mode=ro", uri=True)
    try:
        connection.execute("PRAGMA query_only = ON")
        connection.set_authorizer(_authorizer)
        deadline = time.monotonic() + TIME_LIMIT_S
        connection.set_progress_handler(lambda: int(time.monotonic() > deadline), 10_000)
        try:
            cursor = connection.execute(statement)
            rows = cursor.fetchmany(max_rows + 1)
        except sqlite3.Error as exc:
            raise QueryRejectedError(str(exc)) from exc
        columns = [d[0] for d in cursor.description or []]
        return QueryResult(
            columns=columns,
            rows=[list(r) for r in rows[:max_rows]],
            truncated=len(rows) > max_rows,
        )
    finally:
        connection.close()
