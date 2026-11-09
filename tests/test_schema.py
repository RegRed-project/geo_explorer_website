"""The database provides every table and column the backend config relies on."""
import warnings

import pytest

from app.config import TABLES, TOLERANCES

from conftest import COLUMNS, ID_COL

TABLE_NAMES = sorted({tbl for tbl, _ in TABLES.values()})

# Duplicated IDs already known in the data build; reported as warnings, not failures.
# Remove an entry once the data is fixed. Any duplicate not listed here still fails.
KNOWN_DUPLICATE_IDS = {
    "custom_regions": {"GI_0"},  # 3 Global Islands polygons share this ID
}


def _columns(con, tbl):
    return dict(con.execute(
        "SELECT column_name, data_type FROM information_schema.columns "
        "WHERE table_schema = 'main' AND table_name = ?", [tbl]).fetchall())


@pytest.mark.parametrize("tbl", TABLE_NAMES)
def test_table_has_required_columns(con, tbl):
    cols = _columns(con, tbl)
    assert cols, f"table {tbl} does not exist"
    missing = [c for c in COLUMNS + ["geometry"] if c not in cols]
    assert not missing, f"{tbl} lacks columns {missing}"


@pytest.mark.parametrize("tbl", TABLE_NAMES)
def test_column_types(con, tbl):
    cols = _columns(con, tbl)
    # Filters use LOWER(col) LIKE ..., which needs text columns.
    not_text = {c: cols[c] for c in COLUMNS if c in cols and cols[c] != "VARCHAR"}
    assert not not_text, f"{tbl}: non-VARCHAR filter columns {not_text}"
    assert cols.get("geometry") == "GEOMETRY", f"{tbl}.geometry is {cols.get('geometry')}"


@pytest.mark.parametrize("tbl", TABLE_NAMES)
def test_ids_unique_and_present(con, tbl):
    dupes = con.execute(
        f"SELECT {ID_COL}, count(*) FROM {tbl} GROUP BY 1 HAVING count(*) > 1 "
        f"ORDER BY 2 DESC").fetchall()
    known = KNOWN_DUPLICATE_IDS.get(tbl, set())
    tolerated = [d for d in dupes if d[0] in known]
    if tolerated:
        warnings.warn(f"{tbl}: known duplicated {ID_COL} still present "
                      f"(the map shows an arbitrary one): {tolerated}")
    new = [d for d in dupes if d[0] not in known]
    assert not new, f"{tbl}: duplicated {ID_COL} (the map shows an arbitrary one): {new[:10]}"
    nulls = con.execute(f"SELECT count(*) FROM {tbl} WHERE {ID_COL} IS NULL").fetchone()[0]
    assert nulls == 0, f"{tbl}: {nulls} rows with NULL {ID_COL}"


@pytest.mark.parametrize("tbl", TABLE_NAMES)
def test_geometries(con, tbl):
    n_null, n_empty, n_bad_type, xmin, xmax, ymin, ymax = con.execute(f"""
        SELECT count(*) FILTER (WHERE geometry IS NULL),
               count(*) FILTER (WHERE ST_IsEmpty(geometry)),
               count(*) FILTER (WHERE ST_GeometryType(geometry)::VARCHAR
                                NOT IN ('POLYGON', 'MULTIPOLYGON')),
               min(ST_XMin(geometry)), max(ST_XMax(geometry)),
               min(ST_YMin(geometry)), max(ST_YMax(geometry))
        FROM {tbl}""").fetchone()
    assert n_null == 0, f"{tbl}: {n_null} NULL geometries"
    assert n_empty == 0, f"{tbl}: {n_empty} empty geometries"
    assert n_bad_type == 0, f"{tbl}: {n_bad_type} non-polygon geometries"
    # Leaflet expects lon/lat degrees (WGS84); projected coordinates would fall outside.
    # 1e-6 deg slack absorbs floating-point noise at the antimeridian (e.g. 180.0000000000001).
    eps = 1e-6
    assert -180 - eps <= xmin and xmax <= 180 + eps and -90 - eps <= ymin and ymax <= 90 + eps, \
        f"{tbl}: bounds ({xmin}, {ymin}, {xmax}, {ymax}) are not lon/lat degrees"


def test_tolerances_refer_to_served_tables():
    unknown = set(TOLERANCES) - set(TABLE_NAMES)
    assert not unknown, f"TOLERANCES lists tables not in TABLES: {unknown}"
