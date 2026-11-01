import json

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
