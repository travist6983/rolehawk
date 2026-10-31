# Offerbound AI: Spec + Build Prompts

Oct 31, 2026 · @Travis Terry

## Overview and scope

A free, open source, local-first job search copilot: a React dashboard plus Python backend that builds a candidate profile, finds and ranks jobs, tailors CVs and cover letters, preps interviews, and tracks outcomes, all driven by Claude with persistent memory.

**Goals**

- A non-developer goes from zero to a ranked shortlist in under 20 minutes using one install command.
- Every AI output is reviewable before it reaches an employer.
- All user data stays on the user's machine in readable files and one SQLite database.
- The codebase is clean enough to serve as a portfolio piece for the author.

**Non-goals**

- No hosted SaaS, accounts, or telemetry.
- No browser extension in v1.
- No guaranteed coverage of any single job board.

**Release plan**

| Release | Commands | Target |
| --- | --- | --- |
| v1.0 | /setup, /scrape, /rank, /apply, /html-report, /reset, /add-portal, chat with memory | 2 weeks |
| v1.1 | /outcome, /gmail-sync, /interview, /add-template | +2 weeks |
| v2.0 | /notion-sync, /expand, /upskill, gated auto-submit | later |

The v1 cut is deliberate: job search remains the author's top priority, so v1 must be useful for his own search in week 2, not week 10.

**Name and branding**

The product is **Offerbound AI**: a memorable brand plus "AI" for search traffic, since job seekers search "AI job search" and GitHub ranks on name, description, and topics.

| Item | Value |
| --- | --- |
| Product name | Offerbound AI |
| GitHub repo slug | offerbound-ai-job-search |
| Repo description | Free, open source AI job search copilot. Finds, ranks, and applies to jobs with Claude. Runs locally. |
| GitHub topics | ai, llm, job-search, resume, cover-letter, claude, career, automation |
| CLI command | offerbound |
| Python package | offerbound |
| Data folder | \~/Offerbound (Windows: %USERPROFILE%/Offerbound) |
| App install folder | \~/.offerbound/app |
| Env override | OFFERBOUND\_HOME |
| Database file | offerbound.db |

Before Chunk 1, confirm the name is free on GitHub, PyPI, npm, and a .dev or .app domain.

## Decision log

Thirteen decisions are locked; four carry guardrails because the author chose the riskier option.

| Area | Decision | Guardrail |
| --- | --- | --- |
| Frontend | React + Vite + TypeScript + Tailwind + shadcn/ui | None |
| Backend | Python 3.12 + FastAPI, managed by uv | None |
| Claude access | Both: Anthropic API key and Claude Agent SDK using the user's Claude Code login | Single LLMProvider interface from day one |
| Install | One-line script: bash for Mac/Linux, PowerShell for native Windows | CI on all three OSes before each release |
| Job sources | ATS APIs + feeds by default, LinkedIn and Indeed scraping included | Scraping is opt-in, off by default, runs in the user's own browser with human pacing and a ban-risk warning |
| /apply depth | Draft, auto-fill, and optional full auto-submit | Auto-submit ships in v2 behind fit-score minimum, daily cap of 5, and mandatory preview of custom answers |
| Documents | DOCX and PDF | PDF via Playwright Chromium from HTML; DOCX via python-docx; no Word or LibreOffice dependency |
| Gmail | IMAP + app password | Password stored in OS keychain via keyring, never on disk |
| Storage | SQLite for structured data + markdown memory files | No vector DB in v1; SQLite FTS5 for search |
| Models | User picks one model for everything | Default "Smart routing" toggle is on: small model for ranking, best model for writing; turning it off uses the one chosen model; a monthly spend estimate shows before batch jobs |
| Markets | Global, user sets country | Sources tagged by country; per-country defaults table |
| UI | Dashboard/kanban first, chat as a drawer | Chat drawer reachable from every screen via Cmd/Ctrl+K |

**Advisor dissent on record.** LinkedIn scraping risks users' accounts, and auto-submit risks spam signals that hurt the repo as a portfolio piece. Both are built behind the guardrails above rather than as defaults.

**Added after review: browser agent.** Use a Claude-driven browser wherever scripted automation can't finish a task, as tier 4 behind APIs, structured data, and scripted Playwright, with recipes that convert agent runs into scripts. See Browser agent fallback.

## Architecture

One Python service layer owns all logic; the dashboard, chat drawer, and Claude Code skills are thin callers, so every command behaves identically wherever it is run.

&#91;embedded content: system architecture · 3 callers, 1 service layer, 4 backends\]

Dashed boxes are external services; only the local data folder holds user data.

- **Frontend:** React 18, Vite, TypeScript strict, Tailwind, shadcn/ui, TanStack Query, React Router, dnd-kit, Recharts. Shipped prebuilt, so users never need Node.
- **Backend:** Python 3.12, FastAPI, SQLAlchemy 2.0, Alembic, pydantic v2, httpx, Playwright, python-docx, Jinja2, keyring, imap-tools. Managed by uv.
- **Long jobs:** scrape, rank, and apply run as background tasks with progress over Server-Sent Events.
- **LLM layer:** one `LLMProvider` interface with two backends (Anthropic API key, Claude Agent SDK), structured outputs via pydantic schemas, every call logged for cost.
- **Skills:** `skills/<command>/SKILL.md` files call `offerbound run <command> --json`, which hits the same services.

## Data model and memory

All state lives in one user data folder: a SQLite database for anything queried or counted, and markdown files for anything Claude or the user should read in full.

**Data folder** (`~/Offerbound` on Mac/Linux, `%USERPROFILE%\Offerbound` on Windows)

```
Offerbound/
  offerbound.db            # SQLite, WAL mode
  memory/
    profile.md              # canonical candidate profile, human-editable
    preferences.md          # titles, locations, salary floor, deal-breakers
    facts.md                # durable facts learned in chat
    sessions/YYYY-MM-DD.md  # rolling chat summaries
  documents/
    source/                 # uploaded resumes, syllabi, LinkedIn export
    generated/<app_id>/     # cv.docx, cv.pdf, cover.docx, cover.pdf, answers.md
  templates/<template_id>/  # template.html + template.docx + manifest.json
  portals/<portal_id>.py    # user-added portal plugins
  reports/                  # exported HTML dashboards
  config.toml               # non-secret settings
```

**Core tables**

| Table | Key columns | Notes |
| --- | --- | --- |
| profile\_items | id, kind (experience, education, skill, project, cert, achievement), data JSON, source, confidence, updated\_at | Mirrors profile.md; regenerated on edit |
| search\_targets | id, title, seniority, locations JSON, remote\_policy, country, salary\_min, keywords JSON, exclude JSON, active | Drives /scrape |
| portals | id, name, kind (ats, feed, scraper, plugin), country, enabled, risk\_level, config JSON | risk\_level gates scrapers |
| jobs | id, portal\_id, external\_id, url, company, title, location, remote, salary\_text, description, posted\_at, scraped\_at, hash | Unique on (portal\_id, external\_id) and on hash for cross-portal dedupe |
| job\_scores | job\_id, run\_id, score 0-100, must\_have\_gaps JSON, reasons JSON, model | One row per rank run |
| applications | id, job\_id, stage, applied\_at, method (manual, autofill, autosubmit), cv\_path, cover\_path, notes | Kanban source of truth |
| stage\_events | id, application\_id, from\_stage, to\_stage, source (user, gmail, outcome), evidence, created\_at | Full history; gmail proposals land as pending |
| interviews | id, application\_id, stage, scheduled\_at, prep\_pack\_path, mock\_transcript\_path, self\_rating | /interview |
| outcomes | id, application\_id, result, feedback, follow\_up\_draft, archived\_at | /outcome |
| llm\_calls | id, command, model, input\_tokens, output\_tokens, cost\_usd, created\_at | Powers spend estimate and cap |
| chat\_messages | id, session\_id, role, content, created\_at | Summarized into sessions/\*.md nightly or at 40 messages |

Stages: Saved, Applying, Applied, Screen, Interview, Offer, Rejected, Withdrawn, Ghosted.

**Memory strategy**

- Every Claude call gets a context pack: profile.md, preferences.md, facts.md, the last session summary, and any rows the command needs (pulled with SQL or FTS5).
- After each chat turn, a cheap model call extracts durable facts as proposed diffs to facts.md or profile.md; the UI shows them as accept/reject chips. Nothing changes silently.
- Pipeline questions in chat ("who did I apply to at fintechs last month?") use tool calls that run read-only SQL views, not memory text.
- Retain chat messages for 30 days by default; summaries are kept.

## Command specs

Every command is available three ways: a button in the dashboard, a slash command in the chat drawer, and a Claude skill file (`skills/<command>/SKILL.md`) so Claude Code users can run it from the terminal against the same data folder. Each command is a backend service function first; UI, chat, and skills are thin callers.

**/setup** (v1.0)

- Input: uploaded resume (PDF, DOCX, TXT), pasted CV text, LinkedIn data export ZIP, or none.
- Flow: parse documents to structured profile\_items, then run a gap interview: Claude asks one question at a time, multiple choice where possible, covering missing dates, metrics for achievements, target titles, locations, remote preference, salary floor, work authorization, and deal-breakers.
- Output: profile.md, preferences.md, at least one search\_target.
- Accept when: a user with no resume can finish by interview alone in under 15 minutes; re-running /setup edits rather than duplicates.

**/scrape** (v1.0)

- Input: active search\_targets, enabled portals.
- Flow: run each portal adapter concurrently with per-portal rate limits; normalize to jobs; dedupe by external\_id then by hash of normalized company + title + location.
- Output: new jobs rows, a run summary (found, new, duplicates, errors per portal).
- Accept when: one failing portal never fails the run; progress streams to the UI via SSE.

**/rank** (v1.0)

- Input: a scrape run or any job filter.
- Flow: hard filters first in SQL (location, remote, salary, exclude keywords); then batch LLM scoring of up to 20 jobs per call using structured output: score, must-have gaps, top 3 reasons.
- Output: job\_scores rows, a ranked shortlist view.
- Accept when: 200 jobs rank in under 3 minutes; cost estimate shows before running.

**/apply** (v1.0 draft + autofill, v2.0 auto-submit)

- Flow: fit check (stop with an explanation below a user-set threshold, default 60); draft tailored CV and cover letter; a second Claude pass reviews the drafts against the job and the truth of profile.md, flagging any claim not supported by the profile; compile DOCX and PDF from the chosen template.
- Hard rule: generated documents may rephrase and reorder, but never invent employers, titles, dates, degrees, or metrics.
- Autofill: Playwright opens the application page in a visible browser, fills known fields, and stops before submit.
- Output: files under documents/generated/\<app\_id>/, an applications row at stage Applying.

**/rank** and **/apply** share one fit rubric so scores match.

**/interview** (v1.1)

- Input: application and stage (recruiter screen, hiring manager, technical, behavioral, final).
- Output: prep pack (company brief, likely questions, STAR stories mapped from the profile, questions to ask) as markdown and PDF; then a mock interview in the chat drawer, text by default, with a scored debrief.

**/outcome** (v1.1)

- Records result and feedback, archives the exact documents sent, drafts a follow-up or thank-you note in three tones (warm, concise, assertive).

**/gmail-sync** (v1.1)

- Reads only messages from the last N days matching applied companies or ATS sender domains; classifies each as confirmation, rejection, interview request, offer, or other; writes proposed stage\_events with status pending. The user approves each change. Never sends mail.

**/html-report** (v1.0)

- One self-contained HTML file with pipeline funnel, applications by stage and week, response rate by source, and a searchable table. No network requests.

**/add-template** (v1.1)

- User uploads a DOCX; Claude maps its sections to template placeholders and produces a matching HTML twin for PDF output; user previews both before saving.

**/add-portal** (v1.0)

- User pastes a job board URL; Claude inspects it and generates a portal plugin (see Job sources), runs a test fetch, and shows 5 sample jobs before enabling.

**/reset** (v1.0)

- Choices: profile only, documents only, jobs and scores, applications history, everything. Typed confirmation required; makes a zipped backup first.

**/notion-sync, /expand, /upskill** (v2.0)

- /notion-sync: one-way publish of a read-only pipeline database via Notion integration token.
- /expand: read public GitHub, portfolio site, and pasted course syllabi; propose new skills as accept/reject diffs.
- /upskill: compare top 50 ranked jobs' requirements to the profile; output a gap table and a 4 to 8 week learning plan with free resources.

## Job sources and portal plugins

Every source is a plugin implementing one interface, with a risk level that decides whether it can be on by default. Endpoints below are the author's best knowledge and must be verified in Chunk 6 before shipping.

```python
class Portal(Protocol):
    id: str
    name: str
    kind: Literal["ats", "feed", "scraper", "plugin"]
    countries: list[str]          # ISO codes, or ["*"]
    risk_level: Literal["low", "medium", "high"]
    requires: list[str]           # e.g. ["api_key:adzuna", "browser"]
    async def search(self, target: SearchTarget, since: datetime | None) -> AsyncIterator[RawJob]: ...
    def normalize(self, raw: RawJob) -> Job: ...
```

**Built-in sources**

| Source | Kind | Coverage | Default | Risk |
| --- | --- | --- | --- | --- |
| Greenhouse job board API | ats | Global, per company slug | On | Low |
| Lever postings API | ats | Global, per company slug | On | Low |
| Ashby job board API | ats | Global, per company slug | On | Low |
| Workable widget API | ats | Global, per company slug | On | Low |
| RemoteOK JSON feed | feed | Remote, global | On | Low |
| We Work Remotely RSS | feed | Remote, global | On | Low |
| Adzuna API (free key) | feed | \~20 countries | On if key set | Low |
| USAJOBS API (free key) | feed | US federal | On if country US and key set | Low |
| Indeed | scraper | Global | Off | High |
| LinkedIn Jobs | scraper | Global | Off | High |

**Company watchlist.** ATS sources search by company, not keyword. Ship a curated starter list of about 500 company slugs per ATS in `data/companies/*.csv`, let users add companies, and let /setup suggest companies from the user's industry.

**High-risk scrapers (LinkedIn, Indeed)**

- Off by default. Enabling shows a modal: "Automated access breaks these sites' terms. Your account can be restricted. Use a secondary browser profile." User must tick a checkbox.
- Run in a visible Playwright browser using a persistent profile the user logs into themselves. The app never stores their credentials.
- Human pacing: 8 to 20 second randomized delays, max 100 listings per run, max 2 runs per day per site.
- Search results only; no profile visits, no messaging, no Easy Apply automation.
- Selectors live in a versioned JSON file so fixes ship without code changes; on breakage, the portal disables itself and shows a clear status.

**/add-portal plugin generation**

- Claude fetches the URL, detects JSON endpoints, RSS, or embedded JSON-LD JobPosting data, and prefers those over HTML parsing.
- Generates `portals/<id>.py` from a template, validated by a test run that must return at least 3 normalized jobs.
- Plugins run in a subprocess with a timeout and network-only access; the UI shows the source code before enabling.

**Country defaults.** A `data/country_sources.toml` maps each country to recommended feeds (for example Adzuna in the UK, AU, DE, IN; USAJOBS in the US) and the currency and salary period for that market.

## Browser agent fallback

Claude drives a real browser whenever no API, feed, or scripted flow can finish a task, but always as the last tier: each agent step is a model call, so it is far slower and costlier than scripted automation.

| Tier | Method | Used for | LLM cost |
| --- | --- | --- | --- |
| 1 | API or feed (httpx) | ATS boards, RSS, Adzuna | None |
| 2 | Structured page data (JSON-LD, embedded JSON) | Company career pages | None |
| 3 | Scripted Playwright with versioned selectors | LinkedIn/Indeed search, known ATS autofill | None |
| 4 | Browser agent: Claude reads the page and chooses actions | Unknown career sites, Workday and custom forms, multi-step portals, /add-portal discovery, /interview company research | One call per step |

**Learn once, script after.** When the agent completes a task on a site, it records the working path (URLs, selectors, field mapping) as a tier 3 recipe in `portals/recipes/<domain>.json`. The next run replays the recipe without the agent and falls back to the agent only if the recipe breaks, then repairs it.

**Where it plugs in**

- /scrape: a portal adapter that fails or returns zero results on a site that showed jobs before hands off to the agent.
- /apply autofill: scripted filling for Greenhouse, Lever, and Ashby; the agent handles Workday, iCIMS, Taleo, and custom forms, then stops before submit.
- /add-portal: the agent explores the site first, then generates a tier 2 or 3 plugin.
- /interview: the agent browses the company site, news, and engineering blog to build the company brief.

**Implementation**

- One `BrowserAgent` service with a tool set: navigate, snapshot (accessibility tree), screenshot, click, type, select, upload\_file, scroll, wait, done, ask\_user.
- Accessibility-tree snapshots by default; screenshots only when the tree is empty or ambiguous, to cut tokens.
- API-key path: the Anthropic tool-use loop against Playwright (check whether Anthropic's computer use tool fits better at build time). Claude Code path: the Playwright MCP server. Verify current tool names in official docs.
- A Watch panel in the UI streams each step (screenshot thumbnail + action + reason) with Pause, Take over, and Stop buttons.

**Guardrails**

- Step budget per task (default 40) and a per-task cost cap, with an estimate shown first.
- An allowed-domain list per task; leaving it requires the user's OK.
- The agent never submits applications, pays, sends messages, accepts terms, or creates accounts without an explicit confirmation click in the UI.
- The agent never types passwords: login and CAPTCHAs hand control to the user via Take over.
- Page text is untrusted data; instructions found on pages are ignored and logged as suspicious.
- Each run saves its step log and screenshots to `documents/agent-runs/<id>/`, auto-deleted after 14 days.

## UI spec

The app opens on a kanban board of applications; chat is a right-side drawer available on every screen, and every long-running command shows live progress rather than a spinner.

**Screens**

| Screen | Purpose | Key elements |
| --- | --- | --- |
| Onboarding | First run | 4 steps: connect Claude, upload resume, gap interview, pick sources. Progress bar, skip allowed except step 1 |
| Pipeline (home) | Track applications | Kanban columns per stage, drag to move, card shows company, title, score badge, days in stage, next action |
| Discover | Review scraped jobs | Ranked table with score, filters, bulk actions (Save, Dismiss, Apply), job detail side panel with fit reasons and gaps |
| Application detail | One job end to end | Tabs: Job, Documents (side-by-side DOCX/PDF preview, regenerate, edit), Interview prep, Timeline, Emails |
| Profile | Source of truth | Editable profile.md rendered as sections, memory facts with accept/reject, search targets editor |
| Sources | Manage portals | Card per portal: status, last run, jobs found, risk badge, enable toggle, "Add portal" button |
| Insights | Lightweight analytics | Funnel, response rate by source, weekly activity, spend this month; "Export HTML report" |
| Settings | Config | Claude connection (API key or Claude Code), model, smart routing toggle, spend cap, Gmail, templates, data folder, reset |

**Chat drawer**

- Opens with Cmd/Ctrl+K or a floating button; 420px wide on desktop, full screen below 768px.
- Slash command menu with descriptions; commands render rich cards (job card, document preview, stage change proposal) with action buttons.
- Context chip shows what the chat is looking at ("Viewing: Stripe, Senior Frontend") so "tailor my CV for this" works without naming the job.
- Proposed memory updates appear inline as accept/reject chips.

**Design system**

- shadcn/ui on Tailwind, Inter for UI text, JetBrains Mono for code and IDs.
- Light and dark themes from CSS variables, following the OS by default.
- Neutral zinc base, one accent (indigo 600), semantic colors only for stage and score: 80+ green, 60 to 79 amber, below 60 zinc.
- Motion: 150ms ease-out on drawer and card moves; respect prefers-reduced-motion.
- Accessibility: WCAG 2.1 AA contrast, full keyboard kanban (arrow keys plus Space to pick up), visible focus rings, aria-live for streaming progress.
- Empty states that teach: the empty Pipeline shows the 3 steps to the first application, each a button.

## Installer and first run

A non-developer pastes one line, waits about 3 minutes, and a browser tab opens on the onboarding screen; nothing else is installed by hand.

**The one line**

```bash
# Mac / Linux
curl -fsSL https://raw.githubusercontent.com/<owner>/<repo>/main/install.sh | bash
```

```powershell
# Windows (PowerShell)
irm https://raw.githubusercontent.com/<owner>/<repo>/main/install.ps1 | iex
```

**What the script does**

1. Detect OS and CPU architecture; print plainly what it will install and where.
2. Install `uv` into the user's home folder if missing (no admin rights).
3. Download the latest release ZIP (not a git clone, so no git required) into `~/.offerbound/app`.
4. `uv sync` installs a pinned Python 3.12 and backend dependencies.
5. Install Playwright Chromium (about 150 MB) into the app folder.
6. The frontend ships prebuilt as static files inside the release, so Node is never required for users.
7. Create the data folder, a desktop shortcut, and the `offerbound` command.
8. Start the backend on 127.0.0.1 and open the browser.

**Daily use**

- `offerbound` (or the desktop shortcut) starts the app; `offerbound update` pulls the newest release and runs migrations after a backup; `offerbound doctor` prints a diagnostics report users can paste into a GitHub issue.

**Claude connection step**

- Option A, API key: link to the Anthropic Console, paste key, test call, key stored in OS keychain.
- Option B, Claude Code: detect an existing `claude` login; if absent, show the official install command and a "Check again" button.
- Show estimated monthly cost for typical use (about 50 jobs ranked and 10 applications per week) next to each option.

**Release engineering**

- GitHub Actions builds the frontend, bundles the release ZIP, and runs install plus a smoke test on macos-latest, ubuntu-latest, and windows-latest on every tag.
- README opens with a 60-second GIF, the two install lines, and a "What it costs" table.

## Security, privacy and guardrails

The app handles resumes, salary history, and email access, so the default posture is local-only, explicit consent, and no silent writes to anything outside the data folder.

- **Network:** the backend binds to 127.0.0.1 only; a random session token in the launch URL protects the API from other local web pages (CSRF and DNS rebinding).
- **Secrets:** API keys, Gmail app password, and Notion token live in the OS keychain via `keyring`; config.toml never contains secrets; logs redact them.
- **Outbound data:** only to Anthropic, the enabled job sources, Gmail IMAP, and Notion when enabled. No analytics. A Settings page lists every destination.
- **Truthfulness:** the /apply reviewer pass rejects drafts containing employers, titles, dates, degrees, certifications, or numbers absent from profile.md; flagged lines are highlighted for the user.
- **Prompt injection:** job descriptions and emails are untrusted text. They go in clearly delimited blocks, never in system prompts, and tool calls triggered while processing them are limited to read-only actions.
- **Auto-submit (v2):** off by default; requires fit score at or above the user's threshold, max 5 per day, preview of every custom-question answer, and a per-job confirmation the first 10 times.
- **Scrapers:** consent modal, user-owned browser session, pacing limits, no credential storage (see Job sources).
- **Plugins:** generated portal code is shown before enabling and runs in a subprocess with a timeout.
- **Spend:** optional monthly cap; batch commands show an estimate and stop at the cap.
- **Legal:** MIT license, plus a DISCLAIMER.md stating that users are responsible for complying with each site's terms and that the tool provides no employment or legal advice.

## Build plan and Claude Code prompts

Thirteen chunks reach v1.0; run them in order, one Claude Code session each, committing and testing after every chunk. Paste this spec into the repo as `docs/SPEC.md` first: every prompt points at it.

| # | Chunk | Depends on | Release |
| --- | --- | --- | --- |
| 1 | Repo scaffold + CLAUDE.md | None | v1.0 |
| 2 | Backend core + database | 1 | v1.0 |
| 3 | LLM provider layer + memory | 2 | v1.0 |
| 4 | Frontend shell + chat drawer | 2 | v1.0 |
| 5 | /setup + Profile screen | 3, 4 | v1.0 |
| 6 | Portals + /scrape + Sources screen | 2, 4 | v1.0 |
| 7 | /rank + Discover screen | 3, 6 | v1.0 |
| 8 | Templates + DOCX/PDF rendering | 2 | v1.0 |
| 9 | /apply + Application detail + autofill | 7, 8 | v1.0 |
| 10 | Pipeline kanban + Insights + /html-report + /reset | 9 | v1.0 |
| 11 | /add-portal | 6 | v1.0 |
| 12 | Installer + CI + README | all above | v1.0 |
| 13 | Opt-in LinkedIn/Indeed scrapers | 6 | v1.0 |
| 14 | /outcome + /gmail-sync | 10 | v1.1 |
| 15 | /interview | 9 | v1.1 |
| 16 | /add-template | 8 | v1.1 |

**Chunk 1: Repo scaffold + CLAUDE.md**

```text
Read docs/SPEC.md fully. Create a monorepo:
- backend/ (Python 3.12, FastAPI, uv, ruff, pytest, mypy strict)
- frontend/ (React 18, Vite, TypeScript strict, Tailwind, shadcn/ui, TanStack Query, React Router, Vitest)
- skills/ (one folder per command with SKILL.md stubs)
- scripts/ (install.sh, install.ps1 stubs), data/ (companies/, country_sources.toml)
Write CLAUDE.md with: architecture summary, folder map, commands to run/test/lint, coding rules (services hold logic; API routes and chat tools are thin; no secrets in files; never invent profile facts in generated docs).
Add cross-platform task scripts run via `uv run` and npm scripts (no Makefile, so Windows works). Add .github/workflows/ci.yml running lint and tests on ubuntu, macos, windows.
Done when: `uv run pytest` and `npm test` pass on an empty test each, and CI is green.
```

**Chunk 2: Backend core + database**

```text
Using docs/SPEC.md "Data model and memory":
- Implement the data folder resolver (Mac/Linux/Windows paths, overridable via env OFFERBOUND_HOME).
- SQLAlchemy 2.0 models for every core table; Alembic migrations; SQLite in WAL mode; FTS5 virtual table over jobs(title, company, description).
- config.toml loader (pydantic-settings) and a secrets module wrapping `keyring`.
- FastAPI app bound to 127.0.0.1, random session token required on every request (header or cookie set from launch URL).
- SSE endpoint /api/events for streaming job progress; a simple background job runner (asyncio tasks + jobs table status).
- Auto-backup: zip the data folder before migrations.
Write tests for path resolution on all OSes (mocked), migrations up/down, token auth, and the job runner.
```

**Chunk 3: LLM provider layer + memory**

```text
Implement backend/llm/ per docs/SPEC.md:
- LLMProvider protocol: complete(), stream(), structured(schema) -> pydantic model, with tool-use support.
- AnthropicAPIProvider using the official anthropic SDK; ClaudeCodeProvider using the Claude Agent SDK and the user's existing Claude Code login. Detect availability of each.
- Model routing: settings.model plus settings.smart_routing; a route(task) function returning a model per task type (rank, extract, write, review, chat).
- Cost tracking: log every call to llm_calls with tokens and estimated cost; enforce optional monthly cap; estimate() for batch jobs.
- Memory: context_pack(command, ids) assembling profile.md, preferences.md, facts.md, latest session summary, and requested rows. Fact extraction after chat turns returning proposed diffs, never writing directly.
- Chat service with tools: run_command, query_pipeline (read-only SQL views), propose_memory_update.
- Write skills/*/SKILL.md so Claude Code can call the same services through a small CLI (`offerbound run <command> --json`).
Look up current model IDs and SDK APIs from official docs rather than memory. Tests use a FakeProvider.
```

**Chunk 4: Frontend shell + chat drawer**

```text
Build the React shell per docs/SPEC.md "UI spec":
- Layout with left nav (Pipeline, Discover, Profile, Sources, Insights, Settings), theme toggle, and the chat drawer (Cmd/Ctrl+K).
- Typed API client generated from FastAPI OpenAPI (openapi-typescript); auth token read from launch URL then stored in memory.
- SSE hook for progress events; a global toast + progress tray for running jobs.
- Chat drawer: streaming messages, slash command menu, rich card renderer registry (job, document, stage proposal, memory proposal), context chip from current route.
- Empty-state components and skeleton loaders for every screen.
Use the design system rules in the spec. Add Vitest + Testing Library tests for the drawer, slash menu, and SSE hook. Run the frontend skill's guidance before styling.
```

**Chunk 5: /setup + Profile screen**

```text
Implement /setup per docs/SPEC.md:
- Parsers: PDF (pypdf + pdfplumber fallback), DOCX (python-docx), TXT, LinkedIn export ZIP (CSV files).
- Extraction to profile_items via structured output; write profile.md and preferences.md.
- Gap interview engine: computes missing fields, asks one question at a time, prefers multiple choice, accepts free text, resumable.
- Onboarding wizard steps 2 and 3 in the UI, and the Profile screen with inline editing and memory accept/reject chips.
Acceptance: setup by interview alone works with no resume; re-running edits existing items. Include fixture resumes in tests.
```

**Chunk 6: Portals + /scrape + Sources screen**

```text
Implement the Portal protocol and built-in sources from docs/SPEC.md "Job sources".
First, verify each endpoint (Greenhouse, Lever, Ashby, Workable, RemoteOK, We Work Remotely, Adzuna, USAJOBS) against its current public docs and record the URL and date in backend/portals/SOURCES.md. Drop any that no longer work and tell me.
- Concurrent scrape runner with per-portal rate limits, retries with backoff, per-portal error isolation.
- Normalization and dedupe (external_id, then normalized hash).
- Company watchlist CSVs with a starter list and an import UI.
- Sources screen with status cards, enable toggles, risk badges, API key inputs.
Tests use recorded HTTP fixtures (respx/vcrpy), never live calls in CI.
```

**Chunk 7: /rank + Discover screen**

```text
Implement /rank per docs/SPEC.md: SQL hard filters, then batched structured scoring (20 jobs per call) with a shared fit rubric module also used by /apply. Show cost estimate before running. Discover screen: ranked virtualized table, filters, bulk actions, detail side panel with reasons and gaps. Acceptance: 200 fixture jobs rank in under 3 minutes with FakeProvider latency simulated.
```

**Chunk 8: Templates + DOCX/PDF rendering**

```text
Create a CV data schema (pydantic) and a renderer: Jinja2 HTML templates to PDF via Playwright Chromium page.pdf(), and python-docx builders for DOCX from the same data. Ship 3 templates (Classic, Modern, Compact) plus 2 cover letter templates, all ATS friendly (single column, real text, standard headings). Snapshot tests compare extracted text from both outputs so DOCX and PDF never diverge in content.
```

**Chunk 9: /apply + Application detail + autofill**

```text
Implement /apply per docs/SPEC.md: fit gate, draft CV and cover letter, reviewer pass enforcing the truthfulness rule (flag any employer, title, date, degree, cert, or number not in profile.md), render via Chunk 8, create applications row. Application detail screen with side-by-side preview, inline edit, regenerate per section. Autofill: Playwright visible browser, fill common ATS fields (Greenhouse, Lever, Ashby, Workday), upload files, stop before submit, record method=autofill. No auto-submit code in v1.
```

**Chunk 10: Pipeline kanban + Insights + /html-report + /reset**

```text
Pipeline screen: kanban with dnd-kit, keyboard support, stage_events on every move, card details per spec. Insights: funnel, response rate by source, weekly activity, monthly spend (Recharts). /html-report: single self-contained HTML file with inlined data and charts, no network requests. /reset with scope choices, typed confirmation, and backup first.
```

**Chunk 11: /add-portal**

```text
Implement /add-portal: fetch URL, detect JSON API, RSS, or JSON-LD JobPosting before HTML parsing; generate portals/<id>.py from a template; run in a subprocess sandbox with timeout; require 3+ normalized jobs in a test run; show code and samples in the UI before enabling.
```

**Chunk 12: Installer + CI + README**

```text
Write scripts/install.sh and scripts/install.ps1 per docs/SPEC.md "Installer": install uv without admin, download the release ZIP, uv sync, install Playwright Chromium, create data folder, desktop shortcut, and `offerbound` command with start, update, doctor subcommands. Release workflow builds the frontend, bundles the ZIP, and smoke-tests install on macos, ubuntu, windows runners. README: GIF placeholder, two install lines, cost table, FAQ, troubleshooting, DISCLAIMER.md, MIT LICENSE, CONTRIBUTING.md.
```

**Chunk 13: Opt-in LinkedIn/Indeed scrapers**

```text
Implement high-risk scrapers per docs/SPEC.md guardrails exactly: off by default, consent modal, persistent user-owned Playwright profile, no credential storage, 8 to 20s randomized delays, 100 listings and 2 runs per day caps, search results only, selectors in versioned JSON, self-disable on breakage with a clear status. Mark both as experimental in the UI and README.
```

**Chunk 13b: Browser agent fallback** (after Chunks 6 and 9)

```text
Implement the BrowserAgent service per docs/SPEC.md "Browser agent fallback":
- Tool set (navigate, snapshot, screenshot, click, type, select, upload_file, scroll, wait, done, ask_user) over Playwright, accessibility snapshots by default.
- Two drivers: Anthropic tool-use loop for API-key users; Playwright MCP for Claude Code users. Check current official docs for tool names and whether the computer use tool fits better.
- Guardrails exactly as specified: step budget, cost cap, allowed domains, confirmation before any submit/pay/send/accept/create-account action, user takeover for logins and CAPTCHAs, untrusted page text.
- Recipe recorder: on success, save a replayable tier 3 recipe to portals/recipes/<domain>.json; replay first next time, fall back to the agent and repair on failure.
- Watch panel in the UI with live step stream and Pause, Take over, Stop.
- Wire into /scrape fallback, /apply autofill for non-scripted ATS forms, /add-portal discovery, and /interview research.
Tests: run against local fixture HTML sites (a fake Workday-style multi-page form, a career page with no API) with a scripted FakeProvider; assert the agent stops before submit and records a working recipe.
```

**Chunks 14 to 16 (v1.1)** follow the same pattern from the Command specs section: /outcome + /gmail-sync (IMAP via imap-tools, proposals only), /interview (prep pack + text mock interview with scored debrief), /add-template (DOCX upload mapped to placeholders with an HTML twin).

## Open questions and v2 backlog

Five decisions are still open; none block Chunks 1 to 4.

- [ ] Project name and GitHub owner for the install URLs.
- [x] Does the Claude Agent SDK path permit use inside a distributed third-party app? **Resolved 2026-10-31: no.** The Agent SDK docs state that, unless previously approved, Anthropic does not allow third-party developers to offer claude.ai login or rate limits in their products. The in-app provider is API-key only; Claude Code users run commands through `skills/`, where their own Claude Code session does the reasoning.
- [ ] Voice mode for /interview mock sessions: v1.1 or v2?
- [ ] Should the starter company watchlist be curated by industry or by country first?
- [ ] Telemetry stays off, but do you want an opt-in "share anonymized source health" ping so broken portals get noticed faster?

**v2 backlog:** /notion-sync, /expand, /upskill, gated auto-submit, desktop app wrapper (Tauri), browser extension for one-click save from any job page, local model option via Ollama for ranking.
