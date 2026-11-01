# Backlog

Ideas we've agreed are worth doing but haven't scheduled. Pick one off, move it into a chunk,
and delete it here when it ships. The planned roadmap (v1.1 commands, LinkedIn/Indeed, the
browser agent, v2) lives in [SPEC.md](SPEC.md); this file is for everything else.

## For people who don't code

From comparing setup and daily use with ai-job-search (2026-10-31). The first three fixes
shipped: the first release, a walkthrough for making a Claude API key with a monthly limit,
and moving sources that need a developer key under "Advanced".

- [ ] **No terminal to install.** The install is still "paste this line into a terminal".
  Options: a desktop wrapper (Tauri; already in SPEC's v2 backlog) that bundles the backend
  and opens the dashboard in its own window, or signed installers (a notarized macOS `.pkg`
  or `.dmg`, a signed Windows `.msi`) that run the same steps. Signing needs an Apple Developer
  account and a Windows code-signing certificate.
- [ ] **Walkthrough video and GIFs** for the README: install, connect Claude, import a resume,
  rank, apply. Record after the UI overhaul; `backend/scripts/seed_demo.py` and
  `capture_screenshots.py` (kept locally, not committed) make a realistic demo data folder.
- [ ] **Linux without a keychain.** Saving the API key fails on desktops without a Secret
  Service (some minimal distros, WSL). An encrypted-file fallback with a clear warning would
  remove the last "install this package" step.

## From the ai-job-search review

- [ ] **Company research cache.** Research a company once (site, recent news, reviews) and
  reuse it for 30 days in cover letters and interview prep, storing where each fact came
  from so claims can be re-checked. Needs /interview and the browser agent first.
- [ ] **"Does it work?" section in the README** with real results (applications sent,
  interviews, offers). Needs real numbers from a real search; never invent them.

## Repository settings (manual)

- [ ] Turn on **private vulnerability reporting** (Settings → Code security). SECURITY.md
  tells people to report through it.

## Design

- [ ] **UI overhaul** from the Claude Design prompt (layout, Pipeline, Discover, Application
  review, Insights, Chat) so the app stops looking machine-made.
