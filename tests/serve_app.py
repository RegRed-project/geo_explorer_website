"""Test-only server: the real API plus the frontend on one origin.

Serving both from the same port means the browser test needs no CORS
exception for a localhost origin. app.js is served with API_BASE pointed at
this server instead of production; every other frontend file is served as is.
"""
import re
from pathlib import Path

from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles

from app.main import app

FRONTEND = Path(__file__).resolve().parent.parent / "frontend"
API_BASE_RE = re.compile(r'^const API_BASE = ".*?";', re.M)


@app.get("/js/app.js", include_in_schema=False)
def app_js():
    src = (FRONTEND / "js" / "app.js").read_text(encoding="utf-8")
    src, n = API_BASE_RE.subn("const API_BASE = window.location.origin;", src, count=1)
    if n != 1:
        raise RuntimeError("API_BASE declaration not found in frontend/js/app.js")
    return Response(src, media_type="text/javascript")


app.mount("/", StaticFiles(directory=FRONTEND, html=True), name="frontend")
