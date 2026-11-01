"""Build fit scores for tests: every part set to the same value, so the overall score is it."""

from __future__ import annotations

from rolehawk.fit.rubric import Gate, GateVerdict, JobFit


def fit_of(
    job_id: int,
    score: int,
    reasons: list[str] | None = None,
    gaps: list[str] | None = None,
    eligibility: GateVerdict = "pass",
    language: GateVerdict = "pass",
    deal_breaker: str = "",
) -> JobFit:
    return JobFit(
        job_id=job_id,
        eligibility=Gate(verdict=eligibility),
        language=Gate(verdict=language),
        experience=score,
        skills=score,
        career=score,
        logistics=score,
        deal_breaker=deal_breaker,
        reasons=reasons or [],
        must_have_gaps=gaps or [],
    )


def fit_json(job_id: int, score: int, **extra: object) -> dict[str, object]:
    return {**fit_of(job_id, score).model_dump(), **extra}
