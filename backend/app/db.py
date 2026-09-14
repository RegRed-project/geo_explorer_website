"""Shared read-only DuckDB connection, opened once at app startup."""
from contextlib import asynccontextmanager

import duckdb
from fastapi import FastAPI

from .config import DB_PATH

_state: dict = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    con = duckdb.connect(DB_PATH, read_only=True)
    con.execute("INSTALL spatial; LOAD spatial;")
    _state["con"] = con
    try:
        yield
    finally:
        con.close()
        _state.clear()


def get_cursor():
    """A cheap, independent handle onto the shared read-only connection.

    DuckDB connections aren't safe to share across concurrent requests directly;
    .cursor() hands out an independent cursor onto the same open database file
    without re-attaching or re-loading the spatial extension each time.
    """
    return _state["con"].cursor()
