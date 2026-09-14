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
    "Custom and additional administrative regions": (
        "custom_and_additional_admin_regions_full",
        "locationID",
    ),
}

# Simplification tolerance (degrees) by table - coarser for larger polygons
TOLERANCES = {
    "adm0_prepared": 0.05,
    "adm1_prepared": 0.01,
    "adm2_prepared": 0.005,
}
DEFAULT_TOLERANCE = 0.001

DISPLAY_COLS = [
    "continent", "country", "countryCode",
    "stateProvince", "county", "locality",
    "isCustomRegion", "geometrySource",
]

FILTER_COLS = [
    "locationID", "continent", "country",
    "stateProvince", "county", "locality",
]
