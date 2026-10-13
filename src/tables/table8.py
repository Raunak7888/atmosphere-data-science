"""
TABLE 8: event_countries  (which countries each event touched)   HAND-TYPED

event_id | iso_code | role        role = treated or control

Input file: raw/manual/event_countries.csv  (created with only the header; YOU choose the countries)
Example rows:
    china_air_plan,CHN,treated
    china_air_plan,IND,control
Every event used in D1/F3 needs at least one treated and one control country.
iso_code must exist in Table 3, event_id must exist in Table 7.

Until you add rows this table is PENDING (not an error) and skipped.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from common import (MANUAL_DIR, ManualInputPending, PipelineError, dedupe, ensure_manual_template,
                    finalize, get_table, log, read_manual, run_standalone)
from tables import table3, table7

NAME = "event_countries"
CSV_NAME = "table8.csv"
KEY = ["event_id", "iso_code"]
DEPENDS = [table3, table7]

SCHEMA = {
    "event_id": "string",
    "iso_code": "string",
    "role": "string",
}

CREATE_SQL = """
CREATE TABLE event_countries (
    event_id  TEXT NOT NULL,
    iso_code  TEXT NOT NULL,
    role      TEXT NOT NULL CHECK (role IN ('treated', 'control')),
    PRIMARY KEY (event_id, iso_code),
    FOREIGN KEY (event_id) REFERENCES events (event_id)
);
"""

FILE = MANUAL_DIR / "event_countries.csv"
COLUMNS = ["event_id", "iso_code", "role"]
ROLES = {"treated", "control"}


def build(ctx=None) -> pd.DataFrame:
    ctx = {} if ctx is None else ctx
    events = get_table(ctx, table7)
    countries = get_table(ctx, table3)

    ensure_manual_template(FILE, pd.DataFrame(columns=COLUMNS))
    df = read_manual(FILE, COLUMNS)
    if df.empty:
        raise ManualInputPending(f"add rows to {FILE} (event_id, iso_code, role = treated/control)")

    empty_cells = df.isna().any(axis=1)
    if empty_cells.any():
        raise PipelineError(f"{FILE.name}: {int(empty_cells.sum())} row(s) have empty cells")

    df["event_id"] = df["event_id"].astype("string").str.lower()
    df["iso_code"] = df["iso_code"].astype("string").str.upper()
    df["role"] = df["role"].astype("string").str.lower()

    problems = []
    bad_role = sorted(set(df["role"]) - ROLES)
    if bad_role:
        problems.append(f"role must be treated or control, found {bad_role}")
    bad_event = sorted(set(df["event_id"]) - set(events["event_id"]))
    if bad_event:
        problems.append(f"event_id not in events table: {bad_event}")
    bad_iso = sorted(set(df["iso_code"]) - set(countries["iso_code"]))
    if bad_iso:
        problems.append(f"iso_code not in country_yearly (countries only, no aggregates): {bad_iso}")
    if problems:
        raise PipelineError(f"{FILE.name}:\n  " + "\n  ".join(problems))

    # a country listed twice for one event, once as treated and once as control, is a conflict
    df = dedupe(df, KEY, FILE.name)

    for event_id, group in df.groupby("event_id"):
        roles = set(group["role"])
        if roles != ROLES:
            log.warning("%s: event '%s' has only %s countries; D1 needs both treated and control",
                        NAME, event_id, "/".join(sorted(roles)))
    log.info("%s: %d rows across %d events", NAME, len(df), df["event_id"].nunique())
    return finalize(df, SCHEMA, KEY, NAME)


if __name__ == "__main__":
    run_standalone(sys.modules[__name__])