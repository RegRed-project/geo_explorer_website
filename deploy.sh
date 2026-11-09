#!/usr/bin/env bash
# Deploys the website: backend (API + data) to the VPS, frontend to GitHub Pages.
#
# Usage: ./deploy.sh [all|backend|frontend] [--skip-tests] [--host user@host]
#   all (default)  test, deploy the backend, check it is live, then deploy the frontend.
#                  Backend goes first: the new frontend needs the new API.
#   backend        only the API + data on the VPS (rsync + docker compose over SSH).
#   frontend       only GitHub Pages (pushes main; the Pages workflow publishes frontend/).
#   --skip-tests   do not run ./test_site.sh --no-serve first.
#   --host         VPS login (default: $VPS or gortega@147.251.255.246).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

TARGET="all"
RUN_TESTS=1
VPS="${VPS:-gortega@147.251.255.246}"
while [[ $# -gt 0 ]]; do
  case "$1" in
    all|backend|frontend) TARGET="$1" ;;
    --skip-tests) RUN_TESTS=0 ;;
    --host) VPS="$2"; shift ;;
    *@*) VPS="$1" ;;   # old usage: ./deploy.sh user@host
    -h|--help) sed -n '2,10p' "$0"; exit 0 ;;
    *) echo "Unknown argument: $1 (see --help)" >&2; exit 2 ;;
  esac
  shift
done

REMOTE_DIR="/opt/geo-explorer"
API_URL="https://geo-explorer.geomattr.org"
PAGES_ORIGIN="https://regred-project.github.io"
PAGES_URL="$PAGES_ORIGIN/geo_explorer_website"
DB_FILE="geographic_entities_prepared.duckdb"

# Everything the VPS needs to build and run the backend, and nothing else.
# docker-compose.yml builds backend/Dockerfile (which copies requirements.txt and
# app/), mounts backend/Caddyfile into Caddy and bind-mounts the database.
BACKEND_FILES=(
  ./docker-compose.yml
  ./backend/Dockerfile
  ./backend/requirements.txt
  ./backend/Caddyfile
  ./backend/app/
  "./$DB_FILE"
)
# Same list without leading ./ or trailing / (for the remote leftover check).
BACKEND_TOP_LEVEL="docker-compose.yml backend $DB_FILE"

step() { echo; echo "==> $*"; }
die()  { echo "ERROR: $*" >&2; exit 1; }

# --- Tests ---------------------------------------------------------------------
if [[ "$RUN_TESTS" == 1 ]]; then
  step "Running pre-deploy tests"
  ./test_site.sh --no-serve -q || die "tests failed: nothing deployed"
fi

# --- Backend -------------------------------------------------------------------
deploy_backend() {
  [[ -f "$DB_FILE.wal" ]] && die "$DB_FILE.wal exists: close the connection writing to the database first"
  for f in "${BACKEND_FILES[@]}"; do [[ -e "$f" ]] || die "missing $f"; done
  if ! git diff --quiet HEAD -- backend docker-compose.yml; then
    echo "WARNING: backend has uncommitted changes; the VPS will run your working copy, not a commit."
  fi

  step "Syncing backend files to $VPS:$REMOTE_DIR (the .duckdb only re-transfers if it changed)"
  # -R keeps the relative paths; --delete only acts inside the directories sent
  # (backend/app/), so modules removed locally are removed remotely too.
  rsync -avzR --delete --info=progress2 --exclude '__pycache__/' \
    "${BACKEND_FILES[@]}" "$VPS:$REMOTE_DIR/"

  step "Building and restarting containers on $VPS"
  # `up -d --build` only recreates a container when its image or compose
  # config changed — it does NOT notice that the bind-mounted .duckdb file's
  # *content* changed, so fastapi would otherwise keep serving from its
  # already-open connection to the old data indefinitely. Always restart it
  # explicitly so data updates actually take effect.
  ssh "$VPS" "cd $REMOTE_DIR && docker compose up -d --build && docker compose restart fastapi"

  step "Checking the API at $API_URL"
  local body=""
  for _ in $(seq 60); do
    body="$(curl -fsS "$API_URL/api/tables" 2>/dev/null)" && [[ "$body" == *'"columns"'* ]] && break
    body=""; sleep 2
  done
  [[ -n "$body" ]] || die "$API_URL/api/tables did not return the current API within 2 min"
  curl -fsS -o /dev/null -D - -H "Origin: $PAGES_ORIGIN" "$API_URL/api/tables" \
    | grep -qi "^access-control-allow-origin: $PAGES_ORIGIN" \
    || die "API does not send the CORS header for $PAGES_ORIGIN"
  echo "API is live and allows $PAGES_ORIGIN."

  # Earlier versions of this script synced the whole repo; list what is left over.
  local stale
  stale="$(ssh "$VPS" "cd $REMOTE_DIR && ls -A" | grep -vxF -f <(tr ' ' '\n' <<<"$BACKEND_TOP_LEVEL") || true)"
  if [[ -n "$stale" ]]; then
    echo "Note: $REMOTE_DIR also holds files the backend does not use (not deleted):"
    sed 's/^/        /' <<<"$stale"
  fi
}

# --- Frontend ------------------------------------------------------------------
# GitHub Pages publishes frontend/ from main via .github/workflows/deploy-frontend.yml,
# which runs on every push to main that touches frontend/. So deploying = getting the
# local frontend committed and onto origin/main, then checking Pages serves it.
pages_matches_local() {
  local f
  for f in index.html js/app.js css/style.css; do
    # Query string bypasses the Pages CDN cache (max-age 600 s).
    cmp -s <(curl -fsS "$PAGES_URL/$f?nocache=$RANDOM$RANDOM" 2>/dev/null) "frontend/$f" || return 1
  done
}

deploy_frontend() {
  local branch
  branch="$(git rev-parse --abbrev-ref HEAD)"
  [[ "$branch" == "main" ]] || die "on branch '$branch'; Pages deploys from main"
  if ! git diff --quiet HEAD -- frontend || [[ -n "$(git ls-files --others --exclude-standard frontend)" ]]; then
    git status --short frontend
    die "frontend/ has uncommitted changes; commit them first"
  fi

  step "Checking origin/main"
  git fetch -q origin main
  local behind ahead
  read -r behind ahead < <(git rev-list --left-right --count origin/main...HEAD)
  [[ "$behind" == 0 ]] || die "local main is $behind commit(s) behind origin/main; pull first"

  if pages_matches_local; then
    echo "GitHub Pages already serves the local frontend. Nothing to do."
    return
  fi

  if [[ "$ahead" -gt 0 ]]; then
    step "Pushing $ahead commit(s) to origin/main (triggers the Pages workflow if frontend/ changed)"
    git push origin main
  fi
  if [[ "$ahead" == 0 ]] || git diff --quiet "HEAD~$ahead" HEAD -- frontend .github/workflows/deploy-frontend.yml; then
    # Nothing pushed touches frontend/, so the workflow won't start on its own.
    step "Starting the Pages workflow manually"
    if gh workflow run deploy-frontend.yml --ref main 2>/dev/null; then
      echo "Workflow started."
    else
      die "could not start it with gh (try 'gh auth login'), or run it from GitHub: Actions -> 'Deploy frontend to GitHub Pages' -> Run workflow"
    fi
  fi

  step "Waiting for GitHub Pages to serve the new files ($PAGES_URL/)"
  for _ in $(seq 60); do
    if pages_matches_local; then
      echo "GitHub Pages serves the local frontend."
      return
    fi
    sleep 10
  done
  die "Pages still serves different files after 10 min; check the workflow run in the repo's Actions tab"
}

case "$TARGET" in
  backend)  deploy_backend ;;
  frontend) deploy_frontend ;;
  all)      deploy_backend; deploy_frontend ;;
esac
step "Done. Site: $PAGES_URL/  API: $API_URL/api/tables"
