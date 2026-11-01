"""What a typical month of RoleHawk costs on the Claude API, priced from the model catalog.

Shown on Connect Claude so people know what they're signing up for before they add credit.
The workloads are assumptions kept in one place. The per-call token sizes are generous
averages of the app's real requests, rounded up so the estimate errs high:

- Ranking sends 20 jobs per call (`fit.ranker.BATCH_SIZE`), each posting up to 5,000
  characters, and gets about 260 output tokens per job (`OUTPUT_TOKENS_PER_JOB`).
- /apply writes twice (draft, then one automatic revision) and reviews once. Output budgets
  include thinking at high effort, so they sit above the 3,000/1,000 the apply plan assumes.
- A chat message carries the system prompt, memory and recent history.

Each call is priced on its own so per-call rules (Haiku's long-prompt tier) apply correctly.
"""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel

from rolehawk.config import LLMSettings
from rolehawk.llm import models
from rolehawk.llm.routing import route
from rolehawk.llm.types import Task, Usage

WEEKS_PER_MONTH = 52 / 12
RANK_BATCH = 20


@dataclass(frozen=True)
class Workload:
    """Work done in one week."""

    jobs_ranked: int
    applications: int
    chat_messages: int


ACTIVE = Workload(jobs_ranked=200, applications=10, chat_messages=20)
LIGHT = Workload(jobs_ranked=50, applications=2, chat_messages=5)

# Tokens for one call of each kind.
RANK_CALL = Usage(input_tokens=40_000, output_tokens=RANK_BATCH * 260)
WRITE_CALL = Usage(input_tokens=8_000, output_tokens=4_000)
REVIEW_CALL = Usage(input_tokens=11_000, output_tokens=2_000)
CHAT_CALL = Usage(input_tokens=8_000, output_tokens=1_000)
WRITE_CALLS_PER_APPLICATION = 2


class WorkloadView(BaseModel):
    jobs_ranked_per_week: int
    applications_per_week: int
    chat_messages_per_week: int
    monthly_usd: float


class TypicalCost(BaseModel):
    active: WorkloadView
    light: WorkloadView
    writing_model: str
    ranking_model: str


def _label(model_id: str) -> str:
    info = models.get(model_id)
    return info.label if info else model_id


def weekly_cost(workload: Workload, settings: LLMSettings) -> float:
    def price(task: Task, call: Usage, calls: float) -> float:
        return models.cost_usd(route(task, settings).model, call) * calls

    return (
        price(Task.RANK, RANK_CALL, workload.jobs_ranked / RANK_BATCH)
        + price(Task.WRITE, WRITE_CALL, workload.applications * WRITE_CALLS_PER_APPLICATION)
        + price(Task.REVIEW, REVIEW_CALL, workload.applications)
        + price(Task.CHAT, CHAT_CALL, workload.chat_messages)
    )


def _view(workload: Workload, settings: LLMSettings) -> WorkloadView:
    return WorkloadView(
        jobs_ranked_per_week=workload.jobs_ranked,
        applications_per_week=workload.applications,
        chat_messages_per_week=workload.chat_messages,
        monthly_usd=round(weekly_cost(workload, settings) * WEEKS_PER_MONTH, 2),
    )


def typical_cost(settings: LLMSettings) -> TypicalCost:
    """Monthly cost of an active and a light search with the user's current model choices."""
    return TypicalCost(
        active=_view(ACTIVE, settings),
        light=_view(LIGHT, settings),
        writing_model=_label(route(Task.WRITE, settings).model),
        ranking_model=_label(route(Task.RANK, settings).model),
    )
