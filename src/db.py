"""Read-only access to data/atmosphere.db for notebooks."""
import sqlite3
from contextlib import closing
from pathlib import Path

import pandas as pd

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "atmosphere.db"


def query(sql: str, params: tuple = ()) -> pd.DataFrame:
    """Run a SELECT and return a DataFrame. Read-only, so a notebook can never damage the data."""
    if not DB_PATH.is_file():
        raise FileNotFoundError(f"Database not found: {DB_PATH}. Run createCsv.py then createDb.py first.")
    with closing(sqlite3.connect(f"{DB_PATH.as_uri()}?mode=ro", uri=True)) as conn:
        return pd.read_sql_query(sql, conn, params=params)