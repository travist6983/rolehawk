"""Assemble the GitHub Pages site into an output folder and check it.

    python3 site/tools/build.py _site

Copies site/ (without tools/) into the output folder, then fails if the page:
  * uses an em dash or en dash in its copy (house style),
  * loads anything from another origin (scripts, styles, fonts, images: no trackers),
  * points at a local file that isn't there.
Standard library only, so the Pages workflow needs no installs.
"""

from __future__ import annotations

import re
import shutil
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]
SITE = ROOT / "site"
TEXT_SUFFIXES = {".html", ".css", ".js", ".svg"}
# Attributes that make the browser fetch something as part of rendering the page.
LOADING_ATTRS = {("script", "src"), ("img", "src"), ("source", "srcset"), ("link", "href")}
# <link rel> values that are only metadata, not loads (canonical points at this site itself).
NON_LOADING_RELS = {"canonical"}


class Refs(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.loads: list[str] = []
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k: v or "" for k, v in attrs}
        for name, value in a.items():
            if (tag, name) in LOADING_ATTRS:
                if tag == "link" and a.get("rel") in NON_LOADING_RELS:
                    continue
                self.loads.append(value)
            elif tag == "a" and name == "href":
                self.links.append(value)


def check(out: Path) -> list[str]:
    problems: list[str] = []
    for path in out.rglob("*"):
        if path.suffix in TEXT_SUFFIXES:
            text = path.read_text(encoding="utf-8")
            for n, line in enumerate(text.splitlines(), 1):
                if "\u2014" in line or "\u2013" in line:
                    problems.append(f"{path.relative_to(out)}:{n}: em or en dash")

    html = (out / "index.html").read_text(encoding="utf-8")
    refs = Refs()
    refs.feed(html)
    css = (out / "styles.css").read_text(encoding="utf-8")
    css_urls = re.findall(r"url\(\"?([^\")]+)\"?\)", css)

    for ref in refs.loads + css_urls:
        if urlsplit(ref).scheme or ref.startswith("//"):
            problems.append(f"loads from another origin: {ref}")
        elif not (out / ref.split("#")[0]).is_file():
            problems.append(f"missing file: {ref}")
    for ref in refs.links:
        parts = urlsplit(ref)
        if parts.scheme and parts.scheme != "https":
            problems.append(f"link is not https: {ref}")
        if not parts.scheme and parts.path not in ("", "./") and not (out / parts.path).exists():
            problems.append(f"broken local link: {ref}")
    for anchor in re.findall(r'href="#([^"]+)"', html):
        if f'id="{anchor}"' not in html:
            problems.append(f"no element with id #{anchor}")
    return problems


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit("usage: build.py <output folder>")
    out = Path(sys.argv[1]).resolve()
    if out in (SITE, ROOT) or SITE in out.parents:
        sys.exit("pick an output folder outside site/")
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(SITE, out, ignore=shutil.ignore_patterns("tools", "__pycache__"))

    problems = check(out)
    if problems:
        print("\n".join(problems))
        sys.exit(f"{len(problems)} problem(s) in the site")
    size = sum(p.stat().st_size for p in out.rglob("*") if p.is_file())
    print(f"Built {out} ({size / 1_000_000:.1f} MB)")


if __name__ == "__main__":
    main()
