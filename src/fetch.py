# src/fetch.py
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

RAW = Path("raw")
HEADERS = {"User-Agent": "atmosphere-student-project (contact: your-email@example.com)"}

SOURCES = {
    "co2_mlo_monthly": (
        "https://gml.noaa.gov/webdata/ccgg/trends/co2/co2_mm_mlo.txt",
        "noaa/co2_mm_mlo.txt",
    ),
    "co2_global_monthly": (
        "https://gml.noaa.gov/webdata/ccgg/trends/co2/co2_mm_gl.txt",
        "noaa/co2_mm_gl.txt",
    ),
    "ch4_global_monthly": (
        "https://gml.noaa.gov/aftp/products/trends/ch4/ch4_mm_gl.txt",
        "noaa/ch4_mm_gl.txt",
    ),
    "n2o_global_monthly": (
        "https://gml.noaa.gov/aftp/products/trends/n2o/n2o_mm_gl.txt",
        "noaa/n2o_mm_gl.txt",
    ),
    "gistemp_global": (
        "https://data.giss.nasa.gov/gistemp/tabledata_v4/GLB.Ts+dSST.csv",
        "nasa/GLB.Ts+dSST.csv",
    ),
    "owid_co2": (
        "https://raw.githubusercontent.com/owid/co2-data/master/owid-co2-data.csv",
        "owid/owid-co2-data.csv",
    ),
    "owid_codebook": (
        "https://raw.githubusercontent.com/owid/co2-data/master/owid-co2-codebook.csv",
        "owid/owid-co2-codebook.csv",
    ),
    "wb_pm25_json": (
        "https://api.worldbank.org/v2/country/all/indicator/EN.ATM.PM25.MC.M3?format=json&per_page=20000",
        "worldbank/pm25.json",
    ),
    "wb_country_meta": (
        "https://api.worldbank.org/v2/country?format=json&per_page=400",
        "worldbank/countries.json",
    ),
}


def fetch_one(name, url, rel_path):
    out = RAW / rel_path
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        r = requests.get(url, headers=HEADERS, timeout=60)
        status = r.status_code
        if status == 200:
            out.write_bytes(r.content)
            sha = hashlib.sha256(r.content).hexdigest()
            size = len(r.content)
        else:
            sha, size = None, 0
    except requests.RequestException as e:
        status, sha, size = f"error: {e}", None, 0
    return {
        "name": name,
        "url": url,
        "file": str(out),
        "status": status,
        "bytes": size,
        "sha256": sha,
        "downloaded_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def fetch_all():
    manifest = []
    for name, (url, rel) in SOURCES.items():
        info = fetch_one(name, url, rel)
        print(f"{info['status']!s:>6}  {info['bytes']:>10,} B  {name}")
        manifest.append(info)
        time.sleep(1)  # be polite to servers
    Path("raw/manifest.json").write_text(json.dumps(manifest, indent=2))

if __name__ == "__main__":
    fetch_all()

