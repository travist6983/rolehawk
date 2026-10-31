"""Reads and writes the profile through the markdown files, keeps `profile_items` and
`search_targets` in sync with them."""

from __future__ import annotations

import threading
from collections.abc import Callable

from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from offerbound import countries
from offerbound.config import Settings
from offerbound.db.models import ProfileItem, ProfileItemKind, RemotePolicy, SearchTarget
from offerbound.memory.files import MemoryFiles, MemoryTarget
from offerbound.profile.markdown import (
    parse_preferences,
    parse_profile,
    render_preferences,
    render_profile,
)
from offerbound.profile.model import Preferences, Profile, SalaryPeriod

_ANNUAL = {SalaryPeriod.YEAR: 1, SalaryPeriod.MONTH: 12, SalaryPeriod.HOUR: 2080}


class Completeness(BaseModel):
    score: int  # 0-100
    missing: list[str]


def completeness(profile: Profile, prefs: Preferences) -> Completeness:
    checks = {
        "name": bool(profile.contact.name),
        "experience": bool(profile.experience),
        "skills": len(profile.skills) >= 3,
        "target titles": bool(prefs.target_titles),
        "locations or remote preference": bool(prefs.locations or prefs.remote),
        "salary floor": prefs.salary_floor is not None,
        "work authorization": bool(prefs.work_authorization),
        "dates for every role": all(e.start for e in profile.experience)
        and bool(profile.experience),
    }
    done = sum(checks.values())
    return Completeness(
        score=round(100 * done / len(checks)),
        missing=[name for name, ok in checks.items() if not ok],
    )


class ProfileService:
    def __init__(
        self,
        files: MemoryFiles,
        sessions: sessionmaker[Session],
        settings: Callable[[], Settings],
    ) -> None:
        self._files = files
        self._sessions = sessions
        self._settings = settings
        self._lock = threading.Lock()  # one writer at a time for read-modify-write

    @property
    def lock(self) -> threading.Lock:
        return self._lock

    def default_currency(self, prefs: Preferences | None = None) -> str:
        country = (prefs.country if prefs else None) or self._settings().search.country
        return countries.defaults_for(country).currency

    def load_profile(self) -> Profile:
        return parse_profile(self._files.read(MemoryTarget.PROFILE))

    def load_preferences(self) -> Preferences:
        text = self._files.read(MemoryTarget.PREFERENCES)
        prefs = parse_preferences(text)
        if prefs.salary_floor is not None:  # re-parse with the right default currency
            prefs = parse_preferences(text, self.default_currency(prefs))
        return prefs

    def save_profile(self, profile: Profile) -> None:
        self._files.write(MemoryTarget.PROFILE, render_profile(profile))
        self.reindex(profile)

    def save_preferences(self, prefs: Preferences) -> None:
        self._files.write(MemoryTarget.PREFERENCES, render_preferences(prefs))
        self.sync_search_targets(prefs)

    def save_raw(self, target: MemoryTarget, markdown: str) -> None:
        """The user's own edit: stored exactly as typed, then the derived tables refresh."""
        self._files.write(target, markdown)
        self.on_memory_changed(target)

    def on_memory_changed(self, target: MemoryTarget) -> None:
        if target is MemoryTarget.PROFILE:
            self.reindex()
        elif target is MemoryTarget.PREFERENCES:
            self.sync_search_targets()

    # --- derived tables -----------------------------------------------------------------

    def reindex(self, profile: Profile | None = None) -> int:
        """Regenerate profile_items from profile.md (it mirrors the file)."""
        profile = profile or self.load_profile()
        rows: list[ProfileItem] = []

        def add(kind: ProfileItemKind, data: dict[str, object]) -> None:
            rows.append(ProfileItem(kind=kind, data=data, source="profile.md"))

        for exp in profile.experience:
            add(ProfileItemKind.EXPERIENCE, exp.model_dump())
        for edu in profile.education:
            add(ProfileItemKind.EDUCATION, edu.model_dump())
        for skill in profile.skills:
            add(ProfileItemKind.SKILL, {"name": skill})
        for project in profile.projects:
            add(ProfileItemKind.PROJECT, project.model_dump())
        for cert in profile.certifications:
            add(ProfileItemKind.CERT, cert.model_dump())
        for achievement in profile.achievements:
            add(ProfileItemKind.ACHIEVEMENT, {"text": achievement})
        with self._sessions.begin() as session:
            session.execute(delete(ProfileItem))
            session.add_all(rows)
        return len(rows)

    def sync_search_targets(self, prefs: Preferences | None = None) -> list[SearchTarget]:
        """One active search target per target title; titles removed later are deactivated,
        never deleted (runs reference them)."""
        prefs = prefs or self.load_preferences()
        country = (prefs.country or self._settings().search.country).upper()
        salary = (
            prefs.salary_floor.amount * _ANNUAL[prefs.salary_floor.period]
            if prefs.salary_floor
            else None
        )
        remote = RemotePolicy(prefs.remote.value) if prefs.remote else RemotePolicy.ANY
        with self._sessions.begin() as session:
            existing = {t.title.casefold(): t for t in session.scalars(select(SearchTarget))}
            wanted = {title.casefold(): title for title in prefs.target_titles}
            for key, title in wanted.items():
                target = existing.get(key) or SearchTarget(title=title, country=country)
                target.seniority = prefs.seniority
                target.locations = list(prefs.locations)
                target.remote_policy = remote
                target.country = country
                target.salary_min = salary
                target.active = True
                session.add(target)
            for key, target in existing.items():
                if key not in wanted:
                    target.active = False
            session.flush()
            return list(session.scalars(select(SearchTarget).order_by(SearchTarget.id)))
