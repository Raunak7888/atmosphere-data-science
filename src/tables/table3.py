"""
TABLE 3: country_yearly  (one row per country per year, COUNTRIES ONLY)

Sources:
  data/cleaned/owid/owid-co2-data.csv      all columns except pm25_exposure
  data/cleaned/worldbank/pm25.csv          pm25_exposure, joined on iso_code + year

OWID aggregates (World, continents, income groups) are NOT here, they go to Table 5.
World Bank aggregates in pm25.csv are dropped automatically: they match no OWID country.

Derived columns are computed by matching on the real year (not row position),
so missing years in the data cannot silently stretch a "10 year" window.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from common import (CLEANED, PipelineError, clean_int_keys, coerce_numeric, dedupe,
                    finalize, get_table, log, read_source, run_standalone)
from owid import owid_countries
from tables import table4

NAME = "country_yearly"
CSV_NAME = "table3.csv"
KEY = ["iso_code", "year"]
DEPENDS = []          # Table 4 is only used for a soft check

SCHEMA = {
    "iso_code": "string",
    "country": "string",
    "year": "int64",
    "population": "float64",
    "gdp": "float64",
    "co2_mt": "float64",
    "co2_per_capita": "float64",
    "cumulative_co2": "float64",
    "share_global_co2": "float64",
    "coal_co2": "float64",
    "oil_co2": "float64",
    "gas_co2": "float64",
    "cement_co2": "float64",
    "flaring_co2": "float64",
    "methane": "float64",
    "nitrous_oxide": "float64",
    "total_ghg": "float64",
    "pm25_exposure": "float64",
    "co2_yoy_pct": "float64",
    "rank_total_co2": "Int64",
    "rank_per_capita": "Int64",
    "co2_per_gdp": "float64",
    "gdp_change_10yr_pct": "float64",
    "co2_change_10yr_pct": "float64",
    "decoupled_flag": "boolean",
}

CREATE_SQL = """
CREATE TABLE country_yearly (
    iso_code             TEXT    NOT NULL,
    country              TEXT    NOT NULL,
    year                 INTEGER NOT NULL,
    population           REAL,
    gdp                  REAL,
    co2_mt               REAL,
    co2_per_capita       REAL,
    cumulative_co2       REAL,
    share_global_co2     REAL,
    coal_co2             REAL,
    oil_co2              REAL,
    gas_co2              REAL,
    cement_co2           REAL,
    flaring_co2          REAL,
    methane              REAL,
    nitrous_oxide        REAL,
    total_ghg            REAL,
    pm25_exposure        REAL,
    co2_yoy_pct          REAL,
    rank_total_co2       INTEGER,
    rank_per_capita      INTEGER,
    co2_per_gdp          REAL,
    gdp_change_10yr_pct  REAL,
    co2_change_10yr_pct  REAL,
    decoupled_flag       INTEGER CHECK (decoupled_flag IN (0, 1)),
    PRIMARY KEY (iso_code, year)
);
"""

PM25_FILE = CLEANED / "worldbank" / "pm25.csv"
PM25_CANDIDATES = {
    "iso_code": ["countryiso3code", "country_iso3", "iso3", "iso_code", "iso3_code", "country_code"],
    "year": ["date", "year"],
    "pm25_exposure": ["value", "pm25_exposure", "pm25"],
}


def _load_pm25() -> pd.DataFrame:
    df = read_source(PM25_FILE, PM25_CANDIDATES)
    df["iso_code"] = df["iso_code"].astype("string").str.strip().str.upper()
    df = df[df["iso_code"].notna() & (df["iso_code"] != "")]
    df = clean_int_keys(df, ["year"], PM25_FILE.name)
    df = coerce_numeric(df, ["pm25_exposure"], PM25_FILE.name)
    df = df.dropna(subset=["pm25_exposure"])          # World Bank lists many years with no value
    if df.empty:
        raise PipelineError(f"{PM25_FILE.name}: no PM2.5 values found")
    return dedupe(df, KEY, PM25_FILE.name)


def _value_n_years_ago(df: pd.DataFrame, column: str, years: int) -> pd.Series:
    """Value of `column` for the same country `years` calendar years earlier (empty if that year is missing)."""
    lagged = df[["iso_code", "year", column]].copy()
    lagged["year"] = lagged["year"] + years
    lagged = lagged.rename(columns={column: "_lagged"})
    merged = df[["iso_code", "year"]].merge(lagged, on=KEY, how="left", validate="one_to_one")
    return pd.Series(merged["_lagged"].to_numpy(), index=df.index)


def _pct_change(current: pd.Series, base: pd.Series) -> pd.Series:
    return ((current - base) / base * 100).where(base > 0)


def build(ctx=None) -> pd.DataFrame:
    ctx = {} if ctx is None else ctx

    df = owid_countries().rename(columns={"co2": "co2_mt"})
    df = dedupe(df, KEY, "OWID countries")

    pm25 = _load_pm25()
    try:
        df = df.merge(pm25, on=KEY, how="left", validate="one_to_one")
    except pd.errors.MergeError as exc:
        raise PipelineError(f"{NAME}: duplicate keys while joining PM2.5 ({exc})") from exc

    matched = int(df["pm25_exposure"].notna().sum())
    if matched == 0:
        raise PipelineError(
            f"{NAME}: none of the {len(pm25)} PM2.5 rows matched an OWID country-year.\n"
            f"  PM2.5 codes look like {sorted(pm25['iso_code'].unique())[:5]}, "
            f"OWID codes look like {sorted(df['iso_code'].unique())[:5]}.\n"
            f"  Probably the wrong ISO column was picked in {PM25_FILE.name}; edit PM25_CANDIDATES."
        )
    log.info("%s: %d of %d PM2.5 rows matched OWID countries (the rest are aggregates/territories)",
             NAME, matched, len(pm25))

    df = df.sort_values(KEY).reset_index(drop=True)

    df["co2_yoy_pct"] = _pct_change(df["co2_mt"], _value_n_years_ago(df, "co2_mt", 1))
    df["rank_total_co2"] = df.groupby("year")["co2_mt"].rank(ascending=False, method="min").astype("Int64")
    df["rank_per_capita"] = df.groupby("year")["co2_per_capita"].rank(ascending=False, method="min").astype("Int64")
    df["co2_per_gdp"] = (df["co2_mt"] * 1e9 / df["gdp"]).where(df["gdp"] > 0)     # kg CO2 per dollar of GDP

    df["gdp_change_10yr_pct"] = _pct_change(df["gdp"], _value_n_years_ago(df, "gdp", 10))
    df["co2_change_10yr_pct"] = _pct_change(df["co2_mt"], _value_n_years_ago(df, "co2_mt", 10))
    known = df["gdp_change_10yr_pct"].notna() & df["co2_change_10yr_pct"].notna()
    flag = pd.Series(pd.NA, index=df.index, dtype="boolean")
    flag[known] = (df.loc[known, "gdp_change_10yr_pct"] > 0) & (df.loc[known, "co2_change_10yr_pct"] < 0)
    df["decoupled_flag"] = flag

    df = finalize(df, SCHEMA, KEY, NAME)

    ref = get_table(ctx, table4, required=False)      # soft check, never blocks
    if ref is not None:
        unmatched = sorted(set(df["iso_code"].dropna()) - set(ref["iso_code"]))
        if unmatched:
            log.warning("%s: %d OWID country code(s) not found in country_ref (region joins for C5 will miss them): %s",
                        NAME, len(unmatched), unmatched[:10])

    log.info("%s: %d rows, %d countries, years %d-%d",
             NAME, len(df), df["iso_code"].nunique(), df["year"].min(), df["year"].max())
    return df


if __name__ == "__main__":
    run_standalone(sys.modules[__name__])