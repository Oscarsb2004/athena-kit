"""Geodata in the store (System Geodata): one GeoParquet file per layer, beside a layers table and the ingest's report.

A layer keeps every attribute its publisher gave it, under the publisher's names, and its geometry in the publisher's
coordinate system; reprojection belongs to whoever draws it. A layer with no coordinate system is refused: a geometry
whose system is unknown cannot be placed on a map without guessing.
"""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import pandas as pd

from athena import dataset

ROOT = dataset.ROOT


def write(name: str, layers: dict[str, gpd.GeoDataFrame], tables: dict[str, pd.DataFrame], report: list[str],
          root: Path = ROOT) -> Path:
    """Every layer as `<layer>.parquet`, the layers table, any other tables and the report."""
    unplaced = sorted(layer for layer, frame in layers.items() if frame.crs is None)
    if unplaced:
        raise ValueError(f"layers without a coordinate system: {unplaced}")
    summary = pd.DataFrame([{"layer": layer, "features": len(frame),
                             "geometry": ";".join(sorted(frame.geom_type.dropna().unique())),
                             "crs": frame.crs.to_string(), "fields": len(frame.columns) - 1}
                            for layer, frame in layers.items()])
    folder = dataset.write(name, {"layers": summary, **tables}, report, root)
    for layer, frame in layers.items():
        frame.to_parquet(folder / f"{layer}.parquet", index=False)
    return folder


def load(name: str, layer: str, root: Path = ROOT) -> gpd.GeoDataFrame:
    return gpd.read_parquet(root / name / f"{layer}.parquet")
