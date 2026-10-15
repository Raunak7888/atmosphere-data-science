"""
TABLE 2: global_yearly  (one row per year, 1880 to latest)

Built from Table 1 (monthly -> yearly) plus the OWID "World" row.
Needs Table 1 first (python src/tables/table1.py), or run createCsv.py which does the order for you.

Rules (change the constants if you disagree):
  - a yearly mean exists only if all MIN_MONTHS months exist, otherwise it is empty
  - is_complete_year = all 12 months of temp_anomaly exist
  - detrended columns: one straight line per series, fitted over the years where BOTH
    co2_mlo_ppm and temp_anomaly exist; empty outside those years
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd

from common import PipelineError, finalize, get_table, log, run_standalone
from owid import load_owid
from tables import global_monthly

NAME = "global_yearly"
CSV_NAME = "global_yearly.csv"
KEY = ["year"]
DEPENDS = [global_monthly]

MIN_MONTHS = 12

SCHEMA = {
    "year": "int64",
    "decade": "int64",
    "is_complete_year": "bool",
    "co2_ppm": "float64",
    "co2_mlo_ppm": "float64",
    "ch4_ppb": "float64",
    "n2o_ppb": "float64",
    "temp_anomaly": "float64",
    "world_co2_mt": "float64",
    "co2_mlo_yoy_change": "float64",
    "co2_pct_index": "float64",
    "ch4_pct_index": "float64",
    "n2o_pct_index": "float64",
    "temp_yoy_change": "float64",
    "co2_mlo_detrended": "float64",
    "temp_detrended": "float64",
}

CREATE_SQL = """
CREATE TABLE global_yearly (
    year                INTEGER PRIMARY KEY,
    decade              INTEGER NOT NULL,
    is_complete_year    INTEGER NOT NULL CHECK (is_complete_year IN (0, 1)),
    co2_ppm             REAL,
    co2_mlo_ppm         REAL,
    ch4_ppb             REAL,
    n2o_ppb             REAL,
    temp_anomaly        REAL,
    world_co2_mt        REAL,
    co2_mlo_yoy_change  REAL,
    co2_pct_index       REAL,
    ch4_pct_index       REAL,
    n2o_pct_index       REAL,
    temp_yoy_change     REAL,
    co2_mlo_detrended   REAL,
    temp_detrended      REAL
);
"""

MEAN_COLUMNS = ["co2_ppm", "co2_mlo_ppm", "ch4_ppb", "n2o_ppb", "temp_anomaly"]


def _yearly_mean(monthly: pd.DataFrame, column: str) -> pd.Series:
    """Mean per year, but empty if the year has fewer than MIN_MONTHS values."""
    grouped = monthly.groupby("year")[column]
    return grouped.mean().where(grouped.count() >= MIN_MONTHS)


def _pct_index(series: pd.Series, label: str) -> pd.Series:
    valid = series.dropna()
    if valid.empty:
        raise PipelineError(f"{NAME}: '{label}' has no complete year, cannot build its index")
    return series / valid.iloc[0] * 100


def _add_detrended(df: pd.DataFrame) -> pd.DataFrame:
    both = df["co2_mlo_ppm"].notna() & df["temp_anomaly"].notna()
    if int(both.sum()) < 10:
        raise PipelineError(f"{NAME}: only {int(both.sum())} years have both CO2 and temperature, too few to detrend")
    years = df.loc[both, "year"].to_numpy(dtype=float)
    for source, target in (("co2_mlo_ppm", "co2_mlo_detrended"), ("temp_anomaly", "temp_detrended")):
        values = df.loc[both, source].to_numpy(dtype=float)
        try:
            slope, intercept = np.polyfit(years, values, 1)
        except np.linalg.LinAlgError as exc:
            raise PipelineError(f"{NAME}: could not fit a trend line for {source} ({exc})") from exc
        df[target] = np.nan
        df.loc[both, target] = values - (slope * years + intercept)
    return df


def _load_world() -> pd.DataFrame:
    world = load_owid()
    world = world[world["country"] == "World"]
    if world.empty:
        raise PipelineError("OWID file has no 'World' rows (country == 'World')")
    return world[["year", "co2"]].rename(columns={"co2": "world_co2_mt"})


def build(ctx=None) -> pd.DataFrame:
    ctx = {} if ctx is None else ctx
    monthly = get_table(ctx, global_monthly)

    yearly = pd.DataFrame({col: _yearly_mean(monthly, col) for col in MEAN_COLUMNS})
    yearly["is_complete_year"] = monthly.groupby("year")["temp_anomaly"].count() == 12
    yearly.index.name = "year"
    df = yearly.reset_index().sort_values("year").reset_index(drop=True)

    if (df["year"].diff().dropna() != 1).any():
        raise PipelineError(f"{NAME}: Table 1 is missing whole year(s), cannot compute year-over-year changes")

    try:
        df = df.merge(_load_world(), on="year", how="left", validate="one_to_one")
    except pd.errors.MergeError as exc:
        raise PipelineError(f"{NAME}: duplicate years in the OWID World rows ({exc})") from exc

    df["decade"] = df["year"] // 10 * 10
    df["co2_mlo_yoy_change"] = df["co2_mlo_ppm"].diff()
    df["temp_yoy_change"] = df["temp_anomaly"].diff()
    df["co2_pct_index"] = _pct_index(df["co2_ppm"], "co2_ppm")
    df["ch4_pct_index"] = _pct_index(df["ch4_ppb"], "ch4_ppb")
    df["n2o_pct_index"] = _pct_index(df["n2o_ppb"], "n2o_ppb")
    df = _add_detrended(df)

    df = finalize(df, SCHEMA, KEY, NAME)
    incomplete = df.loc[~df["is_complete_year"], "year"].tolist()
    log.info("%s: %d years (%d to %d); incomplete years: %s",
             NAME, len(df), df["year"].min(), df["year"].max(), incomplete or "none")
    return df


if __name__ == "__main__":
    run_standalone(sys.modules[__name__])