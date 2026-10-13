"""
TABLE 6: gwp_constants  (3 rows: CO2, CH4, N2O)   HAND-TYPED

gas | gwp20 | gwp100 | owid_gwp_used | source_note

Input file: raw/manual/gwp_constants.csv  (created for you the first time, CO2 row pre-filled)
Fill CH4 and N2O from the IPCC report you cite, and say which edition/table in source_note.
owid_gwp_used = the factor OWID applied to turn tonnes of gas into CO2e (read it in owid-co2-codebook.csv).
Used by B2 (CO2e at 20 years vs 100 years).

Until the blanks are filled this table is reported as PENDING (not an error) and skipped.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from common import (MANUAL_DIR, ManualInputPending, PipelineError, coerce_numeric, dedupe,
                    ensure_manual_template, finalize, log, read_manual, run_standalone)

NAME = "gwp_constants"
CSV_NAME = "table6.csv"
KEY = ["gas"]
DEPENDS = []

SCHEMA = {
    "gas": "string",
    "gwp20": "float64",
    "gwp100": "float64",
    "owid_gwp_used": "float64",
    "source_note": "string",
}

CREATE_SQL = """
CREATE TABLE gwp_constants (
    gas            TEXT PRIMARY KEY CHECK (gas IN ('CO2', 'CH4', 'N2O')),
    gwp20          REAL NOT NULL CHECK (gwp20 > 0),
    gwp100         REAL NOT NULL CHECK (gwp100 > 0),
    owid_gwp_used  REAL NOT NULL CHECK (owid_gwp_used > 0),
    source_note    TEXT
);
"""

FILE = MANUAL_DIR / "gwp_constants.csv"
COLUMNS = ["gas", "gwp20", "gwp100", "owid_gwp_used", "source_note"]
GASES = ["CO2", "CH4", "N2O"]
NUMBERS = ["gwp20", "gwp100", "owid_gwp_used"]

TEMPLATE = pd.DataFrame({
    "gas": GASES,
    "gwp20": [1, None, None],
    "gwp100": [1, None, None],
    "owid_gwp_used": [1, None, None],
    "source_note": ["CO2 is 1 by definition", "", ""],
})


def build(ctx=None) -> pd.DataFrame:
    ensure_manual_template(FILE, TEMPLATE)
    df = read_manual(FILE, COLUMNS)

    df["gas"] = df["gas"].astype("string").str.upper()
    df = coerce_numeric(df, NUMBERS, FILE.name)
    df = dedupe(df, KEY, FILE.name)

    unknown = sorted(set(df["gas"].dropna()) - set(GASES))
    if unknown:
        raise PipelineError(f"{FILE.name}: unknown gas {unknown}; allowed {GASES}")

    missing_rows = [g for g in GASES if g not in set(df["gas"])]
    blanks = [] if missing_rows else [
        f"{r.gas}: {c}" for r in df.itertuples() for c in NUMBERS if pd.isna(getattr(r, c))
    ]
    if not missing_rows:
        blanks += [f"{r.gas}: source_note" for r in df.itertuples()
                   if r.gas != "CO2" and pd.isna(r.source_note)]
    if missing_rows or blanks:
        raise ManualInputPending(
            f"fill {FILE} -> " + ("add rows for " + ", ".join(missing_rows) if missing_rows else "; ".join(blanks))
        )

    bad = [c for c in NUMBERS if (df[c] <= 0).any()]
    if bad:
        raise PipelineError(f"{FILE.name}: {bad} must be positive numbers")

    log.info("%s: %d rows", NAME, len(df))
    return finalize(df, SCHEMA, KEY, NAME)


if __name__ == "__main__":
    run_standalone(sys.modules[__name__])