#!/usr/bin/env bash
# Offerbound AI installer for macOS and Linux.
#
#   curl -fsSL https://raw.githubusercontent.com/travist6983/offerbound-ai-job-search/main/scripts/install.sh | bash
#
# Everything goes in your home folder; nothing needs sudo:
#   ~/.local/bin/uv               uv, if you don't have it (it brings Python 3.12)
#   ~/.offerbound/                the app (one folder per version) and Chromium (~150 MB)
#   ~/.local/bin/offerbound       the `offerbound` command
#   a Desktop shortcut            Offerbound.command (macOS) or offerbound.desktop (Linux)
# Your data lives in ~/Offerbound; reinstalling or updating never touches it.
#
# Optional settings: OFFERBOUND_APP_HOME (install folder), OFFERBOUND_BIN_DIR (where the
# `offerbound` command goes), OFFERBOUND_RELEASE_URL (where the release files come from),
# OFFERBOUND_NO_START=1 (don't start the app at the end), OFFERBOUND_NO_SHORTCUT=1.
#
# Everything is inside main(), called on the last line, so a partial download runs nothing.

set -euo pipefail

UV_VERSION="0.10.7"
RELEASES="https://github.com/travist6983/offerbound-ai-job-search/releases/latest/download"

say() {
  if [ -t 1 ]; then printf '\033[1m%s\033[0m\n' "$*"; else printf '%s\n' "$*"; fi
}

fail() {
  printf 'Offerbound install failed: %s\n' "$*" >&2
  exit 1
}

need() {
  command -v "$1" >/dev/null 2>&1 || fail "this needs '$1', which isn't installed."
}

sha256_of() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | cut -d' ' -f1
  else
    shasum -a 256 "$1" | cut -d' ' -f1
  fi
}

# Single-quote a string for a generated shell script.
quote() {
  printf "'%s'" "$(printf '%s' "$1" | sed "s/'/'\\\\''/g")"
}

find_uv() {
  if command -v uv >/dev/null 2>&1; then
    command -v uv
    return
  fi
  for dir in "${XDG_BIN_HOME:-}" "$HOME/.local/bin" "$HOME/.cargo/bin"; do
    if [ -n "$dir" ] && [ -x "$dir/uv" ]; then
      printf '%s\n' "$dir/uv"
      return
    fi
  done
}

write_launcher() {
  local bindir="$1" home_ref="$2"
  cat >"$bindir/offerbound" <<EOF
#!/bin/sh
# Offerbound launcher, written by the installer. Runs the version named in "current";
# \`offerbound update\` installs new versions next to it and moves that pointer.
home=$home_ref
version="\$(cat "\$home/current" 2>/dev/null)" || {
  echo "Offerbound isn't installed in \$home. Run the install line from the README." >&2
  exit 1
}
exec "\$home/versions/\$version/backend/.venv/bin/offerbound" "\$@"
EOF
  chmod +x "$bindir/offerbound"
}

write_shortcut() {
  local os="$1" bindir="$2"
  if [ "$os" = macOS ]; then
    [ -d "$HOME/Desktop" ] || return 0
    printf '#!/bin/sh\nexec %s start\n' "$(quote "$bindir/offerbound")" >"$HOME/Desktop/Offerbound.command"
    chmod +x "$HOME/Desktop/Offerbound.command"
    return 0
  fi
  local apps="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
  mkdir -p "$apps"
  cat >"$apps/offerbound.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Offerbound AI
Comment=AI job search copilot
Exec="$bindir/offerbound" start
Terminal=true
Categories=Office;
EOF
  local desktop
  desktop="$(xdg-user-dir DESKTOP 2>/dev/null || printf '%s' "$HOME/Desktop")"
  if [ -d "$desktop" ] && [ "$desktop" != "$HOME" ]; then
    cp "$apps/offerbound.desktop" "$desktop/offerbound.desktop"
    chmod +x "$desktop/offerbound.desktop"
    gio set "$desktop/offerbound.desktop" metadata::trusted true >/dev/null 2>&1 || true
  fi
}

main() {
  local os
  case "$(uname -s)" in
    Darwin) os=macOS ;;
    Linux) os=Linux ;;
    *) fail "this installer is for macOS and Linux. On Windows, use install.ps1 (see the README)." ;;
  esac
  need curl
  need uname
  need mktemp

  local home="${OFFERBOUND_APP_HOME:-$HOME/.offerbound}"
  local base="${OFFERBOUND_RELEASE_URL:-$RELEASES}"
  base="${base%/}"

  say "Offerbound AI installer ($os, $(uname -m))"
  echo "This installs, in your home folder only (no admin rights needed):"
  echo "  - uv, which manages Python 3.12 for the app (if it isn't installed yet)"
  echo "  - Offerbound into $home, including Chromium for PDFs and autofill (about 150 MB)"
  echo "  - the 'offerbound' command and a Desktop shortcut"
  echo "Your data will live in ${OFFERBOUND_HOME:-~/Offerbound}."
  echo

  local uv
  uv="$(find_uv)"
  if [ -z "$uv" ]; then
    say "Installing uv $UV_VERSION..."
    curl -LsSf "https://astral.sh/uv/$UV_VERSION/install.sh" | sh
    uv="$(find_uv)"
    [ -n "$uv" ] || fail "uv didn't install. See https://docs.astral.sh/uv/ and try again."
  fi
  echo "Using uv at $uv"

  local tmp
  tmp="$(mktemp -d)"
  trap 'rm -rf "$tmp"' EXIT

  say "Downloading the latest release..."
  curl -fsSL --retry 3 -o "$tmp/offerbound.zip" "$base/offerbound.zip" ||
    fail "couldn't download $base/offerbound.zip"
  curl -fsSL --retry 3 -o "$tmp/offerbound.zip.sha256" "$base/offerbound.zip.sha256" ||
    fail "couldn't download the checksum file"
  local expected actual
  expected="$(cut -d' ' -f1 <"$tmp/offerbound.zip.sha256")"
  actual="$(sha256_of "$tmp/offerbound.zip")"
  [ "$expected" = "$actual" ] || fail "the download doesn't match its checksum. Try again."

  # Python's zipfile (through uv) unpacks it, so `unzip` isn't needed. It drops absolute
  # paths and '..' from member names, and never creates links.
  "$uv" run --quiet --no-project --python 3.12 python -m zipfile -e "$tmp/offerbound.zip" "$tmp/x"
  local unpacked=("$tmp"/x/offerbound-*)
  if [ "${#unpacked[@]}" -ne 1 ] || [ ! -f "${unpacked[0]}/VERSION" ]; then
    fail "the release has an unexpected layout."
  fi
  local version
  version="$(cat "${unpacked[0]}/VERSION")"
  [[ "$version" =~ ^[0-9]{1,4}\.[0-9]{1,4}\.[0-9]{1,4}$ ]] || fail "bad release version."

  local app="$home/versions/$version"
  mkdir -p "$home/versions"
  if [ -d "$app" ]; then
    echo "Reinstalling version $version."
    rm -rf "$app"
  fi
  mv "${unpacked[0]}" "$app"

  say "Installing Offerbound $version (Python 3.12 and packages)..."
  (cd "$app/backend" && "$uv" sync --quiet --frozen --no-dev --python 3.12)
  local exe="$app/backend/.venv/bin/offerbound"

  say "Installing Chromium (PDF export and autofill)..."
  "$exe" install-browser

  printf '%s' "$version" >"$home/current.partial"
  mv -f "$home/current.partial" "$home/current"

  say "Setting up your data folder..."
  "$exe" db upgrade

  local bindir uv_bin home_ref
  uv_bin="$("$uv" tool dir --bin)"
  bindir="${OFFERBOUND_BIN_DIR:-$uv_bin}"
  mkdir -p "$bindir"
  if [ -n "${OFFERBOUND_APP_HOME:-}" ]; then
    home_ref="$(quote "$home")"
  else
    home_ref='"$HOME/.offerbound"'
  fi
  write_launcher "$bindir" "$home_ref"
  local path_note=""
  case ":$PATH:" in
    *":$bindir:"*) ;;
    *)
      if [ "$bindir" = "$uv_bin" ]; then
        # uv adds its tool folder to your shell's startup files (the same folder uv uses).
        "$uv" tool update-shell >/dev/null 2>&1 || true
        path_note="Open a new terminal window for the 'offerbound' command to work."
      else
        path_note="Add $bindir to your PATH to use the 'offerbound' command."
      fi
      ;;
  esac

  if [ "${OFFERBOUND_NO_SHORTCUT:-}" != 1 ]; then
    write_shortcut "$os" "$bindir"
  fi

  rm -rf "$tmp"
  trap - EXIT
  echo
  say "Offerbound $version is installed."
  echo "Start it any time with 'offerbound' or the Offerbound shortcut on your Desktop."
  echo "Update with 'offerbound update'. Diagnostics: 'offerbound doctor'."
  [ -z "$path_note" ] || echo "$path_note"
  if [ "${OFFERBOUND_NO_START:-}" != 1 ]; then
    echo
    say "Starting Offerbound (press Ctrl+C to stop)..."
    exec "$exe" start
  fi
}

main "$@"
