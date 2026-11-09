"""Shared fixtures: database connection, running test server, HTTP client, browser."""
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import duckdb
import httpx
import pytest

from app.config import DB_PATH, DISPLAY_COLS, TABLES

RESERVED_PORTS = {8000, 8001, 8787}  # claude-science, RStudio
TESTS_DIR = Path(__file__).resolve().parent
ROOT = TESTS_DIR.parent
ID_COL = next(iter(TABLES.values()))[1]
COLUMNS = [ID_COL] + DISPLAY_COLS


@pytest.fixture(scope="session")
def con():
    c = duckdb.connect(DB_PATH, read_only=True)
    c.execute("LOAD spatial")
    yield c
    c.close()


@pytest.fixture(scope="session")
def base_url():
    port = int(os.environ.get("TEST_PORT", "18731"))
    if port in RESERVED_PORTS:
        pytest.exit(f"Port {port} is reserved (claude-science / RStudio)", returncode=2)
    with socket.socket() as s:
        if s.connect_ex(("127.0.0.1", port)) == 0:
            pytest.exit(f"Port {port} is already in use", returncode=2)

    env = {**os.environ, "DB_PATH": DB_PATH,
           "PYTHONPATH": f"{ROOT / 'backend'}{os.pathsep}{TESTS_DIR}"}
    # Server output goes to a temp file (a pipe could fill up and block the server).
    log = tempfile.TemporaryFile(mode="w+")
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "serve_app:app",
         "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"],
        env=env, stdout=log, stderr=subprocess.STDOUT, text=True,
    )
    url = f"http://127.0.0.1:{port}"
    deadline = time.time() + 120
    while time.time() < deadline:
        if proc.poll() is not None:
            log.seek(0)
            pytest.exit(f"Test server exited:\n{log.read()}", returncode=2)
        try:
            if httpx.get(f"{url}/api/tables", timeout=2).status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(0.3)
    else:
        proc.terminate()
        pytest.exit("Test server did not start within 120 s", returncode=2)

    yield url
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
    log.close()


@pytest.fixture(scope="session")
def api(base_url):
    with httpx.Client(base_url=base_url, timeout=60) as c:
        yield c


@pytest.fixture(scope="session")
def browser():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()
