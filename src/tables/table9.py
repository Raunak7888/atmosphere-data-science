"""
TABLE 9: data_coverage  (how much is missing, per variable per decade)

source | variable | decade | pct_missing | n_countries_with_data

Built from Table 1 (global variables) and Table 3 (country variables), whichever are available.
Used by G1. For global variables n_countries_with_data is empty.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from common import PipelineError, finalize, get_table, log, run_standalone
from tables import table1, table3

NAME = "data_coverage"
CSV_NAME = "table9.csv"
KEY = ["source", "variable", "decade"]
DEPENDS = []          # soft: uses whatever tables exist

SCHEMA = {
    "source": "string",
    "variable": "string",
    "decade": "int64",
    "pct_missing": "float64",
    "n_countries_with_data": "Int64",
}

CREATE_SQL = """
CREATE TABLE data_coverage (
    source                 TEXT    NOT NULL,
    variable               TEXT    NOT NULL,
    decade                 INTEGER NOT NULL,
    pct_missing            REAL    NOT NULL CHECK (pct_missing BETWEEN 0 AND 100),
    n_countries_with_data  INTEGER,
    PRIMARY KEY (source, variable, decade)
);
"""

GLOBAL_VARIABLES = {
    "co2_ppm": "NOAA",
    "co2_mlo_ppm": "NOAA",
    "co2_mlo_deseason_ppm": "NOAA",
    "ch4_ppb": "NOAA",
    "n2o_ppb": "NOAA",
    "temp_anomaly": "NASA",
}
COUNTRY_VARIABLES = {
    "population": "OWID", "gdp": "OWID", "co2_mt": "OWID", "co2_per_capita": "OWID",
    "cumulative_co2": "OWID", "share_global_co2": "OWID", "coal_co2": "OWID", "oil_co2": "OWID",
    "gas_co2": "OWID", "cement_co2": "OWID", "flaring_co2": "OWID", "methane": "OWID",
    "nitrous_oxide": "OWID", "total_ghg": "OWID", "pm25_exposure": "World Bank",
}


def _coverage(df: pd.DataFrame, variables: dict, by_country: bool) -> pd.DataFrame:
    work = df.copy()
    work["decade"] = work["year"] // 10 * 10
    decades = sorted(work["decade"].unique())
    rows = []
    for variable, source in variables.items():
        pct_missing = work.groupby("decade")[variable].apply(lambda s: s.isna().mean() * 100)
        if by_country:
            counts = work[work[variable].notna()].groupby("decade")["iso_code"].nunique()
        for decade in decades:
            rows.append({
                "source": source,
                "variable": variable,
                "decade": int(decade),
                "pct_missing": round(float(pct_missing[decade]), 2),
                "n_countries_with_data": int(counts.get(decade, 0)) if by_country else pd.NA,
            })
    return pd.DataFrame(rows)


def build(ctx=None) -> pd.DataFrame:
    ctx = {} if ctx is None else ctx
    frames = []

    monthly = get_table(ctx, table1, required=False)
    if monthly is not None:
        frames.append(_coverage(monthly, GLOBAL_VARIABLES, by_country=False))
    else:
        log.warning("%s: global_monthly not available, its variables are not covered", NAME)

    countries = get_table(ctx, table3, required=False)
    if countries is not None:
        frames.append(_coverage(countries, COUNTRY_VARIABLES, by_country=True))
    else:
        log.warning("%s: country_yearly not available, its variables are not covered", NAME)

    if not frames:
        raise PipelineError(f"{NAME}: neither global_monthly nor country_yearly is available")

    df = pd.concat(frames, ignore_index=True)
    df = finalize(df, SCHEMA, KEY, NAME)
    worst = df.sort_values("pct_missing", ascending=False).head(1).iloc[0]
    log.info("%s: %d rows; most missing: %s (%s, %ds) %.1f%%",
             NAME, len(df), worst["variable"], worst["source"], worst["decade"], worst["pct_missing"])
    return df


if __name__ == "__main__":
    run_standalone(sys.modules[__name__])