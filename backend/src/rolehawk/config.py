"""Non-secret settings from <data>/config.toml, overridable by ROLEHAWK_* env vars.

Every section forbids unknown keys, so a secret pasted into config.toml fails loudly
instead of being stored in plain text. Secrets belong in the keychain (see keychain.py).
"""

from __future__ import annotations

import tomllib
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

import tomlkit
from pydantic import BaseModel, ConfigDict, Field
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict


class ProviderKind(StrEnum):
    # The in-app provider. Claude Code users run commands through skills/ instead: Anthropic
    # doesn't allow third-party apps to offer claude.ai login (see docs/SPEC.md decision log).
    ANTHROPIC_API = "anthropic_api"


class _Section(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LLMSettings(_Section):
    provider: ProviderKind = ProviderKind.ANTHROPIC_API
    model: str | None = None  # None means the catalog default (rolehawk.llm.models)
    smart_routing: bool = True
    monthly_cap_usd: float | None = Field(default=None, ge=0)


class SearchSettings(_Section):
    country: str = Field(default="US", min_length=2, max_length=2)
    fit_threshold: int = Field(default=60, ge=0, le=100)


class ServerSettings(_Section):
    port: int = Field(default=8765, ge=1024, le=65535)


class ChatSettings(_Section):
    retention_days: int = Field(default=30, ge=1)


class DocumentSettings(_Section):
    cv_template: str = Field(default="classic", pattern=r"^[a-z0-9-]{1,40}$")
    cover_template: str = Field(default="classic-letter", pattern=r"^[a-z0-9-]{1,40}$")
    paper: Literal["letter", "a4"] | None = None  # None: from the search country


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="ROLEHAWK_", env_nested_delimiter="__", extra="forbid"
    )

    llm: LLMSettings = Field(default_factory=LLMSettings)
    search: SearchSettings = Field(default_factory=SearchSettings)
    server: ServerSettings = Field(default_factory=ServerSettings)
    chat: ChatSettings = Field(default_factory=ChatSettings)
    documents: DocumentSettings = Field(default_factory=DocumentSettings)

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        # Env vars override values passed in from config.toml; no .env or secret-file sources.
        return (env_settings, init_settings)


DEFAULT_CONFIG = """\
# RoleHawk settings. Secrets (API keys, passwords, tokens) never go here:
# they are stored in your operating system's keychain from the Settings screen.

[llm]
provider = "anthropic_api"
# model = "claude-opus-5-5"    # set from Settings; unset uses the recommended default
smart_routing = true
# monthly_cap_usd = 20

[search]
country = "US"
fit_threshold = 60

[server]
port = 8765

[chat]
retention_days = 30

[documents]
cv_template = "classic"
cover_template = "classic-letter"
# paper = "a4"                 # unset: Letter in the US, Canada, Mexico...; A4 elsewhere
"""


def load_settings(config_file: Path) -> Settings:
    data = tomllib.loads(config_file.read_text(encoding="utf-8")) if config_file.exists() else {}
    return Settings(**data)


def update_settings(config_file: Path, section: str, values: dict[str, Any]) -> Settings:
    """Merge `values` into one [section] of config.toml, keeping the user's comments and
    formatting. A None value removes the key. Validates before writing."""
    text = config_file.read_text(encoding="utf-8") if config_file.exists() else DEFAULT_CONFIG
    document = tomlkit.parse(text)
    table = document.get(section)
    if table is None:
        table = tomlkit.table()
        document[section] = table
    for key, value in values.items():
        if value is None:
            table.pop(key, None)
        else:
            table[key] = value
    validated = Settings(**document.unwrap())
    tmp = config_file.with_suffix(".toml.tmp")
    tmp.write_text(tomlkit.dumps(document), encoding="utf-8")
    tmp.replace(config_file)
    return validated


def write_default_config(config_file: Path) -> bool:
    """Write the commented default config if none exists. Returns True if written."""
    if config_file.exists():
        return False
    config_file.write_text(DEFAULT_CONFIG, encoding="utf-8")
    return True
