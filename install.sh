#!/usr/bin/env bash
# Beatmaper — clone (if needed), git pull, then npm start (TUI: browser vs Electron).
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/icedmoca/beatmaper/main/install.sh | bash
# Optional env:
#   BEATMAPER_REPO   git URL (default: https://github.com/icedmoca/beatmaper.git)
#   BEATMAPER_DIR    install path (default: ~/beatmaper, or current dir if it already looks like this repo)

set -euo pipefail

REPO="${BEATMAPER_REPO:-https://github.com/icedmoca/beatmaper.git}"
DEFAULT_DIR="${HOME}/beatmaper"

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "error: '$1' not found. $2" >&2
    exit 1
  }
}

need_cmd git "Install Git: https://git-scm.com/downloads"
need_cmd node "Install Node.js LTS: https://nodejs.org"

is_beatmaper_dir() {
  local d="$1"
  [[ -f "$d/package.json" ]] && grep -q '"name"[[:space:]]*:[[:space:]]*"beatmaper"' "$d/package.json" 2>/dev/null \
    && [[ -f "$d/scripts/launch.mjs" ]]
}

ROOT=""
if [[ -n "${BEATMAPER_DIR:-}" ]]; then
  ROOT="${BEATMAPER_DIR}"
elif is_beatmaper_dir "$(pwd)"; then
  ROOT="$(pwd)"
else
  ROOT="$DEFAULT_DIR"
fi

if [[ ! -d "$ROOT/.git" ]] || ! is_beatmaper_dir "$ROOT"; then
  if [[ -e "$ROOT" ]]; then
    echo "error: $ROOT exists but is not a beatmaper git checkout." >&2
    echo "  Remove it, or: export BEATMAPER_DIR=/path/to/empty-or-repo" >&2
    exit 1
  fi
  echo "→ Cloning $REPO"
  echo "    into: $ROOT"
  mkdir -p "$(dirname "$ROOT")"
  git clone "$REPO" "$ROOT"
fi

cd "$ROOT"
echo "→ Updating (git pull)…"
git pull --ff-only 2>/dev/null || true

echo "→ Starting Beatmaper (npm install + setup, then choose browser or Electron)…"
exec npm start
