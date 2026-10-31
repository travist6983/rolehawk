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
import json
import os
import secrets
import sys
import threading
import time
import urllib.request
import webbrowser
from collections.abc import Sequence

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
