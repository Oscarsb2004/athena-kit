"""IMF PortWatch: its ports and chokepoints, with their daily port calls, transits and trade estimates, read whole
from the four CSV files PortWatch publishes for download (portwatch.imf.org, served by ArcGIS Hub).

    ports, chokepoints              point layers, every published column kept; each point from the publisher's own
                                    `lat` and `lon` (WGS84). The hub's `X` and `Y` (in whichever projection the
                                    download names) and its `ObjectId` are dropped
    daily_ports, daily_chokepoints  tables, every published column kept but the hub's `ObjectId`; `date` (UTC, as
                                    PortWatch states) written as YYYY-MM-DD

The four files are released on their own dates, so a port listed without daily rows, or a daily row for a port not
listed, is counted in the report, not refused. Every count and estimate is PortWatch's (AIS-derived; trade in metric
tons), never recomputed. Terms: the IMF's copyright and terms, special terms for data; cite "Sources: UN Global
Platform; IMF PortWatch (portwatch.imf.org)" (read 2026-10-22).
"""

from __future__ import annotations

import io

import geopandas as gpd
import pandas as pd

NAME = "portwatch"
POINTS = ("ports", "chokepoints")
DAILY = {"daily_ports": "ports", "daily_chokepoints": "chokepoints"}
HUB = ["X", "Y", "ObjectId"]
TEXT = ["date", "portid", "portname", "country", "ISO3", "continent", "fullname", "industry_top1", "industry_top2",
        "industry_top3", "LOCODE", "pageid", "countrynoaccents"]
DAY = r"\d{4}/\d{2}/\d{2}"


def _read(data: bytes) -> pd.DataFrame:
    """A hub CSV: text columns as written (an empty cell is ""), every other column as numbers."""
    frame = pd.read_csv(io.BytesIO(data), dtype={c: str for c in TEXT}, keep_default_na=False, na_values=[""],
                        encoding="utf-8")
    for c in frame.columns:
        if c in TEXT:
            frame[c] = frame[c].fillna("")
        elif not pd.api.types.is_numeric_dtype(frame[c]):
            raise ValueError(f"column {c!r} is not numeric: {frame[c].dropna().iloc[0]!r}")
    return frame


def _points(frame: pd.DataFrame) -> gpd.GeoDataFrame:
    frame = frame.drop(columns=[c for c in HUB if c in frame.columns])
    return gpd.GeoDataFrame(frame, geometry=gpd.points_from_xy(frame["lon"], frame["lat"]), crs="EPSG:4326")


def _daily(frame: pd.DataFrame) -> pd.DataFrame:
    bad = ~frame["date"].str.fullmatch(DAY)
    if bad.any():
        raise ValueError(f"dates not written as YYYY/MM/DD: {frame.loc[bad, 'date'].head(3).tolist()}")
    frame = frame.drop(columns=[c for c in HUB if c in frame.columns])
    frame["date"] = frame["date"].str.replace("/", "-", regex=False)
    return frame


def ingest(files: dict[str, bytes], edition: str
           ) -> tuple[str, dict[str, gpd.GeoDataFrame], dict[str, pd.DataFrame], list[str]]:
    """The four files, by name (ports, chokepoints, daily_ports, daily_chokepoints), as one geodataset."""
    missing = sorted((set(POINTS) | set(DAILY)) - set(files))
    if missing:
        raise ValueError(f"PortWatch files missing: {missing}")
    layers = {k: _points(_read(files[k])) for k in POINTS}
    tables = {k: _daily(_read(files[k])) for k in DAILY}
    name = f"{NAME}-{edition}"
    p = layers["ports"]
    report = [f"{name}: IMF PortWatch, its ports and chokepoints and their daily activity (Sources: UN Global "
              f"Platform; IMF PortWatch)",
              f"  ports: {len(p):,} points in {p['ISO3'].nunique()} economies; {(p['LOCODE'] != '').sum():,} with a "
              f"LOCODE; {int(p.geometry.is_empty.sum() + p.geometry.isna().sum())} without a position",
              f"  chokepoints: {len(layers['chokepoints']):,} points"]
    for t, layer in DAILY.items():
        d, listed = tables[t], set(layers[layer]["portid"])
        ids = set(d["portid"])
        report.append(f"  {t}: {len(d):,} rows, {len(ids):,} ids, {d['date'].min()} to {d['date'].max()}; listed "
                      f"without daily rows: {len(listed - ids)}; daily ids not listed: {len(ids - listed)}")
    return name, layers, tables, report
