"""Geographic Entities Explorer API — FastAPI + DuckDB."""
import json

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from .config import DEFAULT_TOLERANCE, DISPLAY_COLS, FILTER_COLS, TABLES, TOLERANCES
from .db import get_cursor, lifespan

app = FastAPI(title="Geographic Entities Explorer API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://regred-project.github.io",  # Pages origin (CORS ignores the /geo_explorer_website/ path)
        "http://localhost:8080",             # local static-file testing
    ],
    allow_methods=["GET"],
    allow_headers=["*"],
)


def _resolve_table(table_label: str) -> tuple[str, str]:
    if table_label not in TABLES:
        raise HTTPException(status_code=400, detail=f"Unknown table '{table_label}'")
    return TABLES[table_label]


@app.get("/api/tables")
def list_tables():
    return {"tables": list(TABLES.keys())}


@app.get("/api/rows")
def get_rows(
    table: str,
    locationID: str = "",
    continent: str = "",
    country: str = "",
    stateProvince: str = "",
    county: str = "",
    locality: str = "",
    limit: int = Query(200, ge=1, le=2000),
):
    tbl, id_col = _resolve_table(table)

    filters = {
        "locationID": locationID,
        "continent": continent,
        "country": country,
        "stateProvince": stateProvince,
        "county": county,
        "locality": locality,
    }

    conds, params = [], []
    for col in FILTER_COLS:
        val = filters[col].strip()
        if val:
            conds.append(f"LOWER({col}) LIKE LOWER(?)")
            params.append(f"%{val}%")

    where = f"WHERE {' AND '.join(conds)}" if conds else ""
    cols_sql = ", ".join([id_col] + DISPLAY_COLS)

    cur = get_cursor()
    rows = cur.execute(
        f"SELECT {cols_sql} FROM {tbl} {where} LIMIT ?",
        params + [limit],
    ).fetchall()
    col_names = [id_col] + DISPLAY_COLS

    return {
        "count": len(rows),
        "id_column": id_col,
        "rows": [dict(zip(col_names, row)) for row in rows],
    }


@app.get("/api/geometry")
def get_geometry(table: str, id: str):
    tbl, id_col = _resolve_table(table)
    tolerance = TOLERANCES.get(tbl, DEFAULT_TOLERANCE)

    cur = get_cursor()
    result = cur.execute(
        f"SELECT ST_AsGeoJSON(ST_Simplify(geometry, ?)) "
        f"FROM {tbl} WHERE {id_col} = ?",
        [tolerance, id],
    ).fetchone()

    if not result or not result[0]:
        raise HTTPException(status_code=404, detail="No geometry found for this row")

    return {"geojson": json.loads(result[0])}
