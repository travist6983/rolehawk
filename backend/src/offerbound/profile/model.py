from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field
from pydantic.json_schema import SkipJsonSchema


class _Model(BaseModel):
    # Responses always include defaulted fields, so the generated TypeScript marks them required.
    model_config = ConfigDict(extra="forbid", json_schema_serialization_defaults_required=True)


class Contact(_Model):
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    location: str | None = None
    links: list[str] = Field(default_factory=list)


class Experience(_Model):
    title: str
    company: str | None = None
    location: str | None = None
    start: str | None = Field(default=None, description="YYYY or YYYY-MM")
    end: str | None = Field(default=None, description="YYYY or YYYY-MM; null when current")
    current: bool = False
    highlights: list[str] = Field(default_factory=list)


class Education(_Model):
    institution: str
    degree: str | None = None
    field: str | None = None
    start: str | None = None
    end: str | None = None
    notes: str | None = None


class Project(_Model):
    name: str
    url: str | None = None
    highlights: list[str] = Field(default_factory=list)


class Certification(_Model):
    name: str
    issuer: str | None = None
    date: str | None = None
    url: str | None = None


class Profile(_Model):
    contact: Contact = Field(default_factory=Contact)
    headline: str | None = None
    summary: str | None = None
    experience: list[Experience] = Field(default_factory=list)
    education: list[Education] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    projects: list[Project] = Field(default_factory=list)
    certifications: list[Certification] = Field(default_factory=list)
    achievements: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    # Sections the parser doesn't know, kept verbatim so hand edits are never lost. Hidden
    # from JSON schemas so structured AI output never fills it.
    extra_sections: SkipJsonSchema[dict[str, str]] = Field(default_factory=dict)


class RemotePreference(StrEnum):
    REMOTE = "remote"
    HYBRID = "hybrid"
    ONSITE = "onsite"
    ANY = "any"


class SalaryPeriod(StrEnum):
    YEAR = "year"
    MONTH = "month"
    HOUR = "hour"


class SalaryFloor(_Model):
    amount: int = Field(ge=0)
    currency: str = Field(min_length=3, max_length=3)
    period: SalaryPeriod = SalaryPeriod.YEAR


class Preferences(_Model):
    target_titles: list[str] = Field(default_factory=list)
    seniority: str | None = None
    locations: list[str] = Field(default_factory=list)
    remote: RemotePreference | None = None
    country: str | None = Field(default=None, description="ISO 3166-1 alpha-2")
    salary_floor: SalaryFloor | None = None
    work_authorization: str | None = None
    deal_breakers: list[str] = Field(default_factory=list)
    extra_sections: SkipJsonSchema[dict[str, str]] = Field(default_factory=dict)
