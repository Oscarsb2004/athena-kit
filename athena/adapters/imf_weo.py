"""The IMF's World Economic Outlook database, read whole from its Excel edition ("Entire Dataset").

Three sheets hold the values, one row per area and indicator with a column per year: Countries, Country Groups and
Commodity Prices. Each row's LATEST_ACTUAL_ANNUAL_DATA is the last year of actual data; every later year is an IMF
projection and is marked OBS_STATUS "F" (SDMX's forecast). The field is a year, a fiscal year ("FY2025/26"), or
empty. For a fiscal year the first calendar year is read as the last actual one: if that is one year early, an actual
value is marked as a projection, never the reverse. Rows without the field carry no status, and are counted.

The group membership sheet becomes the membership table, and every row's metadata (base year, data source,
methodology...) is kept in a table of its own.

Cite as "Source: International Monetary Fund, World Economic Outlook database" (IMF data terms, read 2026-10-18).
"""

from __future__ import annotations

import io
import re

import pandas as pd

from athena.table import table

VALUE_SHEETS = ["Countries", "Country Groups", "Commodity Prices"]
MEMBERSHIP = "Country Group Composition"
FIRST_YEAR = re.compile(r"(\d{4})")


def last_actual(field) -> int | None:
    """The last year of actual data, from a year, a decimal year or a fiscal-year label; None when absent."""
    found = FIRST_YEAR.search(str(field)) if pd.notna(field) else None
    return int(found.group(1)) if found else None


def ingest(data: bytes, edition: str) -> tuple[str, dict[str, pd.DataFrame], list[str]]:
    """The dataset's name, its tables and the report. A sheet that is missing, or a row without its area or
    indicator, stops the ingest."""
    name = f"weo-{edition}"
    book = pd.ExcelFile(io.BytesIO(data))
    missing = sorted(set(VALUE_SHEETS + [MEMBERSHIP]) - set(book.sheet_names))
    if missing:
        raise ValueError(f"the WEO workbook lacks sheets {missing}")
    rows, meta, report = [], [], [f"{name}: IMF World Economic Outlook, edition {edition}"]
    fiscal = undated = 0
    for sheet in VALUE_SHEETS:
        frame = book.parse(sheet)
        years = [c for c in frame.columns if isinstance(c, int)]
        info = [c for c in frame.columns if not isinstance(c, int)]
        bad = frame[frame[["COUNTRY.ID", "INDICATOR.ID"]].isna().any(axis=1)]
        if len(bad):
            raise ValueError(f"{sheet}: {len(bad)} rows without an area or indicator")
        n = 0
        for r in frame.itertuples(index=False):
            record = dict(zip(frame.columns, r))
            last = last_actual(record.get("LATEST_ACTUAL_ANNUAL_DATA"))
            fiscal += str(record.get("LATEST_ACTUAL_ANNUAL_DATA")).startswith("FY")
            undated += last is None
            unit = " ".join(str(record[c]) for c in ("SCALE", "UNIT") if pd.notna(record.get(c)))
            for y in years:
                v = record[y]
                if pd.isna(v):
                    continue
                projected = last is not None and y > last
                rows.append({"DATASET": name, "SERIES": record["INDICATOR.ID"], "REF_AREA": record["COUNTRY.ID"],
                             "TIME_PERIOD": str(y), "OBS_VALUE": float(v), "UNIT_MEASURE": unit,
                             "OBS_STATUS": "F" if projected else "", "EDITION": edition, "DERIVED": False})
                n += 1
            meta.append({k: ("" if pd.isna(record[k]) else str(record[k])) for k in info} | {"sheet": sheet})
        report.append(f"  {sheet}: {len(frame):,} rows, {n:,} values, years {min(years)}-{max(years)}")
    values = table(rows)
    series = pd.DataFrame(meta)
    codebook = (series[["INDICATOR.ID", "INDICATOR", "INDICATOR.Description", "SCALE", "UNIT"]]
                .drop_duplicates("INDICATOR.ID").sort_values("INDICATOR.ID", ignore_index=True))
    membership = book.parse(MEMBERSHIP, dtype=str).fillna("")
    projected = int((values["OBS_STATUS"] == "F").sum())
    report += [f"  {len(values):,} values ({projected:,} projections), {values['SERIES'].nunique()} indicators, "
               f"{values['REF_AREA'].nunique()} areas", f"  {len(membership):,} group memberships",
               f"  rows whose last actual year is a fiscal year, read as its first year: {fiscal:,}; rows without "
               f"one, so without a status: {undated:,}"]
    other = sorted(set(book.sheet_names) - set(VALUE_SHEETS) - {MEMBERSHIP})
    if other:
        report.append(f"  not values, kept out: {other}")
    return name, {"values": values, "codebook": codebook, "series": series, "membership": membership}, report
