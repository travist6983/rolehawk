"""Chat tools. Each declares whether it is read-only: once a turn has processed third-party
text (job postings, pipeline rows), only read-only tools may run for the rest of that turn
(docs/SPEC.md "Prompt injection")."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from rolehawk.chat import pipeline_query
from rolehawk.commands.registry import UnknownCommandError
from rolehawk.commands.runner import CommandStarted, run_command
from rolehawk.llm.prompting import untrusted
from rolehawk.llm.schema import strict_json_schema
from rolehawk.llm.types import ToolDef
from rolehawk.memory.proposals import ProposalIn

if TYPE_CHECKING:
    from rolehawk.services.runtime import Runtime

TAINTED_BLOCK = (
    "Blocked: this turn already processed third-party text (job postings or pipeline data), "
    "so only read-only tools can run. Tell the user what you wanted to do and ask them to "
    "confirm in a new message."
)


@dataclass
class ToolContext:
    runtime: Runtime
    session_id: str
    tainted: bool = False


@dataclass(frozen=True)
class ToolOutcome:
    content: str
    is_error: bool = False
    cards: list[dict[str, Any]] = field(default_factory=list)
    untrusted: bool = False  # the content came from third parties


ToolHandler = Callable[[ToolContext, Any], Awaitable[ToolOutcome]]


@dataclass(frozen=True)
class ChatTool:
    name: str
    description: str
    input_model: type[BaseModel]
    read_only: bool
    handler: ToolHandler

    def definition(self) -> ToolDef:
        return ToolDef(self.name, self.description, strict_json_schema(self.input_model))


# --- query_pipeline ---------------------------------------------------------------------


class QueryPipelineInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sql: str = Field(description="One SQLite SELECT over the v_* views. Add LIMIT for lists.")


async def _query_pipeline(ctx: ToolContext, params: QueryPipelineInput) -> ToolOutcome:
    try:
        result = await asyncio.to_thread(pipeline_query.run_query, ctx.runtime.paths.db, params.sql)
    except pipeline_query.QueryRejectedError as exc:
        return ToolOutcome(f"Query rejected: {exc}", is_error=True)
    payload = json.dumps(result.to_json(), default=str)
    return ToolOutcome(untrusted("pipeline_query", payload), untrusted=True)


# --- run_command ------------------------------------------------------------------------


class RunCommandInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    command: str = Field(description="Command name without the slash, e.g. 'spend'.")
    params_json: str = Field(description='JSON object of parameters; "{}" for none.')


async def _run_command(ctx: ToolContext, params: RunCommandInput) -> ToolOutcome:
    try:
        spec = ctx.runtime.commands.get(params.command)
    except UnknownCommandError:
        spec = None
    if spec is None or not spec.chat_allowed:
        names = ", ".join(c.name for c in ctx.runtime.commands.all() if c.chat_allowed)
        return ToolOutcome(f"Unknown command {params.command!r}. Available: {names}", True)
    try:
        args = json.loads(params.params_json or "{}")
        if not isinstance(args, dict):
            raise ValueError("params_json must be a JSON object")
        spec.params.model_validate(args)
    except (ValueError, ValidationError) as exc:
        return ToolOutcome(f"Invalid parameters for {spec.name}: {exc}", is_error=True)

    if not spec.read_only:
        card = {
            "type": "command_proposal",
            "command": spec.name,
            "params": args,
            "description": spec.description,
        }
        return ToolOutcome(
            "Shown to the user as a confirmation card; it runs only if they click Run.",
            cards=[card],
        )
    result = await run_command(ctx.runtime, spec, args)
    if isinstance(result, CommandStarted):
        card = {"type": "task", "task_id": result.task_id, "command": spec.name}
        return ToolOutcome(f"Started {spec.name} as task {result.task_id}.", cards=[card])
    payload = json.dumps(result, default=str)
    if spec.untrusted_output:
        return ToolOutcome(untrusted(f"command:{spec.name}", payload), untrusted=True)
    return ToolOutcome(payload)


# --- propose_memory_update --------------------------------------------------------------


async def _propose_memory_update(ctx: ToolContext, params: ProposalIn) -> ToolOutcome:
    view = await asyncio.to_thread(ctx.runtime.memory.propose, params, "chat", ctx.session_id)
    card = {"type": "memory_proposal", "proposal": view.model_dump(mode="json")}
    return ToolOutcome(
        "Proposed. The user will accept or reject it; memory is unchanged until then.",
        cards=[card],
    )


def chat_tools() -> list[ChatTool]:
    return [
        ChatTool(
            "query_pipeline",
            "Answer questions about the user's applications, jobs, stage history, interviews, "
            "and AI spend with read-only SQL. Never guess counts or dates; query them.\n"
            + pipeline_query.schema_description(),
            QueryPipelineInput,
            read_only=True,
            handler=_query_pipeline,
        ),
        ChatTool(
            "run_command",
            "Run a RoleHawk command. Read-only commands run immediately; commands that "
            "change data are shown to the user as a card they must confirm.",
            RunCommandInput,
            read_only=False,
            handler=_run_command,
        ),
        ChatTool(
            "propose_memory_update",
            "Propose an edit to the user's memory (profile.md, preferences.md, facts.md) "
            "when they state a durable fact about themselves. Only proposes: the user "
            "accepts or rejects it. Never propose facts they did not state.",
            ProposalIn,
            read_only=False,
            handler=_propose_memory_update,
        ),
    ]


async def execute(tool: ChatTool, ctx: ToolContext, raw_input: dict[str, Any]) -> ToolOutcome:
    if ctx.tainted and not tool.read_only:
        return ToolOutcome(TAINTED_BLOCK, is_error=True)
    try:
        params = tool.input_model.model_validate(raw_input)
    except ValidationError as exc:
        return ToolOutcome(f"Invalid input for {tool.name}: {exc}", is_error=True)
    return await tool.handler(ctx, params)
