"""The fit rubric. /rank and /apply both score with it, so a job's score means the same thing
everywhere (docs/SPEC.md: "/rank and /apply share one fit rubric so scores match")."""

from __future__ import annotations

from pydantic import BaseModel, Field

from offerbound.llm.prompting import TRUTHFULNESS_RULES, UNTRUSTED_RULES

RUBRIC_VERSION = "2026-10-31"

FIT_RUBRIC = f"""You assess how well job postings fit one job seeker, using only their memory
(profile, preferences, facts) and the postings themselves.

Score each job from 0 to 100:
- 90-100: an excellent match. Meets every must-have requirement and fits their preferences
  (role, seniority, location or remote, salary). Apply right away.
- 80-89: a strong match. Meets the must-haves; at most minor gaps in nice-to-haves.
- 60-79: a plausible match. One must-have is missing or unclear, or one preference is off
  (for example a lower salary band or a different seniority). Worth a look.
- 40-59: a stretch. Several must-haves are missing, or the role is adjacent rather than the
  target.
- 0-39: a poor match. Wrong field or level, or it hits one of their deal breakers.

How to judge:
- Must-haves are what the posting says is required (years of experience, specific skills,
  degrees, certifications, clearances, languages, work authorization). Compare them with what
  the profile actually shows. Missing evidence counts as a gap; don't assume skills that aren't
  in the profile.
- Weigh role and seniority match most, then must-have skills, then domain, then logistics
  (location, remote, salary). A deal breaker from their preferences caps the score at 39.
- Be calibrated and consistent across jobs: similar jobs get similar scores. Most jobs in a
  typical batch are not strong matches.

For each job give:
- `reasons`: up to 3 short reasons, most important first, written to the job seeker
  ("Your 6 years of React match their senior frontend role"). Mix strengths and concerns.
- `must_have_gaps`: required items from the posting the profile doesn't show, in a few words
  each ("Kubernetes in production", "active Secret clearance"). Empty when there are none.

{TRUTHFULNESS_RULES}

{UNTRUSTED_RULES}"""


class JobFit(BaseModel):
    """One job's assessment. Kept free of numeric schema constraints (structured outputs
    don't enforce them); `clamped()` normalizes after parsing."""

    job_id: int = Field(description="The job's id, exactly as given")
    score: int = Field(description="0 to 100, per the rubric")
    reasons: list[str] = Field(description="Up to 3 short reasons, most important first")
    must_have_gaps: list[str] = Field(
        description="Required items the profile doesn't show; empty if none"
    )

    def clamped(self) -> JobFit:
        return JobFit(
            job_id=self.job_id,
            score=max(0, min(100, self.score)),
            reasons=[r.strip() for r in self.reasons if r.strip()][:3],
            must_have_gaps=[g.strip() for g in self.must_have_gaps if g.strip()][:8],
        )


class FitBatch(BaseModel):
    jobs: list[JobFit]
