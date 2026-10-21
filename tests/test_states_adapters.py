"""The Wikidata states adapter and the Glottolog adapter, on invented responses in each publisher's format. No Wikidata
or Glottolog content is used. Each has a negative control."""

import json

import pytest

from athena.adapters import glottolog, wikidata_states


def sparql(rows: list[dict]) -> bytes:
    """A SPARQL JSON result, as the query service sends it."""
    return json.dumps({"results": {"bindings": [{k: {"type": "literal", "value": v} for k, v in r.items()}
                                                for r in rows]}}).encode()


E = "http://www.wikidata.org/entity/"


def test_memberships_keep_their_dates_and_a_repeated_statement_is_kept_once():
    rows = [{"iso3": "AAA", "org": E + "Q1", "orgLabel": "Union One", "start": "1975-05-28T00:00:00Z",
             "end": "2025-01-29T00:00:00Z"},
            {"iso3": "BBB", "org": E + "Q1", "orgLabel": "Union One"},
            {"iso3": "BBB", "org": E + "Q1", "orgLabel": "Union One"},  # one statement reached twice
            {"iso3": "BBB", "org": E + "Q2", "orgLabel": "Union Two"}]
    attrs = [{"iso3": "AAA", "property": "P37", "value": E + "Q9", "valueLabel": "Language Nine"}]
    name, tables, report = wikidata_states.ingest(sparql(rows), sparql(attrs), "2026-01-01")
    m = tables["membership"]
    assert name == "wikidata-states-2026-01-01" and len(m) == 3
    left = m[m["iso3"] == "AAA"].iloc[0]
    assert (left["start"], left["end"]) == ("1975-05-28", "2025-01-29")
    assert tables["attributes"].iloc[0]["value"] == "Q9"
    assert (m["end"] != "").sum() == 1 and "3 membership statements (2 current)" in report[1]


def test_a_membership_without_its_state_stops_the_ingest():
    with pytest.raises(ValueError, match="lacks its state"):
        wikidata_states.ingest(sparql([{"org": E + "Q1"}]), sparql([]), "2026-01-01")


def test_the_queries_name_their_edition_so_each_edition_has_its_own_locked_address():
    assert "edition 2026-01-01" in wikidata_states.membership_query("2026-01-01")
    assert wikidata_states.attributes_query("a") != wikidata_states.attributes_query("b")


LANGUAGES = ("ID,Name,Macroarea,Latitude,Longitude,Glottocode,ISO639P3code,Level,Countries,Family_ID,Language_ID,"
             "Closest_ISO369P3code,First_Year_Of_Documentation,Last_Year_Of_Documentation,Is_Isolate\n"
             "fam1,Family One,Africa,,,fam1,,family,,,,,,,\n"
             "lan1,Tongue A,Africa,1.0,2.0,lan1,aaa,language,KE;TZ,fam1,,,,,False\n"
             "lan2,Tongue B,Africa,3.0,4.0,lan2,bbb,language,KE,,,,,,True\n")
CODES = ("ID,Parameter_ID,Name,Description,numerical_value\n"
         "aes-shifting,aes,shifting,,3\nmed-grammar,med,grammar,,1\ncategory-Spoken_L1_Language,category,"
         "Spoken L1 Language,,\n")
PARAMETERS = "ID,Name,Description\naes,AES,\nmed,MED,\ncategory,Category,\n"


def values(rows: str) -> bytes:
    return ("ID,Language_ID,Parameter_ID,Value,Code_ID,Comment,Source,codeReference\n" + rows).encode()


def test_each_language_gets_its_family_name_and_its_assessments():
    files = {"languages": LANGUAGES.encode(), "codes": CODES.encode(), "parameters": PARAMETERS.encode(),
             "values": values("v1,lan1,aes,,aes-shifting,,,\nv2,lan1,med,,med-grammar,,,\n"
                              "v3,lan1,category,,category-Spoken_L1_Language,,,\n")}
    name, tables, _ = glottolog.ingest(files, "9.9")
    t = tables["languoids"].set_index("glottocode")
    assert name == "glottolog-9.9"
    assert (t.loc["lan1", "family_name"], t.loc["lan1", "aes"], t.loc["lan1", "med"]) == ("Family One", "shifting",
                                                                                          "grammar")
    assert t.loc["lan1", "countries"] == "KE;TZ"
    assert t.loc["lan2", "aes"] == "" and t.loc["lan2", "is_isolate"] == "True"  # negative control: unassessed


def test_an_assessment_with_an_undefined_code_stops_the_ingest():
    files = {"languages": LANGUAGES.encode(), "codes": CODES.encode(), "parameters": PARAMETERS.encode(),
             "values": values("v1,lan1,aes,,aes-unheard_of,,,\n")}
    with pytest.raises(ValueError, match="codes not in codes.csv"):
        glottolog.ingest(files, "9.9")


def test_a_missing_table_stops_the_ingest():
    with pytest.raises(ValueError, match="missing CLDF tables"):
        glottolog.ingest({"languages": LANGUAGES.encode()}, "9.9")
