"""`rolehawk` command.

rolehawk                 start the app (same as `rolehawk start`)
rolehawk start           start the backend on 127.0.0.1 and open the browser
rolehawk doctor          print a diagnostics report
rolehawk db upgrade      apply migrations (backs up first)
rolehawk db current      show the schema revision
rolehawk db revision -m  autogenerate a migration (developers)
rolehawk backup          zip the data folder into <data>/backups
rolehawk update          install the newest release (backs up, migrates, keeps the old one)
rolehawk install-browser install or repair Chromium (PDF export and autofill)
rolehawk install-skills  add the RoleHawk skills to Claude Code (~/.claude/skills)
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import json
import os
import secrets
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from collections.abc import Sequence
from typing import Any

from rolehawk import __version__
from rolehawk.install.layout import configure_browsers
from rolehawk.paths import DataPaths

DEV_FRONTEND_ORIGINS = ("http://127.0.0.1:5173", "http://localhost:5173")


def _wait_then_open(url: str, health_url: str, timeout_s: float = 30) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(health_url, timeout=1):  # noqa: S310 - fixed local URL
                webbrowser.open(url)
                return
        except OSError:
            time.sleep(0.25)


def cmd_start(args: argparse.Namespace) -> int:
    import uvicorn

    from rolehawk.api.app import ENV_DEV_ORIGINS, ENV_TOKEN
    from rolehawk.config import load_settings
    from rolehawk.logging_setup import configure_logging
    from rolehawk.services.runtime import prepare_data_folder

    configure_logging()
    paths = DataPaths.default()
    prepare_data_folder(paths)
    if args.port:
        os.environ["ROLEHAWK_SERVER__PORT"] = str(args.port)
    port = load_settings(paths.config_file).server.port

    # Env vars carry the token and dev origins into uvicorn's reload worker processes.
    token = os.environ.get(ENV_TOKEN) or secrets.token_urlsafe(32)
    os.environ[ENV_TOKEN] = token
    if args.dev:
        os.environ[ENV_DEV_ORIGINS] = ",".join(DEV_FRONTEND_ORIGINS)

    base = "http://127.0.0.1:5173" if args.dev else f"http://127.0.0.1:{port}"
    launch_url = f"{base}/?token={token}"
    print(f"RoleHawk {__version__} - data folder: {paths.root}")
    print(f"Open: {launch_url}", flush=True)
    if not args.no_browser:
        threading.Thread(
            target=_wait_then_open,
            args=(launch_url, f"http://127.0.0.1:{port}/api/health"),
            daemon=True,
        ).start()

    uvicorn.run(
        "rolehawk.api.app:create_app",
        factory=True,
        host="127.0.0.1",
        port=port,
        reload=args.dev,
        log_config=None,
        # Open event streams (a browser tab on /api/events) never end by themselves; without a
        # limit, Ctrl+C and dev reloads wait on them forever. Browsers reconnect on their own.
        timeout_graceful_shutdown=2,
    )
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    from rolehawk.services import doctor

    checks = doctor.run_checks(DataPaths.default())
    if args.json:
        print(json.dumps(doctor.as_dicts(checks), indent=2))
    else:
        for check in checks:
            print(f"[{'ok' if check.ok else 'FAIL'}] {check.name}: {check.detail}")
    return 0 if all(check.ok for check in checks) else 1


def cmd_db(args: argparse.Namespace) -> int:
    from rolehawk.db import migrate
    from rolehawk.db.engine import make_engine
    from rolehawk.services.runtime import prepare_data_folder

    paths = DataPaths.default()
    prepare_data_folder(paths)
    engine = make_engine(paths.db)
    try:
        if args.db_command == "upgrade":
            backup_path = migrate.migrate(paths, engine)
            if backup_path:
                print(f"Backup: {backup_path}")
            print(f"Database at revision {migrate.current_revision(engine)}")
        elif args.db_command == "current":
            print(f"{migrate.current_revision(engine)} (head {migrate.head_revision()})")
        elif args.db_command == "revision":
            migrate.upgrade(engine)
            migrate.revision(engine, args.message)
    finally:
        engine.dispose()
    return 0


def cmd_backup(_args: argparse.Namespace) -> int:
    from rolehawk.services import backup

    print(backup.create_backup(DataPaths.default(), reason="manual"))
    return 0


def _app_running() -> bool:
    from rolehawk.config import load_settings

    port = load_settings(DataPaths.default().config_file).server.port
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=1):
            return True
    except OSError:
        return False


def cmd_update(args: argparse.Namespace) -> int:
    import httpx2

    from rolehawk.install.layout import running_from
    from rolehawk.install.release import ReleaseError, release_url
    from rolehawk.install.update import UpdateError, Updater, find_uv
    from rolehawk.portals.http import USER_AGENT
    from rolehawk.services import backup

    installed = running_from()
    if installed is None:
        print("This is a source checkout. Update it with `git pull`, then `npm run setup`.")
        return 2
    layout, running = installed
    with httpx2.Client(
        follow_redirects=True, timeout=60, headers={"User-Agent": USER_AGENT}
    ) as client:
        updater = Updater(
            layout,
            client,
            release_url(),
            uv=find_uv(),
            backup=lambda: backup.create_backup(DataPaths.default(), reason="update"),
            app_running=_app_running,
            running_version=running,
        )
        try:
            if args.check:
                status, _info = updater.check()
                note = "an update is available" if status.available else "up to date"
                print(f"Installed {status.current}, latest {status.latest}: {note}.")
                return 0
            version = updater.update()
        except (ReleaseError, UpdateError) as exc:
            print(f"Update stopped: {exc}", file=sys.stderr)
            return 1
        except subprocess.CalledProcessError as exc:
            print(
                f"Update stopped: {exc.cmd[0]} failed (exit {exc.returncode}). "
                "You're still on the previous version.",
                file=sys.stderr,
            )
            return 1
    if version is None:
        print(f"RoleHawk {layout.current_version()} is the newest release.")
    else:
        print(f"Updated to {version}. Start it with `rolehawk`.")
    return 0


def cmd_install_browser(_args: argparse.Namespace) -> int:
    """Chromium for PDF export (headless) and autofill (visible). Safe to run again."""
    command = [sys.executable, "-m", "playwright", "install", "chromium"]
    result = subprocess.run(command, check=False)  # noqa: S603 - fixed argv
    if result.returncode == 0 and sys.platform.startswith("linux"):
        print(
            "If PDF export fails later, Chromium may need system libraries: "
            f"sudo {sys.executable} -m playwright install-deps chromium"
        )
    return result.returncode


def cmd_install_skills(_args: argparse.Namespace) -> int:
    from rolehawk.install.skills import bundled_skills_dir, claude_skills_dir, install_skills

    dest = claude_skills_dir()
    installed = install_skills(bundled_skills_dir(), dest)
    if not installed:
        print("No skills found to install.", file=sys.stderr)
        return 1
    for folder in installed:
        print(f"  {folder.name}")
    print(f"Installed {len(installed)} skills in {dest}. Restart Claude Code to load them.")
    return 0


def _parse_params(pairs: list[str], params_json: str | None) -> dict[str, Any]:
    params: dict[str, Any] = json.loads(params_json) if params_json else {}
    if not isinstance(params, dict):
        raise SystemExit("--params-json must be a JSON object")
    for pair in pairs:
        key, sep, raw = pair.partition("=")
        if not sep or not key:
            raise SystemExit(f"--param expects key=value, got {pair!r}")
        try:
            params[key] = json.loads(raw)
        except json.JSONDecodeError:
            params[key] = raw
    return params


async def _run_command(name: str, params: dict[str, Any]) -> tuple[int, Any]:
    from pydantic import ValidationError

    from rolehawk.commands.registry import UnknownCommandError
    from rolehawk.commands.runner import CommandStarted, run_command
    from rolehawk.llm.errors import LLMError
    from rolehawk.services.runtime import open_runtime
    from rolehawk.services.tasks import TASK_EVENT

    runtime = open_runtime(DataPaths.default())
    try:
        try:
            spec = runtime.commands.get(name)
        except UnknownCommandError:
            names = ", ".join(c.name for c in runtime.commands.all())
            return 2, {"error": f"unknown command {name!r}", "available": names}
        async with runtime.bus.subscribe() as queue:
            try:
                result = await run_command(runtime, spec, params)
            except ValidationError as exc:
                return 2, {"error": "invalid parameters", "details": exc.errors(include_url=False)}
            except LLMError as exc:
                return 3, {"error": exc.user_message, "kind": type(exc).__name__}
            if not isinstance(result, CommandStarted):
                return 0, result
            while True:
                event = await queue.get()
                if event.type != TASK_EVENT or event.data.get("id") != result.task_id:
                    continue
                if event.data.get("message"):
                    print(f"[{spec.name}] {event.data['message']}", file=sys.stderr, flush=True)
                if event.data.get("status") in {"succeeded", "failed", "cancelled"}:
                    return (0 if event.data["status"] == "succeeded" else 1), event.data
    finally:
        await runtime.aclose()


def cmd_run(args: argparse.Namespace) -> int:
    params = _parse_params(args.param or [], args.params_json)
    code, output = asyncio.run(_run_command(args.name, params))
    text = json.dumps(output, indent=None if args.json else 2, default=str)
    print(text, file=sys.stdout if code == 0 else sys.stderr)
    return code


async def _llm(action: str, key: str | None) -> tuple[int, Any]:
    from rolehawk.llm.errors import LLMError
    from rolehawk.services import llm_settings
    from rolehawk.services.runtime import open_runtime

    runtime = open_runtime(DataPaths.default())
    try:
        if action == "set-key" and key:
            result = await llm_settings.set_api_key(runtime, key)
            return (0 if result.saved else 3), result.model_dump(mode="json")
        if action == "test-key":
            test = await llm_settings.check_api_key(runtime)
            return (0 if test.ok else 3), test.model_dump(mode="json")
        if action == "clear-key":
            status = await llm_settings.clear_api_key(runtime)
        else:
            status = llm_settings.status(runtime)
        return 0, status.model_dump(mode="json")
    except LLMError as exc:
        return 3, {"error": exc.user_message}
    finally:
        await runtime.aclose()


def cmd_llm(args: argparse.Namespace) -> int:
    key = None
    if args.llm_command == "set-key":
        key = sys.stdin.readline().strip() if args.stdin else getpass.getpass("Anthropic API key: ")
        if not key:
            print("No key entered.", file=sys.stderr)
            return 2
    code, output = asyncio.run(_llm(args.llm_command, key))
    print(json.dumps(output, indent=2), file=sys.stdout if code == 0 else sys.stderr)
    return code


def cmd_openapi(args: argparse.Namespace) -> int:
    import tempfile
    from pathlib import Path

    from rolehawk.api.app import create_app

    with tempfile.TemporaryDirectory() as tmp:
        schema = create_app(paths=DataPaths(Path(tmp)), token="schema-export").openapi()  # noqa: S106
    text = json.dumps(schema, indent=2, ensure_ascii=False) + "\n"
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8", newline="\n")
    else:
        sys.stdout.write(text)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="rolehawk", description="RoleHawk job search copilot")
    parser.add_argument("--version", action="version", version=f"rolehawk {__version__}")
    sub = parser.add_subparsers(dest="command")

    start = sub.add_parser("start", help="start the app")
    start.add_argument("--port", type=int, help="port (default from config.toml, 8765)")
    start.add_argument("--no-browser", action="store_true", help="don't open a browser")
    start.add_argument(
        "--dev", action="store_true", help="autoreload and allow the Vite dev server origin"
    )
    start.set_defaults(func=cmd_start)

    doctor = sub.add_parser("doctor", help="print diagnostics")
    doctor.add_argument("--json", action="store_true", help="machine-readable output")
    doctor.set_defaults(func=cmd_doctor)

    db = sub.add_parser("db", help="database migrations")
    db_sub = db.add_subparsers(dest="db_command", required=True)
    db_sub.add_parser("upgrade", help="apply pending migrations (backs up first)")
    db_sub.add_parser("current", help="show current revision")
    revision = db_sub.add_parser("revision", help="autogenerate a migration from models")
    revision.add_argument("-m", "--message", required=True)
    db.set_defaults(func=cmd_db)

    sub.add_parser("backup", help="zip the data folder").set_defaults(func=cmd_backup)

    update = sub.add_parser("update", help="install the newest release")
    update.add_argument("--check", action="store_true", help="only check for a newer release")
    update.set_defaults(func=cmd_update)

    sub.add_parser(
        "install-browser", help="install or repair Chromium (PDF export and autofill)"
    ).set_defaults(func=cmd_install_browser)

    sub.add_parser(
        "install-skills", help="add the RoleHawk skills to Claude Code (~/.claude/skills)"
    ).set_defaults(func=cmd_install_skills)

    run = sub.add_parser("run", help="run a command against the data folder")
    run.add_argument("name", help="command name, e.g. context, memory, spend, selftest")
    run.add_argument(
        "--param", action="append", metavar="KEY=VALUE", help="parameter (value may be JSON)"
    )
    run.add_argument("--params-json", help="all parameters as one JSON object")
    run.add_argument("--json", action="store_true", help="compact JSON output for tools")
    run.set_defaults(func=cmd_run)

    llm = sub.add_parser("llm", help="Claude connection")
    llm_sub = llm.add_subparsers(dest="llm_command", required=True)
    llm_sub.add_parser("status", help="show connection, model routing and spend")
    set_key = llm_sub.add_parser("set-key", help="validate and store an API key in the keychain")
    set_key.add_argument("--stdin", action="store_true", help="read the key from stdin")
    llm_sub.add_parser("clear-key", help="remove the stored API key")
    llm_sub.add_parser("test-key", help="send one tiny real message with the stored key")
    llm.set_defaults(func=cmd_llm)

    openapi = sub.add_parser("openapi", help="export the OpenAPI schema")
    openapi.add_argument("--out", help="write to this file instead of stdout")
    openapi.set_defaults(func=cmd_openapi)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    configure_browsers()
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        args = parser.parse_args(["start", *(argv or sys.argv[1:])])
    result: int = args.func(args)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
