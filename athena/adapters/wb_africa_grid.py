"""The World Bank's Africa electricity transmission and distribution grid map (2017), read whole.

One layer of lines, existing and planned, with status, country, source, operator, endpoints, voltage and length as
published. The `source` attribute names where each line came from; those from OpenStreetMap keep ODbL inside an
otherwise CC BY 4.0 map, so the `sources` table counts them.

The published file ends with the text `System.IO.MemoryStream` after the closing brace of its JSON, an artefact of
the server that wrote it. Exactly that trailer is removed, and the report says so; any other text after the JSON
stops the read.

CC BY 4.0 (energydata.info record, read 2026-10-18). Run through `athena.ingest`.
"""

from __future__ import annotations

import io

import geopandas as gpd
import pandas as pd
import pyogrio

NAME = "wb-africa-grid-2017"
TRAILER = b"System.IO.MemoryStream"


def body(data: bytes) -> tuple[bytes, bool]:
    """The JSON, without the server's trailer if it is there. Anything else after the closing brace is an error."""
    text = data.rstrip()
    trailed = text.endswith(TRAILER)
    if trailed:
        text = text[: -len(TRAILER)].rstrip()
    if not text.endswith(b"}"):
        raise ValueError(f"unexpected text after the JSON: {text[-40:]!r}")
    return text, trailed


def ingest(data: bytes) -> tuple[str, dict[str, gpd.GeoDataFrame], dict[str, pd.DataFrame], list[str]]:
    text, trailed = body(data)
    grid = pyogrio.read_dataframe(io.BytesIO(text))
    sources = grid["source"].fillna("").astype(str).value_counts().rename_axis("value").reset_index(name="features")
    status = grid["status"].fillna("").astype(str).value_counts()
    report = [f"{NAME}: World Bank, Africa electricity transmission and distribution grid map (2017)",
              f"  {len(grid):,} lines in {grid['country'].nunique()} countries, {grid.crs}; by status: "
              + ", ".join(f"{k} {v:,}" for k, v in status.items()),
              f"  {len(sources)} stated sources; OpenStreetMap's (ODbL): "
              f"{int(sources[sources['value'].str.contains('OpenStreetMap')]['features'].sum()):,} lines",
              "  the server's trailer `System.IO.MemoryStream` after the JSON was removed" if trailed
              else "  no trailer after the JSON"]
    return NAME, {"grid": grid}, {"sources": sources}, report
