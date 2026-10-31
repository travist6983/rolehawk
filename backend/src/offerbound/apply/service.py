"""/apply: fit gate, tailored drafts, fact check + revision, AI review, DOCX/PDF, and the
application row. Documents and their review flags live in
documents/generated/<application id>/application.json next to the rendered files."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, update
from sqlalchemy.orm import Session, sessionmaker

from offerbound.apply.autofill import Autofiller, AutofillReport, applicant_from
from offerbound.apply.drafts import (
    WRITER_RULES,
    ApplicationDraft,
    Section,
    build_cv,
    build_letter,
    draft_from_documents,
    draft_prompt,
    job_brief,
    revision_prompt,
    section_prompt,
)
from offerbound.apply.review import REVIEW_RULES, ReviewResult, review_prompt
from offerbound.apply.style import check_style, polish
from offerbound.apply.truth import Flag, check_cv, check_letter
from offerbound.config import Settings
from offerbound.db.models import (
    Application,
    ApplyMethod,
    Job,
    JobScore,
    Stage,
    StageEvent,
    StageEventSource,
)
from offerbound.db.types import utcnow
from offerbound.fit.ranker import Ranker
from offerbound.jobs.store import JobDetail, JobStore
from offerbound.llm.meter import estimate_tokens
from offerbound.llm.service import LLMService
from offerbound.llm.types import Message, SystemBlock, Task
from offerbound.memory.context import ContextPack
from offerbound.memory.proposals import MemoryService
from offerbound.paths import DataPaths
from offerbound.profile.model import Profile
from offerbound.rendering.model import CoverLetter, CvDocument, DocumentKind
from offerbound.rendering.pdf import PdfUnavailableError
from offerbound.rendering.service import FORMATS, DocumentService, Format

log = logging.getLogger(__name__)

Progress = Callable[[float | None, str | None], Awaitable[None]]
BUNDLE = "application.json"


class ProfileIncompleteError(ValueError):
    user_message = "Add your work experience to your profile first; /apply tailors from it."


class UnknownJobError(KeyError):
    user_message = "That job is no longer in your list."


class FitView(BaseModel):
    score: int
    reasons: list[str]
    must_have_gaps: list[str]
    threshold: int
    passes: bool


class ApplyParams(BaseModel):
    job_id: int
    force: bool = Field(default=False, description="Draft even if the fit is below threshold")
    cv_template: str | None = None
    cover_template: str | None = None


class ApplyPlan(BaseModel):
    """What /apply will do for a job, shown before it starts."""

    job_id: int
    fit: FitView | None = Field(description="The latest score; null means /apply scores it")
    threshold: int
    application_id: int | None
    has_documents: bool
    has_profile: bool
    configured: bool
    estimated_cost_usd: float


class ApplyOutcome(BaseModel):
    status: Literal["ready", "needs_review", "below_threshold"]
    job_id: int
    application_id: int | None
    fit: FitView
    flags: list[Flag]


class DocumentFiles(BaseModel):
    model_config = ConfigDict(json_schema_serialization_defaults_required=True)

    cv: dict[Format, str] = Field(default_factory=dict)
    cover_letter: dict[Format, str] = Field(default_factory=dict)


class Bundle(BaseModel):
    """application.json: the documents as data, their review flags, and their files."""

    model_config = ConfigDict(json_schema_serialization_defaults_required=True)

    version: int = 1
    job_id: int
    cv: CvDocument
    cover_letter: CoverLetter
    cv_template: str
    cover_template: str
    flags: list[Flag]
    fit: FitView | None
    model: str | None
    files: DocumentFiles
    pdf_unavailable: bool = False
    updated_at: datetime


class StageEventView(BaseModel):
    from_stage: Stage | None
    to_stage: Stage
    source: StageEventSource
    created_at: datetime


class ApplicationDetail(BaseModel):
    id: int
    stage: Stage
    method: ApplyMethod | None
    applied_at: datetime | None
    stage_changed_at: datetime
    notes: str | None
    job: JobDetail
    documents: Bundle | None
    history: list[StageEventView]


class DocumentsIn(BaseModel):
    cv: CvDocument | None = None
    cover_letter: CoverLetter | None = None


class StagePatch(BaseModel):
    stage: Stage | None = None
    notes: str | None = Field(default=None, max_length=10_000)


def _review_flags(result: ReviewResult) -> list[Flag]:
    flags: list[Flag] = []
    for item in result.flags:
        document, _, location = item.location.partition(":")
        if document not in ("cv", "cover_letter") or not location:
            document, location = "cv", item.location
        flags.append(
            Flag(
                document="cv" if document == "cv" else "cover_letter",
                location=location,
                text=item.text,
                issue=item.issue,
                source="review",
            )
        )
    return flags


class ApplyService:
    def __init__(
        self,
        paths: DataPaths,
        sessions: sessionmaker[Session],
        settings: Callable[[], Settings],
        llm: LLMService,
        memory: MemoryService,
        load_profile: Callable[[], Profile],
        ranker: Ranker,
        jobs: JobStore,
        documents: DocumentService,
    ) -> None:
        self._paths = paths
        self._sessions = sessions
        self._settings = settings
        self._llm = llm
        self._memory = memory
        self._load_profile = load_profile
        self._ranker = ranker
        self._jobs = jobs
        self._documents = documents

    # --- helpers ------------------------------------------------------------------------

    def job(self, job_id: int) -> Job:
        with self._sessions() as session:
            job = session.get(Job, job_id)
        if job is None:
            raise UnknownJobError(job_id)
        return job

    def latest_fit(self, job_id: int) -> FitView | None:
        with self._sessions() as session:
            row = session.scalar(
                select(JobScore).where(JobScore.job_id == job_id).order_by(JobScore.id.desc())
            )
        if row is None:
            return None
        return self._fit_view(row.score, row.reasons, row.must_have_gaps)

    def _fit_view(self, score: int, reasons: list[str], gaps: list[str]) -> FitView:
        threshold = self._settings().search.fit_threshold
        return FitView(
            score=score,
            reasons=list(reasons),
            must_have_gaps=list(gaps),
            threshold=threshold,
            passes=score >= threshold,
        )

    def folder(self, application_id: int) -> Path:
        return self._paths.generated_documents / str(application_id)

    def load_bundle(self, application_id: int) -> Bundle | None:
        path = self.folder(application_id) / BUNDLE
        if not path.is_file():
            return None
        return Bundle.model_validate_json(path.read_text(encoding="utf-8"))

    def _save_bundle(self, application_id: int, bundle: Bundle) -> None:
        folder = self.folder(application_id)
        folder.mkdir(parents=True, exist_ok=True)
        tmp = folder / f"{BUNDLE}.tmp"
        tmp.write_text(bundle.model_dump_json(indent=2), encoding="utf-8")
        tmp.replace(folder / BUNDLE)

    def _system(self, rules: str) -> list[SystemBlock]:
        pack = ContextPack(command="apply", memory=self._memory.snapshot())
        return [SystemBlock(rules), pack.memory_block()]

    # --- the pipeline -------------------------------------------------------------------

    def plan(self, job_id: int) -> ApplyPlan:
        job = self.job(job_id)
        profile = self._load_profile()
        application_id = self.application_for_job(job_id)
        system_tokens = sum(estimate_tokens(b.text) for b in self._system(WRITER_RULES))
        prompt_tokens = system_tokens + estimate_tokens(draft_prompt(job, profile))
        cost = sum(
            self._llm.estimate(
                task, input_tokens=prompt_tokens, output_tokens=out, calls=calls
            ).cost_usd
            for task, out, calls in ((Task.WRITE, 3_000, 2), (Task.REVIEW, 1_000, 1))
        )
        return ApplyPlan(
            job_id=job_id,
            fit=self.latest_fit(job_id),
            threshold=self._settings().search.fit_threshold,
            application_id=application_id,
            has_documents=application_id is not None
            and self.load_bundle(application_id) is not None,
            has_profile=bool(profile.experience),
            configured=self._llm.configured,
            estimated_cost_usd=round(cost, 4),
        )

    async def apply(
        self, params: ApplyParams, progress: Progress, task_id: str | None = None
    ) -> ApplyOutcome:
        job = await asyncio.to_thread(self.job, params.job_id)
        await progress(0.05, "Checking the fit")
        fit = await asyncio.to_thread(self.latest_fit, job.id)
        if fit is None:
            scored = await self._ranker.score_one(job.id, task_id)
            fit = self._fit_view(scored.score, scored.reasons, scored.must_have_gaps)
        if not fit.passes and not params.force:
            return ApplyOutcome(
                status="below_threshold", job_id=job.id, application_id=None, fit=fit, flags=[]
            )

        profile = await asyncio.to_thread(self._load_profile)
        if not profile.experience:
            raise ProfileIncompleteError("no experience in profile")

        await progress(0.2, "Writing your tailored CV and cover letter")
        cv, letter, model = await self._draft(job, profile, task_id, progress)
        await progress(0.7, "Fact-checking against your profile")
        flags = await self._review(job, profile, cv, letter, task_id)

        await progress(0.85, "Creating Word and PDF files")
        application_id = await asyncio.to_thread(self.ensure_application, job.id)
        bundle = await self._render(
            application_id,
            job.id,
            cv,
            letter,
            flags,
            fit,
            model,
            params.cv_template,
            params.cover_template,
        )
        await asyncio.to_thread(self._record_files, application_id, bundle)
        return ApplyOutcome(
            status="needs_review" if bundle.flags else "ready",
            job_id=job.id,
            application_id=application_id,
            fit=fit,
            flags=bundle.flags,
        )

    async def _draft(
        self, job: Job, profile: Profile, task_id: str | None, progress: Progress
    ) -> tuple[CvDocument, CoverLetter, str]:
        system = self._system(WRITER_RULES)
        messages = [Message(role="user", text=draft_prompt(job, profile))]
        result = await self._llm.structured_result(
            command="apply",
            task=Task.WRITE,
            system=system,
            messages=messages,
            schema=ApplicationDraft,
            task_id=task_id,
        )
        draft = result.value
        cv, letter = build_cv(profile, draft.cv), build_letter(profile, job, draft.cover_letter)
        problems = (
            check_cv(cv, profile)
            + check_letter(letter, profile, job.description)
            + check_style(cv, letter)
        )
        if problems:  # one revision round with the fact and style checks' findings
            await progress(0.5, "Fixing details your profile doesn't support")
            messages += [
                Message(role="assistant", text=draft.model_dump_json()),
                Message(
                    role="user",
                    text=revision_prompt([f'"{p.text}": {p.issue}' for p in problems]),
                ),
            ]
            revised = await self._llm.structured_result(
                command="apply",
                task=Task.WRITE,
                system=system,
                messages=messages,
                schema=ApplicationDraft,
                task_id=task_id,
            )
            draft = revised.value
            cv = build_cv(profile, draft.cv)
            letter = build_letter(profile, job, draft.cover_letter)
        cv, letter = polish(cv, letter)
        return cv, letter, result.model

    async def _review(
        self,
        job: Job,
        profile: Profile,
        cv: CvDocument,
        letter: CoverLetter,
        task_id: str | None,
    ) -> list[Flag]:
        flags = (
            check_cv(cv, profile)
            + check_letter(letter, profile, job.description)
            + check_style(cv, letter)
        )
        review = await self._llm.structured(
            command="apply",
            task=Task.REVIEW,
            system=self._system(REVIEW_RULES),
            messages=[Message(role="user", text=review_prompt(job_brief(job), cv, letter))],
            schema=ReviewResult,
            task_id=task_id,
        )
        checked = {(f.document, f.location) for f in flags}
        flags += [f for f in _review_flags(review) if (f.document, f.location) not in checked]
        return flags

    async def _render(
        self,
        application_id: int,
        job_id: int,
        cv: CvDocument,
        letter: CoverLetter,
        flags: list[Flag],
        fit: FitView | None,
        model: str | None,
        cv_template: str | None,
        cover_template: str | None,
    ) -> Bundle:
        docs = self._documents
        folder = self.folder(application_id)
        cv_manifest = docs.template_for(DocumentKind.CV, cv_template)
        cover_manifest = docs.template_for(DocumentKind.COVER_LETTER, cover_template)
        name = cv.contact.name
        formats: tuple[Format, ...] = FORMATS
        pdf_unavailable = False
        try:
            cv_files = await docs.write(cv, folder, f"{name} CV", cv_manifest.id, formats)
        except PdfUnavailableError:
            pdf_unavailable, formats = True, ("docx",)
            cv_files = await docs.write(cv, folder, f"{name} CV", cv_manifest.id, formats)
        cover_files = await docs.write(
            letter, folder, f"{name} cover letter", cover_manifest.id, formats
        )
        bundle = Bundle(
            job_id=job_id,
            cv=cv,
            cover_letter=letter,
            cv_template=cv_manifest.id,
            cover_template=cover_manifest.id,
            flags=flags,
            fit=fit,
            model=model,
            files=DocumentFiles(
                cv={f.format: f.path for f in cv_files.files},
                cover_letter={f.format: f.path for f in cover_files.files},
            ),
            pdf_unavailable=pdf_unavailable,
            updated_at=utcnow(),
        )
        await asyncio.to_thread(self._save_bundle, application_id, bundle)
        return bundle

    async def render_documents(
        self,
        application_id: int,
        job_id: int,
        cv: CvDocument,
        letter: CoverLetter,
        flags: list[Flag],
        fit: FitView | None,
        model: str | None,
    ) -> Bundle:
        """Render with the chosen templates, save the bundle, and link the files."""
        bundle = await self._render(
            application_id, job_id, cv, letter, flags, fit, model, None, None
        )
        await asyncio.to_thread(self._record_files, application_id, bundle)
        return bundle

    # --- application rows ---------------------------------------------------------------

    def ensure_application(self, job_id: int) -> int:
        """The job's application, created at Applying (or moved there from Saved)."""
        with self._sessions.begin() as session:
            app = session.scalar(select(Application).where(Application.job_id == job_id))
            if app is None:
                app = Application(job_id=job_id, stage=Stage.APPLYING)
                session.add(app)
                session.flush()
                session.add(
                    StageEvent(
                        application_id=app.id,
                        from_stage=None,
                        to_stage=Stage.APPLYING,
                        source=StageEventSource.USER,
                    )
                )
            elif app.stage is Stage.SAVED:
                self._move(session, app, Stage.APPLYING)
            session.execute(update(Job).where(Job.id == job_id).values(dismissed_at=None))
            return app.id

    @staticmethod
    def _move(session: Session, app: Application, stage: Stage) -> None:
        session.add(
            StageEvent(
                application_id=app.id,
                from_stage=app.stage,
                to_stage=stage,
                source=StageEventSource.USER,
            )
        )
        app.stage = stage
        app.stage_changed_at = utcnow()
        if stage is Stage.APPLIED and app.applied_at is None:
            app.applied_at = utcnow()

    def _record_files(self, application_id: int, bundle: Bundle) -> None:
        with self._sessions.begin() as session:
            app = session.get(Application, application_id)
            if app is None:
                return
            app.cv_path = bundle.files.cv.get("pdf") or bundle.files.cv.get("docx")
            app.cover_path = bundle.files.cover_letter.get("pdf") or bundle.files.cover_letter.get(
                "docx"
            )

    def detail(self, application_id: int) -> ApplicationDetail:
        with self._sessions() as session:
            app = session.get(Application, application_id)
            if app is None:
                raise KeyError(application_id)
            events = session.scalars(
                select(StageEvent)
                .where(StageEvent.application_id == app.id)
                .order_by(StageEvent.created_at, StageEvent.id)
            )
            history = [
                StageEventView(
                    from_stage=e.from_stage,
                    to_stage=e.to_stage,
                    source=e.source,
                    created_at=e.created_at,
                )
                for e in events
            ]
            job_id = app.job_id
            fields = {
                "id": app.id,
                "stage": app.stage,
                "method": app.method,
                "applied_at": app.applied_at,
                "stage_changed_at": app.stage_changed_at,
                "notes": app.notes,
            }
        return ApplicationDetail.model_validate(
            {
                **fields,
                "job": self._jobs.get(job_id),
                "documents": self.load_bundle(application_id),
                "history": history,
            }
        )

    def application_for_job(self, job_id: int) -> int | None:
        with self._sessions() as session:
            return session.scalar(select(Application.id).where(Application.job_id == job_id))

    def update(self, application_id: int, patch: StagePatch) -> ApplicationDetail:
        with self._sessions.begin() as session:
            app = session.get(Application, application_id)
            if app is None:
                raise KeyError(application_id)
            if patch.stage is not None and patch.stage is not app.stage:
                self._move(session, app, patch.stage)
            if patch.notes is not None:
                app.notes = patch.notes.strip() or None
        return self.detail(application_id)

    # --- edits --------------------------------------------------------------------------

    def _require_bundle(self, application_id: int) -> Bundle:
        bundle = self.load_bundle(application_id)
        if bundle is None:
            raise KeyError(application_id)
        return bundle

    async def save_documents(self, application_id: int, edits: DocumentsIn) -> ApplicationDetail:
        """Hand edits: re-run the fact check, keep AI review flags whose text is still there,
        and re-render."""
        bundle = await asyncio.to_thread(self._require_bundle, application_id)
        profile = await asyncio.to_thread(self._load_profile)
        job = await asyncio.to_thread(self.job, bundle.job_id)
        cv = edits.cv or bundle.cv
        letter = edits.cover_letter or bundle.cover_letter
        flags = (
            check_cv(cv, profile)
            + check_letter(letter, profile, job.description)
            + check_style(cv, letter)
        )
        text = json.dumps([cv.model_dump(), letter.model_dump()])
        checked = {(f.document, f.location) for f in flags}
        flags += [
            f
            for f in bundle.flags
            if f.source == "review" and f.text in text and (f.document, f.location) not in checked
        ]
        new = await self._render(
            application_id,
            bundle.job_id,
            cv,
            letter,
            flags,
            bundle.fit,
            bundle.model,
            bundle.cv_template,
            bundle.cover_template,
        )
        await asyncio.to_thread(self._record_files, application_id, new)
        return await asyncio.to_thread(self.detail, application_id)

    async def regenerate(
        self,
        application_id: int,
        section: Section,
        instruction: str | None,
        progress: Progress,
        task_id: str | None = None,
    ) -> ApplyOutcome:
        bundle = await asyncio.to_thread(self._require_bundle, application_id)
        job = await asyncio.to_thread(self.job, bundle.job_id)
        profile = await asyncio.to_thread(self._load_profile)
        current = draft_from_documents(bundle.cv, bundle.cover_letter, profile)
        await progress(0.1, f"Rewriting the {section.replace('_', ' ')}")
        result = await self._llm.structured_result(
            command="apply",
            task=Task.WRITE,
            system=self._system(WRITER_RULES),
            messages=[
                Message(role="user", text=draft_prompt(job, profile)),
                Message(role="assistant", text=current.model_dump_json()),
                Message(role="user", text=section_prompt(section, "(above)", instruction)),
            ],
            schema=ApplicationDraft,
            task_id=task_id,
        )
        new = result.value
        merged = current.model_copy(deep=True)
        if section == "summary":
            merged.cv.headline, merged.cv.summary = new.cv.headline, new.cv.summary
        elif section == "experience":
            merged.cv.roles, merged.cv.projects = new.cv.roles, new.cv.projects
        elif section == "skills":
            merged.cv.skills = new.cv.skills
        else:
            merged.cover_letter = new.cover_letter
        cv = build_cv(profile, merged.cv)
        letter = (
            build_letter(profile, job, merged.cover_letter)
            if section == "cover_letter"
            else bundle.cover_letter
        )
        cv, letter = polish(cv, letter, section)
        await progress(0.6, "Fact-checking against your profile")
        flags = await self._review(job, profile, cv, letter, task_id)
        await progress(0.85, "Creating Word and PDF files")
        rendered = await self._render(
            application_id,
            job.id,
            cv,
            letter,
            flags,
            bundle.fit,
            result.model,
            bundle.cv_template,
            bundle.cover_template,
        )
        await asyncio.to_thread(self._record_files, application_id, rendered)
        return ApplyOutcome(
            status="needs_review" if rendered.flags else "ready",
            job_id=job.id,
            application_id=application_id,
            fit=bundle.fit or self._fit_view(0, [], []),
            flags=rendered.flags,
        )

    def file_path(self, application_id: int, document: str, fmt: Format) -> Path:
        bundle = self._require_bundle(application_id)
        files = bundle.files.cv if document == "cv" else bundle.files.cover_letter
        path = Path(files.get(fmt, ""))
        folder = self.folder(application_id).resolve()
        if not path.is_file() or path.resolve().parent != folder:
            raise KeyError(f"{document}.{fmt}")
        return path

    async def autofill(self, application_id: int, autofiller: Autofiller) -> AutofillReport:
        """Open the job's application form in a visible browser and fill what we know."""
        bundle = await asyncio.to_thread(self._require_bundle, application_id)
        job = await asyncio.to_thread(self.job, bundle.job_id)
        if not job.url.startswith(("https://", "http://")):
            raise ValueError("this job has no web link to apply on")
        c = bundle.cv.contact
        applicant = applicant_from(c.name, c.email, c.phone, c.location, c.links)

        def pick(files: dict[Format, str]) -> Path | None:
            found = files.get("pdf") or files.get("docx")
            return Path(found) if found else None

        letter = "\n\n".join(
            [bundle.cover_letter.greeting, *bundle.cover_letter.paragraphs,
             bundle.cover_letter.closing, bundle.cover_letter.signature or c.name]
        )  # fmt: skip
        report, _page = await autofiller.open(
            job.url,
            applicant,
            pick(bundle.files.cv),
            pick(bundle.files.cover_letter),
            letter,
        )
        if report.filled or report.attached:
            await asyncio.to_thread(self.mark_autofilled, application_id)
        return report

    def mark_autofilled(self, application_id: int) -> None:
        with self._sessions.begin() as session:
            app = session.get(Application, application_id)
            if app is not None:
                app.method = ApplyMethod.AUTOFILL
