"""The USGS Minerals Yearbook, volume III (Area Reports — International), as its data release publishes it: every
country's mineral production over five years, and its mineral facilities, each one CSV.

Two tables, every column under the publisher's name, every cell as text exactly as published: `production` (one row
per locality, commodity at five levels, unit and year, with the value, whether USGS estimated it, and its sources) and
`facilities` (one row per facility and commodity: its type, capacity, status, place and owners). Places are named as
USGS names them ("Congo (Kinshasa)"); a project matches them to its own codes by a rule it states. A file without the
expected columns, or a production value that is not a number, stops the ingest.

Terms: the release is marked CC0 1.0, "in the public domain" without use constraints (ScienceBase, the release's
rights statement, read 2026-10-23); USGS asks for the credit "U.S. Geological Survey" and the release's citation.
"""

from __future__ import annotations

import io

import pandas as pd

PLACE = "Country (Short Form) or Locality"
LEVELS = ["Level 1 (Commodity Group)", "Level 2 (Commodity)", "Level 3 (Type)", "Level 4 (Phase)", "Level 5 (Form)"]
PRODUCTION = [PLACE, *LEVELS, "Descriptor", "Commodity Unit", "Time Period", "Data Type", "Value", "Unit",
              "Value Notes"]
FACILITIES = ["USGS Facility ID", PLACE, "Facility Name", "Feature Type", *LEVELS, "Annual Production Capacity",
              "Capacity Unit", "Facility Status"]


def _read(data: bytes, required: list[str], what: str) -> pd.DataFrame:
    frame = pd.read_csv(io.BytesIO(data), dtype=str, keep_default_na=False, encoding="utf-8-sig")
    missing = [c for c in required if c not in frame.columns]
    if missing:
        raise ValueError(f"{what}: columns missing: {missing}")
    return frame


def ingest(production: bytes, facilities: bytes, edition: str) -> tuple[str, dict[str, pd.DataFrame], list[str]]:
    p = _read(production, PRODUCTION, "production")
    f = _read(facilities, FACILITIES, "facilities")
    values = pd.to_numeric(p["Value"].str.replace(",", ""), errors="coerce")
    if values.isna().any():
        raise ValueError(f"production values that are not numbers: {p.loc[values.isna(), 'Value'].unique()[:5].tolist()}")
    key = [PLACE, *LEVELS, "Descriptor", "Commodity Unit", "Time Period", "Data Type"]
    years = sorted(p["Time Period"].unique())
    name = f"usgs-myb3-{edition}"
    report = [f"{name}: USGS Minerals Yearbook {edition}, volume III, data release",
              f"production: {len(p):,} rows, {p[PLACE].nunique()} localities, {p[LEVELS[1]].nunique()} commodities, "
              f"years {years[0]} to {years[-1]}; {(p['Value Notes'] == 'Estimated').sum():,} estimated by USGS; "
              f"{p.duplicated(key).sum()} rows repeat another's key (kept as published)",
              f"facilities: {len(f):,} rows, {f['USGS Facility ID'].nunique():,} facilities, "
              f"{f[PLACE].nunique()} localities"]
    return name, {"production": p, "facilities": f}, report
