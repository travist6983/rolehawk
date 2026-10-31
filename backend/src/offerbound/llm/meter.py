"""Cost tracking: every call is logged to `llm_calls`; the optional monthly cap is enforced
before each call and checked against estimates before batch jobs."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from offerbound.db.models import LLMCall
from offerbound.llm import models
from offerbound.llm.errors import SpendCapExceededError
from offerbound.llm.types import Usage


def estimate_tokens(text: str) -> int:
    """Rough, deliberately high token estimate (~3 chars/token) for pre-run cost estimates."""
    return max(1, math.ceil(len(text) / 3))


def month_start(now: datetime) -> datetime:
    """Months are calendar months in UTC."""
    now = now.astimezone(UTC)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


@dataclass(frozen=True)
class Estimate:
    model: str
    calls: int
    input_tokens: int
    output_tokens: int
    cost_usd: float
    month_to_date_usd: float
    cap_usd: float | None

    @property
    def exceeds_cap(self) -> bool:
        return self.cap_usd is not None and self.month_to_date_usd + self.cost_usd > self.cap_usd


class SpendMeter:
    def __init__(self, sessions: sessionmaker[Session]) -> None:
        self._sessions = sessions

    def record(
        self,
        *,
        command: str,
        provider: str,
        model: str,
        usage: Usage,
        task_id: str | None = None,
    ) -> float:
        cost = models.cost_usd(model, usage)
        with self._sessions.begin() as session:
            session.add(
                LLMCall(
                    command=command,
                    provider=provider,
                    model=model,
                    input_tokens=usage.input_tokens,
                    output_tokens=usage.output_tokens,
                    cache_read_tokens=usage.cache_read_tokens,
                    cache_write_tokens=usage.cache_write_tokens,
                    cost_usd=cost,
                    task_id=task_id,
                )
            )
        return cost

    def month_to_date(self, now: datetime | None = None) -> float:
        start = month_start(now or datetime.now(UTC))
        with self._sessions() as session:
            total = session.scalar(
                select(func.coalesce(func.sum(LLMCall.cost_usd), 0.0)).where(
                    LLMCall.created_at >= start
                )
            )
        return round(float(total or 0.0), 6)

    def check_cap(self, cap_usd: float | None, upcoming_usd: float = 0.0) -> None:
        if cap_usd is None:
            return
        spent = self.month_to_date()
        if spent >= cap_usd or (upcoming_usd and spent + upcoming_usd > cap_usd):
            raise SpendCapExceededError(spent, cap_usd)

    def estimate(
        self,
        *,
        model: str,
        input_tokens: int,
        output_tokens: int,
        calls: int,
        cap_usd: float | None,
    ) -> Estimate:
        per_call = models.cost_usd(
            model, Usage(input_tokens=input_tokens, output_tokens=output_tokens)
        )
        return Estimate(
            model=model,
            calls=calls,
            input_tokens=input_tokens * calls,
            output_tokens=output_tokens * calls,
            cost_usd=round(per_call * calls, 4),
            month_to_date_usd=self.month_to_date(),
            cap_usd=cap_usd,
        )
