"""`offerbound` command.

offerbound                 start the app (same as `offerbound start`)
offerbound start           start the backend on 127.0.0.1 and open the browser
offerbound doctor          print a diagnostics report
offerbound db upgrade      apply migrations (backs up first)
offerbound db current      show the schema revision
offerbound db revision -m  autogenerate a migration (developers)
offerbound backup          zip the data folder into <data>/backups
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import json
import os
import secrets
import sys
import threading
import time
import urllib.request
import webbrowser
from collections.abc import Sequence
from typing import Any

from offerbound import __version__
from offerbound.paths import DataPaths

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

    from offerbound.api.app import ENV_DEV_ORIGINS, ENV_TOKEN
    from offerbound.config import load_settings
    from offerbound.logging_setup import configure_logging
    from offerbound.services.runtime import prepare_data_folder

    configure_logging()
    paths = DataPaths.default()
    prepare_data_folder(paths)
    if args.port:
        os.environ["OFFERBOUND_SERVER__PORT"] = str(args.port)
    port = load_settings(paths.config_file).server.port

    # Env vars carry the token and dev origins into uvicorn's reload worker processes.
    token = os.environ.get(ENV_TOKEN) or secrets.token_urlsafe(32)
    os.environ[ENV_TOKEN] = token
    if args.dev:
        os.environ[ENV_DEV_ORIGINS] = ",".join(DEV_FRONTEND_ORIGINS)

    base = "http://127.0.0.1:5173" if args.dev else f"http://127.0.0.1:{port}"
    launch_url = f"{base}/?token={token}"
    print(f"Offerbound AI {__version__} - data folder: {paths.root}")
    print(f"Open: {launch_url}", flush=True)
    if not args.no_browser:
        threading.Thread(
            target=_wait_then_open,
            args=(launch_url, f"http://127.0.0.1:{port}/api/health"),
            daemon=True,
        ).start()

    uvicorn.run(
        "offerbound.api.app:create_app",
        factory=True,
        host="127.0.0.1",
        port=port,
        reload=args.dev,
        log_config=None,
    )
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    from offerbound.services import doctor

    checks = doctor.run_checks(DataPaths.default())
    if args.json:
        print(json.dumps(doctor.as_dicts(checks), indent=2))
    else:
        for check in checks:
            print(f"[{'ok' if check.ok else 'FAIL'}] {check.name}: {check.detail}")
    return 0 if all(check.ok for check in checks) else 1


def cmd_db(args: argparse.Namespace) -> int:
    from offerbound.db import migrate
    from offerbound.db.engine import make_engine
    from offerbound.services.runtime import prepare_data_folder

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
    from offerbound.services import backup

    print(backup.create_backup(DataPaths.default(), reason="manual"))
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

    from offerbound.commands.registry import UnknownCommandError
    from offerbound.commands.runner import CommandStarted, run_command
    from offerbound.llm.errors import LLMError
    from offerbound.services.runtime import open_runtime
    from offerbound.services.tasks import TASK_EVENT

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
    from offerbound.llm.errors import LLMError
    from offerbound.services import llm_settings
    from offerbound.services.runtime import open_runtime

    runtime = open_runtime(DataPaths.default())
    try:
        if action == "set-key" and key:
            status = await llm_settings.set_api_key(runtime, key)
        elif action == "clear-key":
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

    from offerbound.api.app import create_app

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
    parser = argparse.ArgumentParser(
        prog="offerbound", description="Offerbound AI job search copilot"
    )
    parser.add_argument("--version", action="version", version=f"offerbound {__version__}")
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
    llm.set_defaults(func=cmd_llm)

    openapi = sub.add_parser("openapi", help="export the OpenAPI schema")
    openapi.add_argument("--out", help="write to this file instead of stdout")
    openapi.set_defaults(func=cmd_openapi)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        args = parser.parse_args(["start", *(argv or sys.argv[1:])])
    result: int = args.func(args)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
