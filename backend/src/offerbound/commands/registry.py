from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:
    from offerbound.services.runtime import Runtime
    from offerbound.services.tasks import TaskContext


class NoParams(BaseModel):
    model_config = ConfigDict(extra="forbid")


@dataclass(frozen=True)
class CommandContext:
    runtime: Runtime
    task: TaskContext | None = None  # set when running as a background task

    async def progress(self, fraction: float | None = None, message: str | None = None) -> None:
        if self.task is not None:
            await self.task.progress(fraction, message)


Handler = Callable[[CommandContext, Any], Awaitable[Any]]


@dataclass(frozen=True)
class CommandSpec:
    name: str
    description: str
    handler: Handler
    params: type[BaseModel] = NoParams
    read_only: bool = True  # chat may run read-only commands without asking
    background: bool = False  # long-running: runs on the task runner with progress
    release: str = "v1.0"
    # False for commands that read local files or are meant for skills/the UI only; chat's
    # run_command neither lists nor runs them.
    chat_allowed: bool = True


class UnknownCommandError(LookupError):
    pass


class CommandRegistry:
    def __init__(self) -> None:
        self._commands: dict[str, CommandSpec] = {}

    def register(self, spec: CommandSpec) -> CommandSpec:
        if spec.name in self._commands:
            raise ValueError(f"command {spec.name!r} already registered")
        self._commands[spec.name] = spec
        return spec

    def get(self, name: str) -> CommandSpec:
        try:
            return self._commands[name.lstrip("/")]
        except KeyError:
            raise UnknownCommandError(name) from None

    def all(self) -> list[CommandSpec]:
        return sorted(self._commands.values(), key=lambda c: c.name)
