from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

from offerbound.commands.registry import CommandContext, CommandSpec

if TYPE_CHECKING:
    from offerbound.services.runtime import Runtime
    from offerbound.services.tasks import TaskContext


class CommandStarted(BaseModel):
    task_id: str


async def run_command(runtime: Runtime, spec: CommandSpec, params: dict[str, Any]) -> Any:
    """Validate params, then run inline (quick commands) or on the task runner (background).
    Background commands return CommandStarted with the task id to follow over SSE."""
    parsed = spec.params.model_validate(params)
    if not spec.background:
        return await spec.handler(CommandContext(runtime), parsed)

    async def as_task(task: TaskContext) -> Any:
        return await spec.handler(CommandContext(runtime, task), parsed)

    task_id = await runtime.tasks.submit(spec.name, as_task, parsed.model_dump(mode="json"))
    return CommandStarted(task_id=task_id)
