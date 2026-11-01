"""House style for generated documents: clichés are flagged, em dashes become commas, and
dashes in number ranges become ASCII hyphens."""

from __future__ import annotations

import pytest

from rolehawk.apply.drafts import build_cv, build_letter
from rolehawk.apply.style import check_style, plain_dashes, polish
from rolehawk.db.models import Job
from rolehawk.rendering.model import CoverLetter, CvDocument
from tests.test_apply import clean_draft, profile

EM = "\N{EM DASH}"
EN = "\N{EN DASH}"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            f"I rebuilt checkout {EM} the slowest page we had.",
            "I rebuilt checkout, the slowest page we had.",
        ),
        (f"I rebuilt checkout{EM}the slowest page.", "I rebuilt checkout, the slowest page."),
        ("Shipped it -- on time.", "Shipped it, on time."),
        (f"Grew it {EN} fast.", "Grew it, fast."),
        (f"From 2019{EN}2021 and 10 {EN} 20 users.", "From 2019-2021 and 10-20 users."),
        (f"It worked {EM}.", "It worked."),
        ("A well-known, plain sentence.", "A well-known, plain sentence."),
    ],
)
def test_plain_dashes(text: str, expected: str) -> None:
    assert plain_dashes(text) == expected


def documents() -> tuple[CvDocument, CoverLetter]:
    draft = clean_draft()
    draft.cv.summary = "Passionate about accessible interfaces and a proven track record."
    draft.cover_letter.paragraphs[0] = f"I am writing to express my interest {EM} truly."
    job = Job(company="Globex", title="Frontend Engineer", description="")
    return build_cv(profile(), draft.cv), build_letter(profile(), job, draft.cover_letter)


def test_cliches_are_flagged_with_what_to_do_instead() -> None:
    cv, letter = documents()
    flags = check_style(cv, letter)
    assert [(f.document, f.location, f.kind) for f in flags] == [
        ("cv", "summary", "style"),
        ("cv", "summary", "style"),
        ("cover_letter", "paragraphs.0", "style"),
    ]
    assert flags[0].issue == '"passionate about" is a cliché: show it with something you did'
    assert len(check_style(*polish(cv, letter))) == 3  # polishing fixes dashes, not wording


def test_polish_touches_only_the_regenerated_section() -> None:
    draft = clean_draft()
    draft.cv.summary = f"Engineer {EM} accessible UIs."
    draft.cv.roles[0].bullets = [f"Lifted conversion 12% {EM} with a redesign"]
    draft.cover_letter.paragraphs = [f"Hello {EM} there."]
    job = Job(company="Globex", title="Frontend Engineer", description="")
    cv, letter = build_cv(profile(), draft.cv), build_letter(profile(), job, draft.cover_letter)

    all_cv, all_letter = polish(cv, letter)
    assert all_cv.summary == "Engineer, accessible UIs."
    assert all_cv.experience[0].bullets == ["Lifted conversion 12%, with a redesign"]
    assert all_letter.paragraphs == ["Hello, there."]

    only_summary, same_letter = polish(cv, letter, "summary")
    assert only_summary.summary == "Engineer, accessible UIs."
    assert only_summary.experience[0].bullets == [f"Lifted conversion 12% {EM} with a redesign"]
    assert same_letter.paragraphs == [f"Hello {EM} there."]
