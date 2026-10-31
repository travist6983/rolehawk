# Offerbound AI

Local-first AI job search copilot: a React dashboard plus a Python backend that builds a candidate profile, finds and ranks jobs, tailors CVs and cover letters, and tracks applications, all driven by Claude. The full spec is `docs/SPEC.md`; read the relevant section before starting any chunk.

## Architecture

One Python service layer owns all logic. Three thin callers sit on top of it, so every command behaves the same wherever it runs:

1. **Dashboard** (React, `frontend/`) calls the FastAPI routes.
2. **Chat drawer** (in the dashboard) calls chat tools, which call services.
3. **Claude Code skills** (`skills/<command>/SKILL.md`) call `offerbound run <command> --json`, which calls services.

Backends behind the service layer: SQLite (`offerbound.db`, WAL, FTS5) plus markdown memory files in the user's data folder, the LLM layer (one `LLMProvider` interface; the in-app provider uses the user's Anthropic API key), job sources (portal plugins), and Playwright for PDF rendering and autofill.

**Claude access decision (2026-10-31):** Anthropic doesn't allow third-party apps to offer claude.ai login, including through the Agent SDK, so the app has no Claude Code login provider. Claude Code users get the same features through `skills/`: Claude Code does the reasoning in their own session and calls `offerbound run` for data and actions.

- The backend binds to `127.0.0.1` only. User data lives in `~/Offerbound` (Windows: `%USERPROFILE%\Offerbound`), overridable with `OFFERBOUND_HOME`. Never in the repo.
- Long jobs (scrape, rank, apply) run as background tasks with progress over SSE.
- The frontend ships prebuilt in releases; users never need Node.

## Folder map

```
backend/                 Python 3.12 package `offerbound` (uv, FastAPI)
  src/offerbound/
    paths.py             data folder resolver (OFFERBOUND_HOME, ~/Offerbound, %USERPROFILE%)
    config.py            config.toml + OFFERBOUND_* env -> Settings (unknown keys rejected)
    keychain.py          secrets via keyring; log redaction
    db/                  SQLAlchemy models, engine (WAL, FKs), FTS5 search, Alembic migrations
    llm/                 provider protocol, AnthropicProvider, FakeProvider, model catalog and
                         pricing, task routing, spend meter, LLMService (the only entry point)
    memory/              markdown memory files, proposals (accept/reject), context packs,
                         fact extraction, session summaries + retention
    profile/             typed profile + preferences, markdown parser/renderer, merge, document
                         parsing (PDF/DOCX/TXT/LinkedIn ZIP), extraction, gap interview, /setup
    chat/                chat turns (streaming, tool loop), tools, read-only pipeline SQL
    portals/             job sources: Portal protocol, ATS boards (Greenhouse, Lever, Ashby,
                         Workable) and feeds (Remote OK, WWR, Adzuna, USAJOBS), PoliteClient
                         (pacing, retries), title matching, Scraper (/scrape, dedupe),
                         PortalStore (source settings, company watchlist), SOURCES.md
    fit/                 the shared fit rubric (/rank and /apply), hard filters, Ranker
    geo.py               countries from free-text job locations (unknown never filters)
    jobs/                JobStore: Discover listing (latest score per job), save, dismiss
    commands/            command registry + built-ins; feature commands register here
    services/            business logic: every command lives here
      runtime.py         opens data folder, migrates, wires every service together
      tasks.py           background task runner (persisted to `tasks`, events on the bus)
      events.py, stream.py  in-process event bus -> SSE
      llm_settings.py    API key (keychain), model settings (config.toml), status
      backup.py, doctor.py
    api/                 FastAPI app factory, SessionGuard auth middleware, thin routes
    cli.py               `offerbound` command (start, doctor, db, backup, run, llm)
  tests/                 pytest (temp data folder, in-memory keyring, FakeProvider per test)
frontend/                React 18 + Vite + TS strict + Tailwind v4 + shadcn/ui + TanStack Query
  src/api/               openapi.json + schema.ts (GENERATED), typed client, queries, SSE parser,
                         session bootstrap
  src/app/               shell, routes (lazy screens with matching skeletons), nav, session gate
  src/features/          one folder per feature: chat (drawer, slash menu, card registry),
                         events (SSE provider, progress tray), memory, settings, profile,
                         sources, discover (virtualized table, detail sheet, rank dialog), ...
  src/components/ui/     shadcn/ui components (add with `npx shadcn@latest add <name>`)
  src/components/        shared app components (empty states, skeletons, layout, ScoreBadge)
  src/lib/               theme, hotkeys, small pure helpers
  src/test/              MSW server + handlers, fixtures, FakeEventSource, renderApp()
skills/<command>/        SKILL.md per command (thin wrappers over the CLI)
scripts/                 install.sh (Mac/Linux), install.ps1 (Windows)
data/
  companies/             ATS company watchlists, one CSV per ATS (verified live; see README)
  country_sources.toml   per-country feeds, currency, salary period
docs/SPEC.md             product spec and build plan
.github/workflows/ci.yml lint + typecheck + tests on ubuntu, macos, windows
```

## Commands

No Makefile; everything runs through `uv run` and npm scripts so Windows works.

Backend (from `backend/`):

| Task | Command |
| --- | --- |
| Install | `uv sync` |
| Run API (port 8765, reload, allows Vite origin) | `uv run poe dev` |
| Run the app as a user would | `uv run offerbound start` |
| Diagnostics | `uv run offerbound doctor` |
| Run a command (what skills call) | `uv run offerbound run context --json` |
| Store an Anthropic API key in the keychain | `uv run offerbound llm set-key` |
| Regenerate fixture resumes | `uv run python tests/fixtures/make_fixtures.py` |
| New migration after editing models | `uv run offerbound db revision -m "add x"` |
| Test | `uv run pytest` or `uv run poe test` |
| Lint | `uv run poe lint` |
| Format | `uv run poe format` (`uv run poe fix` also applies lint fixes) |
| Type-check (mypy strict) | `uv run poe typecheck` |
| Everything CI runs | `uv run poe check` |

Frontend (from `frontend/`):

| Task | Command |
| --- | --- |
| Install | `npm ci` |
| Dev server (port 5173, proxies `/api` to 8765) | `npm run dev` |
| Test (Vitest) | `npm test` |
| Lint (ESLint) | `npm run lint` |
| Type-check | `npm run typecheck` |
| Format (Prettier + Tailwind class order) | `npm run format` |
| Build | `npm run build` |
| Everything CI runs | `npm run check` |

From the repo root, `npm run setup`, `npm test`, `npm run lint`, `npm run typecheck`, and `npm run check` run both halves. After changing any API route or model, run `npm run gen:api` from the root: it exports the OpenAPI schema and regenerates `frontend/src/api/schema.ts`. CI's api-contract job fails if you forget.

Dev loop: `uv run poe dev` (backend, prints a launch URL with a token) and `npm run dev` (frontend on 5173); open the printed URL.

Run `npm run check` from the root before you call a chunk done.

## Coding rules

- **Services hold logic.** API routes, chat tools, and the CLI are thin: parse input, call one service function, return its result. If a route or tool has a branch that isn't input validation, move it into a service.
- **No secrets in files.** API keys, the Gmail app password, and the Notion token go in the OS keychain via `keyring`. `config.toml`, logs, fixtures, and test data never contain secrets; logs redact them.
- **Never invent profile facts in generated documents.** Generated CVs, cover letters, and answers may rephrase and reorder, but must not add employers, titles, dates, degrees, certifications, or numbers that are not in `profile.md`. The /apply reviewer pass enforces this; don't weaken it.
- **Nothing changes memory silently.** Fact extraction produces proposed diffs the user accepts or rejects.
- **profile.md and preferences.md are canonical.** Code reads them through `ProfileService` (parse) and writes through it (render + reindex `profile_items` + sync `search_targets`), or through accepted proposals. The user's own edits are saved verbatim; unknown sections are preserved. Never write those files any other way.
- **Setup is review-first.** Imported or extracted data becomes a draft the user reviews before it is applied; applying merges (existing facts win) so re-running never duplicates. The gap interview is deterministic (no AI), so setup works without an API key.
- **Uploads are untrusted input.** Size caps, archive bomb checks, content-sniffed types, and only known LinkedIn CSVs are read. Commands that read local paths set `chat_allowed=False`.
- **Untrusted text stays untrusted.** Job descriptions, emails, and web pages go in delimited blocks, never in system prompts. Tools triggered while processing them are read-only.
- **No live network calls in tests.** Use recorded fixtures and a `FakeProvider` for the LLM. Job sources use `tests/portal_web.py` (`FakeWeb`: an httpx2 `MockTransport` over `tests/fixtures/portals/`); swap `runtime.scraper.http_factory` to use it in API tests.
- **Job sources are polite.** All source traffic goes through `PoliteClient` (identifying User-Agent, per-host pacing from `min_interval_s`, retries honoring Retry-After). Verify endpoints and terms before adding or changing one and record them in `portals/SOURCES.md`. Third-party XML is parsed with DTDs refused; ATS slugs must match `SLUG_PATTERN` (they go into URL paths).
- **Types are strict on both sides.** mypy `strict = true`; TypeScript `strict` plus `noUncheckedIndexedAccess`. Don't add `Any`, `# type: ignore`, or `as unknown as` without a comment explaining why.
- **Cross-platform always.** Use `pathlib`, no shell-specific syntax in npm or poe scripts, and no tools that need admin rights. CI runs on Linux, macOS, and Windows.
- **Schema changes** go in `db/models.py` plus a migration from `offerbound db revision`; review the generated file. Migrations never import app code (the autogen hook renders plain `sa.*` types). `test_models_match_migrations` fails if they drift.
- **Datetimes are timezone-aware UTC** (`offerbound.db.types.utcnow()`); naive datetimes are rejected at write time.
- **Naming:** `jobs` are job postings; background runs are `tasks`. Long-running commands go through `TaskRunner.submit()` and report with `ctx.progress()`, which streams to the UI as `task.updated` SSE events.
- **API auth:** every `/api/*` route except `/api/health` needs the per-launch session token. The frontend sends it as `X-Offerbound-Token`; the cookie set by the launch URL only works for GET/HEAD (for EventSource). Host and Origin headers are allowlisted. Never loosen these for convenience.
- **Calling Claude:** go through `LLMService` with a `Task` (rank, extract, write, review, chat). Routing picks the model and effort; the meter logs every call to `llm_calls` and enforces the monthly cap. Never construct an SDK client elsewhere. Use `structured()` with a pydantic schema for anything parsed (`structured_result()` when you need the model that answered). Keep numeric constraints out of those schemas (structured outputs don't enforce them); clamp after parsing.
- **Fit scores** come only from `fit/rubric.py` (`FIT_RUBRIC`, `JobFit`). /rank, /apply's fit check, and the Claude Code skill all use it so scores mean the same thing. Batch commands show an estimate (`LLMService.estimate`) before running.
- **Model facts live in `llm/models.py`** (pricing, server-side fallback support). Check Anthropic's docs before adding a model; don't guess IDs.
- **Chat history is append-only text across turns;** within one turn the system prompt and tools stay fixed and assistant content (thinking blocks included) is replayed verbatim. Changing this breaks the API's preserved-thinking check and the prompt cache.
- **New commands** register a `CommandSpec` (params model, `read_only`, `background`) so the API, chat, and CLI all get them. Mark anything that writes data `read_only=False`; chat then shows a confirmation card instead of running it. Set `untrusted_output=True` when the result carries third-party text (job titles, postings); chat wraps it as untrusted.
- **Third-party links** (job URLs) must be http(s): the scraper drops anything else and the UI only links through `safeUrl()`.
- **Frontend data access:** call the API only through `api` (openapi-fetch, typed from the generated schema) and TanStack Query hooks in `src/api/queries.ts`; use `unwrap()` for data-or-ApiError. Never hand-write request/response types the schema already has. The session token lives in memory only, never in storage.
- **Frontend structure:** screens are lazy routes with a matching skeleton; long-running work shows progress from `useEventStream()`; chat cards register through `registerCard()`. Pure helpers live in `.ts` files so component files only export components (Fast Refresh).
- **React 18 + shadcn:** current shadcn templates target React 19 (`ref` as a prop). Components that receive refs (Button, Input, Textarea, and anything used with Radix `asChild`) must use `forwardRef`.
- **Frontend tests** use Vitest, Testing Library, and MSW (`src/test/server.ts`); unhandled requests fail the test. Prefer `renderApp(route)` for anything touching routing, session, or the drawer.
- **Design system** (per spec): shadcn/ui on Tailwind, zinc base, indigo-600 accent, light/dark from CSS variables following the OS, WCAG 2.1 AA, respect `prefers-reduced-motion`.
