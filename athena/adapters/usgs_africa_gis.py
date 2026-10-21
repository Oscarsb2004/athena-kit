"""USGS's GIS compilation for the mineral industries and related infrastructure of Africa (2021), read whole.

The download is a zipped Esri file geodatabase of 24 feature classes. Every layer and every attribute is kept, under
USGS's names. Two things are reported rather than decided here:

- **Each layer's stated sources.** USGS fills `InfSource1` and `LocSource1` with where a feature came from, and they
  differ in their terms: OpenStreetMap for rail and roads, GADM for boundaries, a commercial publisher for power and
  pipelines. The `sources` table counts every value, so whoever publishes a layer reads its sources' terms first.
- **Measures.** Some layers store measured geometries (ZM). The reader keeps x, y and z and drops m, so the ingest
  first counts every m value that is set and stops if there is one. In the 2021 release none is.
- **The publisher's field names.** USGS stores generic names (`DsgAttr01`...) and gives each its meaning as an alias
  ("Commodity Exports", "Voltage"...). GDAL reads aliases but pyogrio does not return them, so `aliases_in` reads them
  from each table's field descriptors, where the OpenFileGDB format writes a field's name and then its alias, each
  as one byte of length and UTF-16LE text. The `fields` table keeps every layer's aliases.

U.S. public domain; access and use constraints "None" (read 2026-10-18). Run through `athena.ingest`.
"""

from __future__ import annotations

import re
import tempfile
import warnings
import zipfile
from pathlib import Path

import geopandas as gpd
import pandas as pd
import pyogrio

NAME = "usgs-africa-gis-2021"
SOURCE_FIELDS = ("InfSource", "LocSource")
TUPLE = re.compile(r"\(([^()]+)\)")


def measures(wkt: str) -> int:
    """How many vertices of a ZM geometry carry an m value (one written as nan is empty)."""
    if " ZM" not in wkt:
        return 0
    return sum(1 for part in TUPLE.findall(wkt) for point in part.split(",")
               if len(xyzm := point.split()) == 4 and xyzm[3].lower() != "nan")


def geodatabase(folder: Path, data: bytes) -> str:
    archive = folder / "download.zip"
    archive.write_bytes(data)
    roots = sorted({n.split("/")[0] for n in zipfile.ZipFile(archive).namelist() if n.split("/")[0].endswith(".gdb")})
    if len(roots) != 1:
        raise ValueError(f"expected one .gdb in the download, found {roots}")
    return f"/vsizip/{archive.as_posix()}/{roots[0]}"


def read(path: str, layer: str) -> gpd.GeoDataFrame:
    wkt = pyogrio.read_dataframe(path, sql=f"SELECT ST_AsText(Shape) AS t FROM {layer}", sql_dialect="SQLITE",
                                 read_geometry=False)["t"].dropna()
    set_m = int(wkt.map(measures).sum())
    if set_m:
        raise ValueError(f"{layer}: {set_m} vertices carry an m value the reader would drop")
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="Measured \\(M\\) geometry types are not supported")
        return pyogrio.read_dataframe(path, layer=layer)


def aliases_in(table: bytes, fields: list[str]) -> dict[str, str] | None:
    """Each field's alias in one .gdbtable, or None unless every field is found in its field descriptors."""
    out = {}
    for field in fields:
        key = bytes([len(field)]) + field.encode("utf-16le")
        i = table.find(key)
        if i < 0:
            return None
        n = table[i + len(key)]
        out[field] = table[i + len(key) + 1:i + len(key) + 1 + 2 * n].decode("utf-16le")
    return out


def aliases(path: str, archive: Path, layers: dict[str, gpd.GeoDataFrame]) -> pd.DataFrame:
    """Every layer's field aliases. The geodatabase's system catalogue names its tables: row n is the table stored as
    a{n:08x}.gdbtable. A layer whose table lacks one of its fields stops the ingest."""
    catalogue = pyogrio.read_dataframe(path, layer="GDB_SystemCatalog", read_geometry=False, fid_as_index=True)
    files = {row.Name: f"a{fid:08x}.gdbtable" for fid, row in catalogue.iterrows()}
    with zipfile.ZipFile(archive) as z:
        stored = {n.rsplit("/", 1)[-1]: n for n in z.namelist()}
        rows = []
        for name, frame in layers.items():
            fields = [c for c in frame.columns if c != "geometry"]
            found = aliases_in(z.read(stored[files[name]])[:1 << 20], fields)
            if found is None:
                raise ValueError(f"{name}: its table {files[name]} does not hold all its fields")
            rows += [{"layer": name, "field": f, "alias": found[f]} for f in fields]
    return pd.DataFrame(rows, columns=["layer", "field", "alias"])


def ingest(data: bytes) -> tuple[str, dict[str, gpd.GeoDataFrame], dict[str, pd.DataFrame], list[str]]:
    with tempfile.TemporaryDirectory() as tmp:
        path = geodatabase(Path(tmp), data)
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message="Measured \\(M\\) geometry types are not supported")
            names = [name for name, _ in pyogrio.list_layers(path)]
        layers = {name: read(path, name) for name in names}
        fields = aliases(path, Path(tmp) / "download.zip", layers)
    sources =pd.DataFrame([{"layer": name, "field": field, "value": value, "features": int(n)}
                            for name, frame in layers.items()
                            for field in frame.columns if field.startswith(SOURCE_FIELDS)
                            for value, n in frame[field].fillna("").astype(str).value_counts().items()])
    replaced = {name: int(frame.drop(columns="geometry").astype(str).apply(lambda c: c.str.contains("�")).sum().sum())
                for name, frame in layers.items()}
    report = [f"{NAME}: USGS GIS compilation for the mineral industries and related infrastructure of Africa (2021)",
              f"  {len(layers)} layers, {sum(map(len, layers.values())):,} features; no m value set in any layer"]
    report += [f"  {name}: {len(frame):,} {';'.join(sorted(frame.geom_type.dropna().unique()))}, {frame.crs}, "
               f"{sources[sources.layer == name]['value'].nunique()} stated sources" for name, frame in layers.items()]
    report += [f"  text cells holding U+FFFD as published: {sum(replaced.values())} "
               f"({', '.join(f'{k} {v}' for k, v in replaced.items() if v) or 'none'})"]
    report += [f"  field aliases: {(fields['alias'] != '').sum():,} of {len(fields):,} fields carry one"]
    return NAME, layers, {"sources": sources, "fields": fields}, report
