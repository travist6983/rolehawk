"""Resume / CV text -> structured profile with Claude (structured output). The result is a
draft the user reviews before anything is saved.

Claude fills a wire schema (`ExtractionOut`), not `Profile` itself. Structured outputs refuse
schemas with more than 24 optional fields or 16 nullable/union fields in total ("Schema is too
complex for compilation"), and `Profile` + `Preferences` have 44 and 24. So on the wire every
field is required and nothing is nullable: unknown text is "" and an unknown amount is 0.
`to_setup()` turns that back into the canonical models.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from rolehawk.llm.prompting import UNTRUSTED_RULES, untrusted
from rolehawk.llm.service import LLMService
from rolehawk.llm.types import Message, SystemBlock, Task
from rolehawk.profile.model import (
    Certification,
    Contact,
    Education,
    Experience,
    Preferences,
    Profile,
    Project,
    RemotePreference,
    SalaryFloor,
    SalaryPeriod,
)

MAX_EXTRACT_CHARS = 120_000

EXTRACTION_PROMPT = f"""\
You turn a job seeker's own resume, CV, or profile text into a structured profile.

Accuracy rules (these matter more than completeness):
- Extract only what the documents state. Never infer, guess, round, or embellish.
- Keep achievements in the candidate's own words; split multi-sentence bullets only where the
  document clearly lists separate points. Never add numbers that aren't in the text.
- Dates: "YYYY-MM" when the month is given, else "YYYY". Mark current roles with current=true
  and end=null. Leave unknown dates null.
- skills: only skills the document lists or that are named in its text; no synonyms.
- preferences: fill only what the document states outright (e.g. an "Objective" naming target
  roles or locations). Otherwise leave preferences empty.
- Contact: copy name, email, phone, location, and profile links exactly.
- Every field must be present. When the document doesn't state something, use "" for text,
  0 for salary_amount, [] for lists, and false for current.
- {UNTRUSTED_RULES}
"""


class ExtractedSetup(BaseModel):
    profile: Profile = Field(default_factory=Profile)
    preferences: Preferences = Field(default_factory=Preferences)


# --- the wire schema Claude fills ---------------------------------------------------------


class _Wire(BaseModel):
    model_config = ConfigDict(extra="forbid")


_DATE = 'YYYY or YYYY-MM, or "" when not stated'


class WireContact(_Wire):
    name: str
    email: str
    phone: str
    location: str
    links: list[str] = Field(description="Profile URLs (LinkedIn, GitHub, site), one per item")


class WireExperience(_Wire):
    title: str
    company: str
    location: str
    start: str = Field(description=_DATE)
    end: str = Field(description=f'{_DATE}; "" when current')
    current: bool
    highlights: list[str]


class WireEducation(_Wire):
    institution: str
    degree: str
    field: str
    start: str = Field(description=_DATE)
    end: str = Field(description=_DATE)
    notes: str


class WireProject(_Wire):
    name: str
    url: str
    highlights: list[str]


class WireCertification(_Wire):
    name: str
    issuer: str
    date: str = Field(description=_DATE)
    url: str


class WireProfile(_Wire):
    contact: WireContact
    headline: str
    summary: str
    experience: list[WireExperience]
    education: list[WireEducation]
    skills: list[str]
    projects: list[WireProject]
    certifications: list[WireCertification]
    achievements: list[str]
    languages: list[str]


class WirePreferences(_Wire):
    target_titles: list[str]
    seniority: str
    locations: list[str]
    remote: Literal["", "remote", "hybrid", "onsite", "any"]
    country: str = Field(description='ISO 3166-1 alpha-2, or ""')
    salary_amount: int = Field(description="Minimum salary stated, or 0 when not stated")
    salary_currency: str = Field(description='ISO 4217 code such as "USD", or ""')
    salary_period: Literal["year", "month", "hour"]
    work_authorization: str
    deal_breakers: list[str]
    energizing: list[str]
    draining: list[str]


class ExtractionOut(_Wire):
    profile: WireProfile
    preferences: WirePreferences

    def to_setup(self) -> ExtractedSetup:
        return ExtractedSetup(
            profile=_profile(self.profile), preferences=_preferences(self.preferences)
        )

    @classmethod
    def from_setup(cls, setup: ExtractedSetup) -> ExtractionOut:
        """The inverse of `to_setup` (for scripted replies in tests and demos)."""
        p, prefs = setup.profile, setup.preferences
        c = p.contact
        floor = prefs.salary_floor
        return cls(
            profile=WireProfile(
                contact=WireContact(
                    name=c.name or "",
                    email=c.email or "",
                    phone=c.phone or "",
                    location=c.location or "",
                    links=list(c.links),
                ),
                headline=p.headline or "",
                summary=p.summary or "",
                experience=[
                    WireExperience(
                        title=e.title,
                        company=e.company or "",
                        location=e.location or "",
                        start=e.start or "",
                        end=e.end or "",
                        current=e.current,
                        highlights=list(e.highlights),
                    )
                    for e in p.experience
                ],
                education=[
                    WireEducation(
                        institution=e.institution,
                        degree=e.degree or "",
                        field=e.field or "",
                        start=e.start or "",
                        end=e.end or "",
                        notes=e.notes or "",
                    )
                    for e in p.education
                ],
                skills=list(p.skills),
                projects=[
                    WireProject(name=x.name, url=x.url or "", highlights=list(x.highlights))
                    for x in p.projects
                ],
                certifications=[
                    WireCertification(
                        name=x.name, issuer=x.issuer or "", date=x.date or "", url=x.url or ""
                    )
                    for x in p.certifications
                ],
                achievements=list(p.achievements),
                languages=list(p.languages),
            ),
            preferences=WirePreferences(
                target_titles=list(prefs.target_titles),
                seniority=prefs.seniority or "",
                locations=list(prefs.locations),
                remote=prefs.remote.value if prefs.remote else "",
                country=prefs.country or "",
                salary_amount=floor.amount if floor else 0,
                salary_currency=floor.currency if floor else "",
                salary_period=floor.period.value if floor else "year",
                work_authorization=prefs.work_authorization or "",
                deal_breakers=list(prefs.deal_breakers),
                energizing=list(prefs.energizing),
                draining=list(prefs.draining),
            ),
        )


def _text(value: str) -> str | None:
    value = value.strip()
    return value or None


def _items(values: list[str]) -> list[str]:
    return [v.strip() for v in values if v.strip()]


def _profile(w: WireProfile) -> Profile:
    c = w.contact
    return Profile(
        contact=Contact(
            name=_text(c.name),
            email=_text(c.email),
            phone=_text(c.phone),
            location=_text(c.location),
            links=_items(c.links),
        ),
        headline=_text(w.headline),
        summary=_text(w.summary),
        experience=[
            Experience(
                title=e.title.strip(),
                company=_text(e.company),
                location=_text(e.location),
                start=_text(e.start),
                end=None if e.current else _text(e.end),
                current=e.current,
                highlights=_items(e.highlights),
            )
            for e in w.experience
            if e.title.strip()
        ],
        education=[
            Education(
                institution=e.institution.strip(),
                degree=_text(e.degree),
                field=_text(e.field),
                start=_text(e.start),
                end=_text(e.end),
                notes=_text(e.notes),
            )
            for e in w.education
            if e.institution.strip()
        ],
        skills=_items(w.skills),
        projects=[
            Project(name=x.name.strip(), url=_text(x.url), highlights=_items(x.highlights))
            for x in w.projects
            if x.name.strip()
        ],
        certifications=[
            Certification(
                name=x.name.strip(), issuer=_text(x.issuer), date=_text(x.date), url=_text(x.url)
            )
            for x in w.certifications
            if x.name.strip()
        ],
        achievements=_items(w.achievements),
        languages=_items(w.languages),
    )


def _preferences(w: WirePreferences) -> Preferences:
    currency = w.salary_currency.strip().upper()
    floor = (
        SalaryFloor(amount=w.salary_amount, currency=currency, period=SalaryPeriod(w.salary_period))
        if w.salary_amount > 0 and len(currency) == 3 and currency.isalpha()
        else None
    )
    return Preferences(
        target_titles=_items(w.target_titles),
        seniority=_text(w.seniority),
        locations=_items(w.locations),
        remote=RemotePreference(w.remote) if w.remote else None,
        country=_text(w.country.upper()),
        salary_floor=floor,
        work_authorization=_text(w.work_authorization),
        deal_breakers=_items(w.deal_breakers),
        energizing=_items(w.energizing),
        draining=_items(w.draining),
    )


async def extract_setup(
    llm: LLMService, documents: list[tuple[str, str]], task_id: str | None = None
) -> ExtractedSetup:
    """`documents` is a list of (label, text)."""
    blocks = [untrusted("candidate_document", text, name=label) for label, text in documents]
    body = "\n\n".join(blocks)
    if len(body) > MAX_EXTRACT_CHARS:
        raise ValueError("Those documents are too long to read at once; upload just your CV.")
    wire = await llm.structured(
        command="setup",
        task=Task.EXTRACT,
        system=[SystemBlock(EXTRACTION_PROMPT)],
        messages=[Message(role="user", text=f"Extract the profile from:\n\n{body}")],
        schema=ExtractionOut,
        task_id=task_id,
    )
    return wire.to_setup()
