"""
TABLE 4: country_ref  (one row per World Bank entry)

iso_code | country | region | income_group | is_aggregate

Source: data/cleaned/worldbank/countries.csv
World Bank lists countries AND aggregates (World, Arab World, ...). Aggregates have region "Aggregates".

Column names in your flattened file are matched from the candidate lists below (case ignored).
If your file uses other names, add them to CANDIDATES. The error message shows the real names.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from common import CLEANED, PipelineError, dedupe, finalize, log, read_source, run_standalone

NAME = "country_ref"
CSV_NAME = "table4.csv"
KEY = ["iso_code"]
DEPENDS = []

SCHEMA = {
    "iso_code": "string",
    "country": "string",
    "region": "string",
    "income_group": "string",
    "is_aggregate": "bool",
}

CREATE_SQL = """
CREATE TABLE country_ref (
    iso_code      TEXT PRIMARY KEY,
    country       TEXT NOT NULL,
    region        TEXT,
    income_group  TEXT,
    is_aggregate  INTEGER NOT NULL CHECK (is_aggregate IN (0, 1))
);
"""

FILE = CLEANED / "worldbank" / "countries.csv"
CANDIDATES = {
    "iso_code": ["id", "iso3", "iso_code", "iso3code", "countryiso3code", "code"],
    "country": ["name", "country", "country_name"],
    "region": ["region", "region_value", "region.value", "region_name"],
    "income_group": ["income_group", "incomelevel", "incomelevel_value", "incomelevel.value",
                     "income_level", "income"],
}


def build(ctx=None) -> pd.DataFrame:
    df = read_source(FILE, CANDIDATES)
    for col in CANDIDATES:
        df[col] = df[col].astype("string").str.strip()
    df["iso_code"] = df["iso_code"].str.upper()

    blank = df["iso_code"].isna() | (df["iso_code"] == "") | df["country"].isna()
    if blank.any():
        log.warning("%s: dropped %d row(s) without an iso code or name", NAME, int(blank.sum()))
        df = df[~blank]

    df["is_aggregate"] = (df["region"].fillna("").str.lower() == "aggregates").astype(bool)
    df = dedupe(df, KEY, FILE.name)

    df = finalize(df, SCHEMA, KEY, NAME)
    if df["region"].isna().all():
        raise PipelineError(f"{NAME}: region is empty for every row, wrong column picked? check CANDIDATES")
    log.info("%s: %d entries, %d aggregates", NAME, len(df), int(df["is_aggregate"].sum()))
    return df


if __name__ == "__main__":
    run_standalone(sys.modules[__name__])