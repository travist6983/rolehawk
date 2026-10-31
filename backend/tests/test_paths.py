from pathlib import Path

import pytest

from offerbound.paths import DataPaths, resolve_data_root


@pytest.mark.parametrize("platform", ["darwin", "linux"])
def test_unix_defaults_to_home_folder(platform: str) -> None:
    home = Path("/home/ada")
    assert resolve_data_root(env={}, platform=platform, home=home) == home / "Offerbound"


def test_windows_uses_userprofile() -> None:
    env = {"USERPROFILE": r"C:\Users\Ada"}
    root = resolve_data_root(env=env, platform="win32", home=Path("/ignored"))
    assert root == Path(r"C:\Users\Ada") / "Offerbound"


def test_windows_without_userprofile_falls_back_to_home() -> None:
    home = Path("/fallback")
    assert resolve_data_root(env={}, platform="win32", home=home) == home / "Offerbound"


@pytest.mark.parametrize("platform", ["darwin", "linux", "win32"])
def test_env_override_wins_everywhere(platform: str, tmp_path: Path) -> None:
    env = {"OFFERBOUND_HOME": str(tmp_path / "custom"), "USERPROFILE": r"C:\Users\Ada"}
    assert resolve_data_root(env=env, platform=platform) == tmp_path / "custom"


def test_blank_override_is_ignored() -> None:
    home = Path("/home/ada")
    assert resolve_data_root(env={"OFFERBOUND_HOME": "  "}, platform="linux", home=home) == (
        home / "Offerbound"
    )


def test_override_expands_user() -> None:
    root = resolve_data_root(env={"OFFERBOUND_HOME": "~/ob"}, platform="linux")
    assert root == Path.home() / "ob"


def test_ensure_creates_layout_idempotently(tmp_path: Path) -> None:
    paths = DataPaths(tmp_path / "Offerbound")
    paths.ensure()
    (paths.memory / "profile.md").write_text("keep me", encoding="utf-8")
    paths.ensure()
    for directory in paths.directories():
        assert directory.is_dir()
    assert (paths.memory / "profile.md").read_text(encoding="utf-8") == "keep me"
    assert paths.db.name == "offerbound.db"
