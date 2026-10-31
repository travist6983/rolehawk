from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from offerbound.db.models import AppState


class AppStateStore:
    """Tiny JSON key-value store backed by the `app_state` table."""

    def __init__(self, sessions: sessionmaker[Session]) -> None:
        self._sessions = sessions

    def get(self, key: str, default: Any = None) -> Any:
        with self._sessions() as session:
            row = session.get(AppState, key)
            return default if row is None else row.value

    def set(self, key: str, value: Any) -> None:
        with self._sessions.begin() as session:
            row = session.get(AppState, key)
            if row is None:
                session.add(AppState(key=key, value=value))
            else:
                row.value = value

    def delete(self, key: str) -> None:
        with self._sessions.begin() as session:
            row = session.get(AppState, key)
            if row is not None:
                session.delete(row)
