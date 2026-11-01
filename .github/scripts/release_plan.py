"""CI helper: decide whether a commit on main should be released.

Reads the version from backend/pyproject.toml (and checks rolehawk/__init__.py agrees), then
asks the remote whether tag v<version> exists. Prints GitHub Actions outputs:

    version=0.2.1
    tag=v0.2.1
    release=true      # the tag doesn't exist yet, so this commit should publish it

A PR that doesn't bump the version (docs, site) finds its tag already there and releases nothing.

    python3 .github/scripts/release_plan.py [--remote origin] [--tag-exists | --tag-missing]

The last two flags skip the remote lookup, for tests.
"""

import argparse
import re
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VERSION = re.compile(r"^[0-9]{1,4}\.[0-9]{1,4}\.[0-9]{1,4}$")


def read_version(root: Path) -> str:
    project = tomllib.loads((root / "backend" / "pyproject.toml").read_text(encoding="utf-8"))
    version = str(project["project"]["version"])
    if not VERSION.match(version):
        sys.exit(f"backend/pyproject.toml has an unexpected version: {version!r}")
    init = (root / "backend" / "src" / "rolehawk" / "__init__.py").read_text(encoding="utf-8")
    found = re.search(r'^__version__ = "([^"]+)"', init, re.MULTILINE)
    if not found or found.group(1) != version:
        sys.exit(f"rolehawk/__init__.py doesn't say {version}; bump both files together")
    return version


def tag_exists(remote: str, tag: str) -> bool:
    # A fixed argv with no shell; git comes from PATH on the runner.
    result = subprocess.run(  # noqa: S603
        ["git", "ls-remote", "--tags", remote, f"refs/tags/{tag}"],  # noqa: S607
        capture_output=True,
        text=True,
        check=True,
    )
    return bool(result.stdout.strip())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--remote", default="origin")
    parser.add_argument("--root", type=Path, default=ROOT)
    known = parser.add_mutually_exclusive_group()
    known.add_argument("--tag-exists", action="store_true")
    known.add_argument("--tag-missing", action="store_true")
    args = parser.parse_args()

    version = read_version(args.root)
    tag = f"v{version}"
    if args.tag_exists or args.tag_missing:
        exists = args.tag_exists
    else:
        exists = tag_exists(args.remote, tag)
    print(f"version={version}")
    print(f"tag={tag}")
    print(f"release={'false' if exists else 'true'}")
    note = f"{tag} already exists: nothing to release." if exists else f"{tag} will be released."
    print(note, file=sys.stderr)


if __name__ == "__main__":
    main()
