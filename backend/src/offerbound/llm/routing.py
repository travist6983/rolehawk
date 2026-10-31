"""Model routing (docs/SPEC.md decision log, "Models").

The user picks one model. With smart routing on (the default), cheap high-volume tasks
(ranking, extraction) use the small model and everything else uses the chosen model. With it
off, every task uses the chosen model.
"""

from __future__ import annotations

from dataclasses import dataclass

from offerbound.config import LLMSettings
from offerbound.llm import models
from offerbound.llm.types import Effort, Task


@dataclass(frozen=True)
class TaskProfile:
    small: bool
    effort: Effort
    max_tokens: int


TASK_PROFILES: dict[Task, TaskProfile] = {
    Task.RANK: TaskProfile(small=True, effort="low", max_tokens=16000),
    Task.EXTRACT: TaskProfile(small=True, effort="low", max_tokens=8000),
    Task.WRITE: TaskProfile(small=False, effort="high", max_tokens=16000),
    Task.REVIEW: TaskProfile(small=False, effort="high", max_tokens=16000),
    Task.CHAT: TaskProfile(small=False, effort="medium", max_tokens=16000),
}


@dataclass(frozen=True)
class Route:
    task: Task
    model: str
    effort: Effort | None
    max_tokens: int


def chosen_model(settings: LLMSettings) -> str:
    return settings.model or models.DEFAULT_MODEL


def route(task: Task, settings: LLMSettings) -> Route:
    profile = TASK_PROFILES[task]
    model = (
        models.SMALL_MODEL if settings.smart_routing and profile.small else chosen_model(settings)
    )
    effort = profile.effort if models.supports_effort(model) else None
    return Route(task=task, model=model, effort=effort, max_tokens=profile.max_tokens)


def route_table(settings: LLMSettings) -> dict[Task, Route]:
    return {task: route(task, settings) for task in Task}
