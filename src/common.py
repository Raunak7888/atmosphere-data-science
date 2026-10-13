"""
Shared helpers for the atmosphere pipeline.

What lives here
  - project paths
  - PipelineError / ManualInputPending (the two kinds of "stop" the pipeline knows)
  - read_source()      read a cleaned CSV, find columns by candidate names, fail with a clear message
  - dedupe()           duplicate handling: identical rows are dropped, conflicting rows STOP the run
  - finalize()         enforce schema + unique keys before anything is written
  - write_csv()        atomic write (a crash never leaves a half-written file)
  - get_table()        fetch another table (from this run, else from its CSV)
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
CLEANED = ROOT / "data" / "cleaned"
TABLES_DIR = ROOT / "data" / "tables"
MANUAL_DIR = ROOT / "raw" / "manual"
DB_PATH = ROOT / "data" / "atmosphere.db"

UNAVAILABLE = "__unavailable__"   # key in ctx: names of tables that failed / were skipped this run

log = logging.getLogger("atmosphere")


class PipelineError(Exception):
    """Something is wrong with the data or a file. The message says what and where."""


class ManualInputPending(PipelineError):
    """A hand-typed file still needs to be filled in. Not a crash, the table is skipped."""


def setup_logging(level: int = logging.INFO) -> None:
    logging.basicConfig(level=level, format="%(levelname)-7s %(message)s")


# ───────────────────────────── reading ─────────────────────────────
def require_file(path: Path) -> None:
    path = Path(path)
    if not path.is_file():
        raise PipelineError(f"Input file not found: {path}")
    if path.stat().st_size == 0:
        raise PipelineError(f"Input file is empty: {path}")


def _norm(name: object) -> str:
    return str(name).strip().lower()


def read_source(path, required: dict, optional: dict | None = None, **read_kwargs) -> pd.DataFrame:
    """
    Read only the columns we need from a CSV.

    required / optional map  our_name -> [candidate column names in the file].
    Matching ignores case and surrounding spaces. If a required column cannot be
    found, the error lists the columns the file really has.
    Optional columns that are absent are filled with empty values (with a warning).
    """
    path = Path(path)
    require_file(path)
    optional = optional or {}
    read_kwargs.setdefault("encoding", "utf-8-sig")

    try:
        header = pd.read_csv(path, nrows=0, **read_kwargs)
    except (pd.errors.EmptyDataError, pd.errors.ParserError, UnicodeDecodeError) as exc:
        raise PipelineError(f"{path.name}: cannot read file ({exc})") from exc

    actual = {_norm(c): c for c in header.columns}
    rename: dict[str, str] = {}
    missing: list[str] = []

    for spec, is_required in ((required, True), (optional, False)):
        for logical, candidates in spec.items():
            hit = next((actual[_norm(c)] for c in candidates if _norm(c) in actual), None)
            if hit is None:
                if is_required:
                    missing.append(f"{logical} (looked for: {', '.join(candidates)})")
                continue
            if hit in rename:
                raise PipelineError(
                    f"{path.name}: column '{hit}' matches both '{rename[hit]}' and '{logical}'"
                )
            rename[hit] = logical

    if missing:
        raise PipelineError(
            f"{path.name}: required column(s) not found:\n    "
            + "\n    ".join(missing)
            + f"\n  columns in the file: {list(header.columns)}"
        )

    df = pd.read_csv(path, usecols=list(rename), **read_kwargs).rename(columns=rename)
    for logical in optional:
        if logical not in df.columns:
            log.warning("%s: optional column '%s' not found, filled with empty values", path.name, logical)
            df[logical] = np.nan
    return df[list(required) + list(optional)]


def read_manual(path, columns: list[str]) -> pd.DataFrame:
    """Read a hand-typed CSV: all text, trimmed, blank cells become missing, blank rows dropped."""
    path = Path(path)
    require_file(path)
    df = pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    df.columns = [_norm(c) for c in df.columns]
    missing = [c for c in columns if c not in df.columns]
    if missing:
        raise PipelineError(f"{path.name}: missing column(s) {missing}; found {list(df.columns)}")
    df = df[columns].apply(lambda s: s.str.strip()).replace("", pd.NA)
    return df.dropna(how="all").reset_index(drop=True)


def ensure_manual_template(path, template: pd.DataFrame) -> bool:
    """Create a starter file once. Never overwrites a file you already edited."""
    path = Path(path)
    if path.exists():
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    template.to_csv(path, index=False)
    log.warning("Created starter file %s. Review/fill it, then re-run.", path)
    return True


# ───────────────────────────── cleaning ─────────────────────────────
def coerce_numeric(df: pd.DataFrame, columns, source: str) -> pd.DataFrame:
    """Convert columns to numbers. Text that is not a number becomes empty (and is counted)."""
    df = df.copy()
    for col in columns:
        before = int(df[col].notna().sum())
        df[col] = pd.to_numeric(df[col], errors="coerce")
        lost = before - int(df[col].notna().sum())
        if lost:
            log.warning("%s: %d non-numeric value(s) in '%s' set to empty", source, lost, col)
    return df


def clean_int_keys(df: pd.DataFrame, columns: list[str], source: str) -> pd.DataFrame:
    """Make key columns whole numbers. Rows whose key is empty/not numeric (e.g. repeated header lines) are dropped."""
    df = df.copy()
    for col in columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    bad = df[columns].isna().any(axis=1)
    if bad.any():
        log.warning("%s: dropped %d row(s) whose %s is empty or not a number", source, int(bad.sum()), columns)
        df = df[~bad]
    if df.empty:
        raise PipelineError(f"{source}: no usable rows after reading {columns}")
    fractional = (df[columns] % 1 != 0).any(axis=1)
    if fractional.any():
        example = df.loc[fractional, columns].head(3).to_dict("records")
        raise PipelineError(f"{source}: {columns} must be whole numbers, e.g. {example}")
    df[columns] = df[columns].astype("int64")
    return df.reset_index(drop=True)


def positive_only(series: pd.Series, label: str) -> pd.Series:
    """Gas concentrations cannot be <= 0. NOAA uses -99.99 for 'missing', so those become empty."""
    bad = series.notna() & (series <= 0)
    if bad.any():
        log.warning("%s: %d value(s) <= 0 treated as missing", label, int(bad.sum()))
    return series.mask(bad)


def dedupe(df: pd.DataFrame, key: list[str], source: str, on_conflict: str = "error") -> pd.DataFrame:
    """
    Duplicate handling, in two steps:
      1. rows that are identical in every column are dropped (and counted)
      2. rows that share a key but DIFFER are a real conflict:
         on_conflict="error" (default) stops with examples; "first"/"last" keeps one and warns
    """
    exact = df.duplicated(keep="first")
    if exact.any():
        log.warning("%s: dropped %d exact duplicate row(s)", source, int(exact.sum()))
        df = df[~exact]

    clash = df.duplicated(key, keep=False)
    if clash.any():
        rows = df[clash].sort_values(key).head(6)
        differing = [c for c in rows.columns if c not in key and rows[c].nunique(dropna=False) > 1]
        sample = rows[key + differing].to_string(index=False)
        if on_conflict == "error":
            raise PipelineError(
                f"{source}: {int(clash.sum())} rows share the key {key} but have different values.\n"
                f"  I will not guess which one is right. Examples:\n{sample}"
            )
        dropped = int(df.duplicated(key, keep=on_conflict).sum())
        log.warning("%s: %d conflicting row(s) on key %s, kept the %s one", source, dropped, key, on_conflict)
        df = df.drop_duplicates(key, keep=on_conflict)
    return df.reset_index(drop=True)


# ───────────────────────────── validation ─────────────────────────────
def apply_schema(df: pd.DataFrame, schema: dict, name: str) -> pd.DataFrame:
    missing = [c for c in schema if c not in df.columns]
    extra = [c for c in df.columns if c not in schema]
    if missing or extra:
        raise PipelineError(f"{name}: columns do not match schema. missing={missing} unexpected={extra}")

    df = df[list(schema)].copy()
    for col, dtype in schema.items():
        if dtype == "bool" and df[col].isna().any():
            raise PipelineError(f"{name}: '{col}' has empty values but is declared bool")
        try:
            df[col] = df[col].astype(dtype)
        except (ValueError, TypeError) as exc:
            raise PipelineError(f"{name}: column '{col}' cannot be converted to {dtype}: {exc}") from exc
        if dtype == "float64" and np.isinf(df[col]).any():
            raise PipelineError(f"{name}: '{col}' contains infinite values (a division by zero somewhere)")
    return df


def validate_keys(df: pd.DataFrame, key: list[str], name: str) -> None:
    nulls = df[key].isna().any(axis=1)
    if nulls.any():
        raise PipelineError(f"{name}: {int(nulls.sum())} row(s) have an empty key {key}")
    dup = df.duplicated(key, keep=False)
    if dup.any():
        sample = df.loc[dup, key].drop_duplicates().head(5).to_dict("records")
        raise PipelineError(f"{name}: duplicate keys {key}, e.g. {sample}")


def finalize(df: pd.DataFrame, schema: dict, key: list[str], name: str) -> pd.DataFrame:
    """Last gate before writing: right columns, right types, unique keys, sorted."""
    if df.empty:
        raise PipelineError(f"{name}: produced 0 rows")
    df = apply_schema(df, schema, name)
    validate_keys(df, key, name)
    return df.sort_values(key).reset_index(drop=True)


# ───────────────────────────── writing / tables ─────────────────────────────
def write_csv(df: pd.DataFrame, filename: str) -> Path:
    """Write to a temp file, then swap it in. A crash never leaves a half-written CSV."""
    TABLES_DIR.mkdir(parents=True, exist_ok=True)
    final = TABLES_DIR / filename
    tmp = final.with_name(final.name + ".tmp")
    try:
        df.to_csv(tmp, index=False)
        tmp.replace(final)
    except PermissionError as exc:
        tmp.unlink(missing_ok=True)
        raise PipelineError(f"Cannot write {final}. Is it open in Excel or another program? ({exc})") from exc
    except OSError as exc:
        tmp.unlink(missing_ok=True)
        raise PipelineError(f"Cannot write {final}: {exc}") from exc
    return final


def read_table_csv(filename: str, schema: dict) -> pd.DataFrame:
    path = TABLES_DIR / filename
    require_file(path)
    special = {c: t for c, t in schema.items() if t in ("string", "boolean", "Int64")}
    try:
        df = pd.read_csv(path, dtype=special)
    except (pd.errors.ParserError, ValueError) as exc:
        raise PipelineError(f"{filename}: cannot be read with the expected types ({exc})") from exc
    return apply_schema(df, schema, filename)


def get_table(ctx: dict, module, required: bool = True):
    """
    Fetch another table. Order of preference:
      1. built earlier in this run (ctx)
      2. failed/skipped in this run -> never fall back to an old CSV (it could be stale)
      3. standalone run -> read its CSV from data/tables
    """
    if module.NAME in ctx:
        return ctx[module.NAME].copy()
    if module.NAME in ctx.get(UNAVAILABLE, set()):
        if required:
            raise PipelineError(f"table '{module.NAME}' is not available in this run")
        return None
    path = TABLES_DIR / module.CSV_NAME
    if not path.is_file():
        if required:
            raise PipelineError(f"table '{module.NAME}' is needed first, but {path.name} does not exist. Build it first.")
        return None
    log.info("reading %s from %s", module.NAME, path.name)
    return read_table_csv(module.CSV_NAME, module.SCHEMA)


def run_standalone(module) -> None:
    """Lets any tables/tableN.py be run on its own."""
    setup_logging()
    try:
        df = module.build({})
        path = write_csv(df, module.CSV_NAME)
        log.info("%s: %d rows -> %s", module.NAME, len(df), path)
    except ManualInputPending as exc:
        log.warning("%s", exc)
    except PipelineError as exc:
        log.error("%s", exc)
        sys.exit(1)