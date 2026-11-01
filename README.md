# RoleHawk

[![CI](https://github.com/travist6983/rolehawk/actions/workflows/ci.yml/badge.svg)](https://github.com/travist6983/rolehawk/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

**Free, local-first, and private.** RoleHawk is an open source AI job search copilot that runs
on your own computer. It builds your profile from your resume, finds jobs across job boards and
company career pages, ranks them against what you want, writes a tailored CV and cover letter
for each one without inventing anything, and tracks every application. Claude does the
thinking; your data stays with you.

![RoleHawk: a pipeline board of job applications, then a tailored application opening](docs/media/hero.gif)

<sub>Every screen in this README shows made-up demo data: a fictional job seeker and fictional
companies. [Try the demo yourself](#try-the-demo).</sub>

## See it in action

### Your whole search on one board

Every application moves from Saved to Offer on one board, by drag or keyboard. Each card shows
its fit score and the one thing to do next: write the application, check a flagged line, send
a follow-up after ten quiet days, or prepare for an interview.

![The Pipeline board with applications from Saved to Offer](docs/media/pipeline.png)

### Find and rank jobs

RoleHawk searches Greenhouse, Lever, Ashby, and Workable boards for a watchlist of companies
you control, plus Remote OK, We Work Remotely, Adzuna, and USAJOBS. Add any careers page
yourself: RoleHawk finds its feed or structured job data, shows you sample jobs, and runs it in
a sandbox. Ranking uses one fit rubric (experience, skills, career goals, logistics, plus
eligibility and language gates), explains every score, and shows its cost before it runs.

![Discover: ranking new jobs and opening one to see why it scored the way it did](docs/media/discover.gif)

### A tailored CV and cover letter, fact-checked

One click writes a CV and cover letter for the posting, as Word and PDF, from ATS-friendly
templates. Facts come from your profile only, and three checks catch anything that isn't there:
drafts pick your roles and projects by reference, a fact check flags unknown numbers and skills,
and an AI review marks stretches and generic lines for you to fix or keep. It also checks the
posting's requirements against your CV, and can fill in the application form in a browser
window, then stop. It never submits.

![Writing an application and reviewing its flagged lines](docs/media/apply.gif)

### See what's working

Insights shows your funnel, response rate by source, weekly activity, and what you've spent on
Claude this month. Export a self-contained HTML report to share with a mentor or career coach.

![Insights: funnel, response rate by source, weekly activity, and AI spend](docs/media/insights.png)

### Ask Claude from any screen

Chat knows your profile, your pipeline, and the page you're on, and takes slash commands. It
remembers what you tell it (preferences, deal breakers, stories) in plain markdown files and
never changes them without your OK.

![The chat drawer answering "What should I focus on today?"](docs/media/chat.gif)

### Light or dark

It follows your system setting, or pick one in the sidebar.

![The Pipeline board in dark mode](docs/media/pipeline-dark.png)

## Install

One line, about three minutes. No admin rights, no Python or Node to install yourself.

**macOS / Linux** (Terminal):

```bash
curl -fsSL https://raw.githubusercontent.com/travist6983/rolehawk/main/scripts/install.sh | bash
```

**Windows** (PowerShell):

```powershell
irm https://raw.githubusercontent.com/travist6983/rolehawk/main/scripts/install.ps1 | iex
```

When it finishes, RoleHawk opens in your browser with three steps to get started. After
that, start it with the **RoleHawk** shortcut on your Desktop or by typing `rolehawk` in
a terminal.

The installer puts everything in your home folder: [uv](https://docs.astral.sh/uv/) (which
brings Python 3.12) if you don't have it, the app in `~/.rolehawk`, and Chromium for PDFs
and autofill (about 150 MB). It checks the download's SHA-256 before unpacking it. Your data
lives separately in `~/RoleHawk` (`%USERPROFILE%\RoleHawk` on Windows). Read the
scripts first if you like: [install.sh](scripts/install.sh), [install.ps1](scripts/install.ps1).

### First run: connect Claude

RoleHawk opens on a four-step setup: Connect Claude, Resume, Questions, and Job sources. It
takes about ten minutes, and you can stop and come back any time.

Connecting Claude takes about five minutes, and the app walks you through it:

1. Create an account on the [Claude Platform](https://platform.claude.com/). It's free, and
   separate from claude.ai (you can use the same email).
2. Add some credit. $10 to $20 covers a few weeks of typical use.
3. Create an API key named "RoleHawk" and copy it. It starts with `sk-ant-` and is shown once.
4. Paste it into RoleHawk and choose a monthly limit. The key goes into your computer's
   keychain, never a file.

<!-- Setup screenshots go here once the Connect Claude step is simplified (separate task). -->

Use Claude Code instead? Skip the key and use the skills (see
[Use it from Claude Code](#use-it-from-claude-code)).

Installed it back when it was called Offerbound? Run the install line again. RoleHawk picks up
your existing `~/Offerbound` folder and saved API key as they are, so nothing needs moving.
You can then delete the old `~/.offerbound` app folder and the old Offerbound shortcut.

## Try the demo

Want to look around before you set it up? A demo with a made-up job seeker runs from a copy of
this repository, with a scripted stand-in for Claude, so it needs no API key and costs nothing.
It uses its own folder and never touches `~/RoleHawk`. You need
[uv](https://docs.astral.sh/uv/) and [Node](https://nodejs.org/).

```bash
git clone https://github.com/travist6983/rolehawk.git
cd rolehawk/frontend && npm ci && npm run build
cd ../backend && uv sync
uv run python scripts/demo_data.py seed ~/RoleHawk-demo
uv run python scripts/demo_data.py serve ~/RoleHawk-demo
```

Delete `~/RoleHawk-demo` when you're done.

## Also in the box

- **Builds your profile** from a resume (PDF, Word, or text) or a LinkedIn data export, then
  fills the gaps with a short interview. You review everything before it's saved.
- **Follow-ups** drafted from what you actually sent, for you to send yourself. RoleHawk
  never sends anything.
- **Learns from results**: as replies and rejections come in, it suggests changes to your
  preferences for you to accept or reject.
- **Backups and updates** that never touch your data without a copy first.

## What it costs

RoleHawk is free. The AI runs on your own API key from the
[Claude Platform](https://platform.claude.com/), so you pay Anthropic for what you use (a
Claude Pro or Max subscription can't be used by other apps). The first screen walks you
through making a key and setting a monthly limit; it takes about five minutes.

Ranking uses Claude Haiku 5.5 and costs cents; writing applications uses Claude Opus 5.5 and
is most of the bill.

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
rolehawk install-skills
```

Then, in Claude Code, ask for things like "set up my job search profile from ~/resume.pdf" or
use `/rolehawk-rank` and `/rolehawk-apply`. Claude Code does the thinking in your own
session and calls `rolehawk run <command> --json` for data and actions, against the same data
folder as the dashboard. RoleHawk itself never signs in to claude.ai (Anthropic doesn't allow
third-party apps to). See [skills/README.md](skills/README.md) for the full list.

## Privacy

- Everything runs on `127.0.0.1`. A random token in the launch link protects the API from
  other web pages, and the app works offline apart from the services below.
- Data goes only to Anthropic (with your key), the job sources you turn on, employer pages you
  open with autofill, and GitHub when you run `rolehawk update`. **Settings → Where your
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
| `rolehawk` | Start the app and open it in your browser (Ctrl+C stops it) |
| `rolehawk update` | Install the newest release. Backs up your data first; the old version stays until the new one works |
| `rolehawk doctor` | A diagnostics report you can paste into a GitHub issue (no personal data) |
| `rolehawk backup` | Zip your data folder into `~/RoleHawk/backups` |
| `rolehawk install-browser` | Install or repair Chromium |
| `rolehawk install-skills` | Add the skills to Claude Code |

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
companies' own boards, which RoleHawk does search.

**Where is my data, and how do I move it?** In `~/RoleHawk`: your profile and memory as
markdown files, documents, backups, and one SQLite database. Copy the folder to move it.

**Which countries does it support?** Any. Job sources are filtered by the countries you search
in, and Adzuna covers 19 countries when you add a free key.

## Troubleshooting

Start with `rolehawk doctor`. Each line says what's wrong and how to fix it.

- **`rolehawk: command not found`**: open a new terminal window (the installer updated your
  PATH). Or use the Desktop shortcut.
- **The browser didn't open**: copy the `Open:` link printed in the terminal into your browser.
  The link includes the session token, so use the full link.
- **"Address already in use"**: RoleHawk is already running in another window, or another
  app uses port 8765. Change it with `rolehawk start --port 8766`.
- **PDF export fails**: run `rolehawk install-browser`. On Linux, Chromium may also need
  system libraries; `rolehawk doctor` prints the exact command (it needs sudo).
- **The API key isn't saved (Linux)**: the keychain needs a Secret Service such as GNOME
  Keyring or KWallet. `rolehawk doctor` shows whether one is available.
- **An update failed**: you're still on the previous version, and your data was backed up
  before anything changed. Run `rolehawk update` again, or reinstall with the install line.
- **Start over**: Settings → Reset deletes chosen data after a backup. Your files in
  `~/RoleHawk/backups` stay.

Still stuck? [Open an issue](https://github.com/travist6983/rolehawk/issues)
with the `rolehawk doctor` output.

## Uninstall

Delete `~/.rolehawk`, the `rolehawk` command (`~/.local/bin/rolehawk`, or
`rolehawk.cmd` on Windows), and the Desktop shortcut. Your data in `~/RoleHawk` stays until
you delete it too. uv stays installed; remove it with `uv self uninstall` if you don't need it.

## Build from source

Python 3.12 (FastAPI, SQLAlchemy, Playwright, mypy strict) and React 18 + TypeScript (Vite,
Tailwind, shadcn/ui, TanStack Query). See [CONTRIBUTING.md](CONTRIBUTING.md) for setup, the
architecture, and the rules every change follows. [docs/SPEC.md](docs/SPEC.md) is the full
product spec.

## License

[MIT](LICENSE). See also the [disclaimer](DISCLAIMER.md).
