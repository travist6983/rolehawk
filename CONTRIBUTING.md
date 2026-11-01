# Contributing

Thanks for helping. RoleHawk is a Python backend (FastAPI) and a React + TypeScript
dashboard in one repository. Everything below works on macOS, Linux, and Windows.

## Set up

You need [uv](https://docs.astral.sh/uv/), Node 22, and git.

```bash
git clone https://github.com/travist6983/offerbound-ai-job-search.git
cd offerbound-ai-job-search
npm run setup                                        # uv sync + npm ci
cd backend && uv run playwright install chromium     # PDF export and autofill
```

Run it in two terminals:

```bash
cd backend && uv run poe dev     # API on 127.0.0.1:8765; prints a launch link with a token
cd frontend && npm run dev       # dashboard on 127.0.0.1:5173 (proxies /api)
```

Open the printed launch link. Your data goes in `~/RoleHawk`; point `ROLEHAWK_HOME` at a
scratch folder to keep development data separate. To use Claude in the app, store a key with
`uv run rolehawk llm set-key` (it goes in your OS keychain).

## Before you open a pull request

```bash
npm run check        # from the root: lint, format, type checks, and tests for both halves
```

- After changing an API route or model, run `npm run gen:api` (CI fails if the generated
  client is stale).
- After changing `db/models.py`, add a migration with `uv run rolehawk db revision -m "..."`
  and read the generated file.
- Tests never touch the network: use the recorded fixtures, `FakeProvider` for Claude, and
  `FakeWeb` for job sources.

CI runs the same checks on Linux, macOS, and Windows. Keep pull requests to one change, based
on `main`.

## How the code is organized

One service layer owns all logic. The dashboard (FastAPI routes), the chat drawer (chat tools),
and Claude Code skills (`rolehawk run <command> --json`) are thin callers on top of it, so a
command behaves the same everywhere. [CLAUDE.md](CLAUDE.md) has the folder map and the rules
every change follows. Highlights:

- **Never invent profile facts** in generated documents. Three layers enforce it; don't weaken
  any of them.
- **Untrusted text stays untrusted**: job postings, emails, and web pages go in delimited
  blocks, never in system prompts.
- **Custom job sources are data, never code**, and run only in the sandbox.
- **Autofill never submits.**
- **Secrets live in the OS keychain**, never in files or logs.
- **Types are strict** on both sides (mypy strict, TypeScript strict).

[docs/SPEC.md](docs/SPEC.md) is the product spec and build plan.

## Adding a job source

Built-in sources live in `backend/src/rolehawk/portals/`. Check the source's API terms and
endpoints first and record them in `portals/SOURCES.md`; all traffic goes through
`PoliteClient`. Add recorded responses under `backend/tests/fixtures/portals/` for the tests.
For one company's careers page, you don't need code: use **Sources → Add a job site**.

## Releasing

1. Bump the version in `backend/pyproject.toml` and `backend/src/rolehawk/__init__.py`
   (a test checks they match), then run `uv lock` in `backend/`.
2. Merge to `main`, then tag it: `git tag v0.2.0 && git push origin v0.2.0`.
3. The Release workflow builds the dashboard and the ZIP, installs it on Linux, macOS, and
   Windows, starts it, tests `rolehawk update`, and then publishes the GitHub release.
   Users get it with `rolehawk update`.

## Reporting a security issue

Please don't open a public issue. Use **Report a vulnerability** on the repository's Security
tab so it can be fixed before it's disclosed.

## Code of conduct

Be kind and assume good intent. Harassment isn't welcome here.
