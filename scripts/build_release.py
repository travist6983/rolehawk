"""Build the release assets (the install scripts and `rolehawk update` read these).

    npm --prefix frontend run build
    uv run --no-project --python 3.12 python scripts/build_release.py --out dist/release

Writes three files to --out:
    rolehawk.zip         rolehawk-<version>/ with VERSION, backend/ (no tests), data/,
                           skills/, frontend/dist/, README.md, LICENSE, DISCLAIMER.md
    rolehawk.zip.sha256  "<sha256>  rolehawk.zip"
    release.json           {"version", "sha256", "size"}

Only git-tracked files go in (never .venv, caches, or local data), plus the frontend build.
The ZIP is deterministic: sorted entries and fixed timestamps. Standard library only."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import tomllib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TRACKED = ["backend", "data", "skills", "README.md", "LICENSE", "DISCLAIMER.md"]
EXCLUDED = ("backend/tests/", "backend/scripts/")
VERSION = re.compile(r"^\d{1,4}\.\d{1,4}\.\d{1,4}$")
EPOCH = (1980, 1, 1, 0, 0, 0)


def project_version() -> str:
    data = tomllib.loads((ROOT / "backend" / "pyproject.toml").read_text(encoding="utf-8"))
    return str(data["project"]["version"])


def tracked_files() -> list[str]:
    out = subprocess.run(
        ["git", "ls-files", "-z", "--", *TRACKED],  # noqa: S607 - git from PATH
        cwd=ROOT,
        check=True,
        capture_output=True,
    ).stdout.decode("utf-8")
    return [name for name in out.split("\0") if name and not name.startswith(EXCLUDED)]


def frontend_files() -> list[str]:
    dist = ROOT / "frontend" / "dist"
    if not (dist / "index.html").is_file():
        sys.exit("frontend/dist is missing: run `npm --prefix frontend run build` first")
    return [p.relative_to(ROOT).as_posix() for p in dist.rglob("*") if p.is_file()]


def entry(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=EPOCH)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o644 << 16
    return info


def build(out: Path, version: str) -> dict[str, object]:
    top = f"rolehawk-{version}"
    out.mkdir(parents=True, exist_ok=True)
    zip_path = out / "rolehawk.zip"
    names = sorted(set(tracked_files()) | set(frontend_files()))
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr(entry(f"{top}/VERSION"), version)
        for name in names:
            archive.writestr(entry(f"{top}/{name}"), (ROOT / name).read_bytes())
    payload = zip_path.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    (out / "rolehawk.zip.sha256").write_text(f"{digest}  rolehawk.zip\n", encoding="utf-8")
    info: dict[str, object] = {"version": version, "sha256": digest, "size": len(payload)}
    (out / "release.json").write_text(json.dumps(info, indent=2) + "\n", encoding="utf-8")
    return info | {"files": len(names) + 1}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default="dist/release", help="output folder")
    parser.add_argument("--tag", help="the git tag being released; must be v<version>")
    parser.add_argument(
        "--version", help="label the release with this version instead (CI's update test)"
    )
    args = parser.parse_args()

    version = args.version or project_version()
    if not VERSION.match(version):
        sys.exit(f"release versions are X.Y.Z, got {version!r}")
    if args.tag and args.tag != f"v{version}":
        sys.exit(f"tag {args.tag} doesn't match backend/pyproject.toml version {version}")
    info = build(ROOT / args.out, version)
    print(json.dumps(info))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
