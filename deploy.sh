#!/usr/bin/env bash
# Deploys the backend to the VPS: syncs the repo, then builds and restarts
# the containers over SSH. No GitHub Actions, no container registry.
#
# Usage: ./deploy.sh [user@host]
# Defaults to VPS_HOST below if no argument is given.
set -euo pipefail

VPS="${1:-gortega@147.251.255.246}"
REMOTE_DIR="/opt/geo-explorer"

echo "==> Syncing repo to $VPS:$REMOTE_DIR (the .duckdb file only re-transfers if it changed)"
rsync -avz --info=progress2 \
  --exclude '.git' \
  --exclude 'frontend' \
  --exclude '__pycache__' \
  ./ "$VPS:$REMOTE_DIR/"

echo "==> Building and restarting containers on $VPS"
# `up -d --build` only recreates a container when its image or compose
# config changed — it does NOT notice that the bind-mounted .duckdb file's
# *content* changed, so fastapi would otherwise keep serving from its
# already-open connection to the old data indefinitely. Always restart it
# explicitly so data updates actually take effect.
ssh "$VPS" "cd $REMOTE_DIR && docker compose up -d --build && docker compose restart fastapi"

echo "==> Done. Check: curl https://geo-explorer.geomattr.org/api/tables"
