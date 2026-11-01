"""The ATS check (text layer and keyword coverage) and the quality review: stretches,
generic lines, and requirements the documents skip."""

from __future__ import annotations

import pytest

from offerbound.apply.ats import (
    PostingRequirement,
    contains,
    coverage,
    cv_text,
    parse_checks,
)
from offerbound.apply.drafts import build_cv
from offerbound.apply.review import RequirementReview, ReviewFlag, ReviewResult
from offerbound.apply.service import ApplyParams, DocumentsIn, FlagRef, KeepFlagError
from offerbound.llm.fake import FakeProvider
from offerbound.services.runtime import Runtime
from tests.test_apply import Scripted, clean_draft, noop_progress, profile, ready

EN = "\N{EN DASH}"


def req(
    text: str, terms: list[str], also: list[str] | None = None, priority: str = "required"
) -> PostingRequirement:
    return PostingRequirement.model_validate(
        {"requirement": text, "priority": priority, "terms": terms, "also": also or []}
    )


@pytest.mark.parametrize(
    ("text", "term", "found"),
    [
        ("Built dashboards in Looker", "dashboard", True),
        ("REACT and typescript", "React", True),
        ("Shipped C++ services", "C++", True),
        ("Shipped C services", "C++", False),
        ("Wrote C# and .NET apps", ".NET", True),
        ("machine-learning models", "machine learning", True),
        ("Reactive systems", "React", False),
        ("", "React", False),
    ],
)
def test_contains_matches_whole_terms(text: str, term: str, found: bool) -> None:
    assert contains(text, term) is found


def test_coverage_statuses() -> None:
    cv = build_cv(profile(), clean_draft().cv)
    views = coverage(
        [
            req("React experience", ["React"]),
            req("ECMAScript", ["ECMAScript"], also=["TypeScript"]),
            req("Accessibility", ["Accessibility"]),
            req("Kubernetes in production", ["Kubernetes"], priority="preferred"),
        ],
        cv_text(cv),
        profile(),
    )
    assert [(v.keyword, v.matched) for v in views] == [
        ("covered", "React"),
        ("synonym", "TypeScript"),
        ("missing_have", None),  # in the profile's skills, but not in this CV
        ("gap", None),
    ]


def test_parse_checks_catch_what_parsers_trip_on() -> None:
    cv = build_cv(profile(), clean_draft().cv)
    text = cv_text(cv)
    assert [c.name for c in parse_checks(cv, text) if not c.passed] == []

    broken = (
        text.replace("ada@example.com", "")
        .replace("Mar 2021 - Present", f"Mar 2021 {EN} Present")
        .replace("Jun 2017 - Feb 2021", "")
    )
    failed = {c.name for c in parse_checks(cv, broken + " (cid:42)") if not c.passed}
    assert failed == {
        "Readable text",
        "Email as text",
        "Plain hyphens in dates",
        "Dates on every entry",
    }


pytestmark = pytest.mark.anyio


async def test_missing_keywords_get_the_revision_round_and_are_reported(
    runtime: Runtime, fake: FakeProvider
) -> None:
    first = clean_draft()
    first.requirements = [
        req("React experience", ["React"]),
        req("Accessibility expertise", ["Accessibility"]),
        req("Kubernetes", ["Kubernetes"], priority="preferred"),
    ]
    script = Scripted(drafts=[first, first])  # the revision still leaves Accessibility out
    job_id = ready(runtime, fake, script)

    result = await runtime.applications.apply(ApplyParams(job_id=job_id), noop_progress)

    assert len(script.prompts["draft"]) == 2
    assert (
        '"Accessibility": The posting asks for this and your profile shows it'
        in (script.prompts["draft"][1])
    )
    assert "Kubernetes" not in script.prompts["draft"][1]  # a real gap is never stuffed in
    assert result.application_id is not None
    bundle = runtime.applications.load_bundle(result.application_id)
    assert bundle is not None
    assert [(r.requirement, r.keyword) for r in bundle.requirements] == [
        ("React experience", "covered"),
        ("Accessibility expertise", "missing_have"),
        ("Kubernetes", "gap"),
    ]
    assert bundle.ats is not None
    assert bundle.ats.source in ("pdf", "docx")
    assert all(c.passed for c in bundle.ats.checks), bundle.ats.checks
    assert [(f.kind, f.text) for f in result.flags] == [("ats", "Accessibility")]
    assert result.status == "needs_review"


async def test_the_review_flags_stretches_generic_lines_and_skipped_requirements(
    runtime: Runtime, fake: FakeProvider
) -> None:
    draft = clean_draft()
    draft.requirements = [req("React", ["React"]), req("On-call rotation", ["on-call"])]
    review = ReviewResult(
        flags=[
            ReviewFlag(
                location="cv:experience.0.bullets.0",
                text="Lifted checkout conversion 12% with a redesign",
                issue="The profile says you led a redesign; 'owned growth' would be a stretch.",
                kind="stretch",
            ),
            ReviewFlag(
                location="cover_letter:paragraphs.2",
                text="I'd love to talk about your 2027 roadmap.",
                issue="Any applicant could write this.",
                kind="generic",
            ),
        ],
        requirements=[
            RequirementReview(index=0, addressed=True, note="Shown in the first role."),
            RequirementReview(index=1, addressed=False, note="Neither document mentions on-call."),
        ],
    )
    script = Scripted(drafts=[draft], review=review)
    job_id = ready(runtime, fake, script)

    result = await runtime.applications.apply(ApplyParams(job_id=job_id), noop_progress)

    assert "0. (required) React" in script.prompts["review"][0]
    assert [(f.kind, f.location) for f in result.flags] == [
        ("stretch", "experience.0.bullets.0"),
        ("style", "paragraphs.2"),
        ("unaddressed", "requirements.1"),
    ]
    assert result.application_id is not None
    bundle = runtime.applications.load_bundle(result.application_id)
    assert bundle is not None
    assert [(r.addressed, r.note) for r in bundle.requirements] == [
        (True, "Shown in the first role."),
        (False, "Neither document mentions on-call."),
    ]


async def test_kept_flags_stay_hidden_but_unsupported_facts_cannot_be_kept(
    runtime: Runtime, fake: FakeProvider
) -> None:
    review = ReviewResult(
        flags=[
            ReviewFlag(
                location="cv:summary",
                text="Frontend engineer who ships accessible React interfaces.",
                issue="A stretch.",
                kind="stretch",
            ),
            ReviewFlag(
                location="cover_letter:paragraphs.0",
                text="Your checkout team's focus on accessibility is why I'm applying.",
                issue="Not in the profile.",
                kind="unsupported",
            ),
        ]
    )
    job_id = ready(runtime, fake, Scripted(review=review))
    result = await runtime.applications.apply(ApplyParams(job_id=job_id), noop_progress)
    app_id = result.application_id
    assert app_id is not None
    stretch, unsupported = result.flags

    detail = runtime.applications.keep_flag(app_id, FlagRef.of(stretch))
    assert detail.documents is not None
    assert [f.kind for f in detail.documents.flags] == ["unsupported"]
    with pytest.raises(KeepFlagError):
        runtime.applications.keep_flag(app_id, FlagRef.of(unsupported))
    with pytest.raises(KeyError):
        runtime.applications.keep_flag(app_id, FlagRef.of(stretch))  # already kept

    again = await runtime.applications.save_documents(app_id, DocumentsIn())
    assert again.documents is not None
    assert [f.kind for f in again.documents.flags] == ["unsupported"]
    assert again.documents.kept == [FlagRef.of(stretch)]
