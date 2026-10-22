"""A FAOSTAT domain, read whole from its normalized bulk file (bulks-faostat.fao.org/production).

The zip holds the domain's long table (one row per area, item, element, year and month), and its area, item, element
and flag lists, all UTF-8 (a file that is not stops the ingest). A row is annual (Months Code 7021) or monthly (7001
to 7012).

    SERIES       "<Item Code>.<Element Code>" (2051.5539: Agriculture, Producer Price Index 2014-2016 = 100)
    REF_AREA     the area's ISO 3166 alpha-3 code, matched by its M49 code; an area with none (a region, a group, a
                 former state) keeps "M49:<code>", and is counted in the report
    TIME_PERIOD  the year, or "<year>-M<month>" for a monthly value
    UNIT_MEASURE the publisher's unit; OBS_STATUS its flag

The codes come from a Natural Earth countries file (public domain), whose ISO_N3 (or ISO_N3_EH, UN_A3) is the M49
code and whose ISO_A3 (or ADM0_A3) is the alpha-3 code. FAOSTAT is CC BY 4.0 unless a dataset's metadata says
otherwise; cite "FAO. <year>. <database: dataset>. <access date>. <URL>. Licence: CC-BY-4.0" (read 2026-10-18).
"""

from __future__ import annotations

import io
import json
import zipfile

import pandas as pd

from athena.table import table

ANNUAL = "7021"
MONTHS = {str(7000 + m): m for m in range(1, 13)}
NONE = {"-99", "", "None", "nan"}


def _number(v) -> str | None:
    """A numeric code as three digits, or None for Natural Earth's markers of none ("-99", "-099", empty)."""
    try:
        n = int(str(v))
    except ValueError:
        return None
    return str(n).zfill(3) if n > 0 else None


def codes_from_natural_earth(countries: bytes) -> dict[str, str]:
    """M49 code -> ISO 3166 alpha-3 code, from a Natural Earth admin-0 countries GeoJSON. A feature with an ISO_A3
    code comes first; ADM0_A3 only fills a number no ISO code holds (a dependency can carry its parent's number). Two
    ISO codes on one number stop."""
    out: dict[str, str] = {}
    fallback: dict[str, str] = {}
    for f in json.loads(countries)["features"]:
        p = f["properties"]
        number = next((n for k in ("ISO_N3", "ISO_N3_EH", "UN_A3") if (n := _number(p.get(k)))), None)
        if number is None:
            continue
        iso = str(p.get("ISO_A3"))
        if iso not in NONE:
            if out.get(number, iso) != iso:
                raise ValueError(f"M49 {number} is both {out[number]} and {iso} in Natural Earth")
            out[number] = iso
        elif str(p.get("ADM0_A3")) not in NONE:
            fallback.setdefault(number, str(p["ADM0_A3"]))
    return fallback | out


def _read(zf: zipfile.ZipFile, suffix: str) -> pd.DataFrame:
    name = next((n for n in zf.namelist() if n.endswith(suffix)), None)
    if name is None:
        raise ValueError(f"the bulk file has no *{suffix}")
    return pd.read_csv(zf.open(name), encoding="utf-8", dtype=str, keep_default_na=False)


def ingest(data: bytes, domain: str, edition: str, codes: dict[str, str]
           ) -> tuple[str, dict[str, pd.DataFrame], list[str]]:
    """The dataset's name, its tables (values, areas, codebook, flags) and the report."""
    name = f"faostat-{domain.lower()}-{edition}"
    zf = zipfile.ZipFile(io.BytesIO(data))
    raw = _read(zf, "_All_Data_(Normalized).csv")
    months = set(raw["Months Code"]) - set(MONTHS) - {ANNUAL}
    if months:
        raise ValueError(f"unknown Months Codes: {sorted(months)}")
    m49 = raw["Area Code (M49)"].str.lstrip("'")
    area = m49.map(codes)
    unmatched = sorted(set(raw.loc[area.isna(), "Area"]))
    area = area.fillna("M49:" + m49)
    month = raw["Months Code"].map(MONTHS)
    period = raw["Year"].where(month.isna(), raw["Year"] + "-M" + month.fillna(0).astype(int).astype(str).str.zfill(2))
    value = pd.to_numeric(raw["Value"], errors="coerce")
    blank = value.isna()
    keep = ~blank
    values = table(pd.DataFrame({
        "DATASET": name, "SERIES": raw["Item Code"] + "." + raw["Element Code"], "REF_AREA": area,
        "TIME_PERIOD": period, "OBS_VALUE": value, "UNIT_MEASURE": raw["Unit"], "OBS_STATUS": raw["Flag"],
        "EDITION": edition, "DERIVED": False})[keep])
    areas = _read(zf, "_AreaCodes.csv")
    areas["REF_AREA"] = areas["M49 Code"].str.lstrip("'").map(codes)
    codebook = (raw[["Item Code", "Item Code (CPC)", "Item", "Element Code", "Element", "Unit"]]
                .drop_duplicates().assign(SERIES=lambda f: f["Item Code"] + "." + f["Element Code"])
                .sort_values(["Item Code", "Element Code"], ignore_index=True))
    report = [f"{name}: FAOSTAT {domain.upper()}, bulk file updated {edition}",
              f"  {len(values):,} values, {values['SERIES'].nunique():,} series, {values['REF_AREA'].nunique()} areas, "
              f"{values['TIME_PERIOD'].min()} to {values['TIME_PERIOD'].max()}",
              f"  rows without a numeric value, left out: {int(blank.sum()):,}",
              f"  areas without an alpha-3 code, kept as M49:<code>: {len(unmatched)} ({', '.join(unmatched[:12])}"
              f"{', ...' if len(unmatched) > 12 else ''})"]
    return name, {"values": values, "areas": areas, "codebook": codebook, "flags": _read(zf, "_Flags.csv")}, report
