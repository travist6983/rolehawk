"""HTML to PDF with Playwright's headless Chromium (page.pdf()).

One browser is started on first use and reused. Pages render offline: JavaScript is off and
every network request is refused, so a template can't fetch anything or phone home."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from offerbound.rendering.templates import Paper

if TYPE_CHECKING:
    from playwright.async_api import Browser, Playwright, Route

log = logging.getLogger(__name__)


class PdfUnavailableError(RuntimeError):
    """Chromium isn't installed (or won't start). DOCX still works."""

    user_message = (
        "PDF export needs the bundled Chromium browser, which isn't installed yet. "
        "Run `offerbound doctor` for the fix; Word (DOCX) files still work."
    )


async def _refuse(route: Route) -> None:
    await route.abort()


class PdfEngine:
    def __init__(self) -> None:
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
            self._browser = await self._playwright.chromium.launch(headless=True)
        except PlaywrightError as exc:
            log.warning("Chromium unavailable: %s", exc)
            raise PdfUnavailableError(str(exc).splitlines()[0]) from exc
        return self._browser

    async def render(self, html: str, paper: Paper, title: str) -> bytes:
        async with self._lock:  # one page at a time keeps memory flat
            browser = await self._browser_ready()
            context = await browser.new_context(java_script_enabled=False, offline=True)
            try:
                await context.route("**/*", _refuse)
                page = await context.new_page()
                await page.set_content(html, wait_until="load")
                return await page.pdf(
                    format="Letter" if paper == "letter" else "A4",
                    prefer_css_page_size=True,
                    print_background=True,
                    tagged=True,  # a structure tree helps screen readers and parsers
                    outline=False,
                )
            finally:
                await context.close()

    async def check(self) -> None:
        """Start the browser, raising PdfUnavailableError if it can't."""
        async with self._lock:
            await self._browser_ready()

    async def aclose(self) -> None:
        if self._browser is not None:
            await self._browser.close()
            self._browser = None
        if self._playwright is not None:
            await self._playwright.stop()
            self._playwright = None
