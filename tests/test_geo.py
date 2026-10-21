"""The geo store and the USGS Africa adapter, on an invented geodatabase. No USGS content is used. Each rule has a
negative control."""

import io
import zipfile
from pathlib import Path

import geopandas as gpd
import pytest
from shapely.geometry import LineString, Point

from athena.adapters import usgs_africa_gis as usgs
from athena import geo


def geodatabase(tmp_path: Path, crs="EPSG:4326") -> bytes:
    """A zipped file geodatabase with a point layer and a line layer, in USGS's field names."""
    folder = tmp_path / "Invented.gdb"
    points = gpd.GeoDataFrame({"FeatureNam": ["Alpha port", "Beta port", "Gamma port"],
                               "InfSource1": ["Atlas A", "Atlas A", "Survey B"]},
                              geometry=[Point(1, 2), Point(3, 4), Point(5, 6)], crs=crs)
    lines = gpd.GeoDataFrame({"FeatureTyp": ["rail"], "InfSource1": ["Survey B"]},
                             geometry=[LineString([(0, 0), (1, 1)])], crs=crs)
    points.to_file(folder, layer="AFR_Ports", driver="OpenFileGDB")
    lines.to_file(folder, layer="AFR_Rail", driver="OpenFileGDB")
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        for f in folder.iterdir():
            z.write(f, f"Invented.gdb/{f.name}")
    return out.getvalue()


def test_every_layer_and_attribute_is_kept_and_sources_are_counted(tmp_path):
    name, layers, tables, report = usgs.ingest(geodatabase(tmp_path))
    assert name == "usgs-africa-gis-2021"
    assert sorted(layers) == ["AFR_Ports", "AFR_Rail"]
    assert list(layers["AFR_Ports"]["FeatureNam"]) == ["Alpha port", "Beta port", "Gamma port"]
    s = tables["sources"].set_index(["layer", "value"])["features"]
    assert (s[("AFR_Ports", "Atlas A")], s[("AFR_Ports", "Survey B")], s[("AFR_Rail", "Survey B")]) == (2, 1, 1)
    assert "2 layers, 4 features" in report[1]


def test_the_store_round_trips_and_refuses_a_layer_without_a_coordinate_system(tmp_path):
    _, layers, tables, report = usgs.ingest(geodatabase(tmp_path))
    geo.write("invented", layers, tables, report, root=tmp_path / "store")
    back = geo.load("invented", "AFR_Ports", root=tmp_path / "store")
    assert back.crs == layers["AFR_Ports"].crs and back.geometry.equals(layers["AFR_Ports"].geometry)
    unplaced = {"AFR_Rail": layers["AFR_Rail"].set_crs(None, allow_override=True)}
    with pytest.raises(ValueError, match="without a coordinate system"):
        geo.write("invented", unplaced, {}, [], root=tmp_path / "store")


def test_a_set_measure_is_counted_and_an_empty_one_is_not():
    assert usgs.measures("POINT ZM (1 2 0 nan)") == 0
    assert usgs.measures("MULTILINESTRING ZM ((0 0 0 nan, 1 1 0 nan))") == 0
    # negative controls: a measure that is set, and a geometry without measures
    assert usgs.measures("MULTILINESTRING ZM ((0 0 0 3.5, 1 1 0 nan))") == 1
    assert usgs.measures("POINT Z (1 2 7)") == 0


def test_a_download_without_one_geodatabase_stops(tmp_path):
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        z.writestr("readme.txt", "no geodatabase here")
    with pytest.raises(ValueError, match="expected one .gdb"):
        usgs.ingest(out.getvalue())


# ── World Bank grid map ─────────────────────────────────────────────────────────────────────────────────────────

GRID = (b'{"type": "FeatureCollection", "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}},'
        b'"features": [{"type": "Feature", "properties": {"status": "Existing", "country": "Alpha", "source": '
        b'"OpenStreetMaps", "voltage_kV": 33.0}, "geometry": {"type": "LineString", "coordinates": [[0, 0], [1, 1]]}},'
        b'{"type": "Feature", "properties": {"status": "Planned", "country": "Alpha", "source": "Utility A", '
        b'"voltage_kV": 132.0}, "geometry": {"type": "LineString", "coordinates": [[1, 1], [2, 2]]}}]}')


def test_the_grid_is_read_whole_and_the_server_trailer_is_reported():
    from athena.adapters import wb_africa_grid as grid
    name, layers, tables, report = grid.ingest(GRID + b"\nSystem.IO.MemoryStream")
    assert name == "wb-africa-grid-2017" and len(layers["grid"]) == 2
    assert "Existing 1, Planned 1" in report[1] and "ODbL): 1 lines" in report[2]
    assert "was removed" in report[3]
    assert "no trailer" in grid.ingest(GRID)[3][3]  # negative control: a clean file reports no trailer


def test_any_other_text_after_the_grid_json_stops_the_read():
    from athena.adapters import wb_africa_grid as grid
    with pytest.raises(ValueError, match="unexpected text"):
        grid.ingest(GRID + b"\nSomething else")


def descriptor(name: str, alias: str) -> bytes:
    """One field descriptor as the OpenFileGDB format writes it: name and alias, each a length byte and UTF-16LE."""
    return bytes([len(name)]) + name.encode("utf-16le") + bytes([len(alias)]) + alias.encode("utf-16le") + b"\x04"


def test_a_fields_alias_is_read_from_its_descriptor_and_a_missing_field_finds_no_table():
    table = b"\x03\x00\x00\x00" + descriptor("DsgAttr01", "Commodity Exports") + descriptor("Country", "")
    assert usgs.aliases_in(table, ["DsgAttr01", "Country"]) == {"DsgAttr01": "Commodity Exports", "Country": ""}
    assert usgs.aliases_in(table, ["DsgAttr01", "DsgAttr02"]) is None  # negative control: not this table


def test_the_ingest_keeps_every_layers_fields_in_the_fields_table(tmp_path):
    _, layers, tables, _ = usgs.ingest(geodatabase(tmp_path))
    f = tables["fields"]
    assert set(f[f.layer == "AFR_Ports"]["field"]) == {"FeatureNam", "InfSource1"}
    assert set(f["layer"]) == set(layers)
