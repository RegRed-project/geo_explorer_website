# Deploying the Geo Explorer

Architecture: a FastAPI + DuckDB API runs in Docker on a VPS (behind Caddy
for HTTPS), **built directly on that VPS** — no container registry, no
self-hosted GitHub Actions runner, no CI permissions to fight with. The
static frontend is served from GitHub Pages and calls the API over
`fetch()`.

Concrete values already wired into the repo:

| Thing | Value |
|---|---|
| GitHub org/repo | `regred-project/geo_explorer_website` |
| Pages URL | `https://regred-project.github.io/geo_explorer_website/` |
| VPS public IP | `147.251.255.246` |
| API hostname (via sslip.io, no DNS setup needed) | `147-251-255-246.sslip.io` |

If any of these change, update: `backend/Caddyfile`, `frontend/js/app.js`
(`API_BASE`), `backend/app/main.py` (`allow_origins`), and the default host
in `deploy.sh`.

## 1. One-time: create the GitHub repo (for the frontend + version control)

```bash
git remote add origin git@github.com:regred-project/geo_explorer_website.git
git add .
git commit -m "Initial FastAPI + static frontend setup"
git push -u origin main
```

Repo Settings → Pages → Source → "GitHub Actions" — that's the only GitHub
Actions workflow left (`deploy-frontend.yml`), and it needs no secrets or
special permissions since it just uploads static files.

## 2. One-time: prepare the VPS (147.251.255.246)

SSH in and install Docker + the Compose plugin:

```bash
ssh gortega@147.251.255.246
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER   # log out/in after this
```

Open the firewall for HTTP/HTTPS only:

```bash
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
```

Create the deploy directory, owned by your user (`/opt` is root-owned by
default):

```bash
sudo mkdir -p /opt/geo-explorer
sudo chown $USER:$USER /opt/geo-explorer
```

Back on your machine, make sure key-based SSH works so `deploy.sh` doesn't
prompt for a password every time:

```bash
ssh-copy-id gortega@147.251.255.246
```

## 3. Deploy the backend

From the repo root, with `geographic_entities_prepared.duckdb` present
(it's gitignored — it just needs to exist on disk here):

```bash
./deploy.sh
```

This does everything:

1. `rsync`s the repo to `/opt/geo-explorer` on the VPS (excludes `.git` and
   `frontend/` — the frontend doesn't belong on the API server). rsync only
   re-transfers the `.duckdb` file if its content actually changed, so
   routine code-only deploys are fast.
2. SSHes in and runs `docker compose up -d --build`, which builds
   `backend/Dockerfile` and (re)starts both the `fastapi` and `caddy`
   containers.

Caddy gets a real Let's Encrypt certificate for
`147-251-255-246.sslip.io` automatically the first time it starts — no DNS
setup needed.

Run `./deploy.sh` again any time you change backend code or the data file.
Pass a different target if needed: `./deploy.sh otheruser@otherhost`.

## 4. Deploy the frontend

Push to `main` with changes under `frontend/` — GitHub's
`deploy-frontend.yml` workflow publishes `frontend/` to GitHub Pages
automatically. No build step, no secrets, runs on a standard hosted
runner.

## 5. Verify

```bash
# API is reachable and has a valid cert
curl https://147-251-255-246.sslip.io/api/tables

# CORS is configured for the Pages origin
curl -I -H "Origin: https://regred-project.github.io" \
  https://147-251-255-246.sslip.io/api/tables | grep -i access-control

# Full site
open https://regred-project.github.io/geo_explorer_website/
```

In the browser: pick a table, filter to a single row, and confirm the
table and the Leaflet map both render.

## Updating the data later

1. Replace `geographic_entities_prepared.duckdb` locally with the new
   version.
2. `./deploy.sh`

That's it — the new file gets rsynced up and the image rebuilds with it.

## Troubleshooting

- **`./deploy.sh` hangs or asks for a password every time**: SSH key auth
  isn't set up — rerun `ssh-copy-id gortega@147.251.255.246`.
- **`docker compose up -d --build` fails with no space left on the VPS**:
  it needs room for the image (~17GB layer) plus the raw `.duckdb` copy
  rsynced alongside it; check `df -h` on the VPS.
- **Caddy cert fails to issue**: confirm ports 80/443 are reachable from
  the internet (`sudo ufw status`, and check the hosting provider isn't
  blocking them at the network level too).
- **CORS errors in the browser console**: the `Origin` header the browser
  sends must exactly match an entry in `allow_origins` in
  `backend/app/main.py` (scheme + host only, no path) — run `./deploy.sh`
  again after changing it.
- **GitHub Pages shows a 404 or old content**: confirm Settings → Pages →
  Source is set to "GitHub Actions", and check the `deploy-frontend.yml`
  run under the Actions tab for errors.
