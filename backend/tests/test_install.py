"""The installed app: layout, release download and unpacking, and `rolehawk update`.
No network: release assets are served by an httpx2 MockTransport."""

from __future__ import annotations

import hashlib
import io
import json
import os
import stat
import zipfile
from collections.abc import Sequence
from pathlib import Path

import httpx2
import pytest

from rolehawk.cli import main
from rolehawk.install.layout import InstallLayout, browser_hint, parse_version, running_from
from rolehawk.install.release import (
    ReleaseError,
    ReleaseInfo,
    download,
    extract,
    fetch_info,
)
from rolehawk.install.skills import bundled_skills_dir, install_skills, released_skills
from rolehawk.install.update import UpdateError, Updater

BASE = "https://releases.test/latest/download"


def release_zip(version: str, extra: dict[str, bytes] | None = None, top: str = "") -> bytes:
    top = top or f"rolehawk-{version}"
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(f"{top}/VERSION", version)
        archive.writestr(f"{top}/backend/pyproject.toml", '[project]\nname = "rolehawk"\n')
        archive.writestr(f"{top}/frontend/dist/index.html", "<!doctype html>")
        for name, data in (extra or {}).items():
            archive.writestr(name, data)
    return buffer.getvalue()


class FakeReleases:
    def __init__(self, version: str, payload: bytes | None = None) -> None:
        self.payload = payload if payload is not None else release_zip(version)
        self.info = {
            "version": version,
            "sha256": hashlib.sha256(self.payload).hexdigest(),
            "size": len(self.payload),
        }
        self.requests: list[str] = []

    def handler(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(str(request.url))
        if str(request.url) == f"{BASE}/release.json":
            return httpx2.Response(200, json=self.info)
        if str(request.url) == f"{BASE}/rolehawk.zip":
            return httpx2.Response(200, content=self.payload)
        return httpx2.Response(404)

    def client(self) -> httpx2.Client:
        return httpx2.Client(transport=httpx2.MockTransport(self.handler))


# --- layout -------------------------------------------------------------------------------


def test_layout_pointer_and_paths(tmp_path: Path) -> None:
    layout = InstallLayout(tmp_path)
    assert layout.current_version() is None
    layout.set_current("0.2.0")
    assert layout.current_file.read_bytes() == b"0.2.0"  # no newline: cmd's `set /p`
    assert layout.current_version() == "0.2.0"
    layout.current_file.write_text("../../etc", encoding="utf-8")
    assert layout.current_version() is None  # never trusted as a path
    with pytest.raises(ValueError, match="release version"):
        layout.set_current("0.2.0; rm -rf ~")

    exe = layout.executable("0.2.0")
    assert exe.parts[-5:-2] == ("0.2.0", "backend", ".venv")
    assert exe.name == ("rolehawk.exe" if os.name == "nt" else "rolehawk")
    assert parse_version("1.10.0") > parse_version("1.9.9")


def test_running_from_knows_installed_releases(tmp_path: Path) -> None:
    assert running_from() is None  # these tests run from a source checkout
    assert browser_hint().startswith("uv run playwright install")

    app = tmp_path / "home" / "versions" / "0.3.1"
    module = app / "backend" / "src" / "rolehawk" / "install" / "layout.py"
    module.parent.mkdir(parents=True)
    module.touch()
    assert running_from(str(module)) is None  # no VERSION file: not a release
    (app / "VERSION").write_text("0.3.1", encoding="utf-8")
    found = running_from(str(module))
    assert found is not None
    assert (found[0].home, found[1]) == ((tmp_path / "home").resolve(), "0.3.1")


# --- release assets -----------------------------------------------------------------------


def test_download_checks_the_checksum(tmp_path: Path) -> None:
    releases = FakeReleases("0.2.0")
    with releases.client() as client:
        info = fetch_info(client, BASE)
        path = download(client, BASE, info, tmp_path)
        assert path.name == "rolehawk-0.2.0.zip"
        assert path.read_bytes() == releases.payload

        tampered = info.model_copy(update={"sha256": "0" * 64})
        with pytest.raises(ReleaseError, match="checksum"):
            download(client, BASE, tampered, tmp_path / "other")
    assert not list((tmp_path / "other").iterdir())  # partial file removed


def test_release_info_is_validated(tmp_path: Path) -> None:
    releases = FakeReleases("0.2.0")
    releases.info["version"] = "../../evil"
    with releases.client() as client, pytest.raises(ReleaseError, match="malformed"):
        fetch_info(client, BASE)


def test_extract_unpacks_the_top_folder(tmp_path: Path) -> None:
    zip_path = tmp_path / "r.zip"
    zip_path.write_bytes(release_zip("0.2.0", {"rolehawk-0.2.0/data/x.csv": b"slug\n"}))
    extract(zip_path, tmp_path / "out", "0.2.0")
    assert (tmp_path / "out" / "VERSION").read_text(encoding="utf-8") == "0.2.0"
    assert (tmp_path / "out" / "data" / "x.csv").is_file()
    with pytest.raises(ReleaseError, match="already exists"):
        extract(zip_path, tmp_path / "out", "0.2.0")
    with pytest.raises(ReleaseError, match=r"outside rolehawk-0\.2\.1"):
        extract(zip_path, tmp_path / "other", "0.2.1")
    mislabeled = tmp_path / "m.zip"
    mislabeled.write_bytes(release_zip("0.2.0", top="rolehawk-0.2.1"))
    with pytest.raises(ReleaseError, match="doesn't match"):
        extract(mislabeled, tmp_path / "other", "0.2.1")


@pytest.mark.parametrize(
    "name",
    [
        "rolehawk-0.2.0/../escape.txt",
        "/etc/rolehawk.txt",
        "rolehawk-0.2.0\\..\\escape.txt",
        "elsewhere/file.txt",
        "C:/Windows/file.txt",
    ],
)
def test_extract_refuses_paths_that_escape(tmp_path: Path, name: str) -> None:
    zip_path = tmp_path / "r.zip"
    zip_path.write_bytes(release_zip("0.2.0", {name: b"x"}))
    with pytest.raises(ReleaseError):
        extract(zip_path, tmp_path / "out", "0.2.0")
    assert not (tmp_path / "out").exists()
    assert not (tmp_path / "escape.txt").exists()


def test_extract_refuses_links(tmp_path: Path) -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("rolehawk-0.2.0/VERSION", "0.2.0")
        link = zipfile.ZipInfo("rolehawk-0.2.0/link")
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(link, "/etc/passwd")
    zip_path = tmp_path / "r.zip"
    zip_path.write_bytes(buffer.getvalue())
    with pytest.raises(ReleaseError, match="Links"):
        extract(zip_path, tmp_path / "out", "0.2.0")


# --- update -------------------------------------------------------------------------------


class Recorder:
    def __init__(self, fail_on: str | None = None) -> None:
        self.commands: list[list[str]] = []
        self.fail_on = fail_on

    def __call__(self, command: Sequence[str], cwd: Path) -> None:
        self.commands.append([Path(command[0]).name, *command[1:]])
        if self.fail_on and self.fail_on in command:
            raise RuntimeError(f"{self.fail_on} failed")


def installed(tmp_path: Path, *versions: str, current: str) -> InstallLayout:
    layout = InstallLayout(tmp_path / "home")
    for version in versions:
        (layout.app_dir(version) / "backend").mkdir(parents=True)
    layout.set_current(current)
    return layout


def updater(
    layout: InstallLayout,
    releases: FakeReleases,
    run: Recorder,
    *,
    running: bool = False,
    uv: str | None = "/bin/uv",
) -> Updater:
    return Updater(
        layout,
        releases.client(),
        BASE,
        uv=uv,
        backup=lambda: layout.home / "backup.zip",
        app_running=lambda: running,
        running_version=layout.current_version(),
        run=run,
        say=lambda _m: None,
    )


def test_update_installs_next_to_the_running_version(tmp_path: Path) -> None:
    layout = installed(tmp_path, "0.0.9", "0.1.0", current="0.1.0")
    run = Recorder()
    assert updater(layout, FakeReleases("0.2.0"), run).update() == "0.2.0"

    assert layout.current_version() == "0.2.0"
    assert (layout.app_dir("0.2.0") / "frontend" / "dist" / "index.html").is_file()
    exe = layout.executable("0.2.0").name
    assert run.commands == [
        ["uv", "sync", "--quiet", "--frozen", "--no-dev", "--python", "3.12"],
        [exe, "install-browser"],
        [exe, "db", "upgrade"],
    ]
    # The running version stays (Windows can't delete it); older ones go.
    assert sorted(p.name for p in layout.versions.iterdir()) == ["0.1.0", "0.2.0"]
    assert not list(layout.downloads.iterdir())


def test_update_is_a_no_op_when_current(tmp_path: Path) -> None:
    layout = installed(tmp_path, "0.2.0", current="0.2.0")
    releases = FakeReleases("0.2.0")
    run = Recorder()
    up = updater(layout, releases, run)
    status, _info = up.check()
    assert (status.current, status.latest, status.available) == ("0.2.0", "0.2.0", False)
    assert up.update() is None
    assert run.commands == []
    assert {r.rsplit("/", 1)[1] for r in releases.requests} == {"release.json"}  # no ZIP


def test_update_waits_for_the_app_to_close(tmp_path: Path) -> None:
    layout = installed(tmp_path, "0.1.0", current="0.1.0")
    releases = FakeReleases("0.2.0")
    with pytest.raises(UpdateError, match="running"):
        updater(layout, releases, Recorder(), running=True).update()
    assert releases.requests == [f"{BASE}/release.json"]
    with pytest.raises(UpdateError, match="uv"):
        updater(layout, releases, Recorder(), uv=None).update()


def test_a_failed_step_keeps_the_old_version(tmp_path: Path) -> None:
    layout = installed(tmp_path, "0.1.0", current="0.1.0")
    with pytest.raises(RuntimeError, match="sync failed"):
        updater(layout, FakeReleases("0.2.0"), Recorder(fail_on="sync")).update()
    assert layout.current_version() == "0.1.0"

    # Trying again replaces the half-installed folder.
    run = Recorder()
    assert updater(layout, FakeReleases("0.2.0"), run).update() == "0.2.0"
    assert layout.current_version() == "0.2.0"


def test_update_refuses_a_bad_download(tmp_path: Path) -> None:
    layout = installed(tmp_path, "0.1.0", current="0.1.0")
    evil = release_zip("0.2.0", {"rolehawk-0.2.0/../../outside.txt": b"x"})
    with pytest.raises(ReleaseError):
        updater(layout, FakeReleases("0.2.0", evil), Recorder()).update()
    assert layout.current_version() == "0.1.0"
    assert not layout.app_dir("0.2.0").exists()
    assert not (tmp_path / "outside.txt").exists()


def test_cli_update_needs_an_installed_copy(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["update"]) == 2
    assert "source checkout" in capsys.readouterr().out


def test_release_info_round_trips() -> None:
    info = ReleaseInfo(version="1.2.3", sha256="a" * 64, size=10)
    assert ReleaseInfo.model_validate_json(json.dumps(info.model_dump())) == info


# --- Claude Code skills -------------------------------------------------------------------


def test_only_shipped_skills_are_installed(tmp_path: Path) -> None:
    names = [name for name, _path in released_skills(bundled_skills_dir())]
    assert "rolehawk-setup" in names
    assert "rolehawk-add-portal" in names
    assert "rolehawk-gmail-sync" not in names  # v1.1: its commands don't exist yet

    dest = tmp_path / "skills"
    (dest / "someone-elses").mkdir(parents=True)
    installed = install_skills(bundled_skills_dir(), dest)
    assert sorted(f.name for f in installed) == sorted(names)
    assert (dest / "rolehawk-setup" / "SKILL.md").read_text(encoding="utf-8").startswith("---")
    assert (dest / "someone-elses").is_dir()  # other skills untouched
    assert install_skills(bundled_skills_dir(), dest) == installed  # safe to run again


def test_cli_install_skills_respects_claude_config_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude"))
    assert main(["install-skills"]) == 0
    assert (tmp_path / "claude" / "skills" / "rolehawk-rank" / "SKILL.md").is_file()
    assert "Restart Claude Code" in capsys.readouterr().out


def test_package_version_matches_pyproject() -> None:
    import tomllib

    from rolehawk import __version__

    pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    assert data["project"]["version"] == __version__
    parse_version(__version__)  # releases are plain X.Y.Z
