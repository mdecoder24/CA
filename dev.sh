#!/usr/bin/env bash
# Start FinTrack: backend on 127.0.0.1:8000, frontend on localhost:3000.
# First run installs dependencies. Ctrl+C stops both.
set -euo pipefail
cd "$(dirname "$0")"

export NEXT_TELEMETRY_DISABLED=1

if [ ! -x backend/.venv/bin/python ]; then
  PY=$(command -v python3.12 || command -v python3.13 || command -v python3.11 || true)
  if [ -z "$PY" ]; then
    echo "Python 3.11+ is required (brew install python@3.12)." >&2
    exit 1
  fi
  echo "Creating Python environment…"
  "$PY" -m venv backend/.venv
  backend/.venv/bin/pip install -q --upgrade pip
  backend/.venv/bin/pip install -q -r backend/requirements.txt "uvicorn[standard]"
fi

if [ ! -d frontend/node_modules ]; then
  echo "Installing frontend packages…"
  (cd frontend && pnpm install)
fi

if command -v fdesetup >/dev/null 2>&1 && ! fdesetup status 2>/dev/null | grep -q "On"; then
  echo "⚠  FileVault appears to be off. Your bank data in ./data is not encrypted on disk."
  echo "   Turn it on in System Settings → Privacy & Security → FileVault."
fi

cleanup() { kill 0 2>/dev/null || true; }
trap cleanup EXIT INT TERM

(cd backend && .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --log-level warning) &
(cd frontend && pnpm exec next dev --hostname 127.0.0.1 --port 3000) &

echo ""
echo "FinTrack is starting → http://127.0.0.1:3000"
wait
