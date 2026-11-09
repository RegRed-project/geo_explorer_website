"""Dataset definitions shared by all query endpoints."""
import os

# In the Docker image the data layer places the file at /data/...; override
# with DB_PATH for local development against a file elsewhere.
DB_PATH = os.environ.get("DB_PATH", "/data/geographic_entities_prepared.duckdb")

# (label shown in UI) -> (table name in DB, primary-key column)
TABLES = {
    "Countries (ADM0)": ("adm0_prepared", "locationID"),
    "States / Provinces (ADM1)": ("adm1_prepared", "locationID"),
    "Counties (ADM2)": ("adm2_prepared", "locationID"),
    "Custom regions": ("custom_regions", "locationID"),
    "Additional administrative regions": ("additional_administrative_regions", "locationID"),
}

# Douglas-Peucker simplification tolerance (degrees) applied before sending a
# polygon to the map. Effective tolerance per polygon:
#   min(table tolerance, SIMPLIFY_FRACTION * max(bbox width, bbox height))
# The table value caps payload size for large polygons; the relative term keeps
# small ones (e.g. Andorra, ~0.4 deg across) from collapsing into a few vertices.
# 1/1000 of the extent is about one pixel when the polygon fills the map popup.
TOLERANCES = {
    "adm0_prepared": 0.05,
    "adm1_prepared": 0.01,
    "adm2_prepared": 0.005,
}
DEFAULT_TOLERANCE = 0.001
SIMPLIFY_FRACTION = 0.001

DISPLAY_COLS = [
    "continent", "country", "countryCode", "parentISO",
    "stateProvince", "county", "locality",
    "isCustomRegion", "geometrySource",
]
