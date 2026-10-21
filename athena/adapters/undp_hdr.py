"""UNDP's Human Development Report data: all composite indices, the complete time series, read whole.

The CSV is wide: a column per indicator and year, named `<indicator>_<year>` (hdi_2023, le_f_1990...), beside the
columns that describe the area (iso3, country, hdicode, region). Every `<indicator>_<year>` column becomes values;
the rest becomes the areas table; the metadata workbook's codebook names each indicator. The file is Windows-1252
encoded. Aggregates (regions, development groups) keep UNDP's own codes.

CC BY 3.0 IGO (read 2026-10-18): keep to the latest edition, and print UNDP's note that the HDI series is
recalculated every year, so values cannot be compared across reports.
"""

from __future__ import annotations

import io
import re

import pandas as pd

from athena.table import table

YEAR = re.compile(r"^(.+)_(\d{4})$")
AREA = ["iso3", "country", "hdicode", "region"]


def ingest(data: bytes, metadata: bytes, edition: str) -> tuple[str, dict[str, pd.DataFrame], list[str]]:
    name = f"hdr-{edition}"
    frame = pd.read_csv(io.BytesIO(data), encoding="cp1252", keep_default_na=False, na_values=[""],
                        dtype={c: str for c in AREA})
    unknown = [c for c in frame.columns if c not in AREA and not YEAR.match(c)]
    if unknown:
        raise ValueError(f"columns that are neither an area field nor <indicator>_<year>: {unknown}")
    long = frame.melt(id_vars=AREA, var_name="column", value_name="OBS_VALUE").dropna(subset=["OBS_VALUE"])
    parts = long["column"].str.extract(YEAR)
    values = table(pd.DataFrame({
        "DATASET": name, "SERIES": parts[0], "REF_AREA": long["iso3"], "TIME_PERIOD": parts[1],
        "OBS_VALUE": long["OBS_VALUE"].astype(float), "EDITION": edition, "DERIVED": False}))
    codebook = pd.read_excel(io.BytesIO(metadata), sheet_name="codebook", dtype=str).fillna("")
    named = set(codebook.get("Short name", pd.Series(dtype=str)))
    report = [f"{name}: UNDP Human Development Report data, edition {edition}",
              f"  {len(values):,} values, {values['SERIES'].nunique()} indicators, {values['REF_AREA'].nunique()} "
              f"areas, years {values['TIME_PERIOD'].min()}-{values['TIME_PERIOD'].max()}"]
    unnamed = sorted(set(values["SERIES"]) - named)
    if unnamed:  # reported, not dropped: UNDP's codebook names indicators by stem, not by every suffix
        report.append(f"  indicators the codebook does not list by this exact name: {len(unnamed)}")
    return name, {"values": values, "areas": frame[AREA], "codebook": codebook}, report
