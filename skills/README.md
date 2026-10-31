# Skills

One folder per command. Each `SKILL.md` lets Claude Code run the command from a terminal
against the same data folder the dashboard uses.

## How skills work

The backend exposes every command through one CLI:

```bash
offerbound run <command> [--param key=value ...] [--params-json '{...}'] [--json]
```

Built-in commands available today:

| Command | What it does |
| --- | --- |
| `context` | Context pack: memory files plus requested jobs/applications (`for_command`, `job_ids`, `application_ids`) |
| `memory` | Memory files and pending proposals |
| `propose` | Propose a memory edit; it stays pending until the user accepts it |
| `spend` | AI spend this month and the cap |
| `selftest` | Short background task to check progress output |
| `setup`, `setup-import`, `setup-extract`, `setup-draft`, `setup-apply` | Profile setup from documents (see `setup/SKILL.md`) |
| `setup-interview`, `setup-answer`, `setup-skip` | The gap interview, one question at a time |
| `scrape` | Search every enabled job source for the active search targets (background; see `scrape/SKILL.md`) |
| `sources` | Job sources: status, what each still needs, jobs found, last search results |
| `watchlist`, `watchlist-add` | The companies whose job boards are searched; add more (checked first) |
| `rank-candidates`, `rank-save` | Score jobs in Claude Code: next batch + rubric, then save the scores (see `rank/SKILL.md`) |
| `rank-plan`, `rank` | Score jobs in the app with the user's API key: estimate first, then run (background) |
| `jobs`, `job`, `jobs-save`, `jobs-dismiss` | Browse jobs with scores, read one posting, save to the pipeline, dismiss |

Feature commands register as they ship (see the release table).

## Two ways to use Claude

- **In the app** (dashboard and chat drawer): the user's Anthropic API key, stored in the OS
  keychain. Costs are logged and capped.
- **From Claude Code** (these skills): Claude Code does the reasoning in the user's own
  session and calls `offerbound run` for data and actions. Offerbound never offers or uses a
  claude.ai login itself: Anthropic doesn't allow third-party apps to do that.

| Release | Commands |
| --- | --- |
| v1.0 | setup, scrape, rank, apply, html-report, reset, add-portal |
| v1.1 | outcome, gmail-sync, interview, add-template |
| v2.0 | notion-sync, expand, upskill |
