"""Setup conflicts: versions of the same fact that disagree are listed with their sources,
and the version the user picks is what gets saved."""

from __future__ import annotations

import pytest

from offerbound.profile.conflicts import find_conflicts, resolve
from offerbound.profile.extraction import ExtractedSetup
from offerbound.profile.merge import merge_profile, title_key
from offerbound.profile.model import Contact, Education, Experience, Preferences, Profile
from offerbound.services.runtime import Runtime

SOURCES = ("your profile", "resume.pdf")


def role(title: str, start: str | None = "2021-03", **values: object) -> Experience:
    return Experience.model_validate(
        {"title": title, "company": "Northwind", "start": start, "current": True, **values}
    )


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("Sr. Data Analyst", "Senior Data Analyst"),
        ("Data Analyst II", "Data Analyst 2"),
        ("Research & Development Eng", "Research and Development Engineer"),
        ("VP, Product", "Vice President Product"),
    ],
)
def test_common_title_spellings_match(a: str, b: str) -> None:
    assert title_key(a) == title_key(b)
    merged, _ = merge_profile(Profile(experience=[role(a)]), Profile(experience=[role(b)]))
    assert [e.title for e in merged.experience] == [a]  # one role, existing wording kept


def test_different_titles_for_the_same_stint_are_a_conflict() -> None:
    current = Profile(experience=[role("Data Analyst II")])
    incoming = Profile(experience=[role("Senior Data Analyst", start="2021-04")])
    [conflict] = find_conflicts(current, incoming, SOURCES)
    assert conflict.kind == "title"
    assert [(o.label, o.source) for o in conflict.options] == [
        ("Data Analyst II", "your profile"),
        ("Senior Data Analyst", "resume.pdf"),
        ("They're different roles: keep both", ""),
    ]

    mine, theirs = resolve(current, incoming, [conflict], {conflict.id: 1})
    merged, _ = merge_profile(mine, theirs)
    assert [e.title for e in merged.experience] == ["Senior Data Analyst"]

    both, other = resolve(current, incoming, [conflict], {conflict.id: 2})
    assert len(merge_profile(both, other)[0].experience) == 2


def test_separate_stints_at_one_company_are_not_a_conflict() -> None:
    current = Profile(experience=[role("Analyst", start="2015-01", current=False, end="2016-06")])
    incoming = Profile(experience=[role("Senior Analyst", start="2020-01")])
    assert find_conflicts(current, incoming, SOURCES) == []


def test_dates_degrees_and_contact_details_that_disagree() -> None:
    current = Profile(
        contact=Contact(name="Ada Example", email="ada@example.com"),
        experience=[role("Data Analyst", start="2021-03")],
        education=[
            Education(institution="UT Austin", degree="BSc", field="Statistics", end="2019")
        ],
    )
    incoming = Profile(
        contact=Contact(name="Ada  example", email="ada.work@example.com"),
        experience=[role("Data Analyst", start="2021-01")],
        education=[Education(institution="UT Austin", degree="BA", field="Statistics", end="2019")],
    )
    conflicts = {c.kind: c for c in find_conflicts(current, incoming, SOURCES)}
    assert set(conflicts) == {"contact", "dates", "degree"}  # the name only differs in case
    assert conflicts["contact"].subject == "Your email"
    assert [o.label for o in conflicts["dates"].options] == [
        "2021-03 - present",
        "2021-01 - present",
    ]
    assert [o.label for o in conflicts["degree"].options] == [
        "BSc Statistics (2019)",
        "BA Statistics (2019)",
    ]

    picks = {conflicts["dates"].id: 1, conflicts["contact"].id: 1}
    mine, theirs = resolve(current, incoming, list(conflicts.values()), picks)
    merged, _ = merge_profile(mine, theirs)
    assert merged.experience[0].start == "2021-01"
    assert merged.contact.email == "ada.work@example.com"
    assert merged.education[0].degree == "BSc"  # not picked: the existing version stays


pytestmark = pytest.mark.anyio


async def test_setup_lists_conflicts_and_applies_the_picks(runtime: Runtime) -> None:
    runtime.profiles.save_profile(Profile(experience=[role("Data Analyst II")]))
    runtime.setup.store_draft(
        ExtractedSetup(
            profile=Profile(experience=[role("Senior Data Analyst", start="2021-04")]),
            preferences=Preferences(),
        )
    )
    draft = runtime.setup.get_draft()
    assert draft is not None
    [conflict] = draft.conflicts
    assert conflict.options[1].source == "the imported documents"

    result = runtime.setup.apply_draft(None, {conflict.id: 1})
    assert result.resolved == 1
    assert [e.title for e in runtime.profiles.load_profile().experience] == ["Senior Data Analyst"]


async def test_unpicked_conflicts_keep_the_existing_version(runtime: Runtime) -> None:
    runtime.profiles.save_profile(Profile(experience=[role("Data Analyst II")]))
    runtime.setup.store_draft(
        ExtractedSetup(profile=Profile(experience=[role("Senior Data Analyst")]))
    )
    result = runtime.setup.apply_draft()
    assert result.resolved == 0
    assert [e.title for e in runtime.profiles.load_profile().experience] == ["Data Analyst II"]


async def test_a_cv_and_a_linkedin_export_that_disagree(runtime: Runtime) -> None:
    from tests.test_setup import FIXTURES, fake_of

    export = runtime.setup.add_document(
        "export.zip", (FIXTURES / "linkedin_export.zip").read_bytes()
    )
    cv = runtime.setup.add_document("cv.txt", (FIXTURES / "ada_example.txt").read_bytes())
    fake_of(runtime).queue_structured(
        {
            "profile": {
                "experience": [
                    {
                        "title": "Lead Frontend Engineer",
                        "company": "Northwind Payments",
                        "start": "2021-03",
                        "current": True,
                    }
                ]
            },
            "preferences": {},
        }
    )
    draft = await runtime.setup.extract([export.id, cv.id])
    [conflict] = [c for c in draft.conflicts if c.kind == "title"]
    assert [(o.label, o.source) for o in conflict.options[:2]] == [
        ("Senior Frontend Engineer", "LinkedIn export"),
        ("Lead Frontend Engineer", "cv.txt"),
    ]
    runtime.setup.apply_draft(None, {conflict.id: 1})
    titles = [e.title for e in runtime.profiles.load_profile().experience]
    assert titles == ["Lead Frontend Engineer", "Frontend Engineer"]
