"""/add-portal commands. They fetch URLs the user gives, so they're for the Sources screen
and skills only (chat_allowed=False): a chat can't be talked into fetching for anyone."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from offerbound.commands.registry import CommandContext, CommandRegistry, CommandSpec
from offerbound.portals.custom.definition import PortalDefinition


class UrlParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    url: str = Field(max_length=2_000)
    name: str | None = Field(default=None, max_length=80)


class DefinitionParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    definition: PortalDefinition


class RemoveParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,40}$")


async def _inspect(ctx: CommandContext, params: UrlParams) -> dict[str, Any]:
    return (await ctx.runtime.add_portal.inspect(params.url)).model_dump(mode="json")


async def _draft(ctx: CommandContext, params: UrlParams) -> dict[str, Any]:
    candidate = await ctx.runtime.add_portal.draft(params.url, params.name)
    return candidate.model_dump(mode="json")


async def _test(ctx: CommandContext, params: DefinitionParams) -> dict[str, Any]:
    return (await ctx.runtime.add_portal.test(params.definition)).model_dump(mode="json")


async def _add(ctx: CommandContext, params: DefinitionParams) -> dict[str, Any]:
    result = await ctx.runtime.add_portal.add(params.definition)
    return {"added": params.definition.id, "jobs_in_test": result.count}


async def _remove(ctx: CommandContext, params: RemoveParams) -> dict[str, Any]:
    return {"removed": ctx.runtime.add_portal.remove(params.id)}


def register_add_portal(registry: CommandRegistry) -> None:
    registry.register(
        CommandSpec(
            "portal-inspect",
            "Look at a careers URL and find how to read its jobs: a known ATS, RSS, JSON-LD "
            "JobPosting data, or a JSON list.",
            _inspect,
            UrlParams,
            untrusted_output=True,
            chat_allowed=False,
        )
    )
    registry.register(
        CommandSpec(
            "portal-draft",
            "Ask Claude to propose a definition (JSON API or CSS selectors) for a careers "
            "page that detection couldn't read.",
            _draft,
            UrlParams,
            read_only=False,
            untrusted_output=True,
            chat_allowed=False,
        )
    )
    registry.register(
        CommandSpec(
            "portal-test",
            "Test-run a custom source definition in the sandbox: job count, 5 samples, and "
            "the plugin file it would create. Needs at least 3 jobs to pass.",
            _test,
            DefinitionParams,
            untrusted_output=True,
            chat_allowed=False,
        )
    )
    registry.register(
        CommandSpec(
            "portal-add",
            "Save and enable a custom source (it's tested again first).",
            _add,
            DefinitionParams,
            read_only=False,
            chat_allowed=False,
        )
    )
    registry.register(
        CommandSpec(
            "portal-remove",
            "Remove a custom source and the jobs it found (jobs you applied to stay).",
            _remove,
            RemoveParams,
            read_only=False,
            chat_allowed=False,
        )
    )
