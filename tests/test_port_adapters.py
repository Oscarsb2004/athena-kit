"""The IMF PortWatch and NGA World Port Index adapters, on synthetic files in each publisher's layout. Invented ports
and figures only; each check has a negative control."""

import pytest

pytest.importorskip("geopandas")

from athena.adapters import imf_portwatch, nga_wpi  # noqa: E402

PORTS = ("X,Y,portid,portname,country,ISO3,continent,fullname,lat,lon,vessel_count_total,LOCODE,ObjectId\n"
         "1000000.5,2000000.5,port1,Alpha,Aland,AAA,Africa,\"Alpha, Aland\",-10.5,20.25,120,AA ALP,1\n"
         "3000000.5,4000000.5,fso1,Aland - Offshore Oil Terminal 1,Aland,AAA,Africa,x,-11.0,21.0,8,,2\n")
CHOKEPOINTS = ("X,Y,portid,portname,country,ISO3,continent,fullname,lat,lon,vessel_count_total,LOCODE,ObjectId\n"
               "5.5,6.5,chokepoint1,Strait A,,,,Strait A,1.0,2.0,9000,,1\n")
DAILY_PORTS = ("date,year,month,day,portid,portname,country,ISO3,portcalls,import,export,ObjectId\n"
               "2020/01/01,2020,1,1,port1,Alpha,Aland,AAA,3,1500,0,1\n"
               "2020/01/02,2020,1,2,port1,Alpha,Aland,AAA,0,0,250,2\n"
               "2020/01/01,2020,1,1,port9,Gone,Aland,AAA,1,0,0,3\n")
DAILY_CHOKEPOINTS = "date,year,month,day,portid,portname,n_total,capacity,ObjectId\n2020/01/01,2020,1,1,chokepoint1,Strait A,40,900000,1\n"


def files(**changes) -> dict[str, bytes]:
    f = {"ports": PORTS, "chokepoints": CHOKEPOINTS, "daily_ports": DAILY_PORTS, "daily_chokepoints": DAILY_CHOKEPOINTS}
    return {k: v.encode() for k, v in (f | changes).items()}


def test_portwatch_keeps_every_published_column_and_places_points_by_lat_and_lon():
    name, layers, tables, report = imf_portwatch.ingest(files(), "2026-10-22")
    assert name == "portwatch-2026-10-22"
    ports = layers["ports"].set_index("portid")
    assert not {"X", "Y", "ObjectId"} & set(ports.columns)  # the hub's own columns, not the publisher's
    assert (ports.loc["port1"].geometry.x, ports.loc["port1"].geometry.y) == (20.25, -10.5)  # not the hub's X, Y
    assert ports.loc["fso1", "LOCODE"] == "" and ports.loc["port1", "fullname"] == "Alpha, Aland"
    d = tables["daily_ports"]
    assert d["date"].tolist() == ["2020-01-01", "2020-01-02", "2020-01-01"] and d["import"].sum() == 1500
    assert "ObjectId" not in d.columns
    assert "listed without daily rows: 1; daily ids not listed: 1" in report[3]  # fso1 has none; port9 is unlisted
    assert "2 with a LOCODE" not in report[1] and "1 with a LOCODE" in report[1]


def test_portwatch_refuses_a_date_it_cannot_read_and_a_missing_file():
    with pytest.raises(ValueError, match="YYYY/MM/DD"):
        imf_portwatch.ingest(files(daily_ports=DAILY_PORTS.replace("2020/01/02", "02/01/2020")), "e")
    with pytest.raises(ValueError, match="not numeric"):
        imf_portwatch.ingest(files(daily_ports=DAILY_PORTS.replace(",1500,", ",many,")), "e")
    with pytest.raises(ValueError, match="daily_chokepoints"):
        imf_portwatch.ingest({k: v for k, v in files().items() if k != "daily_chokepoints"}, "e")


WPI = ("﻿OID_,World Port Index Number,Main Port Name,UN/LOCODE,Country Code,Latitude,Longitude\n"
       "0.0,46135.0,Port B,NB BBB,Bland,4.1,5.9\n"
       "1.0,46135.0,Port C,NB CCC,Bland,6.4,3.4\n"
       "2.0,400.0,Port D,ND DDD,Dland,65.2,-14.0\n"
       "3.0,400.0,Port D,NDDDD,Dland,65.2,-14.0\n"
       "4.0,7950.0,Port E, ,Eland,40.0,-74.0\n")


def test_wpi_gives_a_number_its_locode_only_where_its_rows_agree():
    name, layers, tables, report = nga_wpi.ingest(WPI.encode(), "2026-10-22")
    ports = layers["ports"]
    assert name == "wpi-2026-10-22" and len(ports) == 5 and tables == {}
    assert ports["wpi"].tolist() == [46135, 46135, 400, 400, 7950]
    assert ports.geometry.iloc[2].x == -14.0 and ports["Main Port Name"].iloc[4] == "Port E"  # kept as written
    codes, ambiguous = nga_wpi.locodes(ports)
    assert codes == {400: "NDDDD"}  # "ND DDD" and "NDDDD" are one code; 7950 has none
    assert ambiguous == [46135]     # negative control: two different codes, so the number joins to nothing
    assert "[46135]" in report[1]
    assert nga_wpi.locode(" ng esc ") == "NGESC" and nga_wpi.locode(" ") == ""
