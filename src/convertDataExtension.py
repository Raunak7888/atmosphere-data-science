import json
import re
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent 

RAW_DIR = PROJECT_ROOT / "raw"
DATA_DIR = PROJECT_ROOT / "data/csv"
NASA_RAW_DIR = RAW_DIR / "nasa"
NOAA_RAW_DIR = RAW_DIR / "noaa"
OWID_RAW_DIR = RAW_DIR / "owid"
WORLD_BANK_RAW_DIR = RAW_DIR / "worldbank"
NASA_DATA_DIR = DATA_DIR / "nasa"
NOAA_DATA_DIR = DATA_DIR / "noaa"
OWID_DATA_DIR = DATA_DIR / "owid"
WORLD_BANK_DATA_DIR = DATA_DIR / "worldbank"
NOAA_COLUMNS = {
    "co2_mm_mlo.txt": [
        "year",
        "month",
        "decimal_date",
        "monthly_average",
        "deseasonalized",
        "num_days",
        "stdev_days",
        "unc_monthly_mean",
    ],
    "co2_mm_gl.txt": [
        "year",
        "month",
        "decimal_date",
        "average",
        "average_unc",
        "trend",
        "trend_unc",
    ],
    "ch4_mm_gl.txt": [
        "year",
        "month",
        "decimal_date",
        "average",
        "average_unc",
        "trend",
        "trend_unc",
    ],
    "n2o_mm_gl.txt": [
        "year",
        "month",
        "decimal_date",
        "average",
        "average_unc",
        "trend",
        "trend_unc",
    ],
}


# ============================================================================
# Utilities
# ============================================================================


def ensure_directory(path: Path) -> None:
    """Create a directory if it does not already exist."""
    path.mkdir(parents=True, exist_ok=True)


def require_file(path: Path) -> None:
    """Raise a clear error if an input file does not exist."""
    if not path.is_file():
        raise FileNotFoundError(f"Input file not found:\n  {path}")


def read_text_lines(path: Path) -> list[str]:
    """Read a text file safely and return its lines."""
    require_file(path)

    return path.read_text(
        encoding="utf-8",
        errors="replace",
    ).splitlines()


# ============================================================================
# NASA GISS
# ============================================================================


def convert_giss(input_path: Path, output_dir: Path) -> None:
    """
    Convert NASA GISS temperature data into a clean CSV.

    The GISS file contains documentation before the actual CSV header.
    The first line beginning with 'Year,' is treated as the table header.
    """
    lines = read_text_lines(input_path)

    try:
        header_index = next(
            index for index, line in enumerate(lines) if line.startswith("Year,")
        )
    except StopIteration as exc:
        raise ValueError(
            f"Could not find CSV header beginning with 'Year,' in:\n  {input_path}"
        ) from exc

    df = pd.read_csv(
        input_path,
        skiprows=header_index,
        na_values=["***", "****"],
    )

    ensure_directory(output_dir)

    output_path = output_dir / f"{input_path.stem.replace('+', '_')}.csv"

    df.to_csv(
        output_path,
        index=False,
    )

    print(f"[NASA]      {input_path.name} -> {output_path}")


# ============================================================================
# Our World in Data
# ============================================================================


def convert_owid(input_dir: Path, output_dir: Path) -> None:
    """
    Copy clean OWID CSV files into the processed data directory.

    The files are already tabular, so no structural conversion is required.
    """
    ensure_directory(output_dir)

    for input_path in input_dir.glob("*.csv"):
        require_file(input_path)

        df = pd.read_csv(input_path)

        output_path = output_dir / input_path.name

        df.to_csv(
            output_path,
            index=False,
        )

        print(f"[OWID]      {input_path.name} -> {output_path}")


# ============================================================================
# World Bank
# ============================================================================


def load_world_bank_json(path: Path) -> list[dict]:
    """
    Load a World Bank API response.

    World Bank responses normally have this structure:

        [
            metadata,
            [
                {...},
                {...}
            ]
        ]

    The second element contains the actual records.
    """
    require_file(path)

    with path.open(
        "r",
        encoding="utf-8",
    ) as file:
        data = json.load(file)

    if not isinstance(data, list) or len(data) < 2:
        raise ValueError(f"Unexpected World Bank JSON structure:\n  {path}")

    return data[1]


def convert_world_bank(input_dir: Path, output_dir: Path) -> None:
    """Convert World Bank JSON datasets into flat CSV files."""
    ensure_directory(output_dir)

    # ------------------------------------------------------------------------
    # PM2.5
    # ------------------------------------------------------------------------

    pm25_records = load_world_bank_json(input_dir / "pm25.json")

    pm25 = pd.json_normalize(pm25_records)

    pm25 = pm25.rename(
        columns={
            "indicator.id": "indicator_id",
            "indicator.value": "indicator_name",
            "country.id": "country_id",
            "country.value": "country_name",
            "countryiso3code": "iso3",
            "date": "year",
        }
    )

    pm25.to_csv(
        output_dir / "pm25.csv",
        index=False,
    )

    print("[World Bank] pm25.json -> pm25.csv")

    # ------------------------------------------------------------------------
    # Countries
    # ------------------------------------------------------------------------

    countries_records = load_world_bank_json(input_dir / "countries.json")
    countries = pd.json_normalize(countries_records)
    countries.columns = [column.replace(".", "_") for column in countries.columns]
    countries.to_csv(
        output_dir / "countries.csv",
        index=False,
    )
    print("[World Bank] countries.json -> countries.csv")


# ============================================================================
# NOAA
# ============================================================================


def convert_noaa_txt(
    input_path: Path,
    output_dir: Path,
    columns: list[str],
) -> None:
    """Convert a NOAA whitespace-delimited TXT file to CSV."""

    lines = read_text_lines(input_path)

    data_lines = [
        line
        for line in lines
        if line.strip() and not line.startswith("#")
    ]

    if not data_lines:
        raise ValueError(
            f"No data rows found in:\n  {input_path}"
        )

    ensure_directory(output_dir)

    rows = [
        re.split(r"\s+", line.strip())
        for line in data_lines
    ]

    invalid_rows = [
        row
        for row in rows
        if len(row) != len(columns)
    ]

    if invalid_rows:
        raise ValueError(
            f"Column count mismatch in {input_path.name}. "
            f"Expected {len(columns)}, "
            f"found {len(invalid_rows[0])}."
        )

    df = pd.DataFrame(
        rows,
        columns=columns,
    )

    for column in columns:
        df[column] = pd.to_numeric(
            df[column],
            errors="coerce",
        )

    output_path = output_dir / f"{input_path.stem}.csv"

    df.to_csv(
        output_path,
        index=False,
    )

    print(
        f"[NOAA]      {input_path.name} -> {output_path}"
    )


def convert_noaa(input_dir: Path, output_dir: Path) -> None:
    """Convert all configured NOAA datasets."""
    for filename, columns in NOAA_COLUMNS.items():
        convert_noaa_txt(
            input_path=input_dir / filename,
            output_dir=output_dir,
            columns=columns,
        )


# ============================================================================
# Main
# ============================================================================


def ConvertDataFormat() -> None:
    print(f"Project root: {PROJECT_ROOT}")
    print(f"Raw data:    {RAW_DIR}")
    print(f"Output data: {DATA_DIR}")
    print()

    ensure_directory(DATA_DIR)

    # NASA GISS
    convert_giss(
        input_path=NASA_RAW_DIR / "GLB.Ts+dSST.csv",
        output_dir=NASA_DATA_DIR,
    )

    # Our World in Data
    convert_owid(
        input_dir=OWID_RAW_DIR,
        output_dir=OWID_DATA_DIR,
    )

    # World Bank
    convert_world_bank(
        input_dir=WORLD_BANK_RAW_DIR,
        output_dir=WORLD_BANK_DATA_DIR,
    )

    # NOAA
    convert_noaa(
        input_dir=NOAA_RAW_DIR,
        output_dir=NOAA_DATA_DIR,
    )

    print()
    print("Data conversion completed successfully.")


if __name__ == "__main__":
    ConvertDataFormat()
