#!/usr/bin/env bash
# Beatmaper launcher — starts backend (FastAPI on :8008) + frontend (Vite on :5173).
# Ctrl+C stops both.
set -euo pipefail

cd "$(dirname "$0")"

if [ ! -d .venv ] || [ ! -d node_modules ]; then
  echo "Run ./install.sh first."
  exit 1
fi

# shellcheck disable=SC1091
source .venv/bin/activate

cleanup() {
  echo
  echo "Stopping..."
  [ -n "${BACK_PID:-}" ] && kill "$BACK_PID" 2>/dev/null || true
  [ -n "${FRONT_PID:-}" ] && kill "$FRONT_PID" 2>/dev/null || true
  wait 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo "▶ Starting backend on http://127.0.0.1:8008"
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8008 --log-level warning &
BACK_PID=$!

# Wait briefly for backend port
for i in 1 2 3 4 5 6 7 8 9 10; do
  if (echo >/dev/tcp/127.0.0.1/8008) 2>/dev/null; then break; fi
  sleep 0.5
done

echo "▶ Starting frontend on http://127.0.0.1:5173"
npm run dev -- --host 127.0.0.1 &
FRONT_PID=$!

echo
echo "Open http://127.0.0.1:5173 in your browser."
echo "Press Ctrl+C to stop."
wait
