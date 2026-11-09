"""API behaviour, with expected results computed directly from the database."""
import json
import time

import pytest

from app.config import TABLES

from conftest import COLUMNS, ID_COL

LABELS = list(TABLES)
PAGES_ORIGIN = "https://regred-project.github.io"


def _sample_row(con, tbl):
    row = con.execute(f"SELECT {', '.join(COLUMNS)} FROM {tbl} "
                      f"USING SAMPLE 1 ROWS (reservoir, 42)").fetchone()
    return dict(zip(COLUMNS, row))


def _rows(api, **params):
    r = api.get("/api/rows", params=params)
    assert r.status_code == 200, r.text
    return r.json()


def test_tables_endpoint(api):
    data = api.get("/api/tables").json()
    assert data["tables"] == LABELS
    assert data["columns"] == COLUMNS
    assert data["id_column"] == ID_COL


def test_cors_allows_pages_origin(api):
    r = api.get("/api/tables", headers={"Origin": PAGES_ORIGIN})
    assert r.headers.get("access-control-allow-origin") == PAGES_ORIGIN


@pytest.mark.parametrize("label", LABELS)
def test_rows_unfiltered(api, label):
    data = _rows(api, table=label, limit=5)
    assert 1 <= data["count"] <= 5
    assert list(data["rows"][0]) == COLUMNS


@pytest.mark.parametrize("label", LABELS)
def test_id_exact_vs_partial(api, con, label):
    tbl = TABLES[label][0]
    rid = _sample_row(con, tbl)[ID_COL]

    exact = _rows(api, table=label, locationID=rid)
    assert exact["count"] >= 1 and all(r[ID_COL].lower() == rid.lower() for r in exact["rows"])

    prefix = rid[:-1]
    n_prefix_ids = con.execute(f"SELECT count(*) FROM {tbl} WHERE lower({ID_COL}) = lower(?)",
                               [prefix]).fetchone()[0]
    assert _rows(api, table=label, locationID=prefix)["count"] == n_prefix_ids

    partial = _rows(api, table=label, locationID=prefix, partial="true", limit=2000)
    assert any(r[ID_COL] == rid for r in partial["rows"]) or partial["count"] == 2000
    assert all(prefix.lower() in r[ID_COL].lower() for r in partial["rows"])


@pytest.mark.parametrize("label", LABELS)
def test_general_search_matches_sql(api, con, label):
    tbl = TABLES[label][0]
    row = _sample_row(con, tbl)
    term = next((row[c] for c in ("locality", "county", "stateProvince", "country")
                 if row[c] and row[c].strip()), row[ID_COL])
    term = term.strip()[:6]
    any_col = " OR ".join(f"contains(lower({c}), lower(?))" for c in COLUMNS)
    expected = con.execute(f"SELECT count(*) FROM (SELECT 1 FROM {tbl} WHERE {any_col} LIMIT 2000)",
                           [term] * len(COLUMNS)).fetchone()[0]
    data = _rows(api, table=label, q=term, limit=2000)
    assert data["count"] == expected, f"q={term!r}"
    assert all(any(term.lower() in (r[c] or "").lower() for c in COLUMNS) for r in data["rows"])


def test_search_and_filters_combine_with_and(api, con):
    label = LABELS[0]
    tbl = TABLES[label][0]
    row = _sample_row(con, tbl)
    data = _rows(api, table=label, q=row[ID_COL], country=row["country"] or "", limit=2000)
    assert any(r[ID_COL] == row[ID_COL] for r in data["rows"])
    assert _rows(api, table=label, q=row[ID_COL], country="zz-no-such-country")["count"] == 0


@pytest.mark.parametrize("wildcard", ["%", "_"])
def test_like_wildcards_are_literal(api, con, wildcard):
    label = LABELS[0]
    tbl = TABLES[label][0]
    any_col = " OR ".join(f"contains({c}, ?)" for c in COLUMNS)
    expected = con.execute(f"SELECT count(*) FROM (SELECT 1 FROM {tbl} WHERE {any_col} LIMIT 2000)",
                           [wildcard] * len(COLUMNS)).fetchone()[0]
    assert _rows(api, table=label, q=wildcard, limit=2000)["count"] == expected


@pytest.mark.parametrize("col", [c for c in COLUMNS if c != ID_COL])
def test_column_filter_exact_vs_partial(api, con, col):
    """Every column filter: whole-value match by default, substring with partial=true; case ignored."""
    # Prefer ADM2 (mid-sized); fall back to the first table where the column has values.
    order = sorted(LABELS, key=lambda lab: lab != "Counties (ADM2)")
    for label in order:
        tbl = TABLES[label][0]
        row = con.execute(f"SELECT {col} FROM {tbl} WHERE length(trim({col})) > 1 "
                          f"USING SAMPLE 1 ROWS (reservoir, 3)").fetchone()
        if row is not None:
            break
    else:
        pytest.skip(f"{col} has no values longer than 1 character in any table")
    value = row[0].strip()

    n_whole = con.execute(f"SELECT count(*) FROM (SELECT 1 FROM {tbl} WHERE lower({col}) = lower(?) "
                          f"LIMIT 2000)", [value]).fetchone()[0]
    exact = _rows(api, table=label, limit=2000, **{col: value.swapcase()})
    assert exact["count"] == n_whole >= 1
    assert all(r[col].lower() == value.lower() for r in exact["rows"])

    part = (value[1:4] if len(value) > 4 else value[:-1]).swapcase()  # e.g. "CL" -> "c", "No" -> "n"
    n_whole_part = con.execute(f"SELECT count(*) FROM {tbl} WHERE lower({col}) = lower(?)",
                               [part]).fetchone()[0]
    assert _rows(api, table=label, **{col: part})["count"] == min(n_whole_part, 200)
    partial = _rows(api, table=label, partial="true", limit=2000, **{col: part})
    assert partial["count"] >= 1
    assert all(part.lower() in r[col].lower() for r in partial["rows"])


def test_bad_requests(api):
    assert api.get("/api/rows", params={"table": "no such table"}).status_code == 400
    assert api.get("/api/rows", params={"table": LABELS[0], "limit": 0}).status_code == 422
    assert api.get("/api/rows", params={"table": LABELS[0], "limit": 2001}).status_code == 422
    assert api.get("/api/geometry", params={"table": LABELS[0], "id": "zz-no-such-id"}).status_code == 404


@pytest.mark.parametrize("label", LABELS)
def test_geometry_of_sample_row(api, con, label):
    rid = _sample_row(con, TABLES[label][0])[ID_COL]
    r = api.get("/api/geometry", params={"table": label, "id": rid})
    assert r.status_code == 200, r.text
    assert r.json()["geojson"]["type"] in ("Polygon", "MultiPolygon")


@pytest.mark.parametrize("label", LABELS)
def test_small_polygons_keep_their_shape(api, con, label):
    """Simplification must not collapse small polygons (e.g. Andorra) or erase most of their area.

    Checked on the 30 polygons with the smallest bounding-box extent. The 0.5 area-ratio
    floor allows for archipelagos whose bbox spans far more than their islets.
    """
    tbl = TABLES[label][0]
    ids = [r[0] for r in con.execute(
        f"SELECT {ID_COL} FROM {tbl} ORDER BY GREATEST(ST_XMax(geometry) - ST_XMin(geometry), "
        f"ST_YMax(geometry) - ST_YMin(geometry)) LIMIT 30").fetchall()]
    bad = []
    for rid in ids:
        r = api.get("/api/geometry", params={"table": label, "id": rid})
        if r.status_code != 200:
            bad.append((rid, f"HTTP {r.status_code}"))
            continue
        simplified = r.json()["geojson"]
        ratio = con.execute(
            f"SELECT ST_Area(ST_GeomFromGeoJSON(?)) / ST_Area(geometry) FROM {tbl} "
            f"WHERE {ID_COL} = ? LIMIT 1", [json.dumps(simplified), rid]).fetchone()[0]
        if not ratio or ratio < 0.5:
            bad.append((rid, f"area ratio {ratio}"))
    assert not bad, f"{tbl}: small polygons damaged by simplification: {bad}"


@pytest.mark.parametrize("label", LABELS)
def test_largest_geometry_is_servable(api, con, label):
    """Worst case per table: the polygon with most vertices must load in reasonable time and size."""
    tbl = TABLES[label][0]
    rid, n_vertices = con.execute(
        f"SELECT {ID_COL}, ST_NPoints(geometry) FROM {tbl} "
        f"ORDER BY ST_NPoints(geometry) DESC LIMIT 1").fetchone()
    t0 = time.time()
    r = api.get("/api/geometry", params={"table": label, "id": rid})
    elapsed = time.time() - t0
    assert r.status_code == 200
    mb = len(r.content) / 1e6
    assert elapsed < 10, f"{rid} ({n_vertices} vertices) took {elapsed:.1f} s"
    assert mb < 10, f"{rid} ({n_vertices} vertices) returned {mb:.1f} MB of GeoJSON"
