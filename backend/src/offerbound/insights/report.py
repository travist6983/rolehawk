"""/html-report: one self-contained HTML file you can keep or share.

Everything is inline: CSS, the data, SVG charts drawn here, and a few lines of script for
the table search. A Content-Security-Policy forbids every network request, so opening the
file never contacts anything. All text from job sources is escaped."""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from html import escape

from offerbound.insights.board import ACTIVE, CLOSED, LABELS, Board
from offerbound.insights.stats import Insights

BAR = 18  # bar thickness (<= 24px)
GAP = 10
LABEL_W = 150
PLOT_W = 360


def _hbar(x: float, y: float, width: float, height: float, radius: float = 4) -> str:
    """A bar square at the baseline (left) with a rounded data end (right)."""
    if width <= 0:
        return ""
    r = min(radius, width, height / 2)
    return (
        f"M{x:.1f},{y:.1f}h{width - r:.1f}a{r},{r} 0 0 1 {r},{r}v{height - 2 * r:.1f}"
        f"a{r},{r} 0 0 1 -{r},{r}h-{width - r:.1f}z"
    )


def _vbar(x: float, base: float, width: float, height: float, radius: float = 4) -> str:
    """A column square at the baseline (bottom) with a rounded top."""
    if height <= 0:
        return ""
    r = min(radius, height, width / 2)
    return (
        f"M{x:.1f},{base:.1f}v-{height - r:.1f}a{r},{r} 0 0 1 {r},-{r}h{width - 2 * r:.1f}"
        f"a{r},{r} 0 0 1 {r},{r}v{height - r:.1f}z"
    )


def bar_chart(
    title: str, rows: list[tuple[str, float, str]], max_value: float | None = None
) -> str:
    """Horizontal bars: (label, value, value text). One series, labels at the bar tip."""
    top = max_value if max_value else max((v for _, v, _ in rows), default=0) or 1
    height = len(rows) * (BAR + GAP) + GAP
    parts = [
        f'<svg class="chart" viewBox="0 0 {LABEL_W + PLOT_W + 90} {height}" role="img" '
        f'aria-label="{escape(title)}">'
    ]
    for i, (label, value, text) in enumerate(rows):
        y = GAP + i * (BAR + GAP)
        width = PLOT_W * (value / top) if top else 0
        parts.append(
            f'<text class="axis-label" x="{LABEL_W - 8}" y="{y + BAR / 2}" text-anchor="end" '
            f'dominant-baseline="middle">{escape(label)}</text>'
            f'<path class="bar" d="{_hbar(LABEL_W, y, width, BAR)}"><title>{escape(label)}: '
            f"{escape(text)}</title></path>"
            f'<text class="value" x="{LABEL_W + width + 6:.1f}" y="{y + BAR / 2}" '
            f'dominant-baseline="middle">{escape(text)}</text>'
        )
    parts.append(f'<line class="baseline" x1="{LABEL_W}" x2="{LABEL_W}" y1="0" y2="{height}"/>')
    parts.append("</svg>")
    return "".join(parts)


MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _week(iso: str) -> str:
    """ "2026-10-05" -> "Oct 5", like the app."""
    _year, month, day = iso.split("-")
    return f"{MONTHS[int(month) - 1]} {int(day)}"


def column_chart(title: str, rows: list[tuple[str, int]]) -> str:
    """Weekly columns: (week label, count). Every other week is labeled on the axis."""
    plot_h, col = 140, 18
    step = 34
    width = len(rows) * step + 40
    top = max((v for _, v in rows), default=0) or 1
    base = plot_h + 10
    parts = [
        f'<svg class="chart" viewBox="0 0 {width} {base + 30}" role="img" '
        f'aria-label="{escape(title)}">'
        f'<line class="baseline" x1="20" x2="{width - 10}" y1="{base}" y2="{base}"/>'
    ]
    peak = max(range(len(rows)), key=lambda i: rows[i][1]) if rows else -1
    for i, (label, value) in enumerate(rows):
        x = 26 + i * step
        h = plot_h * value / top
        parts.append(
            f'<path class="bar" d="{_vbar(x, base, col, h)}"><title>Week of {escape(label)}: '
            f"{value}</title></path>"
        )
        if i == peak and value:
            parts.append(
                f'<text class="value" x="{x + col / 2}" y="{base - h - 6:.1f}" '
                f'text-anchor="middle">{value}</text>'
            )
        if i % 2 == 0:
            parts.append(
                f'<text class="axis-label" x="{x + col / 2}" y="{base + 18}" '
                f'text-anchor="middle">{escape(_week(label))}</text>'
            )
    parts.append("</svg>")
    return "".join(parts)


def _table(headers: list[str], rows: list[list[str]]) -> str:
    head = "".join(f"<th scope='col'>{escape(h)}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{escape(c)}</td>" for c in r) + "</tr>" for r in rows)
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def _figure(
    title: str, chart: str, headers: list[str], rows: list[list[str]], note: str = ""
) -> str:
    caption = f"<figcaption>{escape(title)}</figcaption>"
    note_html = f"<p class='note'>{escape(note)}</p>" if note else ""
    return (
        f"<figure>{caption}{chart}{note_html}<details><summary>Show as a table</summary>"
        f"{_table(headers, rows)}</details></figure>"
    )


CSS = """
:root { color-scheme: light; --surface: #ffffff; --surface-2: #f4f4f5; --text: #18181b;
  --muted: #52525b; --line: #e4e4e7; --accent: #4f46e5; }
@media (prefers-color-scheme: dark) { :root { color-scheme: dark; --surface: #18181b;
  --surface-2: #27272a; --text: #fafafa; --muted: #a1a1aa; --line: #3f3f46; --accent: #6366f1; } }
* { box-sizing: border-box; }
body { margin: 0; background: var(--surface); color: var(--text);
  font: 14px/1.5 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; }
main { max-width: 1040px; margin: 0 auto; padding: 32px 16px 64px; }
h1 { font-size: 24px; margin: 0; } h2 { font-size: 16px; margin: 32px 0 12px; }
.sub { color: var(--muted); margin: 4px 0 24px; }
.tiles { display: grid; gap: 12px; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); }
.tile { background: var(--surface-2); border-radius: 10px; padding: 14px 16px; }
.tile .label { color: var(--muted); font-size: 13px; }
.tile .value { font-size: 26px; font-weight: 600; font-variant-numeric: tabular-nums; }
.grid { display: grid; gap: 24px; grid-template-columns: repeat(auto-fit, minmax(420px, 1fr)); }
figure { margin: 0; } figcaption { font-weight: 600; margin-bottom: 8px; }
.chart { width: 100%; height: auto; overflow: visible; }
.bar { fill: var(--accent); } .baseline { stroke: var(--line); stroke-width: 1; }
.axis-label { fill: var(--muted); font-size: 12px; } .value { fill: var(--text); font-size: 12px;
  font-variant-numeric: tabular-nums; }
.note { color: var(--muted); font-size: 12px; margin: 4px 0 0; }
details { margin-top: 6px; color: var(--muted); font-size: 13px; }
table { width: 100%; border-collapse: collapse; font-size: 13px; color: var(--text); }
th, td { text-align: left; padding: 6px 8px; border-bottom: 1px solid var(--line); }
th { color: var(--muted); font-weight: 500; }
td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; }
input[type=search] { width: 100%; max-width: 360px; padding: 8px 10px; border-radius: 8px;
  border: 1px solid var(--line); background: var(--surface); color: var(--text); font: inherit; }
.empty { color: var(--muted); }
"""

SEARCH_JS = """
const box = document.getElementById("q");
const rows = [...document.querySelectorAll("#apps tbody tr")];
const count = document.getElementById("shown");
box.addEventListener("input", () => {
  const q = box.value.trim().toLowerCase();
  let n = 0;
  for (const row of rows) {
    const hit = !q || row.textContent.toLowerCase().includes(q);
    row.hidden = !hit;
    if (hit) n++;
  }
  count.textContent = n;
});
"""

CSP = (
    "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; "
    "img-src data:; base-uri 'none'; form-action 'none'"
)


def _pct(value: float | None) -> str:
    return "\N{EN DASH}" if value is None else f"{round(value * 100)}%"


def render_report(insights: Insights, board: Board, name: str | None, now: datetime) -> str:
    t = insights.totals
    tiles = [
        ("Applications", str(t.applications)),
        ("Applied", str(t.applied)),
        ("Response rate", _pct(t.response_rate)),
        ("Interviews", str(t.interviews)),
        ("Offers", str(t.offers)),
        ("Jobs found", f"{t.jobs:,}"),
    ]
    tiles_html = "".join(
        f"<div class='tile'><div class='label'>{escape(label)}</div>"
        f"<div class='value'>{escape(value)}</div></div>"
        for label, value in tiles
    )

    funnel_rows = [
        (
            step.label,
            float(step.count),
            f"{step.count}"
            + (
                f" ({_pct(step.rate_from_previous)})" if step.rate_from_previous is not None else ""
            ),
        )
        for step in insights.funnel
    ]
    funnel = _figure(
        "Pipeline funnel",
        bar_chart("Pipeline funnel", funnel_rows),
        ["Stage", "Reached", "From previous"],
        [[s.label, str(s.count), _pct(s.rate_from_previous)] for s in insights.funnel],
        "Applications that reached each stage, and the share that moved on from the stage before.",
    )

    stage_counts = Counter(card.stage for column in board.columns for card in column.cards)
    stages = [*ACTIVE, *CLOSED]
    by_stage = _figure(
        "Applications by stage now",
        bar_chart(
            "Applications by stage now",
            [
                (LABELS.get(s.value, s.value.title()), float(stage_counts[s]), str(stage_counts[s]))
                for s in stages
            ],
        ),
        ["Stage", "Applications"],
        [[s.value.title(), str(stage_counts[s])] for s in stages],
    )

    sources = insights.by_source
    by_source = _figure(
        "Response rate by source",
        bar_chart(
            "Response rate by source",
            [(s.source, s.rate, f"{_pct(s.rate)} of {s.applied}") for s in sources],
            max_value=1.0,
        )
        if sources
        else "<p class='empty'>No applications sent yet.</p>",
        ["Source", "Applied", "Responses", "Rate"],
        [[s.source, str(s.applied), str(s.responses), _pct(s.rate)] for s in sources],
        "A response is a screen, an interview, an offer, or a rejection.",
    )

    weekly = _figure(
        "Applications sent per week",
        column_chart(
            "Applications sent per week", [(w.week_start, w.applied) for w in insights.weekly]
        ),
        ["Week of", "Applied", "Jobs found"],
        [[w.week_start, str(w.applied), str(w.jobs_found)] for w in insights.weekly],
        "Last 12 weeks, weeks starting Monday.",
    )

    rows = sorted(
        (card for column in board.columns for card in column.cards),
        key=lambda c: (c.stage.value, -(c.score or 0)),
    )
    table_rows = "".join(
        "<tr>"
        f"<td>{escape(c.company)}</td><td>{escape(c.title)}</td>"
        f"<td>{escape(LABELS.get(c.stage.value, c.stage.value.title()))}</td>"
        f"<td class='num'>{'' if c.score is None else c.score}</td>"
        f"<td>{escape(c.source)}</td>"
        f"<td>{escape(c.applied_at.date().isoformat()) if c.applied_at else ''}</td>"
        f"<td class='num'>{c.days_in_stage}</td>"
        "</tr>"
        for c in rows
    )
    who = f" for {escape(name)}" if name else ""
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="{CSP}">
<title>Job search report{who}</title>
<style>{CSS}</style>
</head>
<body>
<main>
<h1>Job search report{who}</h1>
<p class="sub">Generated {escape(now.strftime("%d %B %Y"))} by Offerbound.
Everything is in this file; it makes no network requests.</p>
<div class="tiles">{tiles_html}</div>
<div class="grid">
<section>{funnel}</section>
<section>{by_stage}</section>
<section>{by_source}</section>
<section>{weekly}</section>
</div>
<h2>Applications</h2>
<label for="q" class="sub">Search</label>
<input id="q" type="search" placeholder="Company, title, stage, or source" autocomplete="off">
<p class="sub"><span id="shown">{len(rows)}</span> of {len(rows)} shown</p>
<table id="apps">
<thead><tr><th scope="col">Company</th><th scope="col">Title</th><th scope="col">Stage</th>
<th scope="col" class="num">Fit</th><th scope="col">Source</th><th scope="col">Applied</th>
<th scope="col" class="num">Days in stage</th></tr></thead>
<tbody>{table_rows}</tbody>
</table>
</main>
<script>{SEARCH_JS}</script>
</body>
</html>
"""
