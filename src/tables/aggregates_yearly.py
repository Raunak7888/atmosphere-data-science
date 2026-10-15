"""
TABLE 5: aggregates_yearly  (one row per OWID aggregate entity per year)

entity | iso_code | year | co2_mt

Source: the OWID rows that are NOT countries (World, Asia, Europe, income groups, ...).
These are the rows removed from Table 3. Used by G2 (do country sums match the World total?).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from common import PipelineError, dedupe, finalize, log, run_standalone
from owid import owid_aggregates

NAME = "aggregates_yearly"
CSV_NAME = "aggregates_yearly.csv"
KEY = ["entity", "year"]
DEPENDS = []

SCHEMA = {
    "entity": "string",
    "iso_code": "string",
    "year": "int64",
    "co2_mt": "float64",
}

CREATE_SQL = """
CREATE TABLE aggregates_yearly (
    entity    TEXT    NOT NULL,
    iso_code  TEXT,
    year      INTEGER NOT NULL,
    co2_mt    REAL    NOT NULL,
    PRIMARY KEY (entity, year)
);
"""


def build(ctx=None) -> pd.DataFrame:
    df = owid_aggregates().rename(columns={"country": "entity", "co2": "co2_mt"})
    df = df[["entity", "iso_code", "year", "co2_mt"]]

    empty = df["co2_mt"].isna()
    if empty.any():
        log.info("%s: dropped %d aggregate row(s) with no CO2 value", NAME, int(empty.sum()))
        df = df[~empty]
    if not (df["entity"] == "World").any():
        raise PipelineError(f"{NAME}: no 'World' rows found, G2 cannot be answered")

    df = dedupe(df, KEY, NAME)
    df = finalize(df, SCHEMA, KEY, NAME)
    log.info("%s: %d rows, %d entities", NAME, len(df), df["entity"].nunique())
    return df


if __name__ == "__main__":
    run_standalone(sys.modules[__name__])