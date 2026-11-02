"""The /setup gap interview: one question at a time, multiple choice where possible.

Questions are computed from what the profile and preferences are missing, so the interview
is resumable (state is the files themselves plus a small list of skipped questions) and works
with no resume and no API key. Answers are the user's own words and are written directly.

Back asks the previous question again, filled in with what is saved. Answering replaces that
answer; "Keep my answer" leaves it. Lists (skills, titles, deal-breakers) and a form's list
field are replaced by the answer, so it carries the items to keep."""

from __future__ import annotations

import hashlib
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from rolehawk import countries
from rolehawk.profile.model import (
    Contact,
    Education,
    Experience,
    Preferences,
    Profile,
    RemotePreference,
)
from rolehawk.profile.parsing import (
    dedupe,
    format_date_range,
    format_salary,
    parse_date_range,
    parse_salary,
    split_lines,
    split_list,
    split_places,
)

QuestionKind = Literal["single", "multi", "text", "list", "form"]
# A form answer maps field names to text, or to a list for `kind="list"` fields (links).
AnswerValue = str | list[str] | dict[str, str | list[str]]

MAX_METRIC_QUESTIONS = 3


class _Out(BaseModel):
    model_config = ConfigDict(json_schema_serialization_defaults_required=True)


class Choice(_Out):
    value: str
    label: str


class FormField(_Out):
    name: str
    label: str
    # "list": one input per item with add and remove buttons; the answer is a list.
    kind: Literal["text", "textarea", "list"] = "text"
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


class Step(BaseModel):
    """A question the user moved past. `again` is the id that asks it again with the saved
    answer filled in: an added role comes back as `role.edit.<key>`, an achievement under
    its new text."""

    question: str
    again: str
    skipped: bool = False


class InterviewProgress(BaseModel):
    skipped: list[str] = Field(default_factory=list)
    answered: list[str] = Field(default_factory=list)
    adding_role: bool = False
    roles_done: bool = False
    history: list[Step] = Field(default_factory=list)  # oldest first; Back pops the last
    revisit: Step | None = None  # the step Back went to: asked first until answered or kept
    ahead: list[Step] = Field(default_factory=list)  # steps Back went past, back in history after


class InterviewState(_Out):
    question: Question | None
    answered: int
    remaining: int
    complete: bool
    can_go_back: bool


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


KEEP_ANSWER = "Keep my answer"


def _role_edit_id(exp: Experience) -> str:
    return f"role.edit.{_short_hash(exp.title, exp.company)}"


def _education_edit_id(edu: Education) -> str:
    return f"education.edit.{_short_hash(edu.institution, edu.degree)}"


def _joined(items: list[str]) -> str | None:
    return "; ".join(items) or None


def _form_value(fields: dict[str, str | list[str] | None]) -> dict[str, str | list[str]] | None:
    value = {name: v for name, v in fields.items() if v}
    return value or None


def _role_value(exp: Experience) -> dict[str, str | list[str]] | None:
    return _form_value(
        {
            "title": exp.title,
            "company": exp.company,
            "dates": format_date_range(exp.start, exp.end, exp.current),
            "location": exp.location,
            "highlights": "\n".join(exp.highlights),
        }
    )


def _education_question(qid: str, edu: Education | None) -> Question:
    return Question(
        id=qid,
        prompt="What's your highest education?",
        kind="form",
        skip_label="Skip (not relevant)",
        fields=[
            FormField(name="institution", label="School or university", required=True),
            FormField(name="degree", label="Degree", placeholder="BSc"),
            FormField(name="field", label="Field of study", placeholder="Computer Science"),
            FormField(name="dates", label="Dates", placeholder="2015 - 2019"),
        ],
        value=None
        if edu is None
        else _form_value(
            {
                "institution": edu.institution,
                "degree": edu.degree,
                "field": edu.field,
                "dates": format_date_range(edu.start, edu.end, False),
            }
        ),
    )


def _question(qid: str, profile: Profile, prefs: Preferences) -> Question | None:
    """Build one question, filled in with what is saved now (so Back can ask it again).
    None when it no longer applies (the role or achievement it was about is gone)."""
    if qid == "basics.contact":
        c = profile.contact
        return Question(
            id=qid,
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
                    kind="list",
                    placeholder="https://www.linkedin.com/in/you",
                ),
            ],
            value=_form_value(
                {"name": c.name, "email": c.email, "location": c.location, "links": c.links}
            ),
        )
    if qid == "role.add":
        return Question(
            id=qid,
            prompt="Tell me about your most recent role."
            if not profile.experience
            else "Add another role.",
            help="Only what's true: RoleHawk never invents details for your CV.",
            kind="form",
            fields=ROLE_FIELDS,
            skip_label="I don't have work experience yet"
            if not profile.experience
            else "Done adding roles",
        )
    if qid.startswith("role.edit."):
        role = next((e for e in profile.experience if _role_edit_id(e) == qid), None)
        if role is None:
            return None
        return Question(
            id=qid,
            prompt="Edit this role.",
            help="Only what's true: RoleHawk never invents details for your CV.",
            kind="form",
            fields=ROLE_FIELDS,
            value=_role_value(role),
        )
    if qid == "role.more":
        if not profile.experience:
            return None
        return Question(
            id=qid,
            prompt="Is there another role you'd like on your profile?",
            kind="single",
            choices=[
                Choice(value="yes", label="Yes, add a role"),
                Choice(value="no", label="No, that's all"),
            ],
            optional=False,
        )
    if qid == "profile.skills":
        return Question(
            id=qid,
            prompt="What are your strongest skills?",
            help="Tools, languages, and methods you'd be happy to be interviewed on.",
            kind="list",
            placeholder="TypeScript, React, PostgreSQL",
            value=list(profile.skills) or None,
        )
    if qid == "profile.languages":
        return Question(
            id=qid,
            prompt="Which languages do you work in, and how well?",
            help="With your level, so jobs that need another language can be flagged.",
            kind="text",
            placeholder="English (native); Spanish (B2)",
            value=_joined(profile.languages),
        )
    if qid == "profile.education":
        return _education_question(qid, None)
    if qid.startswith("education.edit."):
        edu = next((e for e in profile.education if _education_edit_id(e) == qid), None)
        return None if edu is None else _education_question(qid, edu)
    if qid == "prefs.titles":
        recent_titles = [e.title for e in profile.experience[:3]]
        return Question(
            id=qid,
            prompt="Which job titles should I search for?",
            kind="multi",
            choices=[Choice(value=t, label=t) for t in dedupe(recent_titles + prefs.target_titles)],
            allow_other=True,
            optional=False,
            placeholder="Add other titles, comma separated",
            value=list(prefs.target_titles) or None,
        )
    if qid == "prefs.seniority":
        return Question(
            id=qid,
            prompt="What level are you aiming for?",
            kind="single",
            choices=[Choice(value=s, label=s) for s in SENIORITY],
            value=prefs.seniority,
        )
    if qid == "prefs.remote":
        return Question(
            id=qid,
            prompt="How do you want to work?",
            kind="single",
            choices=[
                Choice(value=RemotePreference.REMOTE.value, label="Remote only"),
                Choice(value=RemotePreference.HYBRID.value, label="Hybrid"),
                Choice(value=RemotePreference.ONSITE.value, label="On-site"),
                Choice(value=RemotePreference.ANY.value, label="Open to any"),
            ],
            optional=False,
            value=prefs.remote.value if prefs.remote else None,
        )
    if qid == "prefs.country":
        return Question(
            id=qid,
            prompt="Which country are you job hunting in?",
            help="Picks the right job sources, currency, and salary format.",
            kind="single",
            choices=[Choice(value=c, label=n) for c, n in countries.known_countries()],
            allow_other=True,
            placeholder="Other country code, e.g. FR",
            optional=False,
            value=prefs.country,
        )
    if qid == "prefs.locations":
        return Question(
            id=qid,
            prompt="Which cities or regions work for you?",
            help="Separate places with semicolons; commas stay part of a place name.",
            kind="text",
            placeholder="Denver, CO; Boulder, CO",
            value=_joined(prefs.locations) or profile.contact.location,
        )
    if qid == "prefs.salary":
        currency = countries.defaults_for(prefs.country).currency
        return Question(
            id=qid,
            prompt="What's the lowest salary you'd accept?",
            help=f"Used to filter out jobs below it. Amounts default to {currency} per year.",
            kind="text",
            placeholder=f"e.g. 120k {currency}",
            value=format_salary(prefs.salary_floor) if prefs.salary_floor else None,
        )
    if qid == "prefs.work_auth":
        return Question(
            id=qid,
            prompt="What's your work authorization in that country?",
            kind="single",
            choices=[Choice(value=w, label=w) for w in WORK_AUTH],
            allow_other=True,
            value=prefs.work_authorization,
        )
    if qid == "prefs.deal_breakers":
        return Question(
            id=qid,
            prompt="Any deal-breakers?",
            kind="multi",
            choices=[Choice(value=d, label=d) for d in dedupe(DEAL_BREAKERS + prefs.deal_breakers)],
            allow_other=True,
            skip_label="None",
            value=list(prefs.deal_breakers) or None,
        )
    if qid == "prefs.energizing":
        return Question(
            id=qid,
            prompt="What kind of work gives you energy?",
            help="Used to score how well a job fits what you want to do, not just can do.",
            kind="text",
            placeholder="Building tools from scratch; mentoring; talking to customers",
            value=_joined(prefs.energizing),
        )
    if qid == "prefs.draining":
        return Question(
            id=qid,
            prompt="And what kind of work drains you?",
            kind="text",
            placeholder="Maintaining legacy systems; heavy travel",
            value=_joined(prefs.draining),
        )
    if qid.startswith("role.dates."):
        exp = next((e for e in profile.experience if _role_dates_id(e) == qid), None)
        if exp is None:
            return None
        return Question(
            id=qid,
            prompt=f"When did you work as {exp.title}"
            + (f" at {exp.company}?" if exp.company else "?"),
            kind="text",
            placeholder="Mar 2021 - present",
            value=format_date_range(exp.start, exp.end, exp.current),
        )
    if qid.startswith("metric."):
        highlight = next(
            (h for e in profile.experience for h in e.highlights if _metric_id(h) == qid), None
        )
        if highlight is None:
            return None
        return Question(
            id=qid,
            prompt="Can you add a number to this achievement?",
            help="Recruiters skim for results. Only add a number you can stand behind.",
            kind="text",
            value=highlight,
            skip_label="Keep as is",
        )
    return None


def open_questions(
    profile: Profile, prefs: Preferences, progress: InterviewProgress
) -> list[Question]:
    """Every question still worth asking, in order. The interview asks the first one; after
    Back, the question being revisited comes first, filled in with the current answer."""
    skipped = set(progress.skipped)
    ids: list[str] = []
    if not profile.contact.name:
        ids.append("basics.contact")
    if (not profile.experience and "role.add" not in skipped) or progress.adding_role:
        ids.append("role.add")
    elif profile.experience and not progress.roles_done:
        ids.append("role.more")
    if len(profile.skills) < 3:
        ids.append("profile.skills")
    if not profile.languages:
        ids.append("profile.languages")
    if not profile.education:
        ids.append("profile.education")
    if not prefs.target_titles:
        ids.append("prefs.titles")
    if not prefs.seniority:
        ids.append("prefs.seniority")
    if not prefs.remote:
        ids.append("prefs.remote")
    if not prefs.country:
        ids.append("prefs.country")
    if not prefs.locations and prefs.remote is not RemotePreference.REMOTE:
        ids.append("prefs.locations")
    if not prefs.salary_floor:
        ids.append("prefs.salary")
    if not prefs.work_authorization:
        ids.append("prefs.work_auth")
    if not prefs.deal_breakers:
        ids.append("prefs.deal_breakers")
    if not prefs.energizing:
        ids.append("prefs.energizing")
    if not prefs.draining:
        ids.append("prefs.draining")

    # Refinements: missing dates, then achievements that could use a number.
    ids += [_role_dates_id(exp) for exp in profile.experience if not exp.start]
    metric_ids: list[str] = []
    for exp in profile.experience[:2]:
        for highlight in exp.highlights:
            question_id = _metric_id(highlight)
            if re.search(r"\d", highlight) or len(highlight) < 25 or question_id in skipped:
                continue
            if len(metric_ids) < MAX_METRIC_QUESTIONS:
                metric_ids.append(question_id)
    ids += metric_ids

    out = [
        q for qid in ids if qid not in skipped and (q := _question(qid, profile, prefs)) is not None
    ]
    step = progress.revisit
    if step is not None:
        natural = next((q for q in out if q.id == step.again), None)
        if natural is not None:
            out.remove(natural)
            out.insert(0, natural)
        elif (again := _question(step.again, profile, prefs)) is not None:
            out.insert(0, again.model_copy(update={"optional": True, "skip_label": KEEP_ANSWER}))
    return out


def state(profile: Profile, prefs: Preferences, progress: InterviewProgress) -> InterviewState:
    remaining = open_questions(profile, prefs, progress)
    return InterviewState(
        question=remaining[0] if remaining else None,
        answered=len(progress.answered),
        remaining=len(remaining),
        complete=not remaining,
        can_go_back=bool(progress.history),
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
    """The form's text fields (list fields are read with `_form_list`)."""
    if not isinstance(value, dict):
        raise AnswerError("Expected a form.")
    form = {k: v.strip() for k, v in value.items() if isinstance(v, str)}
    for name in required:
        if not form.get(name):
            raise AnswerError(f"{name.replace('_', ' ').capitalize()} is required.")
    return form


def _form_list(value: AnswerValue, name: str) -> list[str]:
    """A list field. Older clients (and the CLI) send one comma-separated string, and an item
    can hold several pasted at once; both are split the same way, blanks dropped."""
    raw = value.get(name) if isinstance(value, dict) else None
    if isinstance(raw, str):
        return split_list(raw)
    if isinstance(raw, list):
        return dedupe([part for item in raw if isinstance(item, str) for part in split_list(item)])
    return []


def _dates(text: str | None) -> tuple[str | None, str | None, bool]:
    if not text:
        return None, None, False
    parsed = parse_date_range(text)
    if parsed is None:
        raise AnswerError('Couldn\'t read those dates. Try "Mar 2021 - present" or "2019 - 2021".')
    return parsed.start, parsed.end, parsed.current


def _form_text(value: AnswerValue, name: str, current: str | None) -> str | None:
    """A form's optional text field: a field left out keeps what's saved (older clients)."""
    if isinstance(value, dict) and name in value:
        raw = value[name]
        return raw.strip() or None if isinstance(raw, str) else current
    return current


def _role_from_form(form: dict[str, str], role: Experience | None = None) -> Experience:
    start, end, current = _dates(form.get("dates"))
    fields = {
        "title": form["title"],
        "company": form.get("company") or None,
        "location": form.get("location") or None,
        "start": start,
        "end": end,
        "current": current,
        "highlights": split_lines(form.get("highlights", "")),
    }
    return role.model_copy(update=fields) if role else Experience.model_validate(fields)


def _education_from_form(form: dict[str, str], edu: Education | None = None) -> Education:
    start, end, _ = _dates(form.get("dates"))
    fields = {
        "institution": form["institution"],
        "degree": form.get("degree") or None,
        "field": form.get("field") or None,
        "start": start,
        "end": end,
    }
    return edu.model_copy(update=fields) if edu else Education.model_validate(fields)


def _replace[T](items: list[T], old: T, new: T) -> list[T]:
    return [new if item is old else item for item in items]


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
    again = question_id  # the id that asks this question again (see Step)

    if question_id == "basics.contact":
        form = _form(value, ["name"])
        c = profile.contact
        has_links = isinstance(value, dict) and "links" in value
        profile.contact = Contact(
            name=form["name"],
            email=_form_text(value, "email", c.email),
            phone=c.phone,
            location=_form_text(value, "location", c.location),
            links=_form_list(value, "links") if has_links else c.links,
        )
    elif question_id == "role.add":
        role = _role_from_form(_form(value, ["title"]))
        profile.experience.append(role)
        progress.adding_role = False
        again = _role_edit_id(role)
    elif question_id.startswith("role.edit."):
        old = next((e for e in profile.experience if _role_edit_id(e) == question_id), None)
        if old is None:
            raise AnswerError("That role isn't in your profile anymore.")
        role = _role_from_form(_form(value, ["title"]), old)
        profile.experience = _replace(profile.experience, old, role)
        again = _role_edit_id(role)
    elif question_id == "role.more":
        answer = _text(value)
        progress.adding_role = answer == "yes"
        progress.roles_done = answer != "yes"
    elif question_id == "profile.skills":
        skills = _items(value)
        if not skills:
            raise AnswerError("Add at least one skill, or skip.")
        profile.skills = skills
    elif question_id == "profile.education":
        edu = _education_from_form(_form(value, ["institution"]))
        profile.education.append(edu)
        again = _education_edit_id(edu)
    elif question_id.startswith("education.edit."):
        old_edu = next((e for e in profile.education if _education_edit_id(e) == question_id), None)
        if old_edu is None:
            raise AnswerError("That school isn't in your profile anymore.")
        edu = _education_from_form(_form(value, ["institution"]), old_edu)
        profile.education = _replace(profile.education, old_edu, edu)
        again = _education_edit_id(edu)
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
    elif question_id == "prefs.energizing":
        prefs.energizing = _items(value)
    elif question_id == "prefs.draining":
        prefs.draining = _items(value)
    elif question_id == "profile.languages":
        profile.languages = _items(value)
    elif question_id.startswith("role.dates."):
        dated = next((e for e in profile.experience if _role_dates_id(e) == question_id), None)
        if dated is None:
            raise AnswerError("That role isn't in your profile anymore.")
        dated.start, dated.end, dated.current = _dates(_text(value))
    elif question_id.startswith("metric."):
        new_text = _text(value)
        for exp in profile.experience:
            exp.highlights = [
                new_text if _metric_id(h) == question_id else h for h in exp.highlights
            ]
        again = _metric_id(new_text)
        if not re.search(r"\d", new_text):  # answered without a number: don't ask again
            progress.skipped.append(again)
    else:
        raise AnswerError("Unknown question.")

    revisit = _revisiting(progress, question_id)
    asked = revisit.question if revisit else question_id
    if asked not in progress.answered:
        progress.answered.append(asked)
    _moved_past(progress, Step(question=asked, again=again), resolves=revisit is not None)
    return profile, prefs, progress


def skip(question: Question, progress: InterviewProgress) -> InterviewProgress:
    """Skip an open question, or keep the saved answer to one that Back went to."""
    progress = progress.model_copy(deep=True)
    revisit = _revisiting(progress, question.id)
    if revisit is not None and not revisit.skipped:
        if revisit.question not in progress.answered:
            progress.answered.append(revisit.question)
        _moved_past(progress, revisit, resolves=True)
        return progress
    if not question.optional:
        raise AnswerError("This one is needed to find jobs for you.")
    if question.id == "role.add" and progress.adding_role:
        progress.adding_role = False
        progress.roles_done = True
    elif question.id not in progress.skipped:
        progress.skipped.append(question.id)
    step = Step(question=question.id, again=question.id, skipped=True)
    _moved_past(progress, step, resolves=revisit is not None)
    return progress


def back(progress: InterviewProgress) -> InterviewProgress:
    """Go to the previous question: it is asked again, filled in with the saved answer."""
    progress = progress.model_copy(deep=True)
    if not progress.history:
        raise AnswerError("There's no earlier question to go back to.")
    if progress.revisit is not None:  # going back further: leave this one as it was
        _redo(progress.revisit, progress)
        progress.ahead.insert(0, progress.revisit)
    step = progress.history.pop()
    _undo(step, progress)
    progress.revisit = step
    return progress


def _revisiting(progress: InterviewProgress, question_id: str) -> Step | None:
    step = progress.revisit
    return step if step is not None and step.again == question_id else None


def _moved_past(progress: InterviewProgress, step: Step, *, resolves: bool) -> None:
    progress.history.append(step)
    if resolves:  # done with the revisit: the steps after it come back into history
        progress.history.extend(progress.ahead)
        progress.ahead.clear()
        progress.revisit = None


def _undo(step: Step, progress: InterviewProgress) -> None:
    """Make a step's question open again (for Back)."""
    if step.skipped:
        if step.question in progress.skipped:
            progress.skipped.remove(step.question)
        elif step.question == "role.add":  # "Done adding roles" ended the role loop
            progress.adding_role, progress.roles_done = True, False
        return
    others = [s.question for s in (*progress.history, *progress.ahead)]
    if step.question in progress.answered and step.question not in others:
        progress.answered.remove(step.question)


def _redo(step: Step, progress: InterviewProgress) -> None:
    """Put a step Back went past the way it was before Back opened it."""
    if not step.skipped:
        if step.question not in progress.answered:
            progress.answered.append(step.question)
    elif step.question == "role.add" and progress.adding_role:
        progress.adding_role, progress.roles_done = False, True
    elif step.question not in progress.skipped:
        progress.skipped.append(step.question)
