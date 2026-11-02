import http.server
import json
import os
import socket
import threading
from pathlib import Path

import pytest

from rolehawk import cli
from rolehawk.paths import DataPaths


def test_doctor_json_on_fresh_install(capsys: pytest.CaptureFixture[str]) -> None:
    DataPaths.default().ensure()
    code = cli.main(["doctor", "--json"])
    checks = {c["name"]: c for c in json.loads(capsys.readouterr().out)}
    assert checks["sqlite_fts5"]["ok"] is True
    assert checks["database"]["ok"] is True
    assert code == (0 if all(c["ok"] for c in checks.values()) else 1)


def test_doctor_flags_a_missing_autofill_browser(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from rolehawk.services.doctor import _chromium

    # An empty browsers folder: neither the headless shell (PDFs) nor full Chromium.
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(tmp_path))
    checks = {check.name: check for check in _chromium()}
    assert checks["chromium"].ok is False
    assert checks["autofill_browser"].ok is False
    assert "uv run playwright install chromium (from backend/)" in checks["autofill_browser"].detail


def test_db_upgrade_then_current(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["db", "upgrade"]) == 0
    capsys.readouterr()
    assert cli.main(["db", "current"]) == 0
    out = capsys.readouterr().out
    revision = out.split()[0]
    assert revision != "None"
    assert f"(head {revision})" in out


def test_backup_command(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["backup"]) == 0
    assert capsys.readouterr().out.strip().endswith(".zip")


def test_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        cli.main(["--version"])
    assert "rolehawk" in capsys.readouterr().out


def test_run_context_json(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["run", "context", "--param", "for_command=apply", "--json"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["pack"]["command"] == "apply"
    assert "<profile>" in output["memory_text"]


def test_run_background_command_waits_for_task(capsys: pytest.CaptureFixture[str]) -> None:
    code = cli.main(["run", "selftest", "--params-json", '{"steps": 2, "delay_s": 0}', "--json"])
    captured = capsys.readouterr()
    assert code == 0
    assert json.loads(captured.out)["status"] == "succeeded"
    assert "Step 2 of 2" in captured.err


def test_run_unknown_and_invalid(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["run", "nope"]) == 2
    assert "unknown command" in capsys.readouterr().err
    assert cli.main(["run", "selftest", "--param", "steps=0"]) == 2
    assert "invalid parameters" in capsys.readouterr().err


def test_llm_status_without_key(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["llm", "status"]) == 0
    status = json.loads(capsys.readouterr().out)
    assert status["configured"] is False
    assert status["key_source"] == "none"


def test_run_propose_creates_pending_proposal(capsys: pytest.CaptureFixture[str]) -> None:
    body = {
        "target": "facts",
        "op": "add",
        "section": None,
        "text": "Open to relocating to Austin",
        "old_text": None,
        "reason": "User said so in Claude Code",
    }
    assert cli.main(["run", "propose", "--params-json", json.dumps(body), "--json"]) == 0
    created = json.loads(capsys.readouterr().out)
    assert created["status"] == "pending"
    assert created["source"] == "skill"
    facts = (DataPaths.default().memory / "facts.md").read_text(encoding="utf-8")
    assert "Austin" not in facts


def _listener() -> tuple[socket.socket, int]:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    sock.listen()
    return sock, sock.getsockname()[1]


def test_start_uses_the_configured_port_when_free() -> None:
    sock, port = _listener()
    sock.close()
    assert cli.pick_port(port, pinned=False) == (port, None)


def test_a_busy_port_moves_to_the_next_free_one() -> None:
    sock, port = _listener()
    try:
        picked, note = cli.pick_port(port, pinned=False)
    finally:
        sock.close()
    assert picked is not None
    assert picked > port
    assert note == f"Port {port} is busy: another app is using it. Using port {picked} instead."


def test_a_pinned_busy_port_is_an_error() -> None:
    sock, port = _listener()
    try:
        picked, note = cli.pick_port(port, pinned=True)
    finally:
        sock.close()
    assert picked is None
    assert note is not None
    assert "--port" in note


class _Health(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        body = json.dumps({"status": "ok", "version": "0.2.0"}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args: object) -> None:
        pass


def test_a_running_rolehawk_is_named_in_the_note() -> None:
    server = http.server.HTTPServer(("127.0.0.1", 0), _Health)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]
    try:
        picked, note = cli.pick_port(port, pinned=False)
    finally:
        server.shutdown()
        server.server_close()
    assert picked is not None
    assert note is not None
    assert "RoleHawk is already running there" in note


def test_start_exits_with_the_note_when_it_cannot_start(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    sock, port = _listener()
    started: list[int] = []
    monkeypatch.setattr("uvicorn.run", lambda *_a, **kw: started.append(kw["port"]))
    try:
        code = cli.main(["start", "--port", str(port), "--no-browser"])
    finally:
        sock.close()
    assert code == 1
    assert started == []
    assert f"Port {port} is busy" in capsys.readouterr().err


def test_start_moves_off_a_busy_configured_port(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    sock, port = _listener()
    monkeypatch.setenv("ROLEHAWK_SERVER__PORT", str(port))  # as if set in config.toml
    started: list[int] = []
    monkeypatch.setattr("uvicorn.run", lambda *_a, **kw: started.append(kw["port"]))
    try:
        assert cli.main(["start", "--no-browser"]) == 0
    finally:
        sock.close()
    [moved] = started
    assert moved != port
    assert os.environ["ROLEHAWK_SERVER__PORT"] == str(moved)  # the app's Host allowlist
    out = capsys.readouterr().out
    assert f"Using port {moved} instead." in out
    assert f"Open: http://127.0.0.1:{moved}/?token=" in out
    assert "run 'rolehawk'" in out
