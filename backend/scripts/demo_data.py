"""Made-up demo data for README screenshots, GIFs, and trying the app without an API key.

    uv run python scripts/demo_data.py seed ~/RoleHawk-demo
    uv run python scripts/demo_data.py serve ~/RoleHawk-demo

`seed` fills a NEW data folder with a fictional job seeker (Jordan Avery), made-up companies
and postings, fit scores, applications at every stage with real generated documents, follow-ups,
a chat, and a month of AI spend. Everything is invented: no real people, companies, or job
links (every URL is on example.com).

`serve` runs the dashboard against that folder with a scripted stand-in for Claude, so ranking,
/apply, follow-up drafts, and chat all respond without an API key or any network call. It
prints a launch link like `rolehawk start` does. Build the frontend first (`npm run build` in
frontend/). Your real data folder (~/RoleHawk) is never touched: both commands refuse to run
on it, and `seed` refuses a folder that already has data.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import os
import re
import secrets
import sys
import threading
import webbrowser
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

from pydantic import BaseModel
from sqlalchemy import delete, select

from rolehawk.apply.ats import PostingRequirement
from rolehawk.apply.drafts import ApplicationDraft, CvDraft, LetterDraft, ProjectDraft, RoleDraft
from rolehawk.apply.followup import FollowUpDraftOut
from rolehawk.apply.review import ReviewFlag, ReviewResult
from rolehawk.apply.service import ApplyParams, StagePatch
from rolehawk.db.engine import make_engine, make_session_factory
from rolehawk.db.models import (
    Application,
    ChatRole,
    FollowUp,
    FollowUpChannel,
    Job,
    LLMCall,
    Outcome,
    Stage,
    StageEvent,
)
from rolehawk.db.types import utcnow
from rolehawk.fit.rubric import FitBatch, Gate, JobFit
from rolehawk.llm.fake import FakeProvider, FakeReply
from rolehawk.llm.types import Completion, LLMRequest
from rolehawk.memory.extraction import ExtractedProposals
from rolehawk.memory.sessions import SessionSummary
from rolehawk.paths import DataPaths
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
)
from rolehawk.services.runtime import Runtime, open_runtime

NOW = utcnow()

# --- the job seeker -----------------------------------------------------------------------

PROFILE = Profile(
    contact=Contact(
        name="Jordan Avery",
        email="jordan.avery@example.com",
        phone="+1 555 0142",
        location="Chicago, IL",
        links=["linkedin.com/in/jordan-avery-example", "jordanavery.example.com"],
    ),
    headline="Senior Frontend Engineer",
    summary=(
        "Frontend engineer with eight years of React and TypeScript, most recently leading a "
        "design system and checkout work for a logistics SaaS."
    ),
    experience=[
        Experience(
            title="Senior Frontend Engineer",
            company="Fieldnote Software",
            location="Chicago, IL",
            start="2021-04",
            current=True,
            highlights=[
                "Led the design system used by 7 product teams, built with React and Storybook",
                "Rebuilt the shipment tracking dashboard, cutting load time from 6s to 1.8s",
                "Introduced Playwright end-to-end tests that now gate every release",
                "Mentored 4 engineers through their first year on the team",
            ],
        ),
        Experience(
            title="Frontend Engineer",
            company="Parcelpoint",
            location="Remote",
            start="2018-06",
            end="2021-03",
            highlights=[
                "Shipped the self-serve checkout used by 12,000 merchants",
                "Moved the web app from JavaScript to TypeScript with zero downtime",
                "Raised the accessibility audit score from 61 to 96",
            ],
        ),
        Experience(
            title="Web Developer",
            company="Brickhouse Digital",
            location="Chicago, IL",
            start="2016-01",
            end="2018-05",
            highlights=["Built marketing sites and booking flows for 20 local clients"],
        ),
    ],
    education=[
        Education(institution="Lakeshore State University", degree="BS", field="Computer Science")
    ],
    skills=[
        "TypeScript",
        "React",
        "Next.js",
        "Design systems",
        "Accessibility",
        "Playwright",
        "GraphQL",
        "Node.js",
        "Performance",
        "Storybook",
    ],
    projects=[
        Project(name="Gridkit", highlights=["Open source data grid with 1,400 GitHub stars"]),
    ],
    certifications=[Certification(name="Web Accessibility Specialist", issuer="IAAP")],
    languages=["English", "Spanish"],
)

PREFERENCES = Preferences(
    target_titles=["Senior Frontend Engineer", "Staff Frontend Engineer", "Design Systems Lead"],
    seniority="senior",
    locations=["Chicago, IL", "Remote"],
    remote=RemotePreference.REMOTE,
    country="US",
    salary_floor=SalaryFloor(amount=165_000, currency="USD"),
    work_authorization="US citizen",
    deal_breakers=["On-call more than one week a month", "Crypto or gambling"],
    energizing=["Design systems", "Performance work", "Mentoring"],
    draining=["Pure maintenance roles"],
)

# --- the postings -------------------------------------------------------------------------


@dataclass(frozen=True)
class DemoJob:
    company: str
    title: str
    location: str
    portal: str
    score: int
    salary: str
    reasons: tuple[str, ...]
    gaps: tuple[str, ...] = ()
    posted_days: int = 3
    closes_in: int | None = None
    must: tuple[str, ...] = ("React", "TypeScript")
    nice: tuple[str, ...] = ("Design systems",)
    dismissed: bool = False


JOBS: list[DemoJob] = [
    # On the board (applications below), in the order they're listed there.
    DemoJob(
        "Harborlight Labs",
        "Senior Frontend Engineer",
        "Remote (US)",
        "greenhouse",
        94,
        "$175,000 to $205,000",
        (
            "Design system lead role matches your Fieldnote work",
            "Remote, and above your salary floor",
            "Performance focus you said energizes you",
        ),
        posted_days=2,
        closes_in=9,
    ),
    DemoJob(
        "Quillstack",
        "Staff Frontend Engineer",
        "Chicago, IL (hybrid)",
        "lever",
        91,
        "$190,000 to $220,000",
        ("Staff scope with mentoring, which you want", "Chicago hybrid fits your locations"),
        gaps=("GraphQL federation",),
        posted_days=1,
        must=("React", "TypeScript", "GraphQL"),
    ),
    DemoJob(
        "Copperleaf Health",
        "Senior UI Engineer, Design Systems",
        "Remote (US)",
        "ashby",
        89,
        "$170,000 to $195,000",
        ("Accessibility certification is a stated plus", "Design systems is the whole job"),
        posted_days=4,
        must=("React", "Accessibility"),
        nice=("Storybook",),
    ),
    DemoJob(
        "Tidewater Bank",
        "Senior Frontend Engineer, Web Platform",
        "Remote (US)",
        "greenhouse",
        87,
        "$168,000 to $190,000",
        ("Platform work close to your Parcelpoint migration", "Strong TypeScript match"),
        posted_days=6,
        must=("TypeScript", "React", "Playwright"),
    ),
    DemoJob(
        "Marigold Learning",
        "Frontend Engineer, Growth",
        "Remote (US)",
        "workable",
        82,
        "$160,000 to $180,000",
        (
            "Checkout and experiments echo your Parcelpoint work",
            "Salary range starts just under your floor",
        ),
        posted_days=14,
        must=("React", "Next.js"),
    ),
    DemoJob(
        "Fernhill Robotics",
        "Senior Frontend Engineer, Fleet Console",
        "Chicago, IL",
        "lever",
        85,
        "$165,000 to $185,000",
        (
            "Dashboard performance work like your tracking rebuild",
            "Onsite in Chicago, which you're open to",
        ),
        posted_days=12,
    ),
    DemoJob(
        "Bluefin Logistics",
        "Senior React Engineer",
        "Remote (US)",
        "remoteok",
        80,
        "$150,000 to $175,000",
        ("Logistics domain you know well", "Range overlaps your floor"),
        posted_days=13,
    ),
    DemoJob(
        "Cedarline Software",
        "Senior Frontend Engineer",
        "Remote (US)",
        "ashby",
        86,
        "$172,000 to $198,000",
        ("Design system ownership", "Remote first"),
        posted_days=20,
    ),
    DemoJob(
        "Sparrowgrid",
        "Lead Frontend Engineer",
        "Remote (US)",
        "greenhouse",
        90,
        "$185,000 to $210,000",
        ("Lead role with mentoring", "Energy sector mission"),
        posted_days=24,
    ),
    DemoJob(
        "Juniper Ledger",
        "Frontend Engineer, Payments",
        "New York, NY",
        "lever",
        78,
        "$165,000 to $180,000",
        ("Payments UI like your checkout work",),
        gaps=("Relocation to New York",),
        posted_days=30,
    ),
    DemoJob(
        "Larkspur Media",
        "Senior Web Engineer",
        "Remote (US)",
        "weworkremotely",
        74,
        "$140,000 to $160,000",
        ("Strong React match",),
        gaps=("Below your salary floor",),
        posted_days=28,
    ),
    DemoJob(
        "Orchard Ops",
        "Senior Frontend Engineer",
        "Remote (US)",
        "workable",
        81,
        "$160,000 to $178,000",
        ("Internal tools with heavy tables",),
        posted_days=35,
    ),
    # Discover only.
    DemoJob(
        "Riverglass",
        "Design Systems Engineer",
        "Remote (US)",
        "ashby",
        92,
        "$178,000 to $200,000",
        ("Design systems is the whole job", "Storybook and accessibility focus"),
        posted_days=0,
        closes_in=5,
    ),
    DemoJob(
        "Halcyon Grid",
        "Senior Frontend Engineer, Energy Dashboards",
        "Remote (US)",
        "greenhouse",
        88,
        "$170,000 to $192,000",
        ("Data-heavy dashboards like yours", "Remote"),
        posted_days=1,
    ),
    DemoJob(
        "Ottervale",
        "Staff Engineer, Web",
        "Remote (US)",
        "lever",
        84,
        "$200,000 to $230,000",
        ("Staff scope", "Strong TypeScript"),
        gaps=("Kubernetes",),
        posted_days=1,
        must=("TypeScript", "React", "Kubernetes"),
    ),
    DemoJob(
        "Pinecrest Analytics",
        "Senior Frontend Engineer",
        "Chicago, IL (hybrid)",
        "workable",
        79,
        "$158,000 to $176,000",
        ("Chicago hybrid", "Charts and tables"),
        posted_days=2,
    ),
    DemoJob(
        "Stonepath Insurance",
        "Frontend Engineer II",
        "Remote (US)",
        "greenhouse",
        63,
        "$120,000 to $140,000",
        ("React match",),
        gaps=("Below your seniority", "Below your salary floor"),
        posted_days=3,
    ),
    DemoJob(
        "Willowcourt",
        "Senior Frontend Engineer, Mobile Web",
        "Austin, TX",
        "ashby",
        58,
        "$150,000 to $170,000",
        ("React match",),
        gaps=("Onsite in Austin",),
        posted_days=2,
    ),
    DemoJob(
        "Lumen & Pine",
        "Frontend Developer",
        "Remote (US)",
        "remoteok",
        51,
        "$95,000 to $115,000",
        ("Small team",),
        gaps=("Junior scope", "Well below your salary floor"),
        posted_days=4,
    ),
    DemoJob(
        "Ninebark Games",
        "Senior Frontend Engineer, Wallet",
        "Remote (US)",
        "lever",
        36,
        "$180,000 to $200,000",
        ("Strong React match",),
        posted_days=1,
        gaps=("Crypto wallet product",),
    ),
    DemoJob(
        "Mapleford Health",
        "Senior Frontend Engineer",
        "Remote (US)",
        "greenhouse",
        0,
        "",
        (),
        posted_days=0,
    ),
]

DEAL_BREAKER = {"Ninebark Games": "Crypto or gambling"}


def description(job: DemoJob) -> str:
    must = "\n".join(f"- {skill} in production" for skill in job.must)
    nice = "\n".join(f"- {skill}" for skill in job.nice)
    return (
        f"{job.company} is hiring a {job.title} to help build the product our customers use "
        f"every day.\n\nWhat you'll do\n- Own key screens end to end, from design review to "
        f"release\n- Make the app fast, accessible, and pleasant to use\n- Raise the bar for "
        f"the engineers around you\n\nWhat you need\n{must}\n- 5+ years building web "
        f"apps\n\nNice to have\n{nice}\n\nSalary: {job.salary or 'not listed'}.\n"
        f"This is a made-up posting for the RoleHawk demo."
    )


# --- applications: stage, days since, documents, follow-ups -------------------------------


@dataclass(frozen=True)
class DemoApp:
    company: str
    path: tuple[Stage, ...]  # stages in order; the last is where it is now
    days_ago: tuple[int, ...]  # days ago each stage was reached
    documents: bool = True
    flags: bool = False
    follow_ups: int = 0
    outcome: str | None = None


APPS: list[DemoApp] = [
    DemoApp("Harborlight Labs", (Stage.SAVED,), (1,), documents=False),
    DemoApp("Quillstack", (Stage.SAVED,), (0,), documents=False),
    DemoApp("Copperleaf Health", (Stage.APPLYING,), (2,), flags=True),
    DemoApp("Tidewater Bank", (Stage.APPLYING,), (3,)),
    DemoApp("Marigold Learning", (Stage.APPLYING, Stage.APPLIED), (14, 12)),
    DemoApp("Fernhill Robotics", (Stage.APPLYING, Stage.APPLIED), (6, 4)),
    DemoApp("Bluefin Logistics", (Stage.APPLYING, Stage.APPLIED), (24, 22), follow_ups=1),
    DemoApp("Cedarline Software", (Stage.APPLYING, Stage.APPLIED, Stage.SCREEN), (20, 18, 3)),
    DemoApp(
        "Sparrowgrid",
        (Stage.APPLYING, Stage.APPLIED, Stage.SCREEN, Stage.INTERVIEW),
        (30, 28, 15, 5),
    ),
    DemoApp(
        "Orchard Ops",
        (Stage.APPLYING, Stage.APPLIED, Stage.SCREEN, Stage.INTERVIEW, Stage.OFFER),
        (40, 38, 26, 16, 2),
        outcome="offer",
    ),
    DemoApp(
        "Juniper Ledger",
        (Stage.APPLYING, Stage.APPLIED, Stage.REJECTED),
        (34, 32, 19),
        outcome="rejected",
    ),
    DemoApp(
        "Larkspur Media", (Stage.APPLYING, Stage.APPLIED, Stage.GHOSTED), (60, 58, 20), follow_ups=2
    ),
]


# --- a scripted stand-in for Claude ----------------------------------------------------------

JOB_LINE = re.compile(r"^Job (\d+):", re.MULTILINE)


@dataclass
class DemoClaude:
    """Answers every structured request the app makes, from the demo data."""

    paths: DataPaths
    flagged: set[str] = field(default_factory=set)

    def job(self, job_id: int) -> DemoJob:
        engine = make_engine(self.paths.db)
        try:
            with make_session_factory(engine)() as session:
                company = session.scalar(select(Job.company).where(Job.id == job_id))
        finally:
            engine.dispose()
        return next((j for j in JOBS if j.company == company), JOBS[0])

    def __call__(self, request: LLMRequest, schema: type[BaseModel]) -> BaseModel:
        prompt = request.messages[-1].text
        if schema is FitBatch:
            return FitBatch(jobs=[fit(int(i), self.job(int(i))) for i in JOB_LINE.findall(prompt)])
        if schema is ApplicationDraft:
            return draft(self.company_in(prompt))
        if schema is ReviewResult:
            return review(self.company_in(prompt) in self.flagged)
        if schema is FollowUpDraftOut:
            company = self.company_in(prompt)
            return FollowUpDraftOut(
                subject="Following up on my application",
                body=(
                    f"Hi {company} team, I applied for the Senior Frontend Engineer role a "
                    "couple of weeks ago and wanted to check in. The work on your design system "
                    "is exactly what I enjoy most: at Fieldnote I lead ours across 7 product "
                    "teams. I'd be glad to share more or answer any questions. Thanks for "
                    "your time, Jordan"
                ),
            )
        if schema is ExtractedProposals:
            return ExtractedProposals(proposals=[])
        if schema is SessionSummary:
            return SessionSummary(bullets=["Talked about the job search."], open_threads=[])
        raise NotImplementedError(f"the demo has no scripted answer for {schema.__name__}")

    @staticmethod
    def company_in(prompt: str) -> str:
        return next((j.company for j in JOBS if j.company in prompt), JOBS[0].company)


def fit(job_id: int, job: DemoJob) -> JobFit:
    breaker = DEAL_BREAKER.get(job.company, "")
    spread = (4, -3, 2, -5)
    return JobFit(
        job_id=job_id,
        eligibility=Gate(verdict="pass"),
        language=Gate(verdict="pass"),
        experience=max(0, min(100, job.score + spread[0])),
        skills=max(0, min(100, job.score + spread[1])),
        career=max(0, min(100, job.score + spread[2])),
        logistics=max(0, min(100, job.score + spread[3])),
        deal_breaker=breaker,
        deadline=(date.today() + timedelta(days=job.closes_in)).isoformat()
        if job.closes_in
        else "",
        reasons=list(job.reasons),
        must_have_gaps=list(job.gaps),
    )


def draft(company: str) -> ApplicationDraft:
    demo = next(j for j in JOBS if j.company == company)
    requirements = [
        PostingRequirement(
            requirement=f"{skill} in production", priority="required", terms=[skill], also=[]
        )
        for skill in demo.must
    ] + [
        PostingRequirement(requirement=skill, priority="preferred", terms=[skill], also=[])
        for skill in demo.nice
    ]
    return ApplicationDraft(
        requirements=requirements,
        cv=CvDraft(
            headline=demo.title,
            summary=(
                "Senior frontend engineer who builds fast, accessible React and TypeScript "
                "interfaces and the design systems behind them. Leads a design system used by 7 "
                "product teams and mentors engineers along the way."
            ),
            roles=[
                RoleDraft(
                    index=0,
                    bullets=[
                        "Led the design system used by 7 product teams, built with React and "
                        "Storybook",
                        "Rebuilt the shipment tracking dashboard, cutting load time from 6s "
                        "to 1.8s",
                        "Introduced Playwright end-to-end tests that gate every release",
                        "Mentored 4 engineers through their first year on the team",
                    ],
                ),
                RoleDraft(
                    index=1,
                    bullets=[
                        "Shipped the self-serve checkout used by 12,000 merchants",
                        "Moved the web app from JavaScript to TypeScript with zero downtime",
                        "Raised the accessibility audit score from 61 to 96",
                    ],
                ),
                RoleDraft(
                    index=2,
                    bullets=[
                        "Built marketing sites and booking flows for 20 local clients",
                    ],
                ),
            ],
            skills=[
                "TypeScript",
                "React",
                "Design systems",
                "Accessibility",
                "Storybook",
                "Playwright",
                "Next.js",
                "Performance",
                "GraphQL",
            ],
            projects=[
                ProjectDraft(
                    index=0,
                    bullets=[
                        "Open source data grid with 1,400 GitHub stars",
                    ],
                )
            ],
            certification_indexes=[0],
        ),
        cover_letter=LetterDraft(
            greeting=f"Dear {company} hiring team,",
            paragraphs=[
                f"I'm applying for the {demo.title} role because it sits right where I do my "
                "best work: React interfaces that are fast, accessible, and built on a shared "
                "design system.",
                "At Fieldnote Software I lead the design system used by 7 product teams, and I "
                "rebuilt our shipment tracking dashboard so it loads in 1.8 seconds instead of "
                "6. Before that, at Parcelpoint, I shipped the self-serve checkout used by "
                "12,000 merchants and raised our accessibility audit score from 61 to 96.",
                "I'd bring the same care to your product, and I'd enjoy helping the engineers "
                "around me grow, as I have with the 4 I've mentored.",
                "I'd welcome the chance to talk about the role.",
            ],
            closing="Best regards,",
        ),
    )


def review(flagged: bool) -> ReviewResult:
    if not flagged:
        return ReviewResult(flags=[])
    return ReviewResult(
        flags=[
            ReviewFlag(
                location="cover_letter:paragraphs.2",
                text="I'd enjoy helping the engineers around me grow",
                issue="Generic: say what you'd do for their team, like the design system reviews.",
                kind="generic",
            ),
            ReviewFlag(
                location="cv:summary",
                text="Leads a design system used by 7 product teams",
                issue="A stretch for a UI engineer posting: lead with the accessibility work.",
                kind="stretch",
            ),
        ]
    )


CHAT_REPLY = (
    "Copperleaf Health is your strongest open application: design systems is the whole job "
    "and your accessibility certification is a stated plus. Two lines are flagged in the draft, "
    "both about tone, not facts. Fix those and it's ready to send.\n\nAfter that, Riverglass "
    "(92) closes in 5 days and you haven't saved it yet."
)


class DemoProvider(FakeProvider):
    """The scripted Claude used by `serve`: structured answers from DemoClaude, and the
    same short chat reply to any message."""

    async def complete(self, request: LLMRequest) -> Completion:
        self.replies.append(FakeReply(text=CHAT_REPLY))
        return await super().complete(request)


# --- seeding -------------------------------------------------------------------------------


def ago(days: float, hours: float = 0) -> datetime:
    return NOW - timedelta(days=days, hours=hours)


def add_jobs(runtime: Runtime) -> dict[str, int]:
    ids: dict[str, int] = {}
    with runtime.sessions.begin() as session:
        for n, demo in enumerate(JOBS):
            slug = re.sub(r"[^a-z0-9]+", "-", demo.company.lower()).strip("-")
            job = Job(
                portal_id=demo.portal,
                external_id=f"demo-{n}",
                url=f"https://jobs.example.com/{slug}/{1000 + n}",
                company=demo.company,
                title=demo.title,
                location=demo.location,
                remote="Remote" in demo.location,
                salary_text=demo.salary or None,
                description=description(demo),
                posted_at=ago(demo.posted_days, 3),
                closes_at=date.today() + timedelta(days=demo.closes_in) if demo.closes_in else None,
                scraped_at=ago(demo.posted_days, 1),
                hash=hashlib.sha256(f"demo-{n}".encode()).hexdigest(),
                dismissed_at=ago(1) if demo.dismissed else None,
            )
            session.add(job)
            session.flush()
            ids[demo.company] = job.id
        # Older jobs found in earlier weeks, so the weekly chart has history.
        for week in range(1, 12):
            for k in range(6 + (week * 7) % 9):
                n = 100 + week * 20 + k
                session.add(
                    Job(
                        portal_id=("greenhouse", "lever", "ashby", "remoteok")[k % 4],
                        external_id=f"demo-old-{n}",
                        url=f"https://jobs.example.com/archive/{n}",
                        company=f"Archive Co {n}",
                        title="Frontend Engineer",
                        location="Remote (US)",
                        description="An older made-up posting for the RoleHawk demo.",
                        scraped_at=ago(week * 7 + k % 5),
                        hash=hashlib.sha256(f"demo-old-{n}".encode()).hexdigest(),
                        dismissed_at=ago(week * 7),
                    )
                )
    return ids


async def seed(home: Path) -> None:
    paths = DataPaths(home)
    claude = DemoClaude(paths)
    runtime = open_runtime(paths, provider=FakeProvider(structured_handler=claude))
    runtime.profiles.save_profile(PROFILE)
    runtime.profiles.save_preferences(PREFERENCES)
    ids = add_jobs(runtime)

    scored = [JOBS.index(j) for j in JOBS if j.score]
    with runtime.sessions() as session:
        jobs = {j.id: j for j in session.scalars(select(Job).where(Job.id.in_(ids.values())))}
    fits = [fit(ids[JOBS[i].company], JOBS[i]) for i in scored]
    runtime.ranker.save_external(fits, "claude-haiku-5-5")
    assert len(jobs) == len(JOBS)  # noqa: S101

    async def quiet(_fraction: float | None, _message: str | None) -> None:
        return None

    for demo in APPS:
        job_id = ids[demo.company]
        if demo.flags:
            claude.flagged.add(demo.company)
        if demo.documents:
            outcome = await runtime.applications.apply(ApplyParams(job_id=job_id), quiet)
            application_id = outcome.application_id
            assert application_id is not None  # noqa: S101
        else:
            runtime.jobs.set_saved([job_id])
            found = runtime.applications.application_for_job(job_id)
            assert found is not None  # noqa: S101
            application_id = found
        for stage in demo.path[1:]:
            runtime.applications.update(application_id, StagePatch(stage=stage))
        backdate(runtime, application_id, demo)
        with runtime.sessions.begin() as session:
            for n in range(demo.follow_ups):  # every 10 quiet days after applying
                session.add(
                    FollowUp(
                        application_id=application_id,
                        channel=FollowUpChannel.EMAIL,
                        subject="Following up on my application",
                        body="Hi team, I wanted to check in on my application. Thanks, Jordan",
                        sent_at=ago(demo.days_ago[1] - 10 * (n + 1)),
                    )
                )
        if demo.outcome:
            with runtime.sessions.begin() as session:
                session.add(
                    Outcome(
                        application_id=application_id,
                        result=demo.outcome,
                        created_at=ago(demo.days_ago[-1]),
                    )
                )

    add_spend(runtime)
    add_chat(runtime)
    runtime.engine.dispose()


def backdate(runtime: Runtime, application_id: int, demo: DemoApp) -> None:
    """Moves the stage history back in time to the demo's days."""
    with runtime.sessions.begin() as session:
        events = list(
            session.scalars(
                select(StageEvent)
                .where(StageEvent.application_id == application_id)
                .order_by(StageEvent.id)
            )
        )
        for event, days in zip(events, demo.days_ago[-len(events) :], strict=False):
            event.created_at = ago(days)
        app = session.get(Application, application_id)
        assert app is not None  # noqa: S101
        app.created_at = ago(demo.days_ago[0])
        app.stage_changed_at = ago(demo.days_ago[-1])
        if Stage.APPLIED in demo.path:
            app.applied_at = ago(demo.days_ago[demo.path.index(Stage.APPLIED)])


def add_spend(runtime: Runtime) -> None:
    """This month's AI spend, so Insights shows the meter."""
    lines = [
        ("rank", "claude-haiku-5-5", 26, 0.012),
        ("apply", "claude-opus-5-5", 9, 0.41),
        ("chat", "claude-sonnet-5-5", 14, 0.035),
        ("followup-draft", "claude-sonnet-5-5", 3, 0.02),
    ]
    with runtime.sessions.begin() as session:
        session.execute(delete(LLMCall))  # the seed's own scripted calls
        start = NOW.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        hours = max((NOW - start).total_seconds() / 3600, 1)
        for command, model, calls, cost in lines:
            for n in range(calls):
                session.add(
                    LLMCall(
                        command=command,
                        provider="anthropic",
                        model=model,
                        input_tokens=4_000,
                        output_tokens=900,
                        cost_usd=cost,
                        created_at=start + timedelta(hours=hours * (n + 0.5) / calls),
                    )
                )


def add_chat(runtime: Runtime) -> None:
    chat = runtime.chat.create_session()
    runtime.chat._save(chat.id, ChatRole.USER, "What should I focus on today?")
    runtime.chat._save(chat.id, ChatRole.ASSISTANT, CHAT_REPLY)


# --- serving -------------------------------------------------------------------------------


def serve(home: Path, port: int, web_dir: Path, open_browser: bool) -> None:
    import uvicorn

    from rolehawk.api.app import create_app

    os.environ["ROLEHAWK_SERVER__PORT"] = str(port)  # the Host allowlist follows the port
    provider = DemoProvider(structured_handler=DemoClaude(DataPaths(home)), latency_s=0.6)
    token = secrets.token_urlsafe(32)
    app = create_app(paths=DataPaths(home), token=token, provider=provider, web_dir=web_dir)
    url = f"http://127.0.0.1:{port}/?token={token}"
    print(f"RoleHawk demo - data folder: {home}")
    print(f"Open: {url}", flush=True)
    if open_browser:
        threading.Timer(1.5, webbrowser.open, args=(url,)).start()
    uvicorn.run(app, host="127.0.0.1", port=port, log_config=None, timeout_graceful_shutdown=2)


def guard(home: Path) -> Path:
    home = home.expanduser().resolve()
    if home == DataPaths.default().root.resolve():
        sys.exit("That's your real RoleHawk data folder. Pick another, like ~/RoleHawk-demo.")
    return home


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    s = sub.add_parser("seed", help="Fill a new folder with demo data")
    s.add_argument("home", type=Path)
    v = sub.add_parser("serve", help="Run the dashboard on a demo folder with scripted Claude")
    v.add_argument("home", type=Path)
    v.add_argument("--port", type=int, default=8777)
    v.add_argument("--no-browser", action="store_true")
    v.add_argument(
        "--web-dir",
        type=Path,
        default=Path(__file__).resolve().parents[2] / "frontend" / "dist",
    )
    args = parser.parse_args()
    home = guard(args.home)
    if args.command == "seed":
        if home.exists() and any(home.iterdir()):
            sys.exit(f"{home} already has files. Seed a new, empty folder.")
        asyncio.run(seed(home))
        print(f"Seeded {home}. Run: uv run python scripts/demo_data.py serve {home}")
    else:
        if not (args.web_dir / "index.html").is_file():
            sys.exit(f"No built frontend in {args.web_dir}. Run `npm run build` in frontend/.")
        serve(home, args.port, args.web_dir.resolve(), not args.no_browser)


if __name__ == "__main__":
    main()
