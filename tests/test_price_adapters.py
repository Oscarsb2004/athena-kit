"""The IMF SDMX and FAOSTAT bulk adapters, on synthetic documents in each publisher's layout. Invented areas and
figures only; each check has a negative control."""

import io
import json
import zipfile

import pytest

from athena.adapters import faostat_bulk, imf_sdmx

CODELISTS = {"INDICATOR": "CL_X_INDICATOR", "TYPE_OF_TRANSFORMATION": "CL_X_TRANSFORMATION", "FREQUENCY": "CL_FREQ"}


def structure(indicators=(("PPI", "Producer price index (PPI)"),)) -> bytes:
    lists = [("CL_X_INDICATOR", indicators),
             ("CL_X_TRANSFORMATION", (("IX", "Index"), ("YOY_PCH_PT", "Year-over-year (YOY) percent change"))),
             ("CL_FREQ", (("A", "Annual"), ("Q", "Quarterly")))]
    return json.dumps({"data": {"codelists": [{"id": i, "codes": [{"id": c, "name": n} for c, n in codes]}
                                              for i, codes in lists]}}).encode()


def data(series=None) -> bytes:
    dims = [{"id": "COUNTRY", "values": [{"id": "AAA"}, {"id": "BBB"}]},
            {"id": "INDICATOR", "values": [{"id": "PPI"}]},
            {"id": "TYPE_OF_TRANSFORMATION", "values": [{"id": "IX"}, {"id": "YOY_PCH_PT"}]},
            {"id": "FREQUENCY", "values": [{"id": "A"}, {"id": "Q"}]}]
    shape = {"dimensions": {"series": dims, "observation": [{"id": "TIME_PERIOD", "values": [
                 {"value": "2020"}, {"value": "2021"}, {"value": "2021-Q1"}]}]},
             "attributes": {"series": [{"id": "SCALE", "values": [{"id": "0"}]}, {"id": "REFERENCE_PERIOD"}],
                            "observation": [{"id": "STATUS", "values": [{"id": "P"}]}]}}
    series = series or {
        "0:0:0:0": {"attributes": [0, "2010=100"], "observations": {"0": ["100.0", None], "1": ["104.5", 0]}},
        "0:0:1:0": {"attributes": [0, None], "observations": {"1": ["4.5", None]}},
        "1:0:1:1": {"attributes": [0, None], "observations": {"2": ["-1.25", None], "0": [None, None]}}}
    return json.dumps({"meta": {}, "data": {"structures": [shape], "dataSets": [{"series": series}]}}).encode()


def test_an_imf_dataflow_becomes_a_dataset_with_the_publishers_labels():
    name, tables, report = imf_sdmx.ingest(data(), structure(), "PPI", "2026-10", CODELISTS)
    v = tables["values"].set_index(["SERIES", "REF_AREA", "TIME_PERIOD"])
    assert name == "ppi-2026-10"
    assert v.OBS_VALUE.to_dict() == {("PPI.IX.A", "AAA", "2020"): 100.0, ("PPI.IX.A", "AAA", "2021"): 104.5,
                                     ("PPI.YOY_PCH_PT.A", "AAA", "2021"): 4.5,
                                     ("PPI.YOY_PCH_PT.Q", "BBB", "2021-Q1"): -1.25}
    assert v.loc[("PPI.IX.A", "AAA", "2021"), "UNIT_MEASURE"] == "Index, 2010=100"
    assert v.loc[("PPI.IX.A", "AAA", "2021"), "OBS_STATUS"] == "P"  # an index into the attribute's values
    book = tables["codebook"].set_index("SERIES")
    assert book.loc["PPI.YOY_PCH_PT.Q", "TYPE_OF_TRANSFORMATION_LABEL"] == "Year-over-year (YOY) percent change"
    assert "observations without a value, left out: 1" in report[-1]


def test_a_code_without_a_label_stops_the_imf_ingest():
    with pytest.raises(ValueError, match=r"codes without a label.*'INDICATOR', 'PPI'"):
        imf_sdmx.ingest(data(), structure(indicators=(("WPI", "Wholesale"),)), "PPI", "2026-10", CODELISTS)
    with pytest.raises(ValueError, match="lacks code lists"):
        imf_sdmx.ingest(data(), structure(), "PPI", "2026-10", CODELISTS | {"FREQUENCY": "CL_NOWHERE"})


NE = json.dumps({"features": [
    {"properties": {"ISO_A3": "AAA", "ISO_N3": "4", "ADM0_A3": "AAA"}},
    {"properties": {"ISO_A3": "-99", "ISO_N3": "-99", "ISO_N3_EH": "8", "ADM0_A3": "BBB"}},
    {"properties": {"ISO_A3": "-99", "ISO_N3": "-99", "ADM0_A3": "ZZZ"}},  # no number: not matched
    {"properties": {"ISO_A3": "-99", "ISO_N3": "-099", "ADM0_A3": "YYY"}},  # Natural Earth writes both
    {"properties": {"ISO_A3": "-99", "ISO_N3": "004", "ADM0_A3": "XXX"}}]}).encode()  # a dependency: AAA's number


def bulk(rows: list[str], encoding: str = "utf-8") -> bytes:
    head = ("Area Code,Area Code (M49),Area,Item Code,Item Code (CPC),Item,Element Code,Element,Year Code,Year,"
            "Months Code,Months,Unit,Value,Flag\n")
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        z.writestr("Prices_E_All_Data_(Normalized).csv", (head + "\n".join(rows) + "\n").encode(encoding))
        z.writestr("Prices_E_AreaCodes.csv", "Area Code,M49 Code,Area\n1,'004,Alpha\n2,'008,Bêta\n9,'002,Region\n"
                   .encode("utf-8"))
        z.writestr("Prices_E_Flags.csv", "Flag, Description\nA,Official value\n".encode("utf-8"))
    return out.getvalue()


ROWS = ["1,'004,Alpha,2051,'F2051,Agriculture,5539,Producer Price Index (2014-2016 = 100),2020,2020,7021,"
        "Annual value,,104.2,A",
        "2,'008,Bêta,15,'0111,Wheat,5530,Producer Price (LCU/tonne),2021,2021,7003,March,LCU,250.0,A",
        "9,'002,Region,2051,'F2051,Agriculture,5539,Producer Price Index (2014-2016 = 100),2020,2020,7021,"
        "Annual value,,99.0,A",
        "1,'004,Alpha,15,'0111,Wheat,5530,Producer Price (LCU/tonne),2019,2019,7021,Annual value,LCU,,A"]


def test_a_faostat_domain_becomes_a_dataset_with_alpha3_codes_and_months():
    codes = faostat_bulk.codes_from_natural_earth(NE)
    assert codes == {"004": "AAA", "008": "BBB"}
    name, tables, report = faostat_bulk.ingest(bulk(ROWS), "pp", "2026-10-09", codes)
    v = tables["values"].set_index(["SERIES", "REF_AREA", "TIME_PERIOD"]).OBS_VALUE
    assert name == "faostat-pp-2026-10-09"
    assert v.to_dict() == {("2051.5539", "AAA", "2020"): 104.2, ("15.5530", "BBB", "2021-M03"): 250.0,
                           ("2051.5539", "M49:002", "2020"): 99.0}  # a region keeps its M49 code, never dropped
    assert "rows without a numeric value, left out: 1" in report[2] and "kept as M49:<code>: 1 (Region)" in report[3]
    assert tables["areas"].set_index("Area").REF_AREA.to_dict()["Bêta"] == "BBB"  # an accent read as written
    with pytest.raises(UnicodeDecodeError):  # a file that is not UTF-8 stops, never garbles names
        faostat_bulk.ingest(bulk(ROWS, encoding="latin-1"), "pp", "2026-10-09", codes)


def test_an_unknown_month_or_a_code_held_twice_stops_the_faostat_ingest():
    with pytest.raises(ValueError, match="unknown Months Codes"):
        faostat_bulk.ingest(bulk([ROWS[0].replace(",7021,", ",7099,")]), "pp", "x", {})
    twice = json.dumps({"features": [{"properties": {"ISO_A3": "AAA", "ISO_N3": "4"}},
                                     {"properties": {"ISO_A3": "CCC", "ISO_N3": "004"}}]}).encode()
    with pytest.raises(ValueError, match="M49 004 is both AAA and CCC"):
        faostat_bulk.codes_from_natural_earth(twice)
