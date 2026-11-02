"""Autofill: open the application form in a visible browser, fill the fields we're sure of,
attach the CV and cover letter, and stop. Nothing here clicks, presses Enter, or submits;
the user reviews the form and submits it themselves.

Fields are matched by their visible label (with name, placeholder, and autocomplete hints),
which works across Greenhouse, Lever, Ashby, Workable, and most custom forms. Workday and
other multi-step portals are opened for the user; the browser agent will handle them."""

from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING, Literal
from urllib.parse import urlsplit, urlunsplit

from pydantic import BaseModel

from rolehawk.install.layout import browser_hint

if TYPE_CHECKING:
    from playwright.async_api import Browser, Page, Playwright

log = logging.getLogger(__name__)

Ats = Literal["greenhouse", "lever", "ashby", "workable", "workday", "other"]
FIELD_TIMEOUT_MS = 15_000


class AutofillUnavailableError(RuntimeError):
    """Chromium is missing or won't start. The message names the fix for how RoleHawk runs
    (an installed release or a source checkout), so it's built when shown."""

    @property
    def user_message(self) -> str:
        if "Executable doesn't exist" in str(self):
            return (
                "Autofill needs the full Chromium browser, which isn't installed. "
                f"Install it with: {browser_hint()}. Then try again."
            )
        return f"Autofill couldn't start Chromium ({self}). Run `rolehawk doctor` for the fix."


class Applicant(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    full_name: str | None = None
    email: str | None = None
    phone: str | None = None
    location: str | None = None
    linkedin: str | None = None
    github: str | None = None
    website: str | None = None


class AutofillReport(BaseModel):
    url: str
    ats: Ats
    filled: list[str]
    attached: list[str]
    needs_you: list[str]  # required fields left empty (custom questions, consent boxes)
    note: str | None = None


def split_name(full: str | None) -> tuple[str | None, str | None]:
    parts = (full or "").split()
    if not parts:
        return None, None
    return parts[0], " ".join(parts[1:]) or None


def applicant_from(
    name: str | None,
    email: str | None,
    phone: str | None,
    location: str | None,
    links: list[str],
) -> Applicant:
    first, last = split_name(name)

    def link(pattern: str) -> str | None:
        found = next((u for u in links if re.search(pattern, u, re.I)), None)
        if found and not found.startswith(("http://", "https://")):
            found = "https://" + found
        return found

    other = [u for u in links if not re.search(r"linkedin\.com|github\.com", u, re.I)]
    return Applicant(
        first_name=first,
        last_name=last,
        full_name=name,
        email=email,
        phone=phone,
        location=location,
        linkedin=link(r"linkedin\.com"),
        github=link(r"github\.com"),
        website=(other[0] if other[0].startswith("http") else f"https://{other[0]}")
        if other
        else None,
    )


def application_url(url: str) -> tuple[str, Ats]:
    """Where the form lives for a posting URL, and which system it is."""
    parts = urlsplit(url)
    host = parts.hostname or ""
    path = parts.path.rstrip("/")
    if host.endswith("lever.co"):
        return urlunsplit(
            parts._replace(path=path if path.endswith("/apply") else f"{path}/apply")
        ), "lever"
    if host == "jobs.ashbyhq.com":
        suffix = "/application"
        return urlunsplit(
            parts._replace(path=path if path.endswith(suffix) else path + suffix)
        ), "ashby"
    if host.endswith("greenhouse.io"):
        return url, "greenhouse"
    if host == "apply.workable.com":
        return urlunsplit(
            parts._replace(path=path if path.endswith("/apply") else f"{path}/apply/")
        ), "workable"
    if "myworkdayjobs.com" in host or host.endswith("workday.com"):
        return url, "workday"
    return url, "other"


# Runs in the page: tags each fillable field with the key it matches (see tag_fields.js).
_TAG_FIELDS = "\n".join(
    line
    for line in (Path(__file__).parent / "tag_fields.js").read_text(encoding="utf-8").splitlines()
    if not line.startswith("//")  # page.evaluate must see a bare function expression
)


class Autofiller:
    def __init__(self, headless: bool = False, field_timeout_ms: int = FIELD_TIMEOUT_MS) -> None:
        self._headless = headless
        self._field_timeout_ms = field_timeout_ms
        self._lock = asyncio.Lock()
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None

    async def _browser_ready(self) -> Browser:
        if self._browser is not None and self._browser.is_connected():
            return self._browser
        from playwright.async_api import Error as PlaywrightError
        from playwright.async_api import async_playwright

        if self._playwright is None:
            self._playwright = await async_playwright().start()
        try:
            self._browser = await self._playwright.chromium.launch(headless=self._headless)
        except PlaywrightError as exc:
            log.warning("autofill browser unavailable: %s", exc)
            raise AutofillUnavailableError(str(exc).splitlines()[0]) from exc
        return self._browser

    async def open(
        self,
        url: str,
        applicant: Applicant,
        resume: Path | None,
        cover_letter: Path | None,
        letter_text: str | None,
    ) -> tuple[AutofillReport, Page]:
        """Fill what we can and leave the page open for the user. Returns the page so tests
        can inspect it; the app doesn't close it."""
        form_url, ats = application_url(url)
        async with self._lock:
            browser = await self._browser_ready()
            context = await browser.new_context()
            page = await context.new_page()
        await page.goto(form_url, wait_until="domcontentloaded")
        if ats == "workday":
            return (
                AutofillReport(
                    url=form_url,
                    ats=ats,
                    filled=[],
                    attached=[],
                    needs_you=[],
                    note=(
                        "Workday applications need a Workday account and several steps, so "
                        "RoleHawk opened the posting for you. Your CV and cover letter are "
                        "ready to upload."
                    ),
                ),
                page,
            )
        try:
            await page.wait_for_selector("input, textarea", timeout=self._field_timeout_ms)
        except Exception:
            return (
                AutofillReport(
                    url=form_url,
                    ats=ats,
                    filled=[],
                    attached=[],
                    needs_you=[],
                    note="No application form found on this page. Use its Apply button.",
                ),
                page,
            )
        report = await self._fill(page, applicant, resume, cover_letter, letter_text)
        return report.model_copy(update={"url": form_url, "ats": ats}), page

    async def _fill(
        self,
        page: Page,
        applicant: Applicant,
        resume: Path | None,
        cover_letter: Path | None,
        letter_text: str | None,
    ) -> AutofillReport:
        fields = await page.evaluate(_TAG_FIELDS)
        values = applicant.model_dump()
        filled: list[str] = []
        attached: list[str] = []
        done: set[int] = set()
        for field in fields:
            key, index = field.get("key"), int(field["index"])
            if not key or not field.get("empty", True):
                continue
            locator = page.locator(f'[data-rolehawk-index="{index}"]')
            if field["type"] == "file":
                path = resume if key == "resume" else cover_letter
                if path is not None and path.is_file():
                    await locator.set_input_files(str(path))
                    attached.append(field["label"])
                    done.add(index)
                continue
            value = letter_text if key == "cover_letter" else values.get(key)
            if not value:
                continue
            await locator.fill(str(value))
            filled.append(field["label"])
            done.add(index)
        needs_you = [
            str(f["label"])
            for f in fields
            if f.get("required") and f.get("empty", True) and int(f["index"]) not in done
        ]
        return AutofillReport(
            url=page.url, ats="other", filled=filled, attached=attached, needs_you=needs_you
        )

    async def aclose(self) -> None:
        if self._browser is not None:
            await self._browser.close()
            self._browser = None
        if self._playwright is not None:
            await self._playwright.stop()
            self._playwright = None
