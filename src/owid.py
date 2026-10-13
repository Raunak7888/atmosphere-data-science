"""
Loads data/cleaned/owid/owid-co2-data.csv ONCE and shares it with tables 2, 3 and 5.

OWID mixes real countries with aggregates (World, Asia, High-income countries, ...).
A row is an AGGREGATE when iso_code is empty or starts with OWID_
(exception: OWID_KOS is Kosovo, a real country).
"""
from __future__ import annotations

from functools import lru_cache

import pandas as pd

from common import CLEANED, PipelineError, clean_int_keys, coerce_numeric, dedupe, log, read_source

FILE = CLEANED / "owid" / "owid-co2-data.csv"

REQUIRED = {
    "country": ["country"],
    "iso_code": ["iso_code"],
    "year": ["year"],
    "co2": ["co2"],
}
OPTIONAL = {
    "population": ["population"],
    "gdp": ["gdp"],
    "co2_per_capita": ["co2_per_capita"],
    "cumulative_co2": ["cumulative_co2"],
    "share_global_co2": ["share_global_co2"],
    "coal_co2": ["coal_co2"],
    "oil_co2": ["oil_co2"],
    "gas_co2": ["gas_co2"],
    "cement_co2": ["cement_co2"],
    "flaring_co2": ["flaring_co2"],
    "methane": ["methane"],
    "nitrous_oxide": ["nitrous_oxide"],
    "total_ghg": ["total_ghg"],
}
NUMERIC = ["co2", *OPTIONAL]


@lru_cache(maxsize=1)
def _load() -> pd.DataFrame:
    df = read_source(FILE, REQUIRED, OPTIONAL)
    df = clean_int_keys(df, ["year"], "OWID")
    df = coerce_numeric(df, NUMERIC, "OWID")

    df["country"] = df["country"].astype("string").str.strip()
    df = df[df["country"].notna() & (df["country"] != "")]

    iso = df["iso_code"].astype("string").fillna("").str.strip().str.upper()
    iso = iso.mask(iso == "")
    is_aggregate = iso.isna() | (
        iso.str.startswith("OWID_").fillna(False) & (iso != "OWID_KOS").fillna(False)
    )
    df["iso_code"] = iso
    df["is_aggregate"] = is_aggregate.astype(bool)

    df = dedupe(df, ["country", "year"], "OWID")
    log.info(
        "OWID: %d rows, %d countries, %d aggregate entities",
        len(df),
        df.loc[~df["is_aggregate"], "country"].nunique(),
        df.loc[df["is_aggregate"], "country"].nunique(),
    )
    return df


_failure: list = []          # remembers a failed load so every table sees the same error


def load_owid() -> pd.DataFrame:
    if _failure:
        raise _failure[0]
    try:
        return _load().copy()
    except PipelineError as exc:
        _failure.append(exc)
        raise


def owid_countries() -> pd.DataFrame:
    df = load_owid()
    return df[~df["is_aggregate"]].drop(columns="is_aggregate").reset_index(drop=True)


def owid_aggregates() -> pd.DataFrame:
    df = load_owid()
    return df[df["is_aggregate"]].drop(columns="is_aggregate").reset_index(drop=True)