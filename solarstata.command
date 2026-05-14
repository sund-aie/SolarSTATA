#!/bin/bash
# SolarSTATA macOS launcher — double-click to boot the app.
#
# - Activates .venv if present; otherwise runs `make setup` to create one.
# - Starts the FastAPI backend on :8000 and the Vite frontend on :5173 in
#   parallel.
# - Opens http://localhost:5173 in the default browser.
# - Ctrl+C in the Terminal window stops both servers.

set -e

# Resolve script directory regardless of where it was double-clicked from
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo ""
echo "  S o l a r S T A T A   v 3 . 0"
echo "  ───────────────────────────────"
echo ""

# Bootstrap if needed
if [ ! -d ".venv" ] || [ ! -d "frontend/node_modules" ]; then
  echo "  First run — provisioning .venv and node_modules…"
  if ! command -v python3 >/dev/null 2>&1; then
    echo "  ✗ python3 not found. Install Python 3.11+ from python.org or via Homebrew (brew install python)."
    exit 1
  fi
  if ! command -v node >/dev/null 2>&1; then
    echo "  ✗ node not found. Install Node 18+ from nodejs.org or via Homebrew (brew install node)."
    exit 1
  fi
  make setup
fi

cleanup() {
  echo ""
  echo "  Shutting down…"
  if [ -n "$BACKEND_PID" ]; then kill "$BACKEND_PID" 2>/dev/null || true; fi
  if [ -n "$FRONTEND_PID" ]; then kill "$FRONTEND_PID" 2>/dev/null || true; fi
  exit 0
}
trap cleanup INT TERM

echo "  → Starting FastAPI on http://localhost:8000"
.venv/bin/python -m uvicorn solarstata.main:app \
  --host 127.0.0.1 --port 8000 --log-level warning &
BACKEND_PID=$!

echo "  → Starting Vite on http://localhost:5173"
(cd frontend && npm run dev -- --host 127.0.0.1 --port 5173) &
FRONTEND_PID=$!

# Give Vite a moment to boot, then open the browser
sleep 2
open "http://localhost:5173"

echo ""
echo "  Both servers are running. Close this Terminal window or press Ctrl+C to stop."
echo ""

wait
