"""The BACI adapter and the store's large tables, on an invented release in BACI's layout. Invented flows only; each
check has a negative control."""

import io
import zipfile

import pytest

pytest.importorskip("pyarrow")

from athena import dataset  # noqa: E402
from athena.adapters import cepii_baci  # noqa: E402

COUNTRIES = "country_code,country_name,country_iso2,country_iso3\n999,Aland,AA,AAA\n998,Bland,BB,BBB\n"
PRODUCTS = 'code,description\n010111,"Horses: live, pure-bred breeding animals"\n260111,Iron ores\n'


def release(head: str = "t,i,j,k,v,q", **years: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for year, rows in years.items():
            z.writestr(f"BACI_HS92_Y{year[1:]}_V209901.csv", head + "\n" + rows)
        z.writestr("country_codes_V209901.csv", COUNTRIES)
        z.writestr("product_codes_HS92_V209901.csv", PRODUCTS)
        z.writestr("Readme.txt", "BACI\n")
    return buf.getvalue()


def test_flows_keep_their_codes_as_published_and_go_to_the_store_part_by_part(tmp_path):
    data = release(y2023="2023,999,998,010111,1.5,0.25\n2023,998,999,260111,  12.0,         NA\n",
                   y2024="2024,999,998,260111,2.25,3\n")
    name, tables, report, parts = cepii_baci.ingest(data, "209901")
    assert name == "baci-hs92-209901" and tables["products"].loc[0, "code"] == "010111"
    assert dataset.write_parts(name, "flows", parts["flows"], tmp_path) == 3
    f = dataset.load_large(name, "flows", root=tmp_path)
    assert f["k"].tolist() == ["010111", "260111", "260111"]  # the leading zero kept
    assert f.loc[1, "v"] == 12.0 and f["q"].isna().tolist() == [False, True, False]  # padding trimmed, NA empty
    assert f["t"].tolist() == [2023, 2023, 2024]
    only = dataset.load_large(name, "flows", columns=["k", "v"], filters=[("t", "==", 2024)], root=tmp_path)
    assert only.to_dict("records") == [{"k": "260111", "v": 2.25}]
    assert "2 years (2023 to 2024)" in report[0] and "1 without a quantity" in report[1] and report[-1] == "3 flows in all"


def test_a_file_that_is_not_a_release_stops():
    with pytest.raises(ValueError, match="not a BACI release"):  # negative control: no year files
        cepii_baci.ingest(release(), "209901")
    _, _, _, parts = cepii_baci.ingest(release("t,i,j,k,x,y", y2023="2023,999,998,010111,1,2\n"), "209901")
    with pytest.raises(ValueError, match="columns missing"):
        list(parts["flows"])
