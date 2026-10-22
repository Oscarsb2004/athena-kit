"""NGA's World Port Index (Pub 150), read whole from the CSV NGA publishes (msi.nga.mil, UpdatedPub150.csv): one point
layer, every published column kept as written, each point from its Latitude and Longitude (WGS84).

Two keys are added for joins, each by a stated rule:
    wpi     the World Port Index Number as an integer (NGA writes "45570.0"); empty where there is none
    locode  the UN/LOCODE without its space (NGA writes both "NG ESC" and "NGESC"); "" where NGA writes a blank

`locodes(layer)` gives each index number its LOCODE where the number's rows agree; a number whose rows give two
different codes gets none, and is listed. NGA's site: information on it "is considered public information and may be
distributed or copied unless otherwise specified"; a byline is requested (read 2026-10-22).
"""

from __future__ import annotations

import io

import geopandas as gpd
import pandas as pd

NAME = "wpi"
NUMBER, CODE = "World Port Index Number", "UN/LOCODE"


def locode(text: str) -> str:
    """A UN/LOCODE as one word: "NG ESC" and "NGESC" are the same code; a blank is ""."""
    return "".join(str(text).split()).upper()


def ingest(data: bytes, edition: str) -> tuple[str, dict[str, gpd.GeoDataFrame], dict[str, pd.DataFrame], list[str]]:
    frame = pd.read_csv(io.BytesIO(data), dtype=str, keep_default_na=False, encoding="utf-8-sig")
    lat, lon = (pd.to_numeric(frame[c].str.strip(), errors="coerce") for c in ("Latitude", "Longitude"))
    frame["wpi"] = pd.to_numeric(frame[NUMBER].str.strip().replace("", None), errors="raise").astype("Int64")
    frame["locode"] = frame[CODE].map(locode)
    layer = gpd.GeoDataFrame(frame, geometry=gpd.points_from_xy(lon, lat), crs="EPSG:4326")
    _, ambiguous = locodes(layer)
    name = f"{NAME}-{edition}"
    report = [f"{name}: NGA World Port Index (Pub 150), UpdatedPub150.csv",
              f"  {len(layer):,} ports; {(layer['locode'] != '').sum():,} with a UN/LOCODE; "
              f"{int(layer['wpi'].duplicated(keep=False).sum())} rows share an index number; numbers whose rows give "
              f"different LOCODEs (joined to none): {ambiguous or 'none'}; {int(lat.isna().sum() + lon.isna().sum())} "
              f"coordinates unreadable"]
    return name, {"ports": layer}, {}, report


def locodes(layer: pd.DataFrame) -> tuple[dict[int, str], list[int]]:
    """Each index number's LOCODE where its rows agree, and the numbers whose rows disagree (they get none)."""
    rows = layer[layer["wpi"].notna() & (layer["locode"] != "")]
    codes = rows.groupby("wpi")["locode"].unique()
    ambiguous = sorted(int(n) for n, c in codes.items() if len(c) > 1)
    return {int(n): c[0] for n, c in codes.items() if len(c) == 1}, ambiguous
