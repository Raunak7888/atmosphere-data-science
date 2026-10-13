"""
Loads data/tables/*.csv into data/atmosphere.db

    python src/createDb.py      (run createCsv.py first)

All-or-nothing: every table is dropped, recreated and filled inside ONE transaction.
If anything is wrong (bad CSV, duplicate key, broken foreign key, locked file) the transaction
is rolled back and the old database is left exactly as it was.

Duplicate protection in three layers:
  1. at read time   identical rows dropped, conflicting rows stop the build
  2. before insert  unique-key check on every table
  3. in the DB      PRIMARY KEY constraints reject duplicates even if layers 1 and 2 were skipped
A table whose CSV does not exist (e.g. a pending hand-typed table) is created EMPTY, never stale.
"""
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import (DB_PATH, TABLES_DIR, PipelineError, log, read_table_csv, setup_logging,
                    validate_keys)
from registry import DB_ORDER


def _verify_columns(conn: sqlite3.Connection, module) -> None:
    actual = [row[1] for row in conn.execute(f'PRAGMA table_info("{module.NAME}")')]
    expected = list(module.SCHEMA)
    if actual != expected:
        raise PipelineError(
            f"{module.NAME}: CREATE_SQL columns do not match SCHEMA.\n  sql:    {actual}\n  schema: {expected}"
        )


def _insert(conn: sqlite3.Connection, module, df) -> None:
    columns = list(module.SCHEMA)
    placeholders = ", ".join("?" * len(columns))
    sql = f'INSERT INTO "{module.NAME}" ({", ".join(columns)}) VALUES ({placeholders})'

    values = df[columns].astype(object).to_numpy()
    values[df[columns].isna().to_numpy()] = None            # every empty cell becomes SQL NULL
    rows = values.tolist()

    try:
        conn.executemany(sql, rows)
    except sqlite3.IntegrityError as exc:
        raise PipelineError(f"{module.NAME}: database rejected the data ({exc})") from exc

    stored = conn.execute(f'SELECT COUNT(*) FROM "{module.NAME}"').fetchone()[0]
    if stored != len(df):
        raise PipelineError(f"{module.NAME}: wrote {stored} rows but the CSV has {len(df)}")


def CreateDb() -> int:
    setup_logging()

    # 1) read and check every CSV BEFORE touching the database
    loaded, problems = {}, []
    for module in DB_ORDER:
        path = TABLES_DIR / module.CSV_NAME
        if not path.is_file():
            log.warning("%s: %s not found, table will be created empty", module.NAME, path.name)
            loaded[module.NAME] = None
            continue
        try:
            df = read_table_csv(module.CSV_NAME, module.SCHEMA)
            validate_keys(df, module.KEY, module.NAME)
            loaded[module.NAME] = df
        except PipelineError as exc:
            problems.append(str(exc))
    if problems:
        for p in problems:
            log.error(p)
        log.error("Database NOT touched.")
        return 1

    # 2) write everything in one transaction
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    try:
        conn = sqlite3.connect(DB_PATH, timeout=10)
    except sqlite3.Error as exc:
        log.error("Cannot open %s: %s", DB_PATH, exc)
        return 1
    conn.isolation_level = None                    # we control BEGIN / COMMIT ourselves

    try:
        conn.execute("PRAGMA foreign_keys = ON")   # must be set outside a transaction
        conn.execute("BEGIN")
        for module in reversed(DB_ORDER):
            conn.execute(f'DROP TABLE IF EXISTS "{module.NAME}"')
        for module in DB_ORDER:
            conn.execute(module.CREATE_SQL)
            _verify_columns(conn, module)
            df = loaded[module.NAME]
            if df is not None:
                _insert(conn, module, df)
                log.info("%-18s %9s rows loaded", module.NAME, f"{len(df):,}")
            else:
                log.info("%-18s created empty", module.NAME)

        broken = conn.execute("PRAGMA foreign_key_check").fetchall()
        if broken:
            raise PipelineError(f"foreign key violations: {broken[:5]}")
        conn.execute("COMMIT")
    except (PipelineError, sqlite3.Error) as exc:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        hint = " (is the database open in DB Browser or another program?)" if "locked" in str(exc).lower() else ""
        log.error("%s%s", exc, hint)
        log.error("Rolled back. The previous database is unchanged.")
        return 1
    finally:
        conn.close()

    with sqlite3.connect(DB_PATH) as check:
        result = check.execute("PRAGMA integrity_check").fetchone()[0]
    log.info("integrity_check: %s", result)
    log.info("Done: %s", DB_PATH)
    return 0 if result == "ok" else 1


if __name__ == "__main__":
    sys.exit(CreateDb())