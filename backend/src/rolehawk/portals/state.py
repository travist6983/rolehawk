"""Source settings and status (the `portals` table) and the ATS company watchlist."""

from __future__ import annotations

import csv
import logging
from collections.abc import Callable, Sequence
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from rolehawk import countries, keychain
from rolehawk.db.models import Company, Job, Portal, PortalKind, RiskLevel
from rolehawk.keychain import SecretName
from rolehawk.portals.base import Portal as PortalImpl
from rolehawk.portals.registry import ATS_IDS, BUILTIN

log = logging.getLogger(__name__)

SECRET_FIELDS: dict[str, list[tuple[str, SecretName]]] = {
    "adzuna": [("app_id", SecretName.ADZUNA_APP_ID), ("app_key", SecretName.ADZUNA_APP_KEY)],
    "usajobs": [("api_key", SecretName.USAJOBS_API_KEY)],
}
CONFIG_FIELDS: dict[str, list[str]] = {"usajobs": ["email"]}
_SECRET_LABELS = {"app_id": "an app ID", "app_key": "an app key", "api_key": "an API key"}


class PortalView(BaseModel):
    model_config = ConfigDict(json_schema_serialization_defaults_required=True)

    id: str
    name: str
    kind: PortalKind
    risk_level: RiskLevel
    countries: list[str]
    enabled: bool
    ready: bool
    missing: list[str] = Field(description="What has to be set up before it can run")
    secret_fields: list[str]
    config_fields: list[str]
    config: dict[str, Any]
    status: str | None
    last_run_at: datetime | None
    last_error: str | None
    jobs_found: int
    companies: int | None
    docs_url: str
    custom: bool = Field(description="Added with /add-portal")


class CompanyView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ats: str
    slug: str
    name: str
    industry: str | None
    country: str | None
    source: str
    enabled: bool
    last_job_count: int | None
    last_error: str | None


# Slugs go into ATS URL paths, so only plain board names are allowed.
SLUG_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._-]*$"


class CompanyIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    slug: str = Field(min_length=1, max_length=128, pattern=SLUG_PATTERN)
    name: str | None = Field(default=None, max_length=255)
    industry: str | None = Field(default=None, max_length=64)


def stored_secrets(portal_id: str) -> dict[str, str]:
    """Secrets this source needs, keyed by their short names (e.g. adzuna_app_id)."""
    values: dict[str, str] = {}
    for _field, name in SECRET_FIELDS.get(portal_id, []):
        try:
            value = keychain.get_secret(name)
        except Exception:  # a broken keychain reads as "not set"
            value = None
        if value:
            values[name.value] = value
    return values


def missing_requirements(
    impl: PortalImpl, config: dict[str, Any], secrets: dict[str, str], companies: int
) -> list[str]:
    missing: list[str] = []
    for requirement in impl.requires:
        kind, _, key = requirement.partition(":")
        if kind == "secret" and key not in secrets:
            field = key.split("_", 1)[1]  # adzuna_app_id -> app_id
            missing.append(_SECRET_LABELS.get(field, field.replace("_", " ")))
        elif kind == "config" and not config.get(key):
            missing.append(f"your {key}")
        elif kind == "watchlist" and companies == 0:
            missing.append("companies in the watchlist")
    return missing


class PortalStore:
    def __init__(
        self,
        sessions: sessionmaker[Session],
        extra: Callable[[], Sequence[PortalImpl]] = lambda: (),
    ) -> None:
        self._sessions = sessions
        self._extra = extra  # custom sources added with /add-portal

    def all(self) -> list[PortalImpl]:
        return [*BUILTIN, *self._extra()]

    def known(self, portal_id: str) -> bool:
        return any(p.id == portal_id for p in self.all())

    def sync_builtin(self) -> None:
        """Make sure every built-in source has a row. Never overrides the user's choices."""
        with self._sessions.begin() as session:
            existing = {p.id for p in session.scalars(select(Portal))}
            for impl in BUILTIN:
                if impl.id not in existing:
                    session.add(
                        Portal(
                            id=impl.id,
                            name=impl.name,
                            kind=impl.kind,
                            countries=list(impl.countries),
                            enabled=impl.default_enabled,
                            risk_level=impl.risk_level,
                            config={},
                        )
                    )

    def seed_watchlist(self) -> int:
        """Load the starter company lists (data/companies/<ats>.csv). Idempotent."""
        added = 0
        with self._sessions.begin() as session:
            existing = {(c.ats, c.slug.lower()) for c in session.scalars(select(Company))}
            for ats in sorted(ATS_IDS):
                path = countries.data_dir() / "companies" / f"{ats}.csv"
                if not path.is_file():
                    continue
                with path.open(encoding="utf-8", newline="") as handle:
                    for row in csv.DictReader(handle):
                        slug = (row.get("slug") or "").strip()
                        if not slug or (ats, slug.lower()) in existing:
                            continue
                        session.add(
                            Company(
                                ats=ats,
                                slug=slug,
                                name=(row.get("name") or slug).strip(),
                                industry=(row.get("industry") or "").strip() or None,
                                country=(row.get("country") or "").strip() or None,
                                source="starter",
                            )
                        )
                        existing.add((ats, slug.lower()))
                        added += 1
        return added

    # --- views ------------------------------------------------------------------------

    def views(self) -> list[PortalView]:
        with self._sessions() as session:
            rows = {p.id: p for p in session.scalars(select(Portal))}
            job_counts = dict(
                session.execute(select(Job.portal_id, func.count()).group_by(Job.portal_id)).all()
            )
            company_counts = dict(
                session.execute(
                    select(Company.ats, func.count())
                    .where(Company.enabled.is_(True))
                    .group_by(Company.ats)
                ).all()
            )
        views: list[PortalView] = []
        for impl in self.all():
            row = rows.get(impl.id)
            if row is None:
                continue
            secrets = stored_secrets(impl.id)
            companies = company_counts.get(impl.id, 0) if impl.id in ATS_IDS else None
            missing = missing_requirements(impl, row.config, secrets, companies or 0)
            views.append(
                PortalView(
                    id=impl.id,
                    name=impl.name,
                    kind=impl.kind,
                    risk_level=impl.risk_level,
                    countries=list(impl.countries),
                    enabled=row.enabled,
                    ready=not missing,
                    missing=missing,
                    secret_fields=[f for f, _ in SECRET_FIELDS.get(impl.id, [])],
                    config_fields=CONFIG_FIELDS.get(impl.id, []),
                    config={
                        k: v for k, v in row.config.items() if k in CONFIG_FIELDS.get(impl.id, [])
                    },
                    status=row.status,
                    last_run_at=row.last_run_at,
                    last_error=row.last_error,
                    jobs_found=int(job_counts.get(impl.id, 0)),
                    companies=companies,
                    docs_url=impl.docs_url,
                    custom=impl.kind is PortalKind.PLUGIN,
                )
            )
        return views

    def view(self, portal_id: str) -> PortalView:
        return next(v for v in self.views() if v.id == portal_id)

    # --- updates ----------------------------------------------------------------------

    def set_enabled(self, portal_id: str, enabled: bool) -> PortalView:
        if not self.known(portal_id):
            raise KeyError(portal_id)
        with self._sessions.begin() as session:
            row = session.get(Portal, portal_id)
            if row is None:
                raise KeyError(portal_id)
            row.enabled = enabled
        return self.view(portal_id)

    def set_credentials(
        self, portal_id: str, secrets: dict[str, str], config: dict[str, str]
    ) -> PortalView:
        fields = dict(SECRET_FIELDS.get(portal_id, []))
        allowed_config = CONFIG_FIELDS.get(portal_id, [])
        unknown = (set(secrets) - set(fields)) | (set(config) - set(allowed_config))
        if unknown:
            raise ValueError(f"unknown fields: {', '.join(sorted(unknown))}")
        for field, value in secrets.items():
            if value.strip():
                keychain.set_secret(fields[field], value.strip())
        if config:
            with self._sessions.begin() as session:
                row = session.get(Portal, portal_id)
                if row is None:
                    raise KeyError(portal_id)
                row.config = {**row.config, **{k: v.strip() for k, v in config.items()}}
        view = self.view(portal_id)
        if view.ready and not view.enabled:  # saving a key means "use this source"
            view = self.set_enabled(portal_id, True)
        return view

    def clear_credentials(self, portal_id: str) -> PortalView:
        for _field, name in SECRET_FIELDS.get(portal_id, []):
            keychain.delete_secret(name)
        return self.view(portal_id)

    # --- watchlist --------------------------------------------------------------------

    def companies(self, ats: str | None = None) -> list[CompanyView]:
        with self._sessions() as session:
            stmt = select(Company).order_by(Company.ats, func.lower(Company.name))
            if ats:
                stmt = stmt.where(Company.ats == ats)
            return [CompanyView.model_validate(c) for c in session.scalars(stmt)]

    def add_companies(self, ats: str, entries: list[CompanyIn]) -> list[CompanyView]:
        if ats not in ATS_IDS:
            raise ValueError(f"{ats!r} is not an ATS source")
        with self._sessions.begin() as session:
            existing = {
                c.slug.lower(): c
                for c in session.scalars(select(Company).where(Company.ats == ats))
            }
            touched: list[Company] = []
            for entry in entries:
                row = existing.get(entry.slug.lower())
                if row is None:
                    row = Company(
                        ats=ats,
                        slug=entry.slug,
                        name=entry.name or entry.slug,
                        industry=entry.industry,
                        source="user",
                    )
                    session.add(row)
                    existing[entry.slug.lower()] = row
                else:
                    row.enabled = True
                touched.append(row)
            session.flush()
            return [CompanyView.model_validate(c) for c in touched]

    def set_company_enabled(self, company_id: int, enabled: bool) -> CompanyView:
        with self._sessions.begin() as session:
            row = session.get(Company, company_id)
            if row is None:
                raise KeyError(company_id)
            row.enabled = enabled
            session.flush()
            return CompanyView.model_validate(row)

    def remove_company(self, company_id: int) -> None:
        """User-added companies are deleted; starter ones are disabled so seeding won't
        bring them back."""
        with self._sessions.begin() as session:
            row = session.get(Company, company_id)
            if row is None:
                raise KeyError(company_id)
            if row.source == "user":
                session.delete(row)
            else:
                row.enabled = False
