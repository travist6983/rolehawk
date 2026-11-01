"""Full-text search over jobs(title, company, description) via the `jobs_fts` FTS5 table."""

from __future__ import annotations

import re

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from rolehawk.db.models import Job

_TOKEN = re.compile(r"\w+", re.UNICODE)


def to_match_query(query: str) -> str | None:
    """Turn free text into a safe FTS5 query: each word quoted, prefix-matched, ANDed.
    Returns None when the input has no searchable words."""
    tokens = _TOKEN.findall(query)
    return " ".join(f'"{token}"*' for token in tokens) or None


def search_jobs(session: Session, query: str, limit: int = 50) -> list[Job]:
    match = to_match_query(query)
    if match is None:
        return []
    ids = (
        session.execute(
            text(
                "SELECT rowid FROM jobs_fts WHERE jobs_fts MATCH :match ORDER BY rank LIMIT :limit"
            ),
            {"match": match, "limit": limit},
        )
        .scalars()
        .all()
    )
    if not ids:
        return []
    jobs = {job.id: job for job in session.scalars(select(Job).where(Job.id.in_(ids)))}
    return [jobs[i] for i in ids if i in jobs]
