#!/usr/bin/env bash
# RoleHawk installer for macOS and Linux.
#
#   curl -fsSL https://raw.githubusercontent.com/travist6983/rolehawk/main/scripts/install.sh | bash
#
# Everything goes in your home folder; nothing needs sudo:
#   ~/.local/bin/uv               uv, if you don't have it (it brings Python 3.12)
#   ~/.rolehawk/                the app (one folder per version) and Chromium (~150 MB)
#   ~/.local/bin/rolehawk       the `rolehawk` command
#   a Desktop shortcut            RoleHawk.command (macOS) or rolehawk.desktop (Linux)
# Your data lives in ~/RoleHawk; reinstalling or updating never touches it.
#
# Optional settings: ROLEHAWK_APP_HOME (install folder), ROLEHAWK_BIN_DIR (where the
# `rolehawk` command goes), ROLEHAWK_RELEASE_URL (where the release files come from),
# ROLEHAWK_NO_START=1 (don't start the app at the end), ROLEHAWK_NO_SHORTCUT=1,
# ROLEHAWK_REINSTALL=1 (download and install again even when this release is installed).
#
# Running it again is safe: when the newest release is already installed it skips the
# download, refreshes the command and shortcut, and starts the app.
#
# Everything is inside main(), called on the last line, so a partial download runs nothing.

set -euo pipefail

UV_VERSION="0.10.7"
RELEASES="https://github.com/travist6983/rolehawk/releases/latest/download"

say() {
  if [ -t 1 ]; then printf '\033[1m%s\033[0m\n' "$*"; else printf '%s\n' "$*"; fi
}

fail() {
  printf 'RoleHawk install failed: %s\n' "$*" >&2
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
  cat >"$bindir/rolehawk" <<EOF
#!/bin/sh
# RoleHawk launcher, written by the installer. Runs the version named in "current";
# \`rolehawk update\` installs new versions next to it and moves that pointer.
home=$home_ref
version="\$(cat "\$home/current" 2>/dev/null)" || {
  echo "RoleHawk isn't installed in \$home. Run the install line from the README." >&2
  exit 1
}
exec "\$home/versions/\$version/backend/.venv/bin/rolehawk" "\$@"
EOF
  chmod +x "$bindir/rolehawk"
}

write_shortcut() {
  local os="$1" bindir="$2"
  if [ "$os" = macOS ]; then
    [ -d "$HOME/Desktop" ] || return 0
    printf '#!/bin/sh\nexec %s start\n' "$(quote "$bindir/rolehawk")" >"$HOME/Desktop/RoleHawk.command"
    chmod +x "$HOME/Desktop/RoleHawk.command"
    return 0
  fi
  local apps="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
  mkdir -p "$apps"
  cat >"$apps/rolehawk.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=RoleHawk
Comment=AI job search copilot
Exec="$bindir/rolehawk" start
Terminal=true
Categories=Office;
EOF
  local desktop
  desktop="$(xdg-user-dir DESKTOP 2>/dev/null || printf '%s' "$HOME/Desktop")"
  if [ -d "$desktop" ] && [ "$desktop" != "$HOME" ]; then
    cp "$apps/rolehawk.desktop" "$desktop/rolehawk.desktop"
    chmod +x "$desktop/rolehawk.desktop"
    gio set "$desktop/rolehawk.desktop" metadata::trusted true >/dev/null 2>&1 || true
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

  local home="${ROLEHAWK_APP_HOME:-$HOME/.rolehawk}"
  local base="${ROLEHAWK_RELEASE_URL:-$RELEASES}"
  base="${base%/}"

  say "RoleHawk installer ($os, $(uname -m))"
  echo "This installs, in your home folder only (no admin rights needed):"
  echo "  - uv, which manages Python 3.12 for the app (if it isn't installed yet)"
  echo "  - RoleHawk into $home, including Chromium for PDFs and autofill (about 150 MB)"
  echo "  - the 'rolehawk' command and a Desktop shortcut"
  echo "Your data will live in ${ROLEHAWK_HOME:-~/RoleHawk}."
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

  # Global, not local: the EXIT trap runs after main has returned.
  tmp="$(mktemp -d)"
  trap 'rm -rf "$tmp"' EXIT

  # The checksum file is tiny: fetch it first, so a rerun with this release already
  # installed (say, after the app was stopped) skips the download and the package install.
  curl -fsSL --retry 3 -o "$tmp/rolehawk.zip.sha256" "$base/rolehawk.zip.sha256" ||
    fail "couldn't download $base/rolehawk.zip.sha256"
  local expected version="" exe=""
  expected="$(cut -d' ' -f1 <"$tmp/rolehawk.zip.sha256")"
  local installed
  installed="$(cat "$home/current" 2>/dev/null || true)"
  if [ "${ROLEHAWK_REINSTALL:-}" != 1 ] && [[ "$installed" =~ ^[0-9]{1,4}\.[0-9]{1,4}\.[0-9]{1,4}$ ]] &&
    [ -x "$home/versions/$installed/backend/.venv/bin/rolehawk" ] &&
    [ "$(cat "$home/versions/$installed/.release-sha256" 2>/dev/null || true)" = "$expected" ]; then
    version="$installed"
    exe="$home/versions/$version/backend/.venv/bin/rolehawk"
    say "RoleHawk $version is already installed and up to date. Skipping the download."
  else
    say "Downloading the latest release..."
    curl -fsSL --retry 3 -o "$tmp/rolehawk.zip" "$base/rolehawk.zip" ||
      fail "couldn't download $base/rolehawk.zip"
    local actual
    actual="$(sha256_of "$tmp/rolehawk.zip")"
    [ "$expected" = "$actual" ] || fail "the download doesn't match its checksum. Try again."

    # Python's zipfile (through uv) unpacks it, so `unzip` isn't needed. It drops absolute
    # paths and '..' from member names, and never creates links.
    "$uv" run --quiet --no-project --python 3.12 python -m zipfile -e "$tmp/rolehawk.zip" "$tmp/x"
    local unpacked=("$tmp"/x/rolehawk-*)
    if [ "${#unpacked[@]}" -ne 1 ] || [ ! -f "${unpacked[0]}/VERSION" ]; then
      fail "the release has an unexpected layout."
    fi
    version="$(cat "${unpacked[0]}/VERSION")"
    [[ "$version" =~ ^[0-9]{1,4}\.[0-9]{1,4}\.[0-9]{1,4}$ ]] || fail "bad release version."

    local app="$home/versions/$version"
    mkdir -p "$home/versions"
    if [ -d "$app" ]; then
      echo "Reinstalling version $version."
      rm -rf "$app"
    fi
    mv "${unpacked[0]}" "$app"

    say "Installing RoleHawk $version (Python 3.12 and packages)..."
    (cd "$app/backend" && "$uv" sync --quiet --frozen --no-dev --python 3.12)
    exe="$app/backend/.venv/bin/rolehawk"

    say "Installing Chromium (PDF export and autofill)..."
    "$exe" install-browser

    printf '%s' "$version" >"$home/current.partial"
    mv -f "$home/current.partial" "$home/current"
    # Written last: its presence means this version installed completely.
    printf '%s' "$expected" >"$app/.release-sha256"
  fi

  say "Setting up your data folder..."
  "$exe" db upgrade

  local bindir uv_bin home_ref
  uv_bin="$("$uv" tool dir --bin)"
  bindir="${ROLEHAWK_BIN_DIR:-$uv_bin}"
  mkdir -p "$bindir"
  if [ -n "${ROLEHAWK_APP_HOME:-}" ]; then
    home_ref="$(quote "$home")"
  else
    # Literal $HOME: the launcher expands it when it runs.
    # shellcheck disable=SC2016
    home_ref='"$HOME/.rolehawk"'
  fi
  write_launcher "$bindir" "$home_ref"
  local path_note=""
  case ":$PATH:" in
    *":$bindir:"*) ;;
    *)
      if [ "$bindir" = "$uv_bin" ]; then
        # uv adds its tool folder to your shell's startup files (the same folder uv uses).
        "$uv" tool update-shell >/dev/null 2>&1 || true
        path_note="Open a new terminal window for the 'rolehawk' command to work."
      else
        path_note="Add $bindir to your PATH to use the 'rolehawk' command."
      fi
      ;;
  esac

  if [ "${ROLEHAWK_NO_SHORTCUT:-}" != 1 ]; then
    write_shortcut "$os" "$bindir"
  fi

  rm -rf "$tmp"
  trap - EXIT
  echo
  say "RoleHawk $version is installed."
  echo "To start it again later (after you stop it, close this window, or restart your"
  echo "computer), you don't need to reinstall. Use the RoleHawk shortcut on your Desktop,"
  echo "or run:"
  echo
  echo "    rolehawk"
  echo
  [ -z "$path_note" ] || echo "$path_note In this window, run: $bindir/rolehawk"
  echo "Update with 'rolehawk update'. Diagnostics: 'rolehawk doctor'."
  if [ "${ROLEHAWK_NO_START:-}" != 1 ]; then
    echo
    say "Starting RoleHawk (press Ctrl+C to stop)..."
    exec "$exe" start
  fi
}

main "$@"
