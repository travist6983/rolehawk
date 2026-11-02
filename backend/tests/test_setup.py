from pathlib import Path

import pytest
from sqlalchemy import select

from rolehawk.db.models import ProfileItem, ProfileItemKind, SearchTarget
from rolehawk.llm.fake import FakeProvider
from rolehawk.memory.files import MemoryTarget
from rolehawk.paths import DataPaths
from rolehawk.profile.documents import DocumentError
from rolehawk.profile.extraction import (
    ExtractedSetup,
    ExtractionOut,
    WirePreferences,
    WireProfile,
)
from rolehawk.profile.interview import AnswerError, AnswerValue
from rolehawk.profile.model import Experience, Profile
from rolehawk.services.runtime import Runtime, open_runtime

FIXTURES = Path(__file__).parent / "fixtures" / "resumes"

pytestmark = pytest.mark.anyio


def fake_of(runtime: Runtime) -> FakeProvider:
    provider = runtime.providers.get()
    assert isinstance(provider, FakeProvider)
    return provider


# Answers a person with no resume might give, keyed by question id.
INTERVIEW_ANSWERS: dict[str, AnswerValue] = {
    "basics.contact": {
        "name": "Sam Rivera",
        "email": "sam@example.com",
        "location": "Denver, CO",
        "links": "",
    },
    "role.add": {
        "title": "Data Analyst",
        "company": "Initech",
        "dates": "Jan 2022 - present",
        "location": "Denver, CO",
        "highlights": (
            "Built the weekly revenue dashboard, used by 40 managers\nAutomated reporting"
        ),
    },
    "role.more": "no",
    "profile.skills": "SQL, Python, Tableau, dbt",
    "prefs.titles": ["Data Analyst", "Analytics Engineer"],
    "prefs.seniority": "Mid level",
    "prefs.remote": "hybrid",
    "prefs.country": "US",
    "prefs.locations": "Denver, CO; Boulder, CO",
    "prefs.salary": "95k",
    "prefs.work_auth": "Citizen or permanent resident",
}


def run_interview(runtime: Runtime, answers: dict[str, AnswerValue]) -> list[str]:
    asked: list[str] = []
    state = runtime.setup.interview_state()
    for _ in range(40):
        question = state.question
        if question is None:
            break
        asked.append(question.id)
        if question.id in answers:
            state = runtime.setup.answer(question.id, answers[question.id])
        else:
            state = runtime.setup.skip(question.id)
    assert state.complete
    return asked


async def test_setup_by_interview_alone_without_ai(runtime: Runtime) -> None:
    asked = run_interview(runtime, INTERVIEW_ANSWERS)

    assert asked[:3] == ["basics.contact", "role.add", "role.more"]
    assert "profile.education" in asked  # offered, skipped
    profile = runtime.profiles.load_profile()
    assert profile.contact.name == "Sam Rivera"
    role = profile.experience[0]
    assert (role.title, role.company, role.start, role.current) == (
        "Data Analyst",
        "Initech",
        "2022-01",
        True,
    )
    assert role.highlights[0] == "Built the weekly revenue dashboard, used by 40 managers"
    assert profile.skills == ["SQL", "Python", "Tableau", "dbt"]

    prefs = runtime.profiles.load_preferences()
    assert prefs.salary_floor is not None
    assert (prefs.salary_floor.amount, prefs.salary_floor.currency) == (95000, "USD")
    text = runtime.memory.files.read(MemoryTarget.PREFERENCES)
    assert "- Hybrid" in text
    assert "- 95000 USD per year" in text

    with runtime.sessions() as session:
        targets = list(session.scalars(select(SearchTarget).order_by(SearchTarget.id)))
        skills = session.scalars(
            select(ProfileItem).where(ProfileItem.kind == ProfileItemKind.SKILL)
        ).all()
    assert prefs.locations == ["Denver, CO", "Boulder, CO"]
    assert [(t.title, t.remote_policy.value, t.salary_min) for t in targets] == [
        ("Data Analyst", "hybrid", 95000),
        ("Analytics Engineer", "hybrid", 95000),
    ]
    assert len(skills) == 4
    assert fake_of(runtime).requests == []
    assert fake_of(runtime).structured_requests == []


async def test_interview_is_resumable(paths: DataPaths, fake: FakeProvider) -> None:
    first = open_runtime(paths, provider=fake)
    first.setup.answer("basics.contact", INTERVIEW_ANSWERS["basics.contact"])
    first.setup.skip("role.add")
    await first.aclose()

    second = open_runtime(paths, provider=fake)
    try:
        state = second.setup.interview_state()
        assert state.answered == 1
        assert state.question is not None
        assert state.question.id == "profile.skills"
    finally:
        await second.aclose()


async def test_required_questions_cannot_be_skipped(runtime: Runtime) -> None:
    with pytest.raises(AnswerError, match="needed"):
        runtime.setup.skip("basics.contact")


@pytest.mark.parametrize(
    ("question_id", "value", "message"),
    [
        ("basics.contact", {"name": ""}, "Name is required"),
        ("role.add", {"title": "Dev", "dates": "a while back"}, "Couldn't read those dates"),
        ("prefs.salary", "lots", "Couldn't read that amount"),
        ("prefs.country", "Narnia", "two-letter country code"),
        ("prefs.titles", [], "at least one title"),
    ],
)
async def test_bad_answers_explain_themselves(
    runtime: Runtime, question_id: str, value: AnswerValue, message: str
) -> None:
    with pytest.raises(AnswerError, match=message):
        runtime.setup.answer(question_id, value)


async def test_refinement_questions_for_dates_and_metrics(runtime: Runtime) -> None:
    runtime.profiles.save_profile(
        Profile(
            experience=[
                Experience(
                    title="Engineer",
                    company="Globex",
                    highlights=["Improved the deployment pipeline for the whole company"],
                )
            ],
            skills=["Go", "Rust", "SQL"],
        )
    )
    asked = run_interview(runtime, INTERVIEW_ANSWERS)  # refinements get skipped here
    date_q = next(q for q in asked if q.startswith("role.dates."))
    metric_q = next(q for q in asked if q.startswith("metric."))
    # Both were skipped by run_interview; answer them explicitly after a restart.
    runtime.setup.restart_interview()
    runtime.setup.answer(date_q, "2019 - 2023")
    runtime.setup.answer(metric_q, "Cut deploy time from 40 to 8 minutes for 30 teams")
    exp = runtime.profiles.load_profile().experience[0]
    assert (exp.start, exp.end) == ("2019", "2023")
    assert exp.highlights == ["Cut deploy time from 40 to 8 minutes for 30 teams"]


def answer_through(runtime: Runtime, last: str) -> None:
    """Answer INTERVIEW_ANSWERS in order up to and including `last` (skipping the rest)."""
    state = runtime.setup.interview_state()
    while state.question is not None:
        qid = state.question.id
        if qid in INTERVIEW_ANSWERS:
            state = runtime.setup.answer(qid, INTERVIEW_ANSWERS[qid])
        else:
            state = runtime.setup.skip(qid)
        if qid == last:
            return
    raise AssertionError(f"{last} was never asked")


async def test_back_asks_the_previous_question_again_with_the_saved_answer(
    runtime: Runtime,
) -> None:
    assert not runtime.setup.interview_state().can_go_back
    with pytest.raises(AnswerError, match="no earlier question"):
        runtime.setup.back()

    answer_through(runtime, "prefs.titles")
    mis_click = runtime.setup.answer("prefs.seniority", "Director+")
    assert mis_click.question is not None
    assert mis_click.question.id == "prefs.remote"
    assert mis_click.can_go_back

    state = runtime.setup.back()
    assert state.question is not None
    assert state.question.id == "prefs.seniority"
    assert state.question.value == "Director+"
    assert (state.question.optional, state.question.skip_label) == (True, "Keep my answer")
    assert state.answered == mis_click.answered - 1

    state = runtime.setup.answer("prefs.seniority", "Mid level")
    assert runtime.profiles.load_preferences().seniority == "Mid level"
    assert state.question is not None
    assert state.question.id == "prefs.remote"  # carries on where it was
    assert state.answered == mis_click.answered


async def test_back_to_a_role_edits_it_instead_of_adding_another(runtime: Runtime) -> None:
    answer_through(runtime, "role.add")
    state = runtime.setup.back()
    assert state.question is not None
    assert state.question.id.startswith("role.edit.")
    form = state.question.value
    assert isinstance(form, dict)
    assert (form["title"], form["company"], form["dates"]) == (
        "Data Analyst",
        "Initech",
        "2022-01 to present",
    )

    runtime.setup.answer(state.question.id, {**form, "title": "Senior Data Analyst"})
    [role] = runtime.profiles.load_profile().experience
    assert (role.title, role.company, role.start, role.current) == (
        "Senior Data Analyst",
        "Initech",
        "2022-01",
        True,
    )
    assert role.highlights[0] == "Built the weekly revenue dashboard, used by 40 managers"
    # Back again reaches the role under its new title.
    again = runtime.setup.back()
    assert again.question is not None
    assert isinstance(again.question.value, dict)
    assert again.question.value["title"] == "Senior Data Analyst"


async def test_back_twice_then_keep_returns_to_where_you_were(runtime: Runtime) -> None:
    answer_through(runtime, "profile.skills")
    before = runtime.setup.interview_state()
    assert before.question is not None
    assert before.question.id == "profile.languages"

    skills = runtime.setup.back()
    assert skills.question is not None
    assert skills.question.id == "profile.skills"
    assert skills.question.value == ["SQL", "Python", "Tableau", "dbt"]
    role_more = runtime.setup.back()
    assert role_more.question is not None
    assert role_more.question.id == "role.more"

    kept = runtime.setup.skip("role.more")  # "Keep my answer"
    assert kept.question is not None
    assert kept.question.id == "profile.languages"
    assert kept.answered == before.answered
    assert runtime.profiles.load_profile().skills == ["SQL", "Python", "Tableau", "dbt"]
    back_again = runtime.setup.back()  # the skills step is still in history
    assert back_again.question is not None
    assert back_again.question.id == "profile.skills"


async def test_back_replaces_a_list_answer(runtime: Runtime) -> None:
    answer_through(runtime, "profile.skills")
    runtime.setup.back()
    runtime.setup.answer("profile.skills", ["SQL", "Python"])  # removed two
    assert runtime.profiles.load_profile().skills == ["SQL", "Python"]


async def test_back_reopens_a_skipped_question(runtime: Runtime) -> None:
    answer_through(runtime, "profile.skills")
    skipped = runtime.setup.skip("profile.languages")
    state = runtime.setup.back()
    assert state.question is not None
    assert state.question.id == "profile.languages"
    assert state.question.skip_label == "Skip"  # still unanswered: a normal skip
    state = runtime.setup.answer("profile.languages", "English (native)")
    assert runtime.profiles.load_profile().languages == ["English (native)"]
    assert state.answered == skipped.answered + 1


async def test_back_after_done_adding_roles_adds_another(runtime: Runtime) -> None:
    answer_through(runtime, "basics.contact")
    runtime.setup.answer("role.add", INTERVIEW_ANSWERS["role.add"])
    runtime.setup.answer("role.more", "yes")
    state = runtime.setup.skip("role.add")  # "Done adding roles"
    assert state.question is not None
    assert state.question.id == "profile.skills"
    state = runtime.setup.back()
    assert state.question is not None
    assert (state.question.id, state.question.prompt) == ("role.add", "Add another role.")


# --- documents, drafts, and re-runs --------------------------------------------------------


async def test_documents_are_stored_once(runtime: Runtime) -> None:
    data = (FIXTURES / "ada_example.pdf").read_bytes()
    first = runtime.setup.add_document("My CV.pdf", data)
    again = runtime.setup.add_document("copy.pdf", data)
    assert again.id == first.id
    assert first.kind == "pdf"
    assert first.chars > 200
    stored = list(runtime.paths.source_documents.iterdir())
    assert [p.name for p in stored] == [f"{first.id}-My_CV.pdf"]
    with pytest.raises(DocumentError):
        runtime.setup.add_text("   ")


def extracted() -> ExtractedSetup:
    return ExtractedSetup.model_validate(
        {
            "profile": {
                "contact": {"name": "Ada Example", "email": "ada@example.com"},
                "experience": [
                    {
                        "title": "Senior Frontend Engineer",
                        "company": "Northwind Payments",
                        "start": "2021-03",
                        "current": True,
                        "highlights": ["Led the checkout redesign, lifting conversion 12%"],
                    }
                ],
                "skills": ["TypeScript", "React"],
            },
            "preferences": {},
        }
    )


def extracted_reply() -> tuple[WireProfile, WirePreferences]:
    """What Claude sends back to the two extraction requests: the wire form of `extracted()`."""
    return ExtractionOut.from_setup(extracted()).parts()


async def test_extract_then_apply_and_rerun_without_duplicates(runtime: Runtime) -> None:
    fake = fake_of(runtime)
    doc = runtime.setup.add_document("cv.txt", (FIXTURES / "ada_example.txt").read_bytes())

    fake.queue_structured(*extracted_reply())
    draft = await runtime.setup.extract([doc.id], task_id=None)
    request, _schema = fake.structured_requests[-1]
    assert (
        '<untrusted_content source="candidate_document" name="cv.txt">' in request.messages[0].text
    )
    assert "Never infer" in request.system[0].text
    assert runtime.profiles.load_profile() == Profile()  # nothing saved before review
    assert runtime.setup.get_draft() == draft

    result = runtime.setup.apply_draft()
    assert result.added == {"experience": 1, "skills": 2}
    assert runtime.setup.get_draft() is None
    profile_md = runtime.memory.files.read(MemoryTarget.PROFILE)
    assert "### Senior Frontend Engineer | Northwind Payments" in profile_md

    # Re-running setup with the same CV edits instead of duplicating.
    fake.queue_structured(*extracted_reply())
    await runtime.setup.extract([doc.id], task_id=None)
    again = runtime.setup.apply_draft()
    assert again.added == {}
    assert again.updated == {}
    assert len(runtime.profiles.load_profile().experience) == 1
    with runtime.sessions() as session:
        assert len(session.scalars(select(ProfileItem)).all()) == 3  # 1 role + 2 skills


async def test_linkedin_import_needs_no_ai(runtime: Runtime) -> None:
    doc = runtime.setup.add_document("export.zip", (FIXTURES / "linkedin_export.zip").read_bytes())
    draft = await runtime.setup.extract([doc.id])
    assert [e.company for e in draft.profile.experience] == [
        "Northwind Payments",
        "Contoso Health",
    ]
    assert fake_of(runtime).structured_requests == []


async def test_user_edited_draft_wins(runtime: Runtime) -> None:
    runtime.setup.store_draft(extracted())
    edited = extracted()
    edited.profile.skills = ["TypeScript"]  # the user removed one in review
    runtime.setup.apply_draft(edited)
    assert runtime.profiles.load_profile().skills == ["TypeScript"]


async def test_hand_edits_and_accepted_proposals_refresh_derived_tables(runtime: Runtime) -> None:
    from rolehawk.db.models import ProposalOp
    from rolehawk.memory.proposals import ProposalIn

    runtime.profiles.save_raw(
        MemoryTarget.PREFERENCES, "# Preferences\n\n## Target titles\n\n- Designer\n- Writer\n"
    )
    runtime.profiles.save_raw(MemoryTarget.PREFERENCES, "## Target titles\n- Writer\n")
    with runtime.sessions() as session:
        targets = {t.title: t.active for t in session.scalars(select(SearchTarget))}
    assert targets == {"Designer": False, "Writer": True}  # deactivated, not deleted

    proposal = runtime.memory.propose(
        ProposalIn(
            target=MemoryTarget.PROFILE,
            op=ProposalOp.ADD,
            section="Skills",
            text="Figma",
            old_text=None,
            reason="User said so",
        ),
        "chat",
    )
    runtime.memory.accept(proposal.id)
    with runtime.sessions() as session:
        names = [i.data["name"] for i in session.scalars(select(ProfileItem))]
    assert names == ["Figma"]


@pytest.mark.parametrize(
    "links",
    [
        ["https://www.linkedin.com/in/sam-example", " ", "https://github.com/sam-example"],
        # Older clients and the CLI send one comma-separated string; it still works.
        "https://www.linkedin.com/in/sam-example, https://github.com/sam-example",
        # So does an item holding a pasted comma-separated pair.
        ["https://www.linkedin.com/in/sam-example, https://github.com/sam-example"],
    ],
)
async def test_contact_links_are_a_list(runtime: Runtime, links: str | list[str]) -> None:
    state = runtime.setup.interview_state()
    assert state.question is not None
    [field] = [f for f in state.question.fields if f.name == "links"]
    assert field.kind == "list"
    runtime.setup.answer("basics.contact", {"name": "Sam Rivera", "links": links})
    assert runtime.profiles.load_profile().contact.links == [
        "https://www.linkedin.com/in/sam-example",
        "https://github.com/sam-example",
    ]
