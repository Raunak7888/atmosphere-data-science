"""
Builds all 9 tables and writes them to data/tables/tableN.csv

    python src/createCsv.py

Safe to re-run any number of times:
  - every CSV is rewritten completely (atomic swap), nothing is appended, so no duplicates build up
  - a table that fails does not stop the others; tables that depend on it are SKIPPED
    (never built from an old CSV), and the exit code is 1
  - hand-typed tables (6, 8) that still need your input are PENDING, not failures
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import UNAVAILABLE, ManualInputPending, PipelineError, log, setup_logging, write_csv
from registry import BUILD_ORDER


def CreateCsv() -> int:
    setup_logging()
    ctx: dict = {UNAVAILABLE: set()}
    status: dict[str, str] = {}
    seen_errors: set[str] = set()

    for module in BUILD_ORDER:
        name = module.NAME
        log.info("── %s ──", name)

        blocked = [d.NAME for d in module.DEPENDS if d.NAME in ctx[UNAVAILABLE]]
        if blocked:
            status[name] = f"SKIPPED (needs {', '.join(blocked)})"
            ctx[UNAVAILABLE].add(name)
            log.warning("%s: skipped because %s did not build", name, ", ".join(blocked))
            continue

        try:
            df = module.build(ctx)
            path = write_csv(df, module.CSV_NAME)
        except ManualInputPending as exc:
            status[name] = "PENDING (manual input)"
            ctx[UNAVAILABLE].add(name)
            log.warning("%s", exc)
        except PipelineError as exc:
            status[name] = "FAILED"
            ctx[UNAVAILABLE].add(name)
            if str(exc) in seen_errors:
                log.error("same error as above (%s)", str(exc).splitlines()[0])
            else:
                seen_errors.add(str(exc))
                log.error("%s", exc)
        except Exception:                      # a bug, not bad data: show the traceback, keep going
            status[name] = "FAILED (unexpected error)"
            ctx[UNAVAILABLE].add(name)
            log.exception("unexpected error while building %s", name)
        else:
            ctx[name] = df
            status[name] = f"ok, {len(df):,} rows -> {path.name}"

    log.info("══════════ SUMMARY ══════════")
    for module in BUILD_ORDER:
        log.info("%-18s %s", module.NAME, status[module.NAME])
    failed = [n for n, s in status.items() if s.startswith(("FAILED", "SKIPPED"))]
    if failed:
        log.error("Not built: %s. Fix the errors above and re-run.", ", ".join(failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(CreateCsv())