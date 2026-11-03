# Job sources: endpoints and terms

Verified **2026-10-31** against each source's public documentation and a live request.
Re-verify before each release; change endpoints here and in `ats.py` / `feeds.py` together.

| Source | Endpoint (public unless noted) | Docs | Live check | Notes |
| --- | --- | --- | --- | --- |
| Greenhouse | `GET https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true` | [developers.greenhouse.io/job-board.html](https://developers.greenhouse.io/job-board.html) (now redirects to docs.greenhouse.io) | 200 | No auth for GET. `content=true` adds the description, departments, offices. |
| Lever | `GET https://api.lever.co/v0/postings/{site}?mode=json` (EU: `api.eu.lever.co`) | [github.com/lever/postings-api](https://github.com/lever/postings-api) | 200 | No auth. Docs: published postings "may be scraped by third parties". We fall back to the EU host on 404. |
| Ashby | `GET https://api.ashbyhq.com/posting-api/job-board/{board}?includeCompensation=true` | [developers.ashbyhq.com/docs/public-job-posting-api](https://developers.ashbyhq.com/docs/public-job-posting-api) (updated 2026-10-23) | 200 | Docs list no `id`, but live responses include one; we fall back to `jobUrl`. `isListed=false` jobs are skipped. |
| Workable | `GET https://apply.workable.com/api/v1/widget/accounts/{subdomain}?details=true` | [help.workable.com/…/115012771647](https://help.workable.com/hc/en-us/articles/115012771647) | 200 | **Correction:** docs show `www.workable.com/api/accounts/{subdomain}?details=true`, which now 302-redirects to the endpoint we call. |
| Remote OK | `GET https://remoteok.com/api` | [remoteok.com/api](https://remoteok.com/api) (terms in the response's `legal` field) | 200 | First array element is the legal notice. **Terms:** link back to the Remote OK job URL and mention Remote OK as the source; don't use their logo. We store and show the remoteok.com URL and the source name. Some postings arrive as UTF-8 read as Latin-1 ("weâ\x80\x99re", seen 2026-11-03); `fix_mojibake` repairs them before cleaning. |
| We Work Remotely | `GET https://weworkremotely.com/remote-jobs.rss` (categories: `/categories/<slug>.rss`) | Docs page returned 403 to automated fetches; feeds verified live | 200 | Item titles are `Company: Position`. RSS parsed with DTDs refused. |
| Adzuna | `GET https://api.adzuna.com/v1/api/jobs/{country}/search/{page}?app_id=…&app_key=…&what=…` | [developer.adzuna.com/docs/search](https://developer.adzuna.com/docs/search), [terms](https://developer.adzuna.com/docs/terms_of_service) | 401 without key (expected) | Free key. Personal job search is a permitted use; show "Adzuna" with a link on listings. **Unverified:** the country list in `feeds.py` is Adzuna's published markets from prior knowledge; the docs' interactive reference didn't render. Confirm with a key. A target with a location is searched twice: `where` + `distance=40` (km, about 25 miles; without it Adzuna searches a tiny area) and `what=<title> remote` with no `where`. Results carry only a ~500-character summary, and the `redirect_url` pages answer tools with 403 (checked 2026-11-03), so the job sheet and /rank say the text is a summary. |
| USAJOBS | `GET https://data.usajobs.gov/api/search?Keyword=…` with headers `Host`, `User-Agent: <email>`, `Authorization-Key` | [developer.usajobs.gov/api-reference/get-api-search](https://developer.usajobs.gov/api-reference/get-api-search) | 401 without key (expected) | Free key. Max 500 rows/page, 10,000/query. |

No source was dropped.

## Indeed and LinkedIn

Checked **2026-11-01**.

- **Indeed: through the user's Claude connector, never scraped.** Indeed's official MCP server
  is "available only for Claude Connector" ([docs.indeed.com/mcp](https://docs.indeed.com/mcp)):
  no public server URL or OAuth client for other apps, and its partner APIs need Indeed's
  written approval. So the dashboard can't search Indeed. The `/scrape` skill in Claude Code
  searches through the user's own Indeed connector and stores the results with `jobs-import`
  (source id `indeed`): title-matched, cleaned, and deduped like any source, kept in the user's
  data folder. Use is subject to Indeed's terms.
- **LinkedIn: not searched.** Its User Agreement and robots.txt forbid automated access,
  logged in or not; the logged-out "jobs-guest" endpoints other tools call break both.
- **Either site, one job at a time:** Discover's **Add a job** (`job-add`) stores a posting the
  user found. Reading its link (`job-read-link`) is one page request through the custom-source
  `Fetcher` (public addresses, same site, robots.txt respected), so LinkedIn links are refused
  and the user pastes the text instead. Added jobs (source id `manual`) are never removed by the
  search cleanup.

## Company watchlists

ATS sources search per company. `data/companies/<ats>.csv` holds a starter list where every
row was checked live (a job board exists with open jobs) on 2026-10-31:

| ATS | Companies |
| --- | --- |
| Greenhouse | 59 |
| Ashby | 33 |
| Lever | 16 |
| Workable | 6 |

To grow or re-check the lists:

```bash
uv run python scripts/verify_watchlist.py candidates.csv   # columns: ats,slug,name,industry,country
```

Users add companies in the Sources screen; each is checked against its ATS before saving.

## Test fixtures

`tests/fixtures/portals/` holds trimmed real responses recorded 2026-10-31 (Greenhouse:
airbnb, Lever: palantir, Ashby: ramp, Workable: workmotion, Remote OK, We Work Remotely).
Adzuna and USAJOBS fixtures follow the documented response shapes (no key to record with).
Tests never make live calls.

## Custom sources (/add-portal)

Users add careers pages and job boards from the Sources screen. Detection prefers, in order:
a known ATS (added to the watchlist instead), an RSS/Atom feed the page links (job feeds
ranked first), JSON-LD `JobPosting` data on the page or on the job pages it links to, a JSON
job list (fields mapped automatically), and only then CSS selectors that Claude proposes.
A source is saved only after a sandboxed test run returns at least 3 jobs. Every page a
custom source reads is checked against the site's robots.txt first (RFC 9309: no file means
allowed, a server error means stay away), so detection and scrapes skip what a site asks
tools not to read. Live check on
2026-10-31: python.org/jobs is detected as its "Python Job Opportunities" RSS feed (20 jobs
in about 1 second through the sandbox).
