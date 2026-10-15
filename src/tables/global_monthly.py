"""
TABLE 1: global_monthly  (one row per month)

year | month | co2_ppm | co2_mlo_ppm | co2_mlo_deseason_ppm | ch4_ppb | n2o_ppb | temp_anomaly

Sources (data/cleaned):
  noaa/co2_mm_gl.csv    average        -> co2_ppm               (global mean, from 1979)
  noaa/co2_mm_mlo.csv   average        -> co2_mlo_ppm           (Mauna Loa, one site, from 1958)
                        deseasonalized -> co2_mlo_deseason_ppm
  noaa/ch4_mm_gl.csv    average        -> ch4_ppb               (from 1983)
  noaa/n2o_mm_gl.csv    average        -> n2o_ppb               (from 2001)
  nasa/GLB.Ts_dSST.csv  Jan..Dec       -> temp_anomaly          (from 1880, baseline 1951-1980)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from common import (CLEANED, PipelineError, clean_int_keys, coerce_numeric, dedupe,
                    finalize, log, positive_only, read_source, run_standalone)

NAME = "global_monthly"
CSV_NAME = "global_monthly.csv"
KEY = ["year", "month"]
DEPENDS = []

SCHEMA = {
    "year": "int64",
    "month": "int64",
    "co2_ppm": "float64",
    "co2_mlo_ppm": "float64",
    "co2_mlo_deseason_ppm": "float64",
    "ch4_ppb": "float64",
    "n2o_ppb": "float64",
    "temp_anomaly": "float64",
}
VALUE_COLUMNS = [c for c in SCHEMA if c not in KEY]

CREATE_SQL = """
CREATE TABLE global_monthly (
    year                  INTEGER NOT NULL,
    month                 INTEGER NOT NULL CHECK (month BETWEEN 1 AND 12),
    co2_ppm               REAL,
    co2_mlo_ppm           REAL,
    co2_mlo_deseason_ppm  REAL,
    ch4_ppb               REAL,
    n2o_ppb               REAL,
    temp_anomaly          REAL,
    PRIMARY KEY (year, month)
);
"""

MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
MONTH_NUMBER = {name: number for number, name in enumerate(MONTHS, start=1)}


def _load_noaa(filename: str, value_columns: dict) -> pd.DataFrame:
    """NOAA files are already long (one row per month). Keep year, month and the wanted columns."""
    required = {"year": ["year"], "month": ["month"], **value_columns}
    df = read_source(CLEANED / "noaa" / filename, required)
    df = clean_int_keys(df, ["year", "month"], filename)
    if not df["month"].between(1, 12).all():
        bad = sorted(df.loc[~df["month"].between(1, 12), "month"].unique())[:5]
        raise PipelineError(f"{filename}: month values outside 1-12: {bad}")
    df = coerce_numeric(df, list(value_columns), filename)
    for col in value_columns:
        df[col] = positive_only(df[col], f"{filename}:{col}")
    return dedupe(df, KEY, filename)


def _load_nasa() -> pd.DataFrame:
    """NASA file is wide (one column per month). Reshape to year | month | temp_anomaly."""
    filename = "GLB.Ts_dSST.csv"
    required = {"year": ["year"], **{m: [m] for m in MONTHS}}
    wide = read_source(CLEANED / "nasa" / filename, required, na_values=["***"])
    wide = clean_int_keys(wide, ["year"], filename)
    wide = dedupe(wide, ["year"], filename)

    long = wide.melt(id_vars="year", var_name="month_name", value_name="temp_anomaly")
    long["month"] = long["month_name"].map(MONTH_NUMBER)
    long = coerce_numeric(long, ["temp_anomaly"], filename)
    return long[["year", "month", "temp_anomaly"]]


def build(ctx=None) -> pd.DataFrame:
    parts = [
        _load_nasa(),
        _load_noaa("co2_mm_gl.csv", {"co2_ppm": ["average"]}),
        _load_noaa("co2_mm_mlo.csv", {
            "co2_mlo_ppm": ["monthly_average", "average"],
            "co2_mlo_deseason_ppm": ["deseasonalized", "deseasonalised"],
        }),
        _load_noaa("ch4_mm_gl.csv", {"ch4_ppb": ["average"]}),
        _load_noaa("n2o_mm_gl.csv", {"n2o_ppb": ["average"]}),
    ]

    table = parts[0]
    for part in parts[1:]:
        try:
            table = table.merge(part, on=KEY, how="outer", validate="one_to_one")
        except pd.errors.MergeError as exc:
            raise PipelineError(f"{NAME}: merge found duplicate year-month rows ({exc})") from exc

    empty = table[VALUE_COLUMNS].isna().all(axis=1)
    if empty.any():
        log.info("%s: dropped %d month(s) with no data at all (future months)", NAME, int(empty.sum()))
        table = table[~empty]

    table = finalize(table, SCHEMA, KEY, NAME)

    for col in VALUE_COLUMNS:
        years = table.loc[table[col].notna(), "year"]
        if years.empty:
            raise PipelineError(f"{NAME}: column '{col}' has no data at all (check the source file)")
        log.info("%s: %-22s %d -> %d", NAME, col, years.min(), years.max())
    return table


if __name__ == "__main__":
    run_standalone(sys.modules[__name__])