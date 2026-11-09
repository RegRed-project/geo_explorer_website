"""The frontend in headless Chromium, against the local API on the same origin."""
import pytest

from app.config import TABLES

from conftest import COLUMNS, ID_COL

LABEL = "Counties (ADM2)" if "Counties (ADM2)" in TABLES else list(TABLES)[0]
DONE = "() => /returned|Error/.test(document.getElementById('row_count').textContent)"


@pytest.fixture
def page(browser, base_url):
    pg = browser.new_page(viewport={"width": 1400, "height": 900})
    errors = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.on("console", lambda m: m.type == "error" and "favicon" not in (m.location or {}).get("url", "")
          and errors.append(m.text))
    pg.goto(base_url + "/")
    pg.wait_for_function(DONE)
    pg.errors = errors
    yield pg
    pg.close()


def _query(pg, action):
    pg.evaluate("document.getElementById('row_count').textContent = ''")
    action()
    pg.wait_for_function(DONE, timeout=60000)
    return pg.text_content("#row_count")


def _count(text):
    assert "returned" in text, text
    return int(text.split()[0])


@pytest.fixture
def sample(con):
    tbl = TABLES[LABEL][0]
    row = con.execute(f"SELECT {', '.join(COLUMNS)} FROM {tbl} "
                      f"WHERE {ID_COL} IN (SELECT {ID_COL} FROM {tbl} GROUP BY 1 HAVING count(*) = 1) "
                      f"AND length({ID_COL}) > 3 USING SAMPLE 1 ROWS (reservoir, 7)").fetchone()
    return dict(zip(COLUMNS, row))


def test_initial_load(page):
    assert _count(page.text_content("#row_count")) >= 1
    labels = page.eval_on_selector_all("#table_name option", "els => els.map(e => e.value)")
    assert labels == list(TABLES)
    assert not page.evaluate("document.getElementById('map_dialog').open"), "map opened without a click"
    assert page.locator("#leaflet-map path").count() == 0
    assert not page.errors, page.errors


def test_filters_sit_above_their_columns(page):
    headers = page.eval_on_selector_all("#header_row th", "els => els.map(e => e.textContent)")
    assert headers == ["Map"] + COLUMNS
    filters = page.eval_on_selector_all("#filter_row th", "els => els.map(e => e.querySelector('input')?.dataset.col ?? null)")
    assert filters == [None] + COLUMNS
    aligned = page.evaluate("""() => {
        const f = [...document.querySelectorAll('#filter_row th')], h = [...document.querySelectorAll('#header_row th')];
        return f.every((c, i) => { const a = c.getBoundingClientRect(), b = h[i].getBoundingClientRect();
                                   return Math.abs(a.left - b.left) < 1 && Math.abs(a.width - b.width) < 1; }); }""")
    assert aligned


def test_search_filter_and_id_modes(page, sample):
    page.select_option("#table_name", LABEL)
    page.wait_for_function(DONE)
    rid = sample[ID_COL]

    page.fill("#search_all", rid)
    assert _count(_query(page, lambda: page.press("#search_all", "Enter"))) >= 1

    page.fill("#search_all", "")
    page.fill("#filter_locationID", rid)
    assert _count(_query(page, lambda: page.click("#query_btn"))) == 1

    page.fill("#filter_locationID", rid[:-1])
    n_exact_prefix = _count(_query(page, lambda: page.press("#filter_locationID", "Enter")))
    n_partial = _count(_query(page, lambda: page.check("#partial")))
    assert n_partial >= 1 and n_partial > n_exact_prefix

    page.uncheck("#partial")
    page.wait_for_function(DONE)
    page.fill("#filter_locationID", "")
    page.fill("#filter_country", "zz-no-such-country")
    assert _count(_query(page, lambda: page.press("#filter_country", "Enter"))) == 0

    # The checkbox applies to every column filter, not only locationID.
    country = sample["country"]
    if country and len(country.strip()) > 4:
        page.fill("#filter_country", country.strip()[1:4])
        n_exact = _count(_query(page, lambda: page.press("#filter_country", "Enter")))
        n_part = _count(_query(page, lambda: page.check("#partial")))
        assert n_part >= 1 and n_part > n_exact
        page.uncheck("#partial")
        page.wait_for_function(DONE)
    assert not page.errors, page.errors


def test_intro_and_checkbox_label(page):
    intro = page.text_content(".intro")
    assert "Allow partial matches" in intro and "Show" in intro
    assert page.text_content("label.checkbox").strip() == "Allow partial matches"
    assert not page.is_checked("#partial")


def test_map_popup(page, sample):
    page.select_option("#table_name", LABEL)
    page.wait_for_function(DONE)
    page.fill("#filter_locationID", sample[ID_COL])
    _query(page, lambda: page.click("#query_btn"))

    for close in ("Escape", "backdrop", "button"):
        page.locator(".map-btn").first.click()
        page.wait_for_function(
            "() => document.getElementById('map_status').textContent !== 'Loading polygon…'", timeout=60000)
        assert page.evaluate("document.getElementById('map_dialog').open")
        assert page.text_content("#map_status") == ""
        assert sample[ID_COL] in page.text_content("#map_title")
        assert page.locator("#leaflet-map path.leaflet-interactive").count() == 1  # previous polygon removed
        if close == "Escape":
            page.keyboard.press("Escape")
        elif close == "backdrop":
            page.mouse.click(3, 3)
        else:
            page.click("#map_close")
        assert not page.evaluate("document.getElementById('map_dialog').open"), f"not closed by {close}"
    assert not page.errors, page.errors


def test_no_horizontal_page_scroll_on_phone(page):
    page.set_viewport_size({"width": 390, "height": 800})
    assert not page.evaluate("document.documentElement.scrollWidth > window.innerWidth")
