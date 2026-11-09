"""Static checks on the frontend files that GitHub Pages will publish."""
import re

from conftest import COLUMNS, ROOT

FRONTEND = ROOT / "frontend"


def test_api_base_points_at_production():
    src = (FRONTEND / "js" / "app.js").read_text(encoding="utf-8")
    m = re.search(r'^const API_BASE = "(.*?)";', src, re.M)
    assert m, "API_BASE declaration not found in app.js"
    url = m.group(1)
    assert url.startswith("https://"), f"API_BASE must be https (Pages is https): {url}"
    assert not re.search(r"localhost|127\.0\.0\.1", url), f"API_BASE points at a local server: {url}"


def test_local_assets_exist():
    html = (FRONTEND / "index.html").read_text(encoding="utf-8")
    refs = re.findall(r'(?:src|href)="([^"]+)"', html)
    local = [r for r in refs if not re.match(r"https?://|#|mailto:", r)]
    missing = [r for r in local if not (FRONTEND / r).is_file()]
    assert not missing, f"index.html references missing files: {missing}"


def test_every_column_has_a_placeholder():
    src = (FRONTEND / "js" / "app.js").read_text(encoding="utf-8")
    block = re.search(r"const PLACEHOLDERS = \{(.*?)\};", src, re.S).group(1)
    keys = set(re.findall(r"^\s*(\w+):", block, re.M))
    assert set(COLUMNS) <= keys, f"columns without a filter placeholder: {set(COLUMNS) - keys}"
