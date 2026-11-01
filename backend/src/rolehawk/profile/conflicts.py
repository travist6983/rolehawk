"""Conflicts between versions of the same fact, for the user to resolve during /setup.

A CV, a LinkedIn export, and the existing profile often disagree: a role's title ("Data
Analyst II" on the CV, "Senior Data Analyst" on LinkedIn), its dates, a degree, an email.
Merging silently keeps one version (existing facts win), which hides the disagreement until
an interviewer notices it. So setup lists each conflict with every version and its source,
and applies the version the user picks to both sides before merging.

Each option carries a patch: the values to set on the matching role, degree, or contact
field. Applying the same patch to both profiles makes them agree, so the merge keeps one
entry. "They're different roles" is a patch that changes nothing.
"""

from __future__ import annotations

import hashlib
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

from rolehawk.profile.merge import merge_profile, norm, title_key
from rolehawk.profile.model import Education, Experience, Profile

ConflictKind = Literal["title", "dates", "degree", "contact"]
PatchKind = Literal["role", "education", "contact", "none"]
Value = str | bool | None


class Patch(BaseModel):
    kind: PatchKind
    company: str = ""  # norm(company) of the role
    titles: list[str] = Field(default_factory=list)  # title_key()s of the roles it applies to
    institution: str = ""  # norm(institution) of the degree
    values: dict[str, Value] = Field(default_factory=dict)


class ConflictOption(BaseModel):
    label: str
    source: str
    patch: Patch


class Conflict(BaseModel):
    id: str
    kind: ConflictKind
    subject: str
    question: str
    options: list[ConflictOption]


def _id(kind: str, *parts: object) -> str:
    return hashlib.sha256(repr((kind, *parts)).encode()).hexdigest()[:12]


def _month(value: str | None) -> str:
    """ "2021-03-15" and "2021-03" compare equal; "2021" stays a year."""
    return (value or "")[:7]


def _period(start: str | None, end: str | None, current: bool) -> str:
    if not start and not end and not current:
        return "no dates"
    return f"{start or '?'} - {'present' if current else end or '?'}"


def _as_date(value: str | None, default: date) -> date:
    if not value:
        return default
    try:
        year, _, month = value.partition("-")
        return date(int(year), int(month[:2] or 1), 1)
    except ValueError:
        return default


def _overlap(a: Experience, b: Experience) -> bool:
    if not a.start or not b.start:
        return False
    today = date.today()
    a_start, b_start = _as_date(a.start, today), _as_date(b.start, today)
    a_end = today if a.current else _as_date(a.end, today)
    b_end = today if b.current else _as_date(b.end, today)
    return a_start <= b_end and b_start <= a_end


def _similar(a: str, b: str) -> bool:
    words_a, words_b = set(title_key(a).split()), set(title_key(b).split())
    if not words_a or not words_b:
        return False
    return len(words_a & words_b) / len(words_a | words_b) >= 0.5


def _role_conflicts(
    current: list[Experience], incoming: list[Experience], sources: tuple[str, str]
) -> list[Conflict]:
    conflicts: list[Conflict] = []
    keyed = {(norm(e.company), title_key(e.title)): e for e in current}
    for new in incoming:
        company = norm(new.company)
        same = keyed.get((company, title_key(new.title)))
        at = f" at {new.company}" if new.company else ""
        if same is not None:
            a = (_month(same.start), _month(same.end), same.current)
            b = (_month(new.start), _month(new.end), new.current)
            if same.start and new.start and a != b:
                key = title_key(new.title)
                conflicts.append(
                    Conflict(
                        id=_id("dates", company, key, a, b),
                        kind="dates",
                        subject=f"{new.title}{at}",
                        question="Which dates are right?",
                        options=[
                            ConflictOption(
                                label=_period(e.start, e.end, e.current),
                                source=source,
                                patch=Patch(
                                    kind="role",
                                    company=company,
                                    titles=[key],
                                    values={"start": e.start, "end": e.end, "current": e.current},
                                ),
                            )
                            for e, source in ((same, sources[0]), (new, sources[1]))
                        ],
                    )
                )
            continue
        twin = next(
            (
                e
                for e in current
                if company
                and norm(e.company) == company
                and (
                    _overlap(e, new)
                    or ((not e.start or not new.start) and _similar(e.title, new.title))
                )
            ),
            None,
        )
        if twin is None:
            continue
        keys = [title_key(twin.title), title_key(new.title)]
        conflicts.append(
            Conflict(
                id=_id("title", company, *sorted(keys)),
                kind="title",
                subject=f"Your role{at}",
                question="Is this the same role? Pick the title that's right.",
                options=[
                    *(
                        ConflictOption(
                            label=title,
                            source=source,
                            patch=Patch(
                                kind="role", company=company, titles=keys, values={"title": title}
                            ),
                        )
                        for title, source in ((twin.title, sources[0]), (new.title, sources[1]))
                    ),
                    ConflictOption(
                        label="They're different roles: keep both",
                        source="",
                        patch=Patch(kind="none"),
                    ),
                ],
            )
        )
    return conflicts


def _degree(e: Education) -> str:
    words = " ".join(x for x in (e.degree, e.field) if x) or "no degree listed"
    if e.start and e.end:
        return f"{words} ({e.start} - {e.end})"
    return f"{words} ({e.end or e.start})" if e.start or e.end else words


def _education_conflicts(
    current: list[Education], incoming: list[Education], sources: tuple[str, str]
) -> list[Conflict]:
    conflicts: list[Conflict] = []
    for new in incoming:
        place = norm(new.institution)
        same = next((e for e in current if norm(e.institution) == place), None)
        if same is None:
            continue
        a = (norm(same.degree), norm(same.field), _month(same.end))
        b = (norm(new.degree), norm(new.field), _month(new.end))
        differs = any(x and y and x != y for x, y in zip(a, b, strict=True))
        if not differs:
            continue
        conflicts.append(
            Conflict(
                id=_id("degree", place, a, b),
                kind="degree",
                subject=new.institution,
                question="Which degree details are right?",
                options=[
                    ConflictOption(
                        label=_degree(e),
                        source=source,
                        patch=Patch(
                            kind="education",
                            institution=place,
                            values={
                                "degree": e.degree,
                                "field": e.field,
                                "start": e.start,
                                "end": e.end,
                            },
                        ),
                    )
                    for e, source in ((same, sources[0]), (new, sources[1]))
                ],
            )
        )
    return conflicts


def find_conflicts(current: Profile, incoming: Profile, sources: tuple[str, str]) -> list[Conflict]:
    """Facts the two profiles state differently, each with both versions and their source."""
    conflicts: list[Conflict] = []
    for name in ("name", "email", "phone"):
        a, b = getattr(current.contact, name), getattr(incoming.contact, name)
        if a and b and norm(a) != norm(b):
            conflicts.append(
                Conflict(
                    id=_id("contact", name, norm(a), norm(b)),
                    kind="contact",
                    subject=f"Your {name}",
                    question=f"Which {name} should your CV use?",
                    options=[
                        ConflictOption(
                            label=value,
                            source=source,
                            patch=Patch(kind="contact", values={name: value}),
                        )
                        for value, source in ((a, sources[0]), (b, sources[1]))
                    ],
                )
            )
    conflicts += _role_conflicts(current.experience, incoming.experience, sources)
    conflicts += _education_conflicts(current.education, incoming.education, sources)
    return list({c.id: c for c in conflicts}.values())


def apply_patch(profile: Profile, patch: Patch) -> Profile:
    out = profile.model_copy(deep=True)
    if patch.kind == "contact":
        out.contact = out.contact.model_copy(update=patch.values)
    elif patch.kind == "role":
        out.experience = [
            e.model_copy(update=patch.values)
            if norm(e.company) == patch.company and title_key(e.title) in patch.titles
            else e
            for e in out.experience
        ]
    elif patch.kind == "education":
        out.education = [
            e.model_copy(update=patch.values) if norm(e.institution) == patch.institution else e
            for e in out.education
        ]
    return out


def resolve(
    current: Profile,
    incoming: Profile,
    conflicts: list[Conflict],
    choices: dict[str, int],
) -> tuple[Profile, Profile]:
    """Apply the chosen version of each conflict to both profiles (the first option, the
    existing version, when the user didn't pick). The incoming side is collapsed so two
    versions of one role in the new documents become one; the current profile isn't (two
    stints at the same company stay two)."""
    for conflict in conflicts:
        pick = choices.get(conflict.id, 0)
        option = conflict.options[pick if 0 <= pick < len(conflict.options) else 0]
        current = apply_patch(current, option.patch)
        incoming = apply_patch(incoming, option.patch)
    collapsed, _ = merge_profile(Profile(), incoming)
    return current, collapsed
