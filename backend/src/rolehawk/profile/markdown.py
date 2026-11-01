"""profile.md / preferences.md <-> typed models.

The renderer writes a fixed, readable layout. The parser accepts that layout plus common hand
edits (e.g. "Title at Company" headings, comma lists) and keeps unknown sections verbatim.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from rolehawk.profile.model import (
    Certification,
    Contact,
    Education,
    Experience,
    Preferences,
    Profile,
    Project,
    RemotePreference,
)
from rolehawk.profile.parsing import (
    dedupe,
    format_date_range,
    format_salary,
    parse_date_range,
    parse_salary,
)

PROFILE_COMMENT = (
    "<!-- Your canonical candidate profile. Generated CVs and cover letters may only use facts\n"
    "written here. Edit freely; RoleHawk changes this file only when you save setup results,\n"
    "answer the setup interview, or accept a proposal. -->"
)

REMOTE_LABELS = {
    RemotePreference.REMOTE: "Remote only",
    RemotePreference.HYBRID: "Hybrid",
    RemotePreference.ONSITE: "On-site",
    RemotePreference.ANY: "Any",
}

_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_BULLET = re.compile(r"^\s*[-*•]\s+(.*)$")
_FIELD = re.compile(r"^([A-Za-z][A-Za-z ]{0,20}):\s*(.*)$")


# --- generic section splitting ---------------------------------------------------------


def _sections(markdown: str) -> list[tuple[str, list[str]]]:
    """Split on `## ` headings. Text before the first heading (title, comments) is dropped."""
    sections: list[tuple[str, list[str]]] = []
    for line in _COMMENT.sub("", markdown).splitlines():
        if line.startswith("## "):
            sections.append((line[3:].strip(), []))
        elif sections and not line.startswith("# "):
            sections[-1][1].append(line.rstrip())
    return sections


def _bullets(lines: Iterable[str]) -> list[str]:
    out: list[str] = []
    for line in lines:
        if match := _BULLET.match(line):
            if match.group(1).strip():
                out.append(match.group(1).strip())
        elif line.strip():
            out.append(line.strip())
    return out


def _text(lines: Iterable[str]) -> str | None:
    paragraph = "\n".join(line for line in lines).strip()
    return paragraph or None


def _entries(lines: list[str]) -> tuple[list[str], list[tuple[str, list[str]]]]:
    """Split a section into `### ` entries. Returns (lines before the first entry, entries)."""
    preamble: list[str] = []
    entries: list[tuple[str, list[str]]] = []
    for line in lines:
        if line.startswith("### "):
            entries.append((line[4:].strip(), []))
        elif entries:
            entries[-1][1].append(line)
        else:
            preamble.append(line)
    return preamble, entries


def _split_heading(heading: str) -> tuple[str, str | None]:
    if " | " in heading:
        left, right = heading.split(" | ", 1)
        return left.strip(), right.strip() or None
    if match := re.match(r"^(.*?)\s+(?:at|@)\s+(.+)$", heading):
        return match.group(1).strip(), match.group(2).strip()
    return heading.strip(), None


# --- profile -----------------------------------------------------------------------------


def _parse_experience(lines: list[str]) -> tuple[list[Experience], str | None]:
    preamble, entries = _entries(lines)
    out: list[Experience] = []
    for heading, body in entries:
        title, company = _split_heading(heading)
        entry = Experience(title=title, company=company)
        for item in _bullets(body):
            field = _FIELD.match(item)
            key = field.group(1).lower() if field else ""
            parsed = (
                parse_date_range(field.group(2)) if field and key in {"when", "dates"} else None
            )
            if parsed:
                entry.start, entry.end, entry.current = parsed.start, parsed.end, parsed.current
                continue
            if key in {"where", "location"} and field:
                entry.location = field.group(2).strip() or None
                continue
            entry.highlights.append(item)
        out.append(entry)
    return out, _text(preamble)


def _parse_education(lines: list[str]) -> list[Education]:
    _, entries = _entries(lines)
    out: list[Education] = []
    for heading, body in entries:
        left, institution = _split_heading(heading)
        if institution is None:
            entry = Education(institution=left)
        else:
            degree, _, field = left.partition(", ")
            entry = Education(institution=institution, degree=degree or None, field=field or None)
        notes: list[str] = []
        for item in _bullets(body):
            field_match = _FIELD.match(item)
            key = field_match.group(1).lower() if field_match else ""
            parsed = (
                parse_date_range(field_match.group(2))
                if field_match and key in {"when", "dates"}
                else None
            )
            if parsed:
                entry.start, entry.end = parsed.start, parsed.end
                continue
            notes.append(field_match.group(2) if key == "notes" and field_match else item)
        entry.notes = "; ".join(notes) or None
        out.append(entry)
    return out


def _parse_projects(lines: list[str]) -> list[Project]:
    _, entries = _entries(lines)
    out: list[Project] = []
    for heading, body in entries:
        project = Project(name=heading)
        for item in _bullets(body):
            field = _FIELD.match(item)
            if field and field.group(1).lower() in {"url", "link"}:
                project.url = field.group(2).strip() or None
            else:
                project.highlights.append(item)
        out.append(project)
    return out


def _parse_certifications(lines: list[str]) -> list[Certification]:
    out: list[Certification] = []
    for item in _bullets(lines):
        parts = [p.strip() for p in item.split(" | ")]
        out.append(
            Certification(
                name=parts[0],
                issuer=parts[1] if len(parts) > 1 and parts[1] else None,
                date=parts[2] if len(parts) > 2 and parts[2] else None,
                url=parts[3] if len(parts) > 3 and parts[3] else None,
            )
        )
    return out


def _parse_contact(lines: list[str]) -> Contact:
    contact = Contact()
    for item in _bullets(lines):
        field = _FIELD.match(item)
        if not field:
            continue
        key, value = field.group(1).lower(), field.group(2).strip()
        if key == "name":
            contact.name = value or None
        elif key == "email":
            contact.email = value or None
        elif key == "phone":
            contact.phone = value or None
        elif key == "location":
            contact.location = value or None
        elif key in {"links", "link"}:
            contact.links = [link.strip() for link in value.split(",") if link.strip()]
    return contact


def _list_items(lines: list[str]) -> list[str]:
    items = _bullets(lines)
    if len(items) == 1 and "," in items[0]:  # "Python, React, SQL" on one line
        items = [part.strip() for part in items[0].split(",")]
    return dedupe(items)


def parse_profile(markdown: str) -> Profile:
    profile = Profile()
    for name, lines in _sections(markdown):
        key = name.strip().lower()
        if key == "contact":
            profile.contact = _parse_contact(lines)
        elif key == "headline":
            profile.headline = _text(lines)
        elif key in {"summary", "about"}:
            profile.summary = _text(lines)
        elif key in {"experience", "work experience"}:
            profile.experience, preamble = _parse_experience(lines)
            if preamble:
                profile.extra_sections["Experience notes"] = preamble
        elif key == "education":
            profile.education = _parse_education(lines)
        elif key == "skills":
            profile.skills = _list_items(lines)
        elif key == "projects":
            profile.projects = _parse_projects(lines)
        elif key in {"certifications", "certificates"}:
            profile.certifications = _parse_certifications(lines)
        elif key == "achievements":
            profile.achievements = dedupe(_bullets(lines))
        elif key == "languages":
            profile.languages = _list_items(lines)
        elif text := _text(lines):
            profile.extra_sections[name.strip()] = text
    return profile


def _join(parts: list[str]) -> str:
    return "\n".join(parts).rstrip() + "\n"


def render_profile(profile: Profile) -> str:
    out = ["# Profile", "", PROFILE_COMMENT, ""]
    c = profile.contact
    out.append("## Contact\n")
    for label, value in [
        ("Name", c.name),
        ("Email", c.email),
        ("Phone", c.phone),
        ("Location", c.location),
        ("Links", ", ".join(c.links) if c.links else None),
    ]:
        if value:
            out.append(f"- {label}: {value}")
    out += ["", "## Headline", ""]
    if profile.headline:
        out += [profile.headline, ""]
    out += ["## Summary", ""]
    if profile.summary:
        out += [profile.summary, ""]
    out += ["## Experience", ""]
    for exp in profile.experience:
        out.append(f"### {exp.title}" + (f" | {exp.company}" if exp.company else ""))
        out.append("")
        if when := format_date_range(exp.start, exp.end, exp.current):
            out.append(f"- When: {when}")
        if exp.location:
            out.append(f"- Where: {exp.location}")
        out += [f"- {h}" for h in exp.highlights]
        out.append("")
    if notes := profile.extra_sections.get("Experience notes"):
        out += [notes, ""]
    out += ["## Education", ""]
    for edu in profile.education:
        left = ", ".join(p for p in [edu.degree, edu.field] if p)
        out.append(f"### {left} | {edu.institution}" if left else f"### {edu.institution}")
        out.append("")
        if when := format_date_range(edu.start, edu.end, False):
            out.append(f"- When: {when}")
        if edu.notes:
            out.append(f"- Notes: {edu.notes}")
        out.append("")
    for title, items in [("Skills", profile.skills)]:
        out += [f"## {title}", ""] + [f"- {s}" for s in items] + ([""] if items else [])
    out += ["## Projects", ""]
    for project in profile.projects:
        out += [f"### {project.name}", ""]
        if project.url:
            out.append(f"- URL: {project.url}")
        out += [f"- {h}" for h in project.highlights]
        out.append("")
    out += ["## Certifications", ""]
    for cert in profile.certifications:
        parts = [cert.name, cert.issuer or "", cert.date or "", cert.url or ""]
        while parts and not parts[-1]:
            parts.pop()
        out.append("- " + " | ".join(parts))
    if profile.certifications:
        out.append("")
    for title, items in [("Achievements", profile.achievements), ("Languages", profile.languages)]:
        out += [f"## {title}", ""] + [f"- {s}" for s in items] + ([""] if items else [])
    for name, text in profile.extra_sections.items():
        if name != "Experience notes":
            out += [f"## {name}", "", text, ""]
    return _join(out)


# --- preferences ---------------------------------------------------------------------------


def _parse_remote(text: str | None) -> RemotePreference | None:
    if not text:
        return None
    value = text.lower()
    if "hybrid" in value:
        return RemotePreference.HYBRID
    if "on-site" in value or "onsite" in value or "office" in value:
        return RemotePreference.ONSITE
    if "any" in value or "flexible" in value or "open" in value:
        return RemotePreference.ANY
    if "remote" in value:
        return RemotePreference.REMOTE
    return None


def parse_preferences(markdown: str, default_currency: str = "USD") -> Preferences:
    prefs = Preferences()
    for name, lines in _sections(markdown):
        key = name.strip().lower()
        items = _bullets(lines)
        first = items[0] if items else None
        # Titles and places can contain commas, so only bullets separate them.
        if key in {"target titles", "target roles", "titles"}:
            prefs.target_titles = dedupe(items)
        elif key == "seniority":
            prefs.seniority = first
        elif key == "locations":
            prefs.locations = dedupe(items)
        elif key == "remote":
            prefs.remote = _parse_remote(first)
        elif key == "country":
            prefs.country = first.upper()[:2] if first else None
        elif key == "salary floor":
            prefs.salary_floor = parse_salary(first, default_currency) if first else None
        elif key == "work authorization":
            prefs.work_authorization = " ".join(items) or None
        elif key in {"deal-breakers", "deal breakers", "dealbreakers"}:
            prefs.deal_breakers = dedupe(items)
        elif key in {"work that energizes me", "energizing work", "what energizes me"}:
            prefs.energizing = dedupe(items)
        elif key in {"work that drains me", "draining work", "what drains me"}:
            prefs.draining = dedupe(items)
        elif text := _text(lines):
            prefs.extra_sections[name.strip()] = text
    return prefs


def render_preferences(prefs: Preferences) -> str:
    def section(title: str, items: list[str]) -> list[str]:
        return [f"## {title}", ""] + [f"- {item}" for item in items] + ([""] if items else [])

    out = ["# Preferences", ""]
    out += section("Target titles", prefs.target_titles)
    out += section("Seniority", [prefs.seniority] if prefs.seniority else [])
    out += section("Locations", prefs.locations)
    out += section("Remote", [REMOTE_LABELS[prefs.remote]] if prefs.remote else [])
    out += section("Country", [prefs.country] if prefs.country else [])
    out += section(
        "Salary floor", [format_salary(prefs.salary_floor)] if prefs.salary_floor else []
    )
    out += section(
        "Work authorization", [prefs.work_authorization] if prefs.work_authorization else []
    )
    out += section("Deal-breakers", prefs.deal_breakers)
    out += section("Work that energizes me", prefs.energizing)
    out += section("Work that drains me", prefs.draining)
    for name, text in prefs.extra_sections.items():
        out += [f"## {name}", "", text, ""]
    return _join(out)
