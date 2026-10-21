"""Transparency International's Corruption Perceptions Index, read whole from its results workbook.

The workbook is saved as Strict Open XML, which pandas' readers do not open; `transitional` rewrites its namespaces
to the usual form in memory, and changes nothing else. The sheet "CPI Historical" holds every country and year in
long form (score, rank, standard error, number of sources, the 90% interval and each source's rescaled score), so it
is the database. The other sheets summarise or repeat the same values and are named in the report.

CC BY 4.0 for the CPI and its datasets (read 2026-10-18): every change is indicated, and nothing is made untrue.
"""

from __future__ import annotations

import io
import re
import zipfile

import pandas as pd

from athena.table import table

SHEET = "CPI Historical"
STRICT = re.compile(rb"http://purl\.oclc\.org/ooxml/(\w+)/")
IDS = {"Country / Territory": "country", "ISO3": "iso3", "Year": "year", "Region": "region"}


def transitional(data: bytes) -> bytes:
    """A Strict Open XML workbook with its namespaces rewritten to the transitional ones; other files untouched."""
    src, out = zipfile.ZipFile(io.BytesIO(data)), io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as dst:
        for item in src.infolist():
            body = src.read(item.filename)
            if item.filename.endswith((".xml", ".rels")):
                body = STRICT.sub(rb"http://schemas.openxmlformats.org/\1/2006/", body)
            dst.writestr(item, body)
    return out.getvalue()


def series_id(column: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", column.lower()).strip("_")


def ingest(data: bytes, edition: str) -> tuple[str, dict[str, pd.DataFrame], list[str]]:
    name = f"cpi-{edition}"
    book = pd.ExcelFile(io.BytesIO(transitional(data)))
    raw = book.parse(SHEET, header=None)
    header = next(i for i, v in raw[0].items() if str(v).startswith("Country"))
    frame = book.parse(SHEET, header=header)
    missing = sorted(set(IDS) - set(frame.columns))
    if missing:
        raise ValueError(f"{SHEET}: missing columns {missing}")
    frame = frame.dropna(subset=["ISO3", "Year"])
    measures = [c for c in frame.columns if c not in IDS]
    codebook = pd.DataFrame({"series": [series_id(c) for c in measures], "name": measures})
    if codebook["series"].duplicated().any():
        raise ValueError("two columns map to the same series id")
    long = frame.melt(id_vars=list(IDS), value_vars=measures, var_name="name", value_name="OBS_VALUE")
    long = long.dropna(subset=["OBS_VALUE"])
    values = table(pd.DataFrame({
        "DATASET": name, "SERIES": long["name"].map(dict(zip(codebook["name"], codebook["series"]))),
        "REF_AREA": long["ISO3"].astype(str), "TIME_PERIOD": long["Year"].astype(int).astype(str),
        "OBS_VALUE": pd.to_numeric(long["OBS_VALUE"]), "EDITION": edition, "DERIVED": False}))
    areas = frame[["ISO3", "Country / Territory", "Region"]].drop_duplicates("ISO3").astype(str)
    report = [f"{name}: Transparency International CPI, edition {edition}",
              f"  {len(values):,} values, {values['SERIES'].nunique()} series, {values['REF_AREA'].nunique()} "
              f"countries, years {values['TIME_PERIOD'].min()}-{values['TIME_PERIOD'].max()}",
              f"  other sheets, summaries or copies of these values: {sorted(set(book.sheet_names) - {SHEET})}"]
    return name, {"values": values, "codebook": codebook, "areas": areas}, report
