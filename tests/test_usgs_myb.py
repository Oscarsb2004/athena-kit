"""The USGS Minerals Yearbook adapter, on invented files in the data release's layout. Invented rows only; each check
has a negative control."""

import pytest

from athena.adapters import usgs_myb

LEVELS = "Level 1 (Commodity Group),Level 2 (Commodity),Level 3 (Type),Level 4 (Phase),Level 5 (Form)"
PROD = ("﻿ObjectID,Country (Short Form) or Locality," + LEVELS + ",Descriptor,Commodity Unit,Time Period,"
        "Data Type,Value,Unit,Value Notes,Source 1\n"
        "1,Aland,Aluminum,Bauxite,,,,,Gross weight,2023,Production,1162000,Metric tons,,https://example.org/a\n"
        "2,Aland,Gold,Gold,,,Mine,,Elemental content,2023,Production,\"1,250\",Kilograms,Estimated,USGS estimate\n")
FAC = ("USGS Facility ID,Country (Short Form) or Locality,Facility Name,Feature Type," + LEVELS +
       ",Annual Production Capacity,Capacity Unit,Facility Status\n"
       "ALA0001,Aland,North pit,Mines and Quarries,Aluminum,Bauxite,,,,500000,Metric tons,Assumed active\n")


def test_both_tables_kept_as_published():
    name, tables, report = usgs_myb.ingest(PROD.encode(), FAC.encode(), "2024")
    p = tables["production"]
    assert name == "usgs-myb3-2024" and list(p.columns)[0] == "ObjectID"  # the byte-order mark is not in a name
    assert p.loc[1, "Value"] == "1,250" and p.loc[1, "Value Notes"] == "Estimated"  # text exactly as published
    assert tables["facilities"].loc[0, "Facility Name"] == "North pit"
    assert "2 rows, 1 localities, 2 commodities, years 2023 to 2023; 1 estimated" in report[1]


def test_a_value_that_is_not_a_number_or_a_missing_column_stops():
    with pytest.raises(ValueError, match="not numbers"):  # negative control: a withheld value
        usgs_myb.ingest(PROD.replace("1162000", "W").encode(), FAC.encode(), "2024")
    with pytest.raises(ValueError, match="facilities: columns missing"):
        usgs_myb.ingest(PROD.encode(), b"id,name\n1,x\n", "2024")
