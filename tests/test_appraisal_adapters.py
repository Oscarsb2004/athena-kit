"""The IMF WEO, UNDP HDR and TI CPI adapters, on invented workbooks in each publisher's layout. No publisher content
is used. Each has a negative control."""

import io
import re

import openpyxl
import pandas as pd
import pytest

from athena.adapters import imf_weo, ti_cpi, undp_hdr


def workbook(sheets: dict[str, list[list]]) -> bytes:
    book = openpyxl.Workbook()
    book.remove(book.active)
    for name, rows in sheets.items():
        sheet = book.create_sheet(name)
        for row in rows:
            sheet.append(row)
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()


# ── IMF WEO ─────────────────────────────────────────────────────────────────────────────────────────────────────

WEO_HEAD = ["DATASET", "SERIES_CODE", "COUNTRY.ID", "COUNTRY", "INDICATOR.ID", "INDICATOR", "INDICATOR.Description",
            "SCALE", "UNIT", "LATEST_ACTUAL_ANNUAL_DATA", 2024, 2025, 2026]


def weo(countries=None, sheets=("Countries", "Country Groups", "Commodity Prices", "Country Group Composition")):
    rows = countries or [
        ["W", "AAA.G.A", "AAA", "Alpha", "G", "Growth", "", "Units", "Percent", 2025, 1.0, 2.0, 3.0],
        ["W", "BBB.G.A", "BBB", "Beta", "G", "Growth", "", "Units", "Percent", "FY2024/25", 4.0, 5.0, None],
        ["W", "CCC.G.A", "CCC", "Gamma", "G", "Growth", "", "Units", "Percent", None, 7.0, None, None],
    ]
    content = {"Countries": [WEO_HEAD] + rows, "Country Groups": [WEO_HEAD], "Commodity Prices": [WEO_HEAD],
               "Country Group Composition": [["groupcode", "groupname", "countrycode"], ["G001", "World", "AAA"]]}
    return workbook({s: content[s] for s in sheets})


def test_weo_marks_every_year_after_the_last_actual_one_as_a_projection():
    name, tables, report = imf_weo.ingest(weo(), "2026-10")
    v = tables["values"].set_index(["REF_AREA", "TIME_PERIOD"])["OBS_STATUS"]
    assert name == "weo-2026-10"
    assert (v[("AAA", "2025")], v[("AAA", "2026")]) == ("", "F")
    assert v[("BBB", "2025")] == "F"  # FY2024/25 is read as 2024: one actual year may show as projected, never less
    assert v[("CCC", "2024")] == ""   # no last actual year: no status
    assert any("fiscal year" in line and ": 1;" in line for line in report)
    assert len(tables["membership"]) == 1


def test_weo_stops_on_a_missing_sheet_or_a_row_without_its_area():
    with pytest.raises(ValueError, match="lacks sheets"):
        imf_weo.ingest(weo(sheets=("Countries", "Country Groups")), "2026-10")
    with pytest.raises(ValueError, match="without an area"):
        imf_weo.ingest(weo([["W", "x", None, "?", "G", "Growth", "", "Units", "Percent", 2025, 1.0, 2.0, 3.0]]),
                       "2026-10")


# ── UNDP HDR ────────────────────────────────────────────────────────────────────────────────────────────────────

def hdr(columns="iso3,country,hdicode,region,hdi_rank_2023,hdi_2022,hdi_2023,le_f_2023"):
    text = f"{columns}\nCIV,Côte d'Ivoire,Medium,SSA,150,0.55,0.56,60.1\nZZK.WORLD,World,,,,0.73,0.74,\n"
    meta = workbook({"codebook": [["Full name", "Short name", "Time series"], ["HDI", "hdi", "1990-2023"]]})
    return text.encode("cp1252"), meta


def test_hdr_reads_every_indicator_year_column_and_keeps_the_areas():
    data, meta = hdr()
    name, tables, report = undp_hdr.ingest(data, meta, "2025")
    v = tables["values"]
    assert name == "hdr-2025"
    assert sorted(v["SERIES"].unique()) == ["hdi", "hdi_rank", "le_f"]
    assert len(v) == 6  # empty cells are not values
    assert tables["areas"].loc[0, "country"] == "Côte d'Ivoire"  # the file is Windows-1252
    assert any("does not list" in line for line in report)  # hdi_rank and le_f are not in the invented codebook


def test_hdr_stops_on_a_column_it_cannot_place():
    data, meta = hdr("iso3,country,hdicode,region,hdi_2023,notes,hdi_rank_2023,le_f_2023")
    with pytest.raises(ValueError, match="neither an area field"):
        undp_hdr.ingest(data, meta, "2025")


# ── TI CPI ──────────────────────────────────────────────────────────────────────────────────────────────────────

def strict(xlsx: bytes) -> bytes:
    """The inverse of ti_cpi.transitional: the workbook as Strict Open XML, as Transparency International saves it."""
    import zipfile
    src, out = zipfile.ZipFile(io.BytesIO(xlsx)), io.BytesIO()
    with zipfile.ZipFile(out, "w") as dst:
        for item in src.infolist():
            body = src.read(item.filename)
            if item.filename.endswith((".xml", ".rels")):
                body = re.sub(rb"http://schemas\.openxmlformats\.org/(\w+)/2006/", rb"http://purl.oclc.org/ooxml/\1/",
                              body)
            dst.writestr(item, body)
    return out.getvalue()


def cpi(head=("Country / Territory", "ISO3", "Year", "Region", "CPI score", "Rank", "Standard error",
              "Lower CI", "Upper CI", "World Bank CPIA")):
    rows = [["Corruption Perceptions Index"], [], [], list(head),
            ["Alpha", "AAA", 2024, "SSA", 40, 10, 2.5, 36, 44, None],
            ["Alpha", "AAA", 2025, "SSA", 41, 9, 2.4, 37, 45, 39.5]]
    return strict(workbook({"CPI Historical": rows, "CPI2025": [["summary"]]}))


def test_cpi_reads_the_strict_workbook_and_every_measure():
    name, tables, report = ti_cpi.ingest(cpi(), "2025")
    v = tables["values"].set_index(["SERIES", "TIME_PERIOD"])["OBS_VALUE"]
    assert name == "cpi-2025"
    assert (v[("cpi_score", "2025")], v[("lower_ci", "2025")], v[("world_bank_cpia", "2025")]) == (41, 37, 39.5)
    assert ("world_bank_cpia", "2024") not in v.index  # an empty cell is not a value
    assert "CPI2025" in report[-1]


def test_cpi_stops_without_its_id_columns_and_the_reader_needs_the_rewrite():
    with pytest.raises(ValueError, match="missing columns"):
        ti_cpi.ingest(cpi(head=("Country / Territory", "ISO3", "Region", "CPI score")), "2025")
    # negative control: pandas cannot see the sheets of a strict workbook until its namespaces are rewritten
    assert pd.ExcelFile(io.BytesIO(cpi())).sheet_names == []
    assert "CPI Historical" in pd.ExcelFile(io.BytesIO(ti_cpi.transitional(cpi()))).sheet_names
