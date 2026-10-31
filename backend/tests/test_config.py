from pathlib import Path

import pytest
from pydantic import ValidationError

from offerbound.config import ProviderKind, load_settings, update_settings, write_default_config


def test_defaults_when_file_missing(tmp_path: Path) -> None:
    settings = load_settings(tmp_path / "config.toml")
    assert settings.server.port == 8765
    assert settings.llm.smart_routing is True
    assert settings.search.fit_threshold == 60


def test_default_file_round_trips(tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    assert write_default_config(config) is True
    assert write_default_config(config) is False  # never overwrites
    assert load_settings(config).search.country == "US"


def test_values_from_file(tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    config.write_text(
        '[llm]\nmodel = "claude-sonnet-5-5"\nmonthly_cap_usd = 15\n', encoding="utf-8"
    )
    settings = load_settings(config)
    assert settings.llm.provider is ProviderKind.ANTHROPIC_API
    assert settings.llm.model == "claude-sonnet-5-5"
    assert settings.llm.monthly_cap_usd == 15


def test_env_overrides_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = tmp_path / "config.toml"
    config.write_text("[server]\nport = 9000\n", encoding="utf-8")
    monkeypatch.setenv("OFFERBOUND_SERVER__PORT", "9100")
    assert load_settings(config).server.port == 9100


def test_unrelated_offerbound_env_vars_are_ignored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OFFERBOUND_SESSION_TOKEN", "x")
    monkeypatch.setenv("OFFERBOUND_DEV_ORIGINS", "http://127.0.0.1:5173")
    assert load_settings(tmp_path / "config.toml").server.port == 8765


@pytest.mark.parametrize(
    "body",
    ['[llm]\napi_key = "sk-ant-oops"\n', 'anthropic_api_key = "sk-ant-oops"\n'],
)
def test_secrets_in_config_are_rejected(tmp_path: Path, body: str) -> None:
    config = tmp_path / "config.toml"
    config.write_text(body, encoding="utf-8")
    with pytest.raises(ValidationError):
        load_settings(config)


def test_invalid_values_rejected(tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    config.write_text("[search]\nfit_threshold = 150\n", encoding="utf-8")
    with pytest.raises(ValidationError):
        load_settings(config)


def test_update_settings_preserves_comments_and_validates(tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    write_default_config(config)
    settings = update_settings(
        config, "llm", {"model": "claude-haiku-5-5", "monthly_cap_usd": 12.5}
    )
    assert settings.llm.model == "claude-haiku-5-5"
    text = config.read_text(encoding="utf-8")
    assert "Secrets (API keys" in text  # user-facing comments survive
    assert load_settings(config).llm.monthly_cap_usd == 12.5

    update_settings(config, "llm", {"monthly_cap_usd": None})
    assert load_settings(config).llm.monthly_cap_usd is None

    with pytest.raises(ValidationError):
        update_settings(config, "search", {"fit_threshold": 500})
    assert load_settings(config).search.fit_threshold == 60  # invalid write left file intact
