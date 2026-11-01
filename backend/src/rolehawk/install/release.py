"""Release assets. Every GitHub release carries three files (scripts/build_release.py):

    release.json            {"version": "0.2.0", "sha256": "...", "size": 1234}
    rolehawk.zip          one top folder, rolehawk-<version>/
    rolehawk.zip.sha256   "<sha256>  rolehawk.zip" (what the install scripts check)

The names don't include the version, so .../releases/latest/download/<name> always points
at the newest release. ROLEHAWK_RELEASE_URL swaps the base URL (CI serves a local build)."""

from __future__ import annotations

import hashlib
import os
import shutil
import stat
import zipfile
from pathlib import Path, PurePosixPath

import httpx2
from pydantic import BaseModel, Field, ValidationError

from rolehawk.install.layout import VERSION_PATTERN

RELEASES = "https://github.com/travist6983/rolehawk/releases/latest/download"
ENV_RELEASE_URL = "ROLEHAWK_RELEASE_URL"
INFO_NAME = "release.json"
ZIP_NAME = "rolehawk.zip"
MAX_ZIP_BYTES = 200_000_000
MAX_UNPACKED_BYTES = 600_000_000


class ReleaseError(RuntimeError):
    pass


class ReleaseInfo(BaseModel):
    version: str = Field(pattern=VERSION_PATTERN.pattern)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    size: int


def release_url() -> str:
    return (os.environ.get(ENV_RELEASE_URL) or RELEASES).rstrip("/")


def fetch_info(client: httpx2.Client, base: str) -> ReleaseInfo:
    try:
        response = client.get(f"{base}/{INFO_NAME}")
        response.raise_for_status()
        return ReleaseInfo.model_validate_json(response.content)
    except httpx2.HTTPError as exc:
        raise ReleaseError(f"Couldn't check for a new release: {exc}") from exc
    except ValidationError as exc:
        raise ReleaseError("The release description is malformed.") from exc


def download(client: httpx2.Client, base: str, info: ReleaseInfo, folder: Path) -> Path:
    """Stream the ZIP to disk, checking its size and SHA-256 against release.json."""
    if info.size > MAX_ZIP_BYTES:
        raise ReleaseError(f"The release is unexpectedly large ({info.size} bytes).")
    folder.mkdir(parents=True, exist_ok=True)
    dest = folder / f"rolehawk-{info.version}.zip"
    partial = dest.with_suffix(".zip.partial")
    digest, size = hashlib.sha256(), 0
    try:
        with client.stream("GET", f"{base}/{ZIP_NAME}") as response, partial.open("wb") as out:
            response.raise_for_status()
            for chunk in response.iter_bytes():
                size += len(chunk)
                if size > MAX_ZIP_BYTES:
                    raise ReleaseError("The download is larger than the release says.")
                digest.update(chunk)
                out.write(chunk)
    except httpx2.HTTPError as exc:
        partial.unlink(missing_ok=True)
        raise ReleaseError(f"Download failed: {exc}") from exc
    except ReleaseError:
        partial.unlink(missing_ok=True)
        raise
    if digest.hexdigest() != info.sha256:
        partial.unlink(missing_ok=True)
        raise ReleaseError("The download doesn't match the release checksum; nothing changed.")
    partial.replace(dest)
    return dest


def _member_path(info: zipfile.ZipInfo, top: str) -> PurePosixPath | None:
    """The member's path inside the top folder; refuses anything that could escape it."""
    name = info.filename
    path = PurePosixPath(name)
    if "\\" in name or path.is_absolute() or ".." in path.parts or ":" in name:
        raise ReleaseError(f"Unsafe path in the release: {name!r}")
    if stat.S_ISLNK(info.external_attr >> 16):
        raise ReleaseError(f"Links aren't allowed in the release: {name!r}")
    if path.parts[0] != top:
        raise ReleaseError(f"Unexpected file outside {top}/: {name!r}")
    inner = PurePosixPath(*path.parts[1:])
    return inner if inner.parts else None


def extract(zip_path: Path, into: Path, version: str) -> None:
    """Unpack rolehawk-<version>/ into `into` (which must not exist yet)."""
    top = f"rolehawk-{version}"
    if into.exists():
        raise ReleaseError(f"{into} already exists")
    with zipfile.ZipFile(zip_path) as archive:
        members = archive.infolist()
        if sum(m.file_size for m in members) > MAX_UNPACKED_BYTES:
            raise ReleaseError("The release unpacks to an unexpected size.")
        planned = [(m, _member_path(m, top)) for m in members]
        if f"{top}/VERSION" not in archive.namelist():
            raise ReleaseError("The release has no VERSION file.")
        if archive.read(f"{top}/VERSION").decode("utf-8").strip() != version:
            raise ReleaseError("The release's VERSION doesn't match release.json.")
        into.mkdir(parents=True)
        try:
            for member, inner in planned:
                if inner is None:
                    continue
                target = into.joinpath(*inner.parts)
                if member.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(member) as source, target.open("wb") as out:
                    shutil.copyfileobj(source, out)
        except BaseException:
            shutil.rmtree(into, ignore_errors=True)
            raise
