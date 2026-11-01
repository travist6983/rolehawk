# Security

RoleHawk handles resumes, salary expectations, and an Anthropic API key, so it's built to
keep them on your computer. This page says what it protects against, how, and how to report
a problem.

## Reporting a vulnerability

Please report privately through GitHub: open the repository's **Security** tab and choose
**Report a vulnerability**. Don't open a public issue for security problems. Include the
version (`rolehawk --version` or `rolehawk doctor`), your OS, and steps to reproduce.

You'll get an acknowledgment within a week. Fixes ship in the next release, and the release
notes credit you unless you'd rather not be named.

Only the latest release is supported; `rolehawk update` installs it.

## What RoleHawk protects against

| Risk | What stops it |
| --- | --- |
| Another web page or local program calling the app's API | The server listens on 127.0.0.1 only and every `/api` route needs a per-launch session token (sent as a header; the cookie works for read-only requests only). Host and Origin headers are allowlisted. |
| Secrets in files or logs | The API key (and later the Gmail and Notion credentials) live in the OS keychain. `config.toml`, logs, and test data never contain them, and logs redact them. |
| A job posting that tries to steer Claude (prompt injection) | Hidden HTML, invisible characters, and smuggled text are removed before a posting is stored or sent to Claude (`portals/integrity.py`); lines aimed at AI tools are quoted for you. Third-party text always goes in delimited untrusted blocks, never in system prompts, and tools triggered while reading it are read-only. Chat asks before running anything that writes. |
| Invented facts in an application | Drafts pick roles, degrees, and certifications from your profile by index; a deterministic check flags numbers and skills your profile lacks; a second review pass flags the rest. Nothing is sent: autofill fills fields and stops before submit. |
| A custom job source running code | Sources added with /add-portal are stored as data (never imported) and run in a separate `python -I` process with a clean environment and a timeout. Requests stay on the source's domain, refuse private and loopback addresses on every hop, and respect robots.txt. |
| Malicious uploads | Size caps, archive-bomb checks, content-sniffed types, and only the known LinkedIn export files are read. |
| A tampered update | Releases are checked against their SHA-256 before unpacking; unpacking refuses absolute paths, `..`, and links. Each version installs into its own folder, and the app switches only after dependencies, migrations, and a backup succeed. |
| Losing your data | `/reset` and updates make a zipped backup first; resets need the scope typed to confirm. |

## Limits worth knowing

- The prompt-injection defenses lower the risk; they don't remove it. Read what RoleHawk
  wrote before you send it, especially for postings flagged as containing lines aimed at AI
  tools.
- Anything you send to Anthropic is covered by your agreement with Anthropic. Job sources,
  employer sites you open with autofill, and GitHub (for updates) see ordinary web requests.
  **Settings → Where your data goes** lists every destination.
- Your data folder (`~/RoleHawk`) is protected by your OS account, not by RoleHawk. Use
  disk encryption if others share your computer.
