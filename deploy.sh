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
ssh "$VPS" "cd $REMOTE_DIR && docker compose up -d --build"

echo "==> Done. Check: curl https://geo-explorer.geomattr.org/api/tables"
