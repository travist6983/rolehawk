"""Non-secret settings from <data>/config.toml, overridable by OFFERBOUND_* env vars.

Every section forbids unknown keys, so a secret pasted into config.toml fails loudly
instead of being stored in plain text. Secrets belong in the keychain (see keychain.py).
"""

from __future__ import annotations

import tomllib
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict


class ProviderKind(StrEnum):
    ANTHROPIC_API = "anthropic_api"
    CLAUDE_CODE = "claude_code"


class _Section(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LLMSettings(_Section):
    provider: ProviderKind | None = None
    model: str | None = None
    smart_routing: bool = True
    monthly_cap_usd: float | None = Field(default=None, ge=0)


class SearchSettings(_Section):
    country: str = Field(default="US", min_length=2, max_length=2)
    fit_threshold: int = Field(default=60, ge=0, le=100)


class ServerSettings(_Section):
    port: int = Field(default=8765, ge=1024, le=65535)


class ChatSettings(_Section):
    retention_days: int = Field(default=30, ge=1)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="OFFERBOUND_", env_nested_delimiter="__", extra="forbid"
    )

    llm: LLMSettings = Field(default_factory=LLMSettings)
    search: SearchSettings = Field(default_factory=SearchSettings)
    server: ServerSettings = Field(default_factory=ServerSettings)
    chat: ChatSettings = Field(default_factory=ChatSettings)

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
# Offerbound AI settings. Secrets (API keys, passwords, tokens) never go here:
# they are stored in your operating system's keychain from the Settings screen.

[llm]
# provider = "anthropic_api"   # or "claude_code"
# model = ""                   # set from Settings
smart_routing = true
# monthly_cap_usd = 20

[search]
country = "US"
fit_threshold = 60

[server]
port = 8765

[chat]
retention_days = 30
"""


def load_settings(config_file: Path) -> Settings:
    data = tomllib.loads(config_file.read_text(encoding="utf-8")) if config_file.exists() else {}
    return Settings(**data)


def write_default_config(config_file: Path) -> bool:
    """Write the commented default config if none exists. Returns True if written."""
    if config_file.exists():
        return False
    config_file.write_text(DEFAULT_CONFIG, encoding="utf-8")
    return True
