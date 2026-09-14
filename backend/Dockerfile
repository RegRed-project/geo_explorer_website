# Built directly on the VPS (docker compose build) — no registry involved.
# Build context is the repo root (see ../docker-compose.yml), so paths below
# are relative to the repo root, not this file's directory.
#
# The .duckdb file is NOT copied into the image — it's bind-mounted at
# runtime (see docker-compose.yml). That keeps the image small and the
# build fast/instant regardless of data size, and means updating the data
# never requires a rebuild, just a container restart.
FROM python:3.12-slim
WORKDIR /srv

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/app/ ./app/

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
