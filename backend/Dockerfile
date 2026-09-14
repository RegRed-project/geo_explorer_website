# Built directly on the VPS (docker compose build) — no registry involved.
# Build context is the repo root (see ../docker-compose.yml), so paths below
# are relative to the repo root, not this file's directory.
FROM python:3.12-slim
WORKDIR /srv

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Docker caches this layer by file content — as long as the .duckdb file on
# the VPS hasn't changed, rebuilding after a code-only change reuses this
# layer instead of recopying the ~17GB file.
COPY geographic_entities_prepared.duckdb /data/geographic_entities_prepared.duckdb
COPY backend/app/ ./app/

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
