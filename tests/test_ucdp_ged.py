"""The UCDP events adapter, on synthetic files in UCDP's layout. Invented events only; each check has a negative
control."""

import io
import zipfile

import pytest

pytest.importorskip("geopandas")

from athena.adapters import ucdp_ged  # noqa: E402

HEAD = ("id,relid,year,code_status,type_of_violence,dyad_dset_id,side_a,side_b,where_prec,adm_1,latitude,longitude,"
        "country,country_id,region,date_start,date_end,best,high,low,source_article\n")
ROWS = ('7,AAA-2026-1-1-1,2026,Clear,1,857,Government of Aland,Group X,1,North,12.5,-3.25,Aland,999,Africa,'
        '2026-03-01 00:00:00.000,2026-03-02 00:00:00.000,4,6,3,"Wire,2026-03-02,a quoted headline"\n'
        '8,BBB-2026-3-1-1,2026,Check deaths,3,,Group Y,Civilians,2,,1.0,30.0,Bland,998,Africa,'
        '2026-04-10 00:00:00.000,2026-04-10 00:00:00.000,2,2,2,\n')


def test_events_keep_every_column_and_their_published_place():
    name, layers, tables, report = ucdp_ged.ingest((HEAD + ROWS).encode(), "26.01.26.09", "candidate")
    e = layers["events"].set_index("id")
    assert name == "ucdp-candidate-26.01.26.09" and tables == {}
    assert (e.loc[7].geometry.x, e.loc[7].geometry.y) == (-3.25, 12.5)  # longitude, latitude
    assert e.loc[7, "date_start"] == "2026-03-01" and e.loc[7, "best"] == 4
    assert e.loc[8, "dyad_dset_id"] == "" and e.loc[7, "dyad_dset_id"] == "857"  # identifiers stay text
    assert e.loc[7, "source_article"] == "Wire,2026-03-02,a quoted headline"
    assert "{'Clear': 1, 'Check deaths': 1}" in report[-1] and "6 deaths" in report[1]


def test_a_zipped_release_reads_the_same_and_a_wrong_file_stops():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("GEDEvent_v26_1.csv", HEAD + ROWS)
    name, layers, _, _ = ucdp_ged.ingest(buf.getvalue(), "26.1", "ged")
    assert name == "ucdp-ged-26.1" and len(layers["events"]) == 2
    with pytest.raises(ValueError, match="columns missing"):  # negative control: not an events file
        ucdp_ged.ingest(b"country,year\nAland,2026\n", "26.1", "ged")
    with pytest.raises(ValueError, match="kind must be"):
        ucdp_ged.ingest((HEAD + ROWS).encode(), "26.1", "acled")
