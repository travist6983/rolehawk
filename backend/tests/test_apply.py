"""/apply: the truthfulness rule (by construction and by check), the fit gate, revision and
review passes, documents and the application row, edits, regeneration, the API and commands,
and autofill against local copies of ATS form shapes (it must never submit)."""

from __future__ import annotations

import re
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from offerbound.apply.autofill import (
    Applicant,
    Autofiller,
    AutofillReport,
    applicant_from,
    application_url,
)
from offerbound.apply.drafts import (
    ApplicationDraft,
    CvDraft,
    LetterDraft,
    ProjectDraft,
    RoleDraft,
    build_cv,
    build_letter,
)
from offerbound.apply.review import ReviewFlag, ReviewResult
from offerbound.apply.service import ApplyParams, DocumentsIn, ProfileIncompleteError
from offerbound.apply.truth import check_cv, check_letter, numbers_in
from offerbound.db.models import Application, Job, Stage
from offerbound.db.types import utcnow
from offerbound.fit.rubric import FitBatch, JobFit
from offerbound.llm.fake import FakeProvider
from offerbound.llm.types import LLMRequest, Task
from offerbound.profile.model import (
    Certification,
    Contact,
    Education,
    Experience,
    Profile,
    Project,
)
from offerbound.rendering.text import docx_text, pdf_text
from offerbound.services.runtime import Runtime
from tests.test_api_setup import wait_for_task

pytestmark = pytest.mark.anyio

FIXTURES = Path(__file__).parent / "fixtures" / "autofill"
JOB_ID = re.compile(r"^Job (\d+):", re.MULTILINE)


def profile() -> Profile:
    return Profile(
        contact=Contact(
            name="Ada Example",
            email="ada@example.com",
            phone="+1 555 0100",
            location="Austin, TX",
            links=["linkedin.com/in/ada", "github.com/ada", "ada.dev"],
        ),
        headline="Senior Frontend Engineer",
        experience=[
            Experience(
                title="Senior Frontend Engineer",
                company="Northwind Payments",
                start="2021-03",
                current=True,
                highlights=[
                    "Led the checkout redesign, lifting conversion 12%",
                    "Built the design system used by 9 teams with React and Storybook",
                ],
            ),
            Experience(
                title="Frontend Engineer",
                company="Contoso",
                start="2017-06",
                end="2021-02",
                highlights=["Shipped the dashboard builder used by 4,000 customers"],
            ),
        ],
        education=[Education(institution="UT Austin", degree="BSc", field="Computer Science")],
        skills=["TypeScript", "React", "Accessibility"],
        projects=[Project(name="Datepicker", highlights=["2,000 GitHub stars"])],
        certifications=[Certification(name="CPACC")],
    )


def clean_draft() -> ApplicationDraft:
    return ApplicationDraft(
        cv=CvDraft(
            headline="Senior Frontend Engineer",
            summary="Frontend engineer who ships accessible React interfaces.",
            roles=[
                RoleDraft(index=0, bullets=["Lifted checkout conversion 12% with a redesign"]),
                RoleDraft(index=1, bullets=["Shipped a dashboard builder for 4,000 customers"]),
            ],
            skills=["React", "TypeScript", "Storybook"],
            projects=[ProjectDraft(index=0, bullets=["Datepicker with 2,000 GitHub stars"])],
            certification_indexes=[0],
        ),
        cover_letter=LetterDraft(
            greeting="Dear Globex team,",
            paragraphs=[
                "Your checkout team's focus on accessibility is why I'm applying.",
                "At Northwind I lifted conversion 12% by redesigning checkout.",
                "I'd love to talk about your 2027 roadmap.",
            ],
            closing="Best regards,",
        ),
    )


def add_job(runtime: Runtime, description: str = "We need React. Our 2027 roadmap matters.") -> int:
    with runtime.sessions.begin() as session:
        job = Job(
            portal_id="greenhouse",
            external_id=f"apply-{utcnow().timestamp()}",
            url="https://job-boards.greenhouse.io/globex/jobs/1",
            company="Globex",
            title="Senior Frontend Engineer",
            location="Remote",
            description=description,
            scraped_at=utcnow(),
            hash=f"apply-{utcnow().timestamp()}",
        )
        session.add(job)
        session.flush()
        return job.id


class Scripted:
    """FakeProvider structured replies by schema: fit scores, drafts in order, a review."""

    def __init__(
        self,
        score: int = 85,
        drafts: list[ApplicationDraft] | None = None,
        review: ReviewResult | None = None,
    ) -> None:
        self.score = score
        self.drafts = list(drafts or [clean_draft()])
        self.review = review or ReviewResult(flags=[])
        self.prompts: dict[str, list[str]] = {"fit": [], "draft": [], "review": []}

    def __call__(self, request: LLMRequest, schema: type[BaseModel]) -> BaseModel:
        prompt = request.messages[-1].text
        if schema is FitBatch:
            self.prompts["fit"].append(prompt)
            job_id = int(JOB_ID.findall(prompt)[0])
            return FitBatch(
                jobs=[
                    JobFit(
                        job_id=job_id, score=self.score, reasons=["Strong React"], must_have_gaps=[]
                    )
                ]
            )
        if schema is ApplicationDraft:
            self.prompts["draft"].append(prompt)
            return self.drafts.pop(0) if len(self.drafts) > 1 else self.drafts[0]
        if schema is ReviewResult:
            self.prompts["review"].append(prompt)
            return self.review
        raise AssertionError(f"unexpected schema {schema}")


def _read(path: Path) -> bytes:
    return path.read_bytes()


async def noop_progress(_fraction: float | None, _message: str | None) -> None:
    return None


def ready(runtime: Runtime, fake: FakeProvider, script: Scripted) -> int:
    runtime.profiles.save_profile(profile())
    fake.structured_handler = script
    return add_job(runtime)


# --- truthfulness, by construction --------------------------------------------------------


def test_cv_facts_come_from_the_profile_by_index() -> None:
    p = profile()
    draft = CvDraft(
        headline="Staff Engineer",
        summary="s",
        roles=[RoleDraft(index=1, bullets=[" "]), RoleDraft(index=0, bullets=["x"]),
               RoleDraft(index=0, bullets=["dup"]), RoleDraft(index=7, bullets=["ghost"])],
        skills=["React", "React", " "],
        projects=[ProjectDraft(index=3, bullets=["nope"])],
        certification_indexes=[0, 0, 5],
    )  # fmt: skip
    cv = build_cv(p, draft)
    assert [(r.title, r.organization, r.start) for r in cv.experience] == [
        ("Frontend Engineer", "Contoso", "2017-06"),
        ("Senior Frontend Engineer", "Northwind Payments", "2021-03"),
    ]
    assert cv.experience[0].bullets == ["Shipped the dashboard builder used by 4,000 customers"]
    assert cv.skills == ["React"]
    assert cv.projects == []
    assert [c.name for c in cv.certifications] == ["CPACC"]
    assert [e.institution for e in cv.education] == ["UT Austin"]
    assert cv.contact.email == "ada@example.com"


# --- truthfulness, by check ---------------------------------------------------------------


def test_numbers_are_normalized() -> None:
    assert numbers_in("lifted 12% for 4,000 users, $1.5M, 3.10x") == {"12", "4000", "1.5", "3.1"}


def test_check_flags_invented_facts() -> None:
    p = profile()
    cv = build_cv(p, clean_draft().cv)
    assert check_cv(cv, p) == []

    cv.experience[0].bullets.append("Grew revenue 47% in a year")
    cv.experience[1].organization = "Initech"
    cv.skills.append("Kubernetes")
    cv.education[0].degree = "PhD"
    cv.summary = "Engineer with 15 years of experience across 3 teams."
    flags = {(f.location, f.issue) for f in check_cv(cv, p)}
    assert ("experience.0.bullets.1", "47% isn't in your profile") in flags
    assert ("summary", "15 isn't in your profile") in flags  # 3 is a counting word: allowed
    assert ("experience.1", "This role, employer, or its dates don't match your profile") in flags
    assert ("skills.3", "This skill isn't in your profile") in flags
    assert ("education.0", "This degree or school doesn't match your profile") in flags


def test_letters_may_quote_the_posting_but_not_invent() -> None:
    p = profile()
    job = Job(company="Globex", title="x", description="Our team of 40 ships weekly.")
    draft = LetterDraft(
        greeting="Hi",
        paragraphs=[
            "Your team of 40 sounds great.",
            "I cut costs 30%.",
            "I lifted conversion 12%.",
        ],
        closing="Thanks",
    )
    letter = build_letter(p, job, draft)
    flags = check_letter(letter, p, job.description)
    assert [(f.location, f.issue) for f in flags] == [("paragraphs.1", "30% isn't in your profile")]


# --- the /apply pipeline ------------------------------------------------------------------


async def test_apply_drafts_reviews_renders_and_creates_the_application(
    runtime: Runtime, fake: FakeProvider
) -> None:
    script = Scripted()
    job_id = ready(runtime, fake, script)
    events: list[str | None] = []

    async def progress(_f: float | None, message: str | None) -> None:
        events.append(message)

    result = await runtime.applications.apply(ApplyParams(job_id=job_id), progress)

    assert result.status == "ready"
    assert result.fit.score == 85
    assert result.application_id is not None
    assert events[0] == "Checking the fit"
    tasks = [req.model for req, _ in fake.structured_requests]
    assert tasks[0] == runtime.llm.route(Task.RANK).model
    assert runtime.llm.route(Task.WRITE).model in tasks
    assert "<untrusted_content" in script.prompts["draft"][0]
    assert "[0] Senior Frontend Engineer at Northwind Payments" in script.prompts["draft"][0]

    detail = runtime.applications.detail(result.application_id)
    assert detail.stage is Stage.APPLYING
    assert [e.to_stage for e in detail.history] == [Stage.APPLYING]
    bundle = detail.documents
    assert bundle is not None
    assert bundle.cv.experience[0].organization == "Northwind Payments"
    assert "Globex" in (bundle.cover_letter.recipient.company or "")
    cv_pdf = Path(bundle.files.cv["pdf"])
    assert cv_pdf.parent == runtime.paths.generated_documents / str(result.application_id)
    assert "Lifted checkout conversion 12%" in pdf_text(_read(cv_pdf))
    assert "2027 roadmap" in docx_text(_read(Path(bundle.files.cover_letter["docx"])))
    with runtime.sessions() as session:
        app = session.get(Application, result.application_id)
        assert app is not None
        assert app.cv_path == str(cv_pdf)


async def test_fit_gate_stops_below_threshold_unless_forced(
    runtime: Runtime, fake: FakeProvider
) -> None:
    script = Scripted(score=40)
    job_id = ready(runtime, fake, script)

    stopped = await runtime.applications.apply(ApplyParams(job_id=job_id), noop_progress)
    assert stopped.status == "below_threshold"
    assert (stopped.fit.score, stopped.fit.threshold, stopped.fit.passes) == (40, 60, False)
    assert stopped.application_id is None
    assert script.prompts["draft"] == []

    forced = await runtime.applications.apply(ApplyParams(job_id=job_id, force=True), noop_progress)
    assert forced.status == "ready"
    assert len(script.prompts["fit"]) == 1  # the stored score is reused


async def test_unsupported_details_get_one_revision_round(
    runtime: Runtime, fake: FakeProvider
) -> None:
    bad = clean_draft()
    bad.cv.roles[0].bullets = ["Grew revenue 47% in a quarter"]
    script = Scripted(drafts=[bad, clean_draft()])
    job_id = ready(runtime, fake, script)

    result = await runtime.applications.apply(ApplyParams(job_id=job_id), noop_progress)

    assert len(script.prompts["draft"]) == 2
    assert "47% isn't in your profile" in script.prompts["draft"][1]
    assert result.status == "ready"
    assert result.flags == []


async def test_review_flags_are_kept_for_the_user(runtime: Runtime, fake: FakeProvider) -> None:
    review = ReviewResult(
        flags=[
            ReviewFlag(
                location="cv:experience.0.bullets.0",
                text="Lifted checkout conversion 12% with a redesign",
                issue="The profile says you led the redesign, not that it was yours alone.",
            ),
            ReviewFlag(location="cover_letter:paragraphs.0", text="x", issue="Overstated."),
        ]
    )
    job_id = ready(runtime, fake, Scripted(review=review))
    result = await runtime.applications.apply(ApplyParams(job_id=job_id), noop_progress)

    assert result.status == "needs_review"
    assert [(f.document, f.location, f.source) for f in result.flags] == [
        ("cv", "experience.0.bullets.0", "review"),
        ("cover_letter", "paragraphs.0", "review"),
    ]


async def test_apply_needs_experience_in_the_profile(runtime: Runtime, fake: FakeProvider) -> None:
    fake.structured_handler = Scripted()
    job_id = add_job(runtime)
    with pytest.raises(ProfileIncompleteError):
        await runtime.applications.apply(ApplyParams(job_id=job_id), noop_progress)


async def test_saved_jobs_move_to_applying(runtime: Runtime, fake: FakeProvider) -> None:
    job_id = ready(runtime, fake, Scripted())
    runtime.jobs.set_saved([job_id])
    result = await runtime.applications.apply(ApplyParams(job_id=job_id), noop_progress)
    assert result.application_id is not None
    history = runtime.applications.detail(result.application_id).history
    assert [(e.from_stage, e.to_stage) for e in history] == [
        (None, Stage.SAVED),
        (Stage.SAVED, Stage.APPLYING),
    ]


# --- edits and regeneration ---------------------------------------------------------------


async def test_hand_edits_are_fact_checked_and_rerendered(
    runtime: Runtime, fake: FakeProvider
) -> None:
    review = ReviewResult(
        flags=[ReviewFlag(location="cv:summary", text="ships accessible", issue="Vague.")]
    )
    job_id = ready(runtime, fake, Scripted(review=review))
    result = await runtime.applications.apply(ApplyParams(job_id=job_id), noop_progress)
    assert result.application_id is not None
    bundle = runtime.applications.load_bundle(result.application_id)
    assert bundle is not None

    cv = bundle.cv.model_copy(deep=True)
    cv.summary = "Engineer who grew signups 300%."
    detail = await runtime.applications.save_documents(result.application_id, DocumentsIn(cv=cv))
    assert detail.documents is not None
    flags = [(f.location, f.source) for f in detail.documents.flags]
    assert flags == [("summary", "check")]  # the review flag's text is gone, so it's dropped
    pdf = _read(Path(detail.documents.files.cv["pdf"]))
    assert "grew signups 300%" in pdf_text(pdf)


async def test_regenerating_one_section_keeps_the_rest(
    runtime: Runtime, fake: FakeProvider
) -> None:
    rewritten = clean_draft()
    rewritten.cv.summary = "A shorter summary."
    rewritten.cv.skills = ["Accessibility"]  # must be ignored: only the summary is regenerated
    script = Scripted(drafts=[clean_draft(), rewritten])
    job_id = ready(runtime, fake, script)
    first = await runtime.applications.apply(ApplyParams(job_id=job_id), noop_progress)
    assert first.application_id is not None

    again = await runtime.applications.regenerate(
        first.application_id, "summary", "Make it shorter", noop_progress
    )
    assert again.status == "ready"
    assert "Rewrite only the summary part." in script.prompts["draft"][-1]
    assert "Make it shorter" in script.prompts["draft"][-1]
    bundle = runtime.applications.load_bundle(first.application_id)
    assert bundle is not None
    assert bundle.cv.summary == "A shorter summary."
    assert bundle.cv.skills == ["React", "TypeScript", "Storybook"]


# --- API and commands ---------------------------------------------------------------------


def runtime_of(client: TestClient) -> Runtime:
    runtime: Runtime = cast(FastAPI, client.app).state.runtime
    return runtime


def test_apply_api_end_to_end(client: TestClient, fake: FakeProvider) -> None:
    runtime = runtime_of(client)
    job_id = ready(runtime, fake, Scripted())

    plan = client.post("/api/apply/plan", json={"job_id": job_id}).json()
    assert plan["fit"] is None
    assert plan["threshold"] == 60
    assert plan["has_profile"] is True
    assert plan["estimated_cost_usd"] > 0
    assert client.post("/api/apply/plan", json={"job_id": 9999}).status_code == 404

    task = wait_for_task(
        client, client.post("/api/apply", json={"job_id": job_id}).json()["task_id"]
    )
    assert task["status"] == "succeeded", task
    application_id = cast(dict[str, int], task["result"])["application_id"]

    detail = client.get(f"/api/applications/{application_id}").json()
    assert detail["stage"] == "applying"
    assert detail["job"]["id"] == job_id
    pdf = client.get(f"/api/applications/{application_id}/files/cv.pdf")
    assert pdf.headers["content-type"] == "application/pdf"
    assert pdf.headers["content-disposition"].startswith("inline")
    docx = client.get(f"/api/applications/{application_id}/files/cover_letter.docx")
    assert docx.headers["content-disposition"].startswith("attachment")
    assert client.get(f"/api/applications/{application_id}/files/cv.txt").status_code == 422
    assert client.get("/api/applications/9999").status_code == 404

    applied = client.patch(f"/api/applications/{application_id}", json={"stage": "applied"}).json()
    assert applied["stage"] == "applied"
    assert applied["applied_at"] is not None
    assert [e["to_stage"] for e in applied["history"]] == ["applying", "applied"]

    regen = client.post(
        f"/api/applications/{application_id}/regenerate", json={"section": "cover_letter"}
    )
    assert wait_for_task(client, regen.json()["task_id"])["status"] == "succeeded"
    assert (
        client.post("/api/applications/9999/regenerate", json={"section": "skills"}).status_code
        == 404
    )


def test_claude_code_drafts_go_through_the_same_rules(client: TestClient) -> None:
    runtime = runtime_of(client)
    runtime.profiles.save_profile(profile())
    job_id = add_job(runtime)

    def run(name: str, params: dict[str, object]) -> dict[str, object]:
        response = client.post(f"/api/commands/{name}", json={"params": params})
        assert response.status_code == 200, response.text
        return cast(dict[str, object], response.json()["result"])

    context = run("apply-context", {"job_id": job_id})
    assert "[1] Frontend Engineer at Contoso" in cast(str, context["profile_index"])
    assert "never add facts" in cast(str, context["writer_rules"])

    draft = clean_draft().model_dump()
    draft["cv"]["roles"].append({"index": 9, "bullets": ["Invented role"]})
    draft["cv"]["skills"].append("Rust")
    saved = run("apply-save", {"job_id": job_id, "draft": draft})
    assert saved["status"] == "needs_review"
    flags = cast(list[dict[str, str]], saved["flags"])
    assert [f["text"] for f in flags] == ["Rust"]  # the invented role was never built
    application_id = cast(int, saved["application_id"])
    detail = runtime.applications.detail(application_id)
    assert detail.documents is not None
    assert detail.documents.model == "claude-code"
    assert len(detail.documents.cv.experience) == 2


# --- autofill -----------------------------------------------------------------------------


def test_application_urls_per_ats() -> None:
    assert application_url("https://jobs.lever.co/globex/abc") == (
        "https://jobs.lever.co/globex/abc/apply",
        "lever",
    )
    assert application_url("https://jobs.ashbyhq.com/globex/abc/") == (
        "https://jobs.ashbyhq.com/globex/abc/application",
        "ashby",
    )
    assert application_url("https://job-boards.greenhouse.io/globex/jobs/1")[1] == "greenhouse"
    assert application_url("https://apply.workable.com/globex/j/AB12/")[0].endswith(
        "/j/AB12/apply/"
    )
    assert (
        application_url("https://globex.wd5.myworkdayjobs.com/en-US/careers/job/1")[1] == "workday"
    )
    assert application_url("https://example.com/careers/1") == (
        "https://example.com/careers/1",
        "other",
    )


def test_applicant_details() -> None:
    a = applicant_from(
        "Ada Lovelace Byron", "a@x.com", None, "London", ["linkedin.com/in/ada", "ada.dev"]
    )
    assert (a.first_name, a.last_name) == ("Ada", "Lovelace Byron")
    assert a.linkedin == "https://linkedin.com/in/ada"
    assert a.website == "https://ada.dev"
    assert a.github is None


@pytest.fixture
def forms() -> Iterator[tuple[str, list[str]]]:
    """Serves the fixture forms; records any request to /submitted (which must never happen)."""
    submitted: list[str] = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path.startswith("/submitted"):
                submitted.append(self.path)
            path = FIXTURES / (self.path.strip("/") or "index.html")
            body = path.read_bytes() if path.is_file() else b"not found"
            self.send_response(200 if path.is_file() else 404)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self) -> None:
            submitted.append(self.path)
            self.send_response(200)
            self.end_headers()

        def log_message(self, *_args: object) -> None:
            return None

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}", submitted
    server.shutdown()
    server.server_close()


APPLICANT = Applicant(
    first_name="Ada",
    last_name="Example",
    full_name="Ada Example",
    email="ada@example.com",
    phone="+1 555 0100",
    location="Austin, TX",
    linkedin="https://linkedin.com/in/ada",
    github="https://github.com/ada",
    website="https://ada.dev",
)


@pytest.fixture
def files(tmp_path: Path) -> tuple[Path, Path]:
    cv, letter = tmp_path / "Ada Example CV.pdf", tmp_path / "Ada Example cover letter.pdf"
    cv.write_bytes(b"%PDF-1.4 cv")
    letter.write_bytes(b"%PDF-1.4 letter")
    return cv, letter


async def _fill(
    base: str, page_name: str, files: tuple[Path, Path]
) -> tuple[AutofillReport, dict[str, str], dict[str, list[str]]]:
    filler = Autofiller(headless=True, field_timeout_ms=3_000)
    try:
        report, page = await filler.open(
            f"{base}/{page_name}", APPLICANT, files[0], files[1], "Dear team,\n\nHello."
        )
        values = await page.evaluate(
            "() => Object.fromEntries([...document.querySelectorAll("
            "'input:not([type=file]):not([type=checkbox]), textarea')]"
            ".map(e => [e.name || e.id, e.value]))"
        )
        uploads = await page.evaluate(
            "() => Object.fromEntries([...document.querySelectorAll('input[type=file]')]"
            ".map(e => [e.name || e.id, [...e.files].map(f => f.name)]))"
        )
        await page.wait_for_timeout(300)  # give any stray submit time to reach the server
    finally:
        await filler.aclose()
    return report, values, uploads


async def test_autofill_greenhouse_shape(
    forms: tuple[str, list[str]], files: tuple[Path, Path]
) -> None:
    base, submitted = forms
    report, values, uploads = await _fill(base, "greenhouse.html", files)
    assert values["job_application[first_name]"] == "Ada"
    assert values["job_application[last_name]"] == "Example"
    assert values["job_application[email]"] == "ada@example.com"
    assert values["job_application[phone]"] == "+1 555 0100"
    assert values["job_application[answers][0][text_value]"] == "https://linkedin.com/in/ada"
    assert values["job_application[answers][1][text_value]"] == "https://ada.dev"
    assert values["job_application[answers][2][text_value]"] == ""  # custom question: left to you
    assert uploads == {
        "resume": ["Ada Example CV.pdf"],
        "cover_letter": ["Ada Example cover letter.pdf"],
    }
    assert "Why do you want to work at Globex?" in report.needs_you
    assert submitted == []


async def test_autofill_lever_shape(forms: tuple[str, list[str]], files: tuple[Path, Path]) -> None:
    base, submitted = forms
    _report, values, uploads = await _fill(base, "lever.html", files)
    assert values["name"] == "Ada Example"
    assert values["email"] == "ada@example.com"
    assert values["location"] == "Austin, TX"
    assert values["org"] == ""  # current company isn't guessed
    assert values["urls[LinkedIn]"] == "https://linkedin.com/in/ada"
    assert values["urls[GitHub]"] == "https://github.com/ada"
    assert values["comments"].startswith("Dear team,")
    assert uploads["resume"] == ["Ada Example CV.pdf"]
    assert submitted == []


async def test_autofill_ashby_shape_waits_for_the_form(
    forms: tuple[str, list[str]], files: tuple[Path, Path]
) -> None:
    base, submitted = forms
    report, values, uploads = await _fill(base, "ashby.html", files)
    assert values["_systemfield_name"] == "Ada Example"
    assert values["_systemfield_email"] == "ada@example.com"
    assert values["q1"] == "https://linkedin.com/in/ada"
    assert values["q2"] == "+1 555 0100"
    assert uploads["_systemfield_resume"] == ["Ada Example CV.pdf"]
    assert report.needs_you == ["Are you authorized to work in the US?"]
    assert submitted == []


async def test_autofill_reports_pages_without_a_form(
    forms: tuple[str, list[str]], files: tuple[Path, Path]
) -> None:
    base, _ = forms
    report, _, _ = await _fill(base, "no-form.html", files)
    assert report.note is not None
    assert "No application form" in report.note


def test_autofill_never_clicks_or_submits() -> None:
    source = (Path(__file__).parents[1] / "src/offerbound/apply/autofill.py").read_text()
    js = (Path(__file__).parents[1] / "src/offerbound/apply/tag_fields.js").read_text()
    for forbidden in (".click(", ".press(", ".submit(", "requestSubmit", "dispatch_event"):
        assert forbidden not in source
        assert forbidden not in js
