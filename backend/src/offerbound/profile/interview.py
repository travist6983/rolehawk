"""The /setup gap interview: one question at a time, multiple choice where possible.

Questions are computed from what the profile and preferences are missing, so the interview
is resumable (state is the files themselves plus a small list of skipped questions) and works
with no resume and no API key. Answers are the user's own words and are written directly."""

from __future__ import annotations

import hashlib
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from offerbound import countries
from offerbound.profile.model import (
    Contact,
    Education,
    Experience,
    Preferences,
    Profile,
    RemotePreference,
)
from offerbound.profile.parsing import (
    dedupe,
    parse_date_range,
    parse_salary,
    split_lines,
    split_list,
    split_places,
)

QuestionKind = Literal["single", "multi", "text", "list", "form"]
AnswerValue = str | list[str] | dict[str, str]

MAX_METRIC_QUESTIONS = 3


class _Out(BaseModel):
    model_config = ConfigDict(json_schema_serialization_defaults_required=True)


class Choice(_Out):
    value: str
    label: str


class FormField(_Out):
    name: str
    label: str
    kind: Literal["text", "textarea"] = "text"
    required: bool = False
    placeholder: str | None = None


class Question(_Out):
    id: str
    prompt: str
    help: str | None = None
    kind: QuestionKind
    choices: list[Choice] = Field(default_factory=list)
    allow_other: bool = False
    optional: bool = True
    skip_label: str = "Skip"
    placeholder: str | None = None
    fields: list[FormField] = Field(default_factory=list)
    value: AnswerValue | None = None  # prefill


class InterviewProgress(BaseModel):
    skipped: list[str] = Field(default_factory=list)
    answered: list[str] = Field(default_factory=list)
    adding_role: bool = False
    roles_done: bool = False


class InterviewState(_Out):
    question: Question | None
    answered: int
    remaining: int
    complete: bool


class AnswerError(ValueError):
    """The answer can't be used; the message is shown next to the question."""


def _short_hash(*parts: str | None) -> str:
    return hashlib.sha256("|".join(p or "" for p in parts).encode()).hexdigest()[:8]


def _role_dates_id(exp: Experience) -> str:
    return f"role.dates.{_short_hash(exp.title, exp.company)}"


def _metric_id(highlight: str) -> str:
    return f"metric.{_short_hash(highlight)}"


SENIORITY = ["Entry level", "Mid level", "Senior", "Staff / Principal", "Manager", "Director+"]
WORK_AUTH = [
    "Citizen or permanent resident",
    "Have a work visa (no sponsorship needed)",
    "Need visa sponsorship",
]
DEAL_BREAKERS = [
    "Relocation required",
    "Mandatory on-call",
    "Contract or agency roles",
    "Unpaid trial work",
    "Fully in-office",
]

ROLE_FIELDS = [
    FormField(
        name="title", label="Job title", required=True, placeholder="Senior Frontend Engineer"
    ),
    FormField(name="company", label="Company", placeholder="Acme Corp"),
    FormField(name="dates", label="Dates", placeholder="Mar 2021 - present"),
    FormField(name="location", label="Location", placeholder="Remote"),
    FormField(
        name="highlights",
        label="What did you achieve? One per line, with numbers where you can.",
        kind="textarea",
        placeholder="Cut page load time 40% by ...",
    ),
]


def open_questions(
    profile: Profile, prefs: Preferences, progress: InterviewProgress
) -> list[Question]:
    """Every question still worth asking, in order. The interview asks the first one."""
    skipped = set(progress.skipped)
    out: list[Question] = []

    def ask(question: Question) -> None:
        if question.id not in skipped:
            out.append(question)

    if not profile.contact.name:
        ask(
            Question(
                id="basics.contact",
                prompt="First, the basics for your CV header.",
                kind="form",
                optional=False,
                fields=[
                    FormField(name="name", label="Full name", required=True),
                    FormField(name="email", label="Email"),
                    FormField(name="location", label="City and country", placeholder="Austin, TX"),
                    FormField(
                        name="links",
                        label="Links (LinkedIn, GitHub, site)",
                        placeholder="comma separated",
                    ),
                ],
            )
        )

    if (not profile.experience and "role.add" not in skipped) or progress.adding_role:
        ask(
            Question(
                id="role.add",
                prompt="Tell me about your most recent role."
                if not profile.experience
                else "Add another role.",
                help="Only what's true: Offerbound never invents details for your CV.",
                kind="form",
                fields=ROLE_FIELDS,
                skip_label="I don't have work experience yet"
                if not profile.experience
                else "Done adding roles",
            )
        )
    elif profile.experience and not progress.roles_done:
        ask(
            Question(
                id="role.more",
                prompt="Is there another role you'd like on your profile?",
                kind="single",
                choices=[
                    Choice(value="yes", label="Yes, add a role"),
                    Choice(value="no", label="No, that's all"),
                ],
                optional=False,
            )
        )

    if len(profile.skills) < 3:
        ask(
            Question(
                id="profile.skills",
                prompt="What are your strongest skills?",
                help="Tools, languages, and methods you'd be happy to be interviewed on.",
                kind="list",
                placeholder="TypeScript, React, PostgreSQL",
                value=profile.skills or None,
            )
        )

    if not profile.education:
        ask(
            Question(
                id="profile.education",
                prompt="What's your highest education?",
                kind="form",
                skip_label="Skip (not relevant)",
                fields=[
                    FormField(name="institution", label="School or university", required=True),
                    FormField(name="degree", label="Degree", placeholder="BSc"),
                    FormField(name="field", label="Field of study", placeholder="Computer Science"),
                    FormField(name="dates", label="Dates", placeholder="2015 - 2019"),
                ],
            )
        )

    recent_titles = dedupe([e.title for e in profile.experience[:3]])
    if not prefs.target_titles:
        ask(
            Question(
                id="prefs.titles",
                prompt="Which job titles should I search for?",
                kind="multi",
                choices=[Choice(value=t, label=t) for t in recent_titles],
                allow_other=True,
                optional=False,
                placeholder="Add other titles, comma separated",
            )
        )
    if not prefs.seniority:
        ask(
            Question(
                id="prefs.seniority",
                prompt="What level are you aiming for?",
                kind="single",
                choices=[Choice(value=s, label=s) for s in SENIORITY],
            )
        )
    if not prefs.remote:
        ask(
            Question(
                id="prefs.remote",
                prompt="How do you want to work?",
                kind="single",
                choices=[
                    Choice(value=RemotePreference.REMOTE.value, label="Remote only"),
                    Choice(value=RemotePreference.HYBRID.value, label="Hybrid"),
                    Choice(value=RemotePreference.ONSITE.value, label="On-site"),
                    Choice(value=RemotePreference.ANY.value, label="Open to any"),
                ],
                optional=False,
            )
        )
    if not prefs.country:
        ask(
            Question(
                id="prefs.country",
                prompt="Which country are you job hunting in?",
                help="Picks the right job sources, currency, and salary format.",
                kind="single",
                choices=[Choice(value=c, label=n) for c, n in countries.known_countries()],
                allow_other=True,
                placeholder="Other country code, e.g. FR",
                optional=False,
            )
        )
    if not prefs.locations and prefs.remote is not RemotePreference.REMOTE:
        ask(
            Question(
                id="prefs.locations",
                prompt="Which cities or regions work for you?",
                help="Separate places with semicolons; commas stay part of a place name.",
                kind="text",
                placeholder="Denver, CO; Boulder, CO",
                value=profile.contact.location,
            )
        )
    if not prefs.salary_floor:
        currency = countries.defaults_for(prefs.country).currency
        ask(
            Question(
                id="prefs.salary",
                prompt="What's the lowest salary you'd accept?",
                help=f"Used to filter out jobs below it. Amounts default to {currency} per year.",
                kind="text",
                placeholder=f"e.g. 120k {currency}",
            )
        )
    if not prefs.work_authorization:
        ask(
            Question(
                id="prefs.work_auth",
                prompt="What's your work authorization in that country?",
                kind="single",
                choices=[Choice(value=w, label=w) for w in WORK_AUTH],
                allow_other=True,
            )
        )
    if not prefs.deal_breakers:
        ask(
            Question(
                id="prefs.deal_breakers",
                prompt="Any deal-breakers?",
                kind="multi",
                choices=[Choice(value=d, label=d) for d in DEAL_BREAKERS],
                allow_other=True,
                skip_label="None",
            )
        )

    # Refinements: missing dates, then achievements that could use a number.
    for exp in profile.experience:
        if not exp.start:
            ask(
                Question(
                    id=_role_dates_id(exp),
                    prompt=f"When did you work as {exp.title}"
                    + (f" at {exp.company}?" if exp.company else "?"),
                    kind="text",
                    placeholder="Mar 2021 - present",
                )
            )
    metric_questions = 0
    for exp in profile.experience[:2]:
        for highlight in exp.highlights:
            if metric_questions >= MAX_METRIC_QUESTIONS:
                break
            if re.search(r"\d", highlight) or len(highlight) < 25:
                continue
            question_id = _metric_id(highlight)
            if question_id in skipped:
                continue
            metric_questions += 1
            out.append(
                Question(
                    id=question_id,
                    prompt="Can you add a number to this achievement?",
                    help="Recruiters skim for results. Only add a number you can stand behind.",
                    kind="text",
                    value=highlight,
                    skip_label="Keep as is",
                )
            )
    return out


def state(profile: Profile, prefs: Preferences, progress: InterviewProgress) -> InterviewState:
    remaining = open_questions(profile, prefs, progress)
    return InterviewState(
        question=remaining[0] if remaining else None,
        answered=len(progress.answered),
        remaining=len(remaining),
        complete=not remaining,
    )


# --- applying answers ---------------------------------------------------------------------


def _text(value: AnswerValue, required: bool = True) -> str:
    if not isinstance(value, str):
        raise AnswerError("Expected a text answer.")
    if required and not value.strip():
        raise AnswerError("Please enter an answer, or skip this question.")
    return value.strip()


def _items(value: AnswerValue) -> list[str]:
    if isinstance(value, list):
        return dedupe([item for v in value for item in split_list(v)])
    if isinstance(value, str):
        return split_list(value)
    raise AnswerError("Expected a list.")


def _form(value: AnswerValue, required: list[str]) -> dict[str, str]:
    if not isinstance(value, dict):
        raise AnswerError("Expected a form.")
    form = {k: v.strip() for k, v in value.items() if isinstance(v, str)}
    for name in required:
        if not form.get(name):
            raise AnswerError(f"{name.replace('_', ' ').capitalize()} is required.")
    return form


def _dates(text: str | None) -> tuple[str | None, str | None, bool]:
    if not text:
        return None, None, False
    parsed = parse_date_range(text)
    if parsed is None:
        raise AnswerError('Couldn\'t read those dates. Try "Mar 2021 - present" or "2019 - 2021".')
    return parsed.start, parsed.end, parsed.current


def apply_answer(
    question_id: str,
    value: AnswerValue,
    profile: Profile,
    prefs: Preferences,
    progress: InterviewProgress,
) -> tuple[Profile, Preferences, InterviewProgress]:
    """Returns updated copies. Raises AnswerError for answers that can't be used."""
    profile = profile.model_copy(deep=True)
    prefs = prefs.model_copy(deep=True)
    progress = progress.model_copy(deep=True)

    if question_id == "basics.contact":
        form = _form(value, ["name"])
        profile.contact = Contact(
            name=form["name"],
            email=form.get("email") or profile.contact.email,
            phone=profile.contact.phone,
            location=form.get("location") or profile.contact.location,
            links=dedupe([*profile.contact.links, *split_list(form.get("links", ""))]),
        )
    elif question_id == "role.add":
        form = _form(value, ["title"])
        start, end, current = _dates(form.get("dates"))
        profile.experience.append(
            Experience(
                title=form["title"],
                company=form.get("company") or None,
                location=form.get("location") or None,
                start=start,
                end=end,
                current=current,
                highlights=split_lines(form.get("highlights", "")),
            )
        )
        progress.adding_role = False
    elif question_id == "role.more":
        answer = _text(value)
        progress.adding_role = answer == "yes"
        progress.roles_done = answer != "yes"
    elif question_id == "profile.skills":
        skills = _items(value)
        if not skills:
            raise AnswerError("Add at least one skill, or skip.")
        profile.skills = dedupe([*profile.skills, *skills])
    elif question_id == "profile.education":
        form = _form(value, ["institution"])
        start, end, _ = _dates(form.get("dates"))
        profile.education.append(
            Education(
                institution=form["institution"],
                degree=form.get("degree") or None,
                field=form.get("field") or None,
                start=start,
                end=end,
            )
        )
    elif question_id == "prefs.titles":
        titles = _items(value)
        if not titles:
            raise AnswerError("Pick or type at least one title.")
        prefs.target_titles = titles
    elif question_id == "prefs.seniority":
        prefs.seniority = _text(value)
    elif question_id == "prefs.remote":
        try:
            prefs.remote = RemotePreference(_text(value))
        except ValueError as exc:
            raise AnswerError("Choose one of the options.") from exc
    elif question_id == "prefs.country":
        code = _text(value).upper()
        if not re.fullmatch(r"[A-Z]{2}", code):
            raise AnswerError("Use a two-letter country code, like US, GB, or DE.")
        prefs.country = code
    elif question_id == "prefs.locations":
        # "Denver, CO" is one place: split on semicolons and newlines only.
        places = value if isinstance(value, list) else split_places(_text(value))
        prefs.locations = dedupe([p.strip() for p in places if p.strip()])
    elif question_id == "prefs.salary":
        floor = parse_salary(_text(value), countries.defaults_for(prefs.country).currency)
        if floor is None:
            raise AnswerError('Couldn\'t read that amount. Try "120k" or "90,000 GBP".')
        prefs.salary_floor = floor
    elif question_id == "prefs.work_auth":
        prefs.work_authorization = _text(value)
    elif question_id == "prefs.deal_breakers":
        prefs.deal_breakers = _items(value)
    elif question_id.startswith("role.dates."):
        role = next((e for e in profile.experience if _role_dates_id(e) == question_id), None)
        if role is None:
            raise AnswerError("That role isn't in your profile anymore.")
        role.start, role.end, role.current = _dates(_text(value))
    elif question_id.startswith("metric."):
        new_text = _text(value)
        for exp in profile.experience:
            exp.highlights = [
                new_text if _metric_id(h) == question_id else h for h in exp.highlights
            ]
        if not re.search(r"\d", new_text):  # answered without a number: don't ask again
            progress.skipped.append(question_id)
    else:
        raise AnswerError("Unknown question.")

    if question_id not in progress.answered:
        progress.answered.append(question_id)
    return profile, prefs, progress


def skip(question_id: str, progress: InterviewProgress, required: bool) -> InterviewProgress:
    if required:
        raise AnswerError("This one is needed to find jobs for you.")
    progress = progress.model_copy(deep=True)
    if question_id == "role.add" and progress.adding_role:
        progress.adding_role = False
        progress.roles_done = True
    elif question_id not in progress.skipped:
        progress.skipped.append(question_id)
    return progress
