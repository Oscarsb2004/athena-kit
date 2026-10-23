"""UCDP's georeferenced events, read whole: the Georeferenced Event Dataset (GED, the annual release) or the Candidate
Events Dataset (the monthly release, provisional). Both share one layout: one row per event, with its date, place,
sides, type of violence and deaths.

One geodataset with one point layer, `events`: every published column kept, each point from the publisher's own
`longitude` and `latitude` (WGS84), the dates written as YYYY-MM-DD. Identifiers and text stay text; only the
columns UCDP defines as numbers are read as numbers. A Candidate event keeps UCDP's `code_status` ("Clear", or what
is still to be checked), which the report counts. A file without the expected columns stops the ingest.

Terms: every UCDP dataset is free under CC BY 4.0, citing the publications listed with it (ucdp.uu.se/downloads,
read 2026-10-23). The `source_*` columns quote news reports: kept as published in the store, they are not for
republishing as text.
"""

from __future__ import annotations

import io
import zipfile

import geopandas as gpd
import pandas as pd

NUMBERS = ["id", "year", "type_of_violence", "number_of_sources", "where_prec", "latitude", "longitude",
           "priogrid_gid", "country_id", "event_clarity", "date_prec", "deaths_a", "deaths_b", "deaths_civilians",
           "deaths_unknown", "best", "high", "low"]
REQUIRED = ["id", "relid", "type_of_violence", "side_a", "side_b", "country", "region", "date_start", "date_end",
            "latitude", "longitude", "best", "high", "low", "code_status"]
KIND = {"ged": "UCDP Georeferenced Event Dataset (GED)", "candidate": "UCDP Candidate Events Dataset (provisional)"}


def _csv(data: bytes) -> bytes:
    """The CSV inside a zip of one, or the bytes themselves."""
    if data[:2] != b"PK":
        return data
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        names = [n for n in z.namelist() if n.lower().endswith(".csv")]
        if len(names) != 1:
            raise ValueError(f"expected one CSV in the zip, found {names}")
        return z.read(names[0])


def ingest(data: bytes, edition: str, kind: str) -> tuple[str, dict[str, gpd.GeoDataFrame], dict[str, pd.DataFrame],
                                                         list[str]]:
    if kind not in KIND:
        raise ValueError(f"kind must be one of {sorted(KIND)}, not {kind!r}")
    frame = pd.read_csv(io.BytesIO(_csv(data)), dtype=str, keep_default_na=False, encoding="utf-8")
    missing = [c for c in REQUIRED if c not in frame.columns]
    if missing:
        raise ValueError(f"columns missing: {missing}")
    for c in NUMBERS:
        if c in frame.columns:
            frame[c] = pd.to_numeric(frame[c].replace("", None), errors="raise")
    for c in ("date_start", "date_end"):
        frame[c] = frame[c].str.slice(0, 10)
    bad = ~frame["date_start"].str.fullmatch(r"\d{4}-\d{2}-\d{2}")
    if bad.any():
        raise ValueError(f"dates not written as YYYY-MM-DD: {frame.loc[bad, 'date_start'].head(3).tolist()}")
    layer = gpd.GeoDataFrame(frame, geometry=gpd.points_from_xy(frame["longitude"], frame["latitude"]), crs="EPSG:4326")
    name = f"ucdp-{kind}-{edition}"
    africa = frame[frame["region"] == "Africa"]
    report = [f"{name}: {KIND[kind]}, version {edition}",
              f"  {len(frame):,} events, {frame['date_start'].min()} to {frame['date_end'].max()}; "
              f"{int(frame['best'].sum()):,} deaths (best estimate)",
              f"  by region: {frame['region'].value_counts().to_dict()}",
              f"  Africa: {len(africa):,} events in {africa['country'].nunique()} countries",
              f"  code_status: {frame['code_status'].value_counts().to_dict()}"]
    return name, {"events": layer}, {}, report
