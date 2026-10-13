"""
clean.py
--------
Cleans every CSV under ./data and writes the result to ./data/cleaned/<source>/<file>.csv
Missing values are KEPT EMPTY (nothing is filled).

Run from the project root:
    python src/clean.py

Requires: pandas, numpy
"""

from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
OUT_DIR = DATA_DIR / "cleaned"

# Strings treated as missing.
# NOTE: "NA" is deliberately NOT here - in the World Bank files it is a real code
# (Namibia's iso2Code, North America's region_id).
NA_VALUES = ["", " ", "NaN", "nan", "null", "NULL", "None", "-", "--",
             "***", "****", "*****"]

# Set True if you also want columns that are completely empty removed
DROP_EMPTY_COLUMNS = False

KEY_COLUMNS = {"year", "month", "decimal_date", "Year"}

# NOAA "no data" codes
NOAA_SENTINELS = [-99.99, -999.99, -9.99, -0.99]


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------
def read_csv_smart(path: Path) -> pd.DataFrame:
    """Read a CSV, skipping title lines / '#' comments (NASA & NOAA files)."""
    skiprows = 0
    source = path.parent.name.lower()
    if source == "nasa":
        with open(path, encoding="utf-8", errors="ignore") as f:
            for i, line in enumerate(f):
                if line.lower().startswith("year"):
                    skiprows = i
                    break
    return pd.read_csv(
        path,
        skiprows=skiprows,
        comment="#" if source == "noaa" else None,
        na_values=NA_VALUES,
        keep_default_na=False,
        encoding="utf-8",
        low_memory=False,
    )


def basic_clean(df: pd.DataFrame) -> pd.DataFrame:
    """Strip whitespace, drop empty rows and exact duplicate rows."""
    df.columns = [str(c).strip() for c in df.columns]
    for col in df.columns:
        if not pd.api.types.is_numeric_dtype(df[col]):
            df[col] = df[col].astype("string").str.strip().replace("", pd.NA)
    df = df.dropna(how="all")
    df = df.drop_duplicates()
    if DROP_EMPTY_COLUMNS:
        df = df.dropna(axis=1, how="all")
    return df


def coerce_numeric_like(df: pd.DataFrame, skip=()) -> pd.DataFrame:
    """Convert text columns to numbers when every non-empty value is numeric."""
    for col in df.columns:
        if col in skip or pd.api.types.is_numeric_dtype(df[col]):
            continue
        converted = pd.to_numeric(df[col], errors="coerce")
        if converted.notna().sum() == df[col].notna().sum():
            df[col] = converted
    return df


# ----------------------------------------------------------------------------
# File-specific cleaners
# ----------------------------------------------------------------------------
def clean_nasa(df):
    df = basic_clean(df)
    # force everything numeric (also removes any repeated header rows)
    for col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["Year"])
    df["Year"] = df["Year"].astype(int)
    return df.sort_values("Year").reset_index(drop=True)


def clean_noaa(df):
    df = basic_clean(df)
    df = coerce_numeric_like(df)
    value_cols = [c for c in df.columns if c not in KEY_COLUMNS]
    df[value_cols] = df[value_cols].replace(NOAA_SENTINELS, np.nan)
    if "num_days" in df.columns:          # -1 means "no data"
        df["num_days"] = df["num_days"].replace(-1, np.nan)
    df = df.dropna(subset=["year", "month"])
    df[["year", "month"]] = df[["year", "month"]].astype(int)
    return df.sort_values(["year", "month"]).reset_index(drop=True)


def clean_owid_data(df):
    df = basic_clean(df)
    df = coerce_numeric_like(df)
    df = df.dropna(subset=["country", "year"])
    df["year"] = df["year"].astype(int)
    return df.sort_values(["country", "year"]).reset_index(drop=True)


def clean_owid_codebook(df):
    return basic_clean(df)


def clean_wb_countries(df):
    df = basic_clean(df)
    return coerce_numeric_like(df, skip=("id", "iso2Code"))


def clean_wb_indicator(df):
    df = basic_clean(df)
    df = coerce_numeric_like(df)
    df = df.dropna(subset=["iso3", "year"])
    df["year"] = df["year"].astype(int)
    return df.sort_values(["iso3", "year"]).reset_index(drop=True)


def clean_generic(df):
    df = basic_clean(df)
    return coerce_numeric_like(df)


def pick_cleaner(path: Path):
    src, name = path.parent.name.lower(), path.name.lower()
    if src == "nasa":
        return clean_nasa
    if src == "noaa":
        return clean_noaa
    if src == "owid":
        return clean_owid_codebook if "codebook" in name else clean_owid_data
    if src == "worldbank":
        return clean_wb_countries if name == "countries.csv" else clean_wb_indicator
    return clean_generic


# ----------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------
def CleanData():
    csv_files = [p for p in DATA_DIR.rglob("*.csv") if OUT_DIR not in p.parents]
    if not csv_files:
        print(f"No CSV files found in {DATA_DIR}")
        return

    for path in sorted(csv_files):
        rel = path.relative_to(DATA_DIR)
        try:
            raw = read_csv_smart(path)
            rows_before, na_before = len(raw), int(raw.isna().sum().sum())
            dupes = int(raw.duplicated().sum())

            cleaned = pick_cleaner(path)(raw)

            out_path = OUT_DIR / rel
            out_path.parent.mkdir(parents=True, exist_ok=True)
            cleaned.to_csv(out_path, index=False, encoding="utf-8")

            print(f"[OK] {rel}: rows {rows_before} -> {len(cleaned)} "
                  f"(exact duplicates in raw: {dupes}), "
                  f"empty cells {na_before} -> {int(cleaned.isna().sum().sum())}")
        except Exception as e:
            print(f"[FAIL] {rel}: {e}")

    print(f"\nCleaned files saved in: {OUT_DIR}")


if __name__ == "__main__":
    CleanData()