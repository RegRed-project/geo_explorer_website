"""Geographic Entities Explorer API — FastAPI + DuckDB."""
import json
import re

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware

from .config import DEFAULT_TOLERANCE, DISPLAY_COLS, SIMPLIFY_FRACTION, TABLES, TOLERANCES
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


def _like_pattern(val: str) -> str:
    """Substring pattern with LIKE wildcards in the user's text taken literally."""
    escaped = val.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _ilike(col: str) -> str:
    return f"LOWER({col}) LIKE LOWER(?) ESCAPE '\\'"


MAX_TERMS = 20  # per search box, to keep the generated SQL small
_OR = re.compile(r"\s+OR\s+")
_AND = re.compile(r"\s+AND\s+")


def _parse_terms(val: str) -> list[list[str]]:
    """Split a search value into OR-groups of AND-terms: 'a AND b OR c' -> [[a, b], [c]].

    Only upper-case AND / OR surrounded by spaces are operators, so values such as
    'Trinidad and Tobago' stay literal. AND binds tighter than OR; no parentheses.
    """
    groups = [[t.strip() for t in _AND.split(g) if t.strip()] for g in _OR.split(val.strip())]
    groups = [g for g in groups if g]
    if sum(len(g) for g in groups) > MAX_TERMS:
        raise HTTPException(status_code=400, detail=f"At most {MAX_TERMS} search terms per box")
    return groups


def _bool_expr(groups: list[list[str]], term_sql) -> tuple[str, list]:
    """SQL for OR-of-AND groups; term_sql(term) returns (sql, params) for one term."""
    or_parts, params = [], []
    for group in groups:
        and_parts = []
        for term in group:
            sql, p = term_sql(term)
            and_parts.append(sql)
            params.extend(p)
        or_parts.append("(" + " AND ".join(and_parts) + ")")
    return "(" + " OR ".join(or_parts) + ")", params


@app.get("/api/tables")
def list_tables():
    # All tables share the same key column, so the column list is table-independent.
    id_col = next(iter(TABLES.values()))[1]
    return {"tables": list(TABLES.keys()), "columns": [id_col] + DISPLAY_COLS, "id_column": id_col}


@app.get("/api/rows")
def get_rows(
    request: Request,
    table: str,
    q: str = "",
    partial: bool = False,
    limit: int = Query(200, ge=1, le=2000),
):
    """Rows of `table`, filtered by any shown column passed as a query parameter.

    - column filters: case-insensitive whole-value match, or substring match
      when `partial=true`.
    - `q`: case-insensitive substring match against any shown column.
    - every value may combine terms with upper-case AND / OR (AND binds tighter).
    All boxes are combined with AND.
    """
    tbl, id_col = _resolve_table(table)
    cols = [id_col] + DISPLAY_COLS

    def add(groups, term_sql):
        if groups:
            sql, p = _bool_expr(groups, term_sql)
            conds.append(sql)
            params.extend(p)

    conds, params = [], []
    for col in cols:
        groups = _parse_terms(request.query_params.get(col, ""))
        if partial:
            add(groups, lambda t, col=col: (_ilike(col), [_like_pattern(t)]))
        else:
            add(groups, lambda t, col=col: (f"LOWER({col}) = LOWER(?)", [t]))

    # Each general-search term may match in any column.
    add(_parse_terms(q),
        lambda t: ("(" + " OR ".join(_ilike(c) for c in cols) + ")", [_like_pattern(t)] * len(cols)))

    where = f"WHERE {' AND '.join(conds)}" if conds else ""

    cur = get_cursor()
    rows = cur.execute(
        f"SELECT {', '.join(cols)} FROM {tbl} {where} LIMIT ?",
        params + [limit],
    ).fetchall()

    return {
        "count": len(rows),
        "id_column": id_col,
        "rows": [dict(zip(cols, row)) for row in rows],
    }


@app.get("/api/geometry")
def get_geometry(table: str, id: str):
    tbl, id_col = _resolve_table(table)
    tolerance = TOLERANCES.get(tbl, DEFAULT_TOLERANCE)

    cur = get_cursor()
    result = cur.execute(
        f"SELECT ST_AsGeoJSON(ST_Simplify(geometry, LEAST(?, ? * GREATEST("
        f"ST_XMax(geometry) - ST_XMin(geometry), ST_YMax(geometry) - ST_YMin(geometry))))) "
        f"FROM {tbl} WHERE {id_col} = ?",
        [tolerance, SIMPLIFY_FRACTION, id],
    ).fetchone()

    if not result or not result[0]:
        raise HTTPException(status_code=404, detail="No geometry found for this row")

    return {"geojson": json.loads(result[0])}
