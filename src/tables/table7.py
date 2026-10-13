"""
TABLE 7: events  (policy / shock events)   HAND-TYPED, seeded with 7 events

event_id | event_name | year | event_type | source_note

Input file: raw/manual/events.csv  (created the first time with the events below; edit freely).
Review each year, add a source_note for each, and add or remove events as you like.
Used by D1 and F3. Which countries each event touched goes in Table 8.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from common import (MANUAL_DIR, PipelineError, dedupe, ensure_manual_template,
                    finalize, log, read_manual, run_standalone)

NAME = "events"
CSV_NAME = "table7.csv"
KEY = ["event_id"]
DEPENDS = []

SCHEMA = {
    "event_id": "string",
    "event_name": "string",
    "year": "int64",
    "event_type": "string",
    "source_note": "string",
}

CREATE_SQL = """
CREATE TABLE events (
    event_id     TEXT PRIMARY KEY,
    event_name   TEXT NOT NULL,
    year         INTEGER NOT NULL CHECK (year BETWEEN 1800 AND 2100),
    event_type   TEXT NOT NULL,
    source_note  TEXT
);
"""

FILE = MANUAL_DIR / "events.csv"
COLUMNS = ["event_id", "event_name", "year", "event_type", "source_note"]

TEMPLATE = pd.DataFrame(
    [
        ("kyoto_adopted",        "Kyoto Protocol adopted",                      1997, "treaty",       ""),
        ("kyoto_in_force",       "Kyoto Protocol enters into force",            2005, "treaty",       ""),
        ("eu_ets_launch",        "EU Emissions Trading System launched",        2005, "policy",       ""),
        ("financial_crisis",     "Global financial crisis (2008-09)",           2008, "economic_shock", ""),
        ("china_air_plan",       "China air-pollution action plan",             2013, "policy",       ""),
        ("paris_agreement",      "Paris Agreement adopted",                     2015, "treaty",       ""),
        ("covid_lockdowns",      "COVID-19 lockdowns",                          2020, "shock",        ""),
    ],
    columns=COLUMNS,
)


def build(ctx=None) -> pd.DataFrame:
    created = ensure_manual_template(FILE, TEMPLATE)
    df = read_manual(FILE, COLUMNS)
    if df.empty:
        raise PipelineError(f"{FILE.name}: no events found")

    problems = []
    for col in ("event_id", "event_name", "year", "event_type"):
        if df[col].isna().any():
            problems.append(f"column '{col}' has empty cells")
    if problems:
        raise PipelineError(f"{FILE.name}: " + "; ".join(problems))

    df["event_id"] = df["event_id"].astype("string").str.lower().str.replace(r"\s+", "_", regex=True)
    odd = df.loc[~df["event_id"].str.fullmatch(r"[a-z0-9_]+"), "event_id"].tolist()
    if odd:
        raise PipelineError(f"{FILE.name}: event_id may only contain letters, digits, underscore: {odd}")

    df["year"] = pd.to_numeric(df["year"], errors="coerce")
    if df["year"].isna().any() or ((df["year"] % 1) != 0).any() or not df["year"].between(1800, 2100).all():
        raise PipelineError(f"{FILE.name}: 'year' must be a whole year between 1800 and 2100")
    df["year"] = df["year"].astype("int64")

    df = dedupe(df, KEY, FILE.name)
    no_source = int(df["source_note"].isna().sum())
    if no_source:
        log.warning("%s: %d event(s) have no source_note yet; add one before you publish findings", NAME, no_source)
    if created:
        log.info("%s: starter file written with %d events", NAME, len(df))
    return finalize(df, SCHEMA, KEY, NAME)


if __name__ == "__main__":
    run_standalone(sys.modules[__name__])