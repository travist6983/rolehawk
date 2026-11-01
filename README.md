# Offerbound AI

[![CI](https://github.com/travist6983/offerbound-ai-job-search/actions/workflows/ci.yml/badge.svg)](https://github.com/travist6983/offerbound-ai-job-search/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

A free, open source AI job search copilot that runs on your own computer. It builds your
profile from your resume, finds jobs across job boards and company career pages, ranks them
against what you want, writes a tailored CV and cover letter for each one without inventing
anything, and tracks every application. Claude does the thinking; your data stays with you.

<!-- Demo GIF (60 seconds): docs/media/demo.gif. Recorded after the final polish pass. -->

## Install

One line, about three minutes. No admin rights, no Python or Node to install yourself.

**macOS / Linux** (Terminal):

```bash
curl -fsSL https://raw.githubusercontent.com/travist6983/offerbound-ai-job-search/main/scripts/install.sh | bash
```

**Windows** (PowerShell):

```powershell
irm https://raw.githubusercontent.com/travist6983/offerbound-ai-job-search/main/scripts/install.ps1 | iex
```

When it finishes, Offerbound opens in your browser with three steps to get started. After
that, start it with the **Offerbound** shortcut on your Desktop or by typing `offerbound` in
a terminal.

The installer puts everything in your home folder: [uv](https://docs.astral.sh/uv/) (which
brings Python 3.12) if you don't have it, the app in `~/.offerbound`, and Chromium for PDFs
and autofill (about 150 MB). It checks the download's SHA-256 before unpacking it. Your data
lives separately in `~/Offerbound` (`%USERPROFILE%\Offerbound` on Windows). Read the
scripts first if you like: [install.sh](scripts/install.sh), [install.ps1](scripts/install.ps1).

## What it does

- **Builds your profile** from a resume (PDF, Word, or text) or a LinkedIn data export, then
  fills the gaps with a short interview. You review everything before it's saved.
- **Finds jobs** from Greenhouse, Lever, Ashby, and Workable boards for a watchlist of
  companies you control, plus Remote OK, We Work Remotely, Adzuna, and USAJOBS. Add any
  careers page yourself: Offerbound finds its feed or structured job data, shows you sample
  jobs, and runs it in a sandbox.
- **Ranks jobs** with one fit rubric (skills, seniority, location, salary, your preferences)
  and explains each score. Ranking shows an estimate before it runs.
- **Writes applications**: a CV and cover letter tailored to the posting, as Word and PDF,
  from ATS-friendly templates. Facts come from your profile only, and three checks catch
  anything that isn't there: drafts pick your roles and projects by reference, a fact check
  flags unknown numbers and skills, and an AI review marks the rest for you.
- **Fills in application forms** in a browser window and stops. It never submits.
- **Tracks the pipeline** on a board (drag or keyboard), with next actions, insights on what's
  working, and a self-contained HTML report you can share.
- **Remembers** what you tell it (preferences, deal-breakers, stories) in plain markdown files,
  and never changes them without your OK.
- **Chat** with Claude about your search from any screen, with slash commands.

## What it costs

Offerbound is free. The AI runs on your own [Anthropic API key](https://console.anthropic.com/),
so you pay Anthropic for what you use. Ranking uses Claude Haiku 5.5 and costs cents; writing
applications uses Claude Opus 5.5 and is most of the bill.

| How you use it (per week) | About per month |
| --- | --- |
| Light: 20 jobs ranked, 3 applications, a little chat | $3 to $6 |
| Typical: 50 jobs ranked, 10 applications, some chat | $12 to $25 |
| Heavy: 200 jobs ranked, 25 applications, daily chat | $30 to $60 |

These are estimates from the app's own pricing table; the range covers how much Claude thinks
on each task. Batch commands show an estimate before they run, Insights shows what you've
spent, and you can set a monthly cap in Settings that stops new AI calls when you reach it.

Already use Claude Code? You can run every command there instead (see below), and the
reasoning happens in your Claude Code session.

## Use it from Claude Code

Every command the dashboard runs is also a Claude Code skill. Add them with:

```bash
offerbound install-skills
```

Then, in Claude Code, ask for things like "set up my job search profile from ~/resume.pdf" or
use `/offerbound-rank` and `/offerbound-apply`. Claude Code does the thinking in your own
session and calls `offerbound run <command> --json` for data and actions, against the same data
folder as the dashboard. Offerbound itself never signs in to claude.ai (Anthropic doesn't allow
third-party apps to). See [skills/README.md](skills/README.md) for the full list.

## Privacy

- Everything runs on `127.0.0.1`. A random token in the launch link protects the API from
  other web pages, and the app works offline apart from the services below.
- Data goes only to Anthropic (with your key), the job sources you turn on, employer pages you
  open with autofill, and GitHub when you run `offerbound update`. **Settings → Where your
  data goes** lists them. No analytics, no telemetry, no account.
- Your API key is stored in your operating system's keychain, never in a file.
- Job postings and web pages are treated as untrusted text: they can't instruct Claude to
  change your data. Hidden text and invisible characters are removed from postings, and
  lines aimed at AI tools are shown to you.

To report a security problem, see [SECURITY.md](SECURITY.md).

Please read the [disclaimer](DISCLAIMER.md): you're responsible for following each job site's
terms and for what you send to employers.

## Everyday commands

| Command | What it does |
| --- | --- |
| `offerbound` | Start the app and open it in your browser (Ctrl+C stops it) |
| `offerbound update` | Install the newest release. Backs up your data first; the old version stays until the new one works |
| `offerbound doctor` | A diagnostics report you can paste into a GitHub issue (no personal data) |
| `offerbound backup` | Zip your data folder into `~/Offerbound/backups` |
| `offerbound install-browser` | Install or repair Chromium |
| `offerbound install-skills` | Add the skills to Claude Code |

## FAQ

**Does it apply to jobs automatically?** No. It drafts documents and fills in forms, then
stops so you can check everything and press submit yourself.

**Will it make things up on my CV?** It's built not to. Employers, titles, dates, degrees,
certifications, and numbers come only from your profile. Anything the checks can't match is
highlighted for you before you use the document.

**Does it work without an API key?** Partly. Importing a LinkedIn export, the setup
interview, job search, the pipeline, insights, and reports all work. Reading a resume,
ranking, writing, and chat need Claude: an API key in the app, or Claude Code with the skills.

**Does it search LinkedIn or Indeed?** Not yet. Searching them breaks their terms, so they'll
come later as opt-in, clearly marked experimental sources. Many of the same jobs are on the
companies' own boards, which Offerbound does search.

**Where is my data, and how do I move it?** In `~/Offerbound`: your profile and memory as
markdown files, documents, backups, and one SQLite database. Copy the folder to move it.

**Which countries does it support?** Any. Job sources are filtered by the countries you search
in, and Adzuna covers 19 countries when you add a free key.

## Troubleshooting

Start with `offerbound doctor`. Each line says what's wrong and how to fix it.

- **`offerbound: command not found`**: open a new terminal window (the installer updated your
  PATH). Or use the Desktop shortcut.
- **The browser didn't open**: copy the `Open:` link printed in the terminal into your browser.
  The link includes the session token, so use the full link.
- **"Address already in use"**: Offerbound is already running in another window, or another
  app uses port 8765. Change it with `offerbound start --port 8766`.
- **PDF export fails**: run `offerbound install-browser`. On Linux, Chromium may also need
  system libraries; `offerbound doctor` prints the exact command (it needs sudo).
- **The API key isn't saved (Linux)**: the keychain needs a Secret Service such as GNOME
  Keyring or KWallet. `offerbound doctor` shows whether one is available.
- **An update failed**: you're still on the previous version, and your data was backed up
  before anything changed. Run `offerbound update` again, or reinstall with the install line.
- **Start over**: Settings → Reset deletes chosen data after a backup. Your files in
  `~/Offerbound/backups` stay.

Still stuck? [Open an issue](https://github.com/travist6983/offerbound-ai-job-search/issues)
with the `offerbound doctor` output.

## Uninstall

Delete `~/.offerbound`, the `offerbound` command (`~/.local/bin/offerbound`, or
`offerbound.cmd` on Windows), and the Desktop shortcut. Your data in `~/Offerbound` stays until
you delete it too. uv stays installed; remove it with `uv self uninstall` if you don't need it.

## Build from source

Python 3.12 (FastAPI, SQLAlchemy, Playwright, mypy strict) and React 18 + TypeScript (Vite,
Tailwind, shadcn/ui, TanStack Query). See [CONTRIBUTING.md](CONTRIBUTING.md) for setup, the
architecture, and the rules every change follows. [docs/SPEC.md](docs/SPEC.md) is the full
product spec.

## License

[MIT](LICENSE). See also the [disclaimer](DISCLAIMER.md).
