#!/usr/bin/env bash
# Offerbound AI installer for macOS and Linux.
# Stub: the real installer lands in Chunk 12 (docs/SPEC.md "Installer and first run").
# Planned steps: detect OS/arch, install uv to $HOME, download the release ZIP to
# ~/.offerbound/app, uv sync, install Playwright Chromium, create ~/Offerbound,
# add the `offerbound` command and a desktop shortcut, then start the app.
set -euo pipefail

echo "Offerbound AI installer is not available yet." >&2
echo "To run from source, see CLAUDE.md." >&2
exit 1
