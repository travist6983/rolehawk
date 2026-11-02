"""The fit rubric. /rank and /apply both score with it, so a job's score means the same thing
everywhere (docs/SPEC.md: "/rank and /apply share one fit rubric so scores match").

Claude scores four parts and reads two gates; the overall score is computed here from the
parts, so it's explainable and consistent across batches. A failed gate or a deal breaker
caps it at 39."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from rolehawk.llm.prompting import TRUTHFULNESS_RULES, UNTRUSTED_RULES
from rolehawk.portals.text import parse_date

RUBRIC_VERSION = "2026-11-01.1"

# How much each part counts toward the overall score.
WEIGHTS: dict[str, float] = {"experience": 0.35, "skills": 0.30, "career": 0.20, "logistics": 0.15}
CAP = 39  # a failed gate or a deal breaker: "a poor match", whatever the parts say

FIT_RUBRIC = f"""You assess how well job postings fit one job seeker, using only their memory
(profile, preferences, facts) and the postings themselves.

First read two gates. Each gets a verdict and the posting's exact words as `quote` (empty
when the posting says nothing on it):

- eligibility: can they hold this job at all? Read the posting's citizenship, residency,
  work-permit, sponsorship, and security-clearance wording against their work authorization.
  fail: it requires something they lack (citizenship or permanent residency they don't have,
  a clearance, or "no sponsorship" when they need it). pass: nothing restricts them, or it
  explicitly welcomes their status. check: it's silent or unclear and their status could
  matter (they need sponsorship or aren't a citizen there). Silence is not permission, and a
  company-wide welcome isn't role-level permission.
- language: languages the role itself requires (not the language the ad is written in),
  against their languages and levels. fail: it requires a language they don't list at all.
  check: they list it, but the stated bar ("fluent", "native", "C1") plausibly exceeds their
  level; prefer check over pass when unsure, the person decides. pass: no requirement, or
  one they clearly meet.

Then score four parts from 0 to 100:
- experience (35%): role, seniority, and domain. Match the function of the work, not the
  literal title ("Data Consultant" and "Data Scientist" can be the same job).
- skills (30%): the posting's must-haves (skills, tools, years, degrees, certifications)
  against what the profile actually shows. Missing evidence is a gap; don't assume skills.
- career (20%): does it move them toward their target titles and goals, and is it mostly
  work that energizes them rather than work that drains them?
- logistics (15%): location or remote, salary against their floor, schedule and travel.

For each part: 90-100 fits fully; 75-89 small gaps; 50-74 one real gap; 25-49 several gaps
or adjacent rather than on target; 0-24 a mismatch. Be calibrated and consistent across
jobs: similar jobs get similar scores, and most jobs in a typical batch are not strong
matches. The overall score is the weighted average, capped at {CAP} by a failed gate or a
deal breaker.

`deal_breaker`: the deal breaker from their preferences this job hits, in their words, or
empty. Report it; don't lower the parts for it.

`deadline`: the application deadline the posting states, as YYYY-MM-DD, or empty. Only a
stated date ("apply by 15 November 2026"); never guess one from "ASAP" or the posting date.

Write to the job seeker, most important first:
- `reasons`: up to 3 short reasons it fits them, strengths only ("Your 6 years of React
  match their senior frontend role").
- `concerns`: up to 3 short reasons it might not fit them: a seniority or domain mismatch,
  a salary below their floor or not stated, location or schedule, work that drains them, or
  a direction away from their goals ("They want 8+ years leading teams; you show 3"). Don't
  repeat must_have_gaps. Empty when nothing stands out.
- `must_have_gaps`: required items the profile doesn't show, a few words each ("Kubernetes
  in production", "active Secret clearance"). Empty when there are none.

{TRUTHFULNESS_RULES}

{UNTRUSTED_RULES}"""

GateVerdict = Literal["pass", "check", "fail"]


class Gate(BaseModel):
    model_config = ConfigDict(json_schema_serialization_defaults_required=True)

    verdict: GateVerdict = Field(description="pass, check, or fail")
    quote: str = Field(default="", description="The posting's exact words; empty if silent")


class Breakdown(BaseModel):
    """The four parts of a fit score, 0 to 100 each."""

    experience: int
    skills: int
    career: int
    logistics: int

    def overall(self) -> int:
        parts = {
            "experience": self.experience,
            "skills": self.skills,
            "career": self.career,
            "logistics": self.logistics,
        }
        return round(sum(parts[name] * weight for name, weight in WEIGHTS.items()))


class JobFit(BaseModel):
    """One job's assessment. Kept free of numeric schema constraints (structured outputs
    don't enforce them); `clamped()` normalizes after parsing."""

    job_id: int = Field(description="The job's id, exactly as given")
    eligibility: Gate
    language: Gate
    experience: int = Field(description="0 to 100: role, seniority, and domain")
    skills: int = Field(description="0 to 100: the posting's must-haves")
    career: int = Field(description="0 to 100: their goals, and work that energizes them")
    logistics: int = Field(description="0 to 100: location or remote, salary, schedule")
    deal_breaker: str = Field(description="The deal breaker it hits, in their words; or empty")
    deadline: str = Field(default="", description="Stated deadline as YYYY-MM-DD, or empty")
    reasons: list[str] = Field(description="Up to 3 reasons it fits, strengths only")
    concerns: list[str] = Field(
        default_factory=list, description="Up to 3 reasons it might not fit; empty if none"
    )
    must_have_gaps: list[str] = Field(
        description="Required items the profile doesn't show; empty if none"
    )

    @property
    def breakdown(self) -> Breakdown:
        return Breakdown(
            experience=self.experience,
            skills=self.skills,
            career=self.career,
            logistics=self.logistics,
        )

    @property
    def capped(self) -> bool:
        failed = self.eligibility.verdict == "fail" or self.language.verdict == "fail"
        return failed or bool(self.deal_breaker.strip())

    @property
    def score(self) -> int:
        overall = self.breakdown.overall()
        return min(overall, CAP) if self.capped else overall

    def clamped(self) -> JobFit:
        def part(value: int) -> int:
            return max(0, min(100, value))

        def gate(g: Gate) -> Gate:
            return Gate(verdict=g.verdict, quote=" ".join(g.quote.split())[:300])

        return JobFit(
            job_id=self.job_id,
            eligibility=gate(self.eligibility),
            language=gate(self.language),
            experience=part(self.experience),
            skills=part(self.skills),
            career=part(self.career),
            logistics=part(self.logistics),
            deal_breaker=" ".join(self.deal_breaker.split())[:200],
            deadline=closes.isoformat() if (closes := parse_date(self.deadline)) else "",
            reasons=[r.strip() for r in self.reasons if r.strip()][:3],
            concerns=[c.strip() for c in self.concerns if c.strip()][:3],
            must_have_gaps=[g.strip() for g in self.must_have_gaps if g.strip()][:8],
        )


class FitBatch(BaseModel):
    jobs: list[JobFit]


class Gates(BaseModel):
    """What's stored with a score: the two gates and any deal breaker."""

    model_config = ConfigDict(json_schema_serialization_defaults_required=True)

    eligibility: Gate
    language: Gate
    deal_breaker: str = ""

    @classmethod
    def of(cls, fit: JobFit) -> Gates:
        return cls(
            eligibility=fit.eligibility, language=fit.language, deal_breaker=fit.deal_breaker
        )
