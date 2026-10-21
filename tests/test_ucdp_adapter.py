"""The UCDP country-year adapter, on an invented download in UCDP's layout. No UCDP content is used. Each rule has a
negative control."""

import io
import zipfile

import pandas as pd
import pytest

from athena.adapters import ucdp

HEAD = ("country,country_id,year,region,govt_name,sb_dyad_ids,sb_dyad_names,sb_exist,"
        "sb_total_deaths_best,sb_total_deaths_low,Version")
ROWS = ['Alpha,901,2024,Africa,Government of Alpha,"1, 2","Alpha vs A; Alpha vs B",1,30,25,26.1',
        "Alpha,901,2025,Africa,Government of Alpha,,,0,0,0,26.1",
        "Beta (Old Name),902,2025,Asia,Government of Beta,,,0,0,0,26.1"]
CROSSWALK = pd.DataFrame({"country_id": ["901", "902"], "country": ["Alpha", "Beta (Old Name)"],
                          "iso3": ["AAA", "BBB"], "how": ["name", "alias"]})


def download(rows=ROWS, head=HEAD) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        z.writestr("Invented.csv", "\n".join([head] + rows) + "\n")
    return out.getvalue()


def test_every_numeric_column_is_a_series_and_a_quiet_year_is_a_zero():
    name, tables, report = ucdp.ingest(download(), "26.1", CROSSWALK)
    v = tables["values"].set_index(["SERIES", "REF_AREA", "TIME_PERIOD"])["OBS_VALUE"]
    assert name == "ucdp-cy-26.1"
    assert sorted(tables["codebook"]["series"]) == ["sb_exist", "sb_total_deaths_best", "sb_total_deaths_low"]
    assert (v[("sb_total_deaths_best", "AAA", "2024")], v[("sb_total_deaths_best", "AAA", "2025")]) == (30, 0)
    assert len(v) == 9
    r = tables["records"].set_index(["REF_AREA", "TIME_PERIOD"])
    assert r.loc[("AAA", "2024"), "sb_dyad_names"] == "Alpha vs A; Alpha vs B"
    assert r.loc[("AAA", "2025"), "sb_dyad_ids"] == ""
    assert "1 of 2 countries matched by a written alias" in report[2]


def test_an_unlisted_or_renamed_country_stops_the_read():
    rows = ROWS[:2] + ["Gamma,903,2025,Asia,Government of Gamma,,,0,0,0,26.1",
                       "Beta,902,2025,Asia,Government of Beta,,,0,0,0,26.1"]
    with pytest.raises(ValueError, match=r"903 Gamma.*902 Beta \(Old Name\) -> Beta"):
        ucdp.ingest(download(rows), "26.1", CROSSWALK)


def test_a_version_or_column_it_does_not_expect_stops_the_read():
    with pytest.raises(ValueError, match="version"):
        ucdp.ingest(download(), "25.1", CROSSWALK)
    head = HEAD.replace("sb_exist", "sb_notes")
    rows = [r.replace(",1,30,", ",high,30,").replace(",0,0,0,", ",low,0,0,") for r in ROWS]
    with pytest.raises(ValueError, match=r"neither numeric nor known text: \['sb_notes'\]"):
        ucdp.ingest(download(rows, head), "26.1", CROSSWALK)
    # negative control: the same rows with a numeric column in that place read
    assert ucdp.ingest(download(), "26.1", CROSSWALK)[0] == "ucdp-cy-26.1"


def test_the_committed_crosswalk_maps_each_code_once_and_covers_the_asi_states():
    listed = pd.read_csv(ucdp.CROSSWALK, dtype=str, keep_default_na=False)
    assert not listed["country_id"].duplicated().any() and not listed["iso3"].duplicated().any()
    assert set(listed["how"]) == {"name", "alias"}
    assert {"CIV", "COD", "COG", "EGY", "SSD", "ZAF"} <= set(listed["iso3"])
