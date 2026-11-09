#!/usr/bin/env bash
# Pre-deploy test of the website against the local .duckdb file:
# database schema vs. backend config, API behaviour, and the frontend in a
# headless browser. Exits non-zero if any check fails.
#
# If every check passes, the tested site is served locally and opened in the
# browser until Ctrl+C. If any check fails, nothing is served.
#
# Usage: ./test_site.sh [--no-serve] [extra pytest args, e.g. -k ui  or  -x]
#   --no-serve   only run the tests (e.g. in scripts or CI)
#
# Environment overrides:
#   DB_PATH    database to test against (default: ./geographic_entities_prepared.duckdb)
#   TEST_PORT  port for the local test server (default: 18731; 8000, 8001 and 8787 are refused)
#   TEST_VENV  test virtualenv (default: ~/.cache/geo-explorer-test-venv, kept outside
#              the synced project folder)
#   BASE_PY    Python used to create the venv (default: the mamba geostatistics env)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export DB_PATH="${DB_PATH:-$ROOT/geographic_entities_prepared.duckdb}"
TEST_VENV="${TEST_VENV:-$HOME/.cache/geo-explorer-test-venv}"
BASE_PY="${BASE_PY:-$HOME/miniforge3/envs/geostatistics/bin/python}"
RESERVED_PORTS=(8000 8001 8787)   # claude-science, RStudio

SERVE=1
PYTEST_ARGS=()
for arg in "$@"; do
  if [[ "$arg" == "--no-serve" ]]; then SERVE=0; else PYTEST_ARGS+=("$arg"); fi
done

port_in_use() { ss -ltnH "( sport = :$1 )" 2>/dev/null | grep -q .; }
is_reserved() { local p; for p in "${RESERVED_PORTS[@]}"; do [[ "$1" == "$p" ]] && return 0; done; return 1; }

# --- Port ---------------------------------------------------------------------
PORT="${TEST_PORT:-18731}"
if is_reserved "$PORT"; then
  echo "ERROR: port $PORT is reserved (claude-science / RStudio). Choose another TEST_PORT." >&2
  exit 2
fi
if port_in_use "$PORT"; then
  if [[ -n "${TEST_PORT:-}" ]]; then
    echo "ERROR: TEST_PORT=$PORT is already in use." >&2
    exit 2
  fi
  for p in $(seq 18732 18799); do
    if ! port_in_use "$p"; then PORT="$p"; break; fi
  done
  port_in_use "$PORT" && { echo "ERROR: no free port in 18731-18799." >&2; exit 2; }
fi
export TEST_PORT="$PORT"

# --- Database -----------------------------------------------------------------
if [[ ! -f "$DB_PATH" ]]; then
  echo "ERROR: database not found: $DB_PATH" >&2
  exit 2
fi
if [[ -f "$DB_PATH.wal" ]]; then
  echo "ERROR: $DB_PATH.wal exists: uncheckpointed writes. Close the writing connection" >&2
  echo "       (e.g. Positron's DuckDB data connection) so they are saved into the file." >&2
  exit 2
fi
if command -v fuser >/dev/null && fuser "$DB_PATH" >/dev/null 2>&1; then
  echo "WARNING: another process has the database open:" >&2
  fuser -v "$DB_PATH" 2>&1 | sed 's/^/         /' >&2
  echo "         If it holds a write lock the tests will fail to connect." >&2
fi

# --- Test environment -----------------------------------------------------------
if [[ ! -x "$TEST_VENV/bin/python" ]]; then
  echo "==> Creating test venv at $TEST_VENV"
  "$BASE_PY" -m venv "$TEST_VENV"
fi
echo "==> Installing test dependencies"
"$TEST_VENV/bin/pip" install -q --disable-pip-version-check \
  -r "$ROOT/backend/requirements.txt" -r "$ROOT/tests/requirements-test.txt"
# Downloads Chromium once into ~/.cache/ms-playwright; no-op afterwards.
"$TEST_VENV/bin/python" -m playwright install chromium >/dev/null

# --- Run ------------------------------------------------------------------------
echo "==> Testing against $DB_PATH on port $PORT"
cd "$ROOT"
if ! PYTHONPATH="$ROOT/backend" "$TEST_VENV/bin/python" -m pytest -p no:cacheprovider \
       "$ROOT/tests" "${PYTEST_ARGS[@]}"; then
  echo "==> Tests failed: site not served." >&2
  exit 1
fi

[[ "$SERVE" == 1 ]] || exit 0

# --- Serve the tested site --------------------------------------------------------
# Same server the browser tests used: real API + frontend on one origin, local data.
URL="http://127.0.0.1:$PORT/"
echo "==> All tests passed. Serving the site at $URL (Ctrl+C to stop)"
PYTHONPATH="$ROOT/backend:$ROOT/tests" "$TEST_VENV/bin/python" -m uvicorn serve_app:app \
  --host 127.0.0.1 --port "$PORT" --log-level warning &
SERVER_PID=$!
trap 'kill "$SERVER_PID" 2>/dev/null; wait "$SERVER_PID" 2>/dev/null' EXIT INT TERM

for _ in $(seq 240); do
  curl -fs "${URL}api/tables" >/dev/null 2>&1 && break
  kill -0 "$SERVER_PID" 2>/dev/null || { echo "ERROR: server exited" >&2; exit 1; }
  sleep 0.5
done
if command -v xdg-open >/dev/null; then
  xdg-open "$URL" >/dev/null 2>&1 || echo "    Open $URL in a browser."
else
  echo "    Open $URL in a browser."
fi
wait "$SERVER_PID"
