from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, ValidationError

from offerbound.api.deps import RuntimeDep
from offerbound.commands.registry import UnknownCommandError
from offerbound.commands.runner import CommandStarted, run_command

router = APIRouter(prefix="/api/commands", tags=["commands"])


class CommandInfo(BaseModel):
    name: str
    description: str
    read_only: bool
    background: bool
    release: str
    chat_allowed: bool
    params_schema: dict[str, Any]


class CommandIn(BaseModel):
    params: dict[str, Any] = Field(default_factory=dict)


class CommandOut(BaseModel):
    task_id: str | None = None
    result: Any = None


@router.get("")
def list_commands(runtime: RuntimeDep) -> list[CommandInfo]:
    return [
        CommandInfo(
            name=c.name,
            description=c.description,
            read_only=c.read_only,
            background=c.background,
            release=c.release,
            chat_allowed=c.chat_allowed,
            params_schema=c.params.model_json_schema(),
        )
        for c in runtime.commands.all()
    ]


@router.post("/{name}")
async def post_command(name: str, runtime: RuntimeDep, body: CommandIn | None = None) -> CommandOut:
    """Runs quick commands inline; background commands return a task_id to follow over SSE."""
    try:
        spec = runtime.commands.get(name)
    except UnknownCommandError:
        raise HTTPException(status_code=404, detail=f"Unknown command {name!r}") from None
    try:
        result = await run_command(runtime, spec, (body or CommandIn()).params)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors(include_url=False)) from None
    if isinstance(result, CommandStarted):
        return CommandOut(task_id=result.task_id)
    return CommandOut(result=result)
