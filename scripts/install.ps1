# Offerbound AI installer for Windows (PowerShell).
# Stub: the real installer lands in Chunk 12 (docs/SPEC.md "Installer and first run").
# Planned steps: detect arch, install uv to the user profile, download the release ZIP to
# %USERPROFILE%\.offerbound\app, uv sync, install Playwright Chromium, create
# %USERPROFILE%\Offerbound, add the `offerbound` command and a desktop shortcut, then start the app.
$ErrorActionPreference = "Stop"

Write-Error "Offerbound AI installer is not available yet. To run from source, see CLAUDE.md."
exit 1
