import json

import pytest

from offerbound import cli
from offerbound.paths import DataPaths


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
    assert "offerbound" in capsys.readouterr().out
