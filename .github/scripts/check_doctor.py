"""CI helper: print an `rolehawk doctor --json` report and fail unless everything a fresh
install needs passed. The keychain is skipped: CI's Linux runner has no Secret Service."""

import json
import sys
from pathlib import Path

REQUIRED = (
    "install",
    "python",
    "sqlite_fts5",
    "data_folder",
    "config",
    "database",
    "chromium",
    "autofill_browser",
)

# PowerShell 5.1 writes UTF-8 with a byte order mark.
report = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8-sig"))
checks = {check["name"]: check for check in report}
for check in report:
    print(f"[{'ok' if check['ok'] else 'FAIL'}] {check['name']}: {check['detail']}")
failed = [name for name in REQUIRED if not checks.get(name, {}).get("ok")]
if failed:
    sys.exit(f"doctor checks failed: {', '.join(failed)}")
if not checks["install"]["detail"].startswith("release "):
    sys.exit("doctor isn't running from the installed release")
