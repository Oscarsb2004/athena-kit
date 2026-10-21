"""Figure shells and sections (P54), on invented series. Each rule has a negative control."""

import math
import statistics

import pandas as pd
import pytest

from athena import figures, sections
from athena.sections import SectionError
from athena.table import table


def s(values: dict) -> pd.Series:
    return figures.prepare(pd.Series(values, dtype=float))


# ── figure shells ───────────────────────────────────────────────────────────────────────────────────────────

def test_latest_skips_missing_values_and_an_empty_series_gives_none():
    assert figures.latest(s({"2020": 1.0, "2021": 2.0, "2022": None})) == {"value": 2.0, "period": "2021", "n": 1}
    assert figures.latest(s({})) == {"value": None, "period": None, "n": 0}


def test_first_is_the_earliest_value_and_an_empty_series_gives_none():
    assert figures.first(s({"2020": None, "2021": 2.0, "2022": 3.0})) == {"value": 2.0, "period": "2021", "n": 1}
    assert figures.first(s({})) == {"value": None, "period": None, "n": 0}
    assert figures.first(s({"2021": 2.0, "2022": 3.0})) != figures.latest(s({"2021": 2.0, "2022": 3.0}))


def test_mean_uses_the_last_k_observations_and_refuses_fewer():
    x = s({"2019": 9.0, "2020": 1.0, "2021": 2.0, "2022": 6.0})
    assert figures.mean(x, 3) == {"value": 3.0, "period": "2020/2022", "n": 3}
    assert figures.mean(s({"2021": 2.0, "2022": 6.0}), 3) == {"value": None, "period": None, "n": 2}


def test_a_gap_shows_in_the_period_range_rather_than_being_filled():
    assert figures.mean(s({"2010": 3.0, "2020": 3.0, "2022": 3.0}), 3)["period"] == "2010/2022"


def test_spread_is_the_sample_standard_deviation():
    x = s({"2020": 1.0, "2021": 2.0, "2022": 6.0})
    assert figures.spread(x, 3)["value"] == pytest.approx(statistics.stdev([1.0, 2.0, 6.0]), rel=1e-15)
    assert figures.spread(x, 1)["value"] is None


def test_change_and_growth_compare_the_ends_of_the_window():
    x = s({"2020": 100.0, "2021": 110.0, "2022": 121.0})
    assert figures.change(x, 2) == {"value": 21.0, "period": "2020/2022", "n": 2}
    assert figures.growth(x, 2)["value"] == pytest.approx(10.0, rel=1e-12)
    assert figures.growth(s({"2020": -1.0, "2022": 121.0}), 1)["value"] is None
    assert figures.growth(x, 3)["value"] is None


def test_extremes_count_one_episode_once():
    x = s({"2000": 50.0, "2001": 60.0, "2002": 55.0, "2010": 40.0, "2015": 30.0})
    apart = figures.extremes(x, k=3, gap=3)
    assert [(v["period"], v["value"]) for v in apart["values"]] == [("2001", 60.0), ("2010", 40.0), ("2015", 30.0)]
    assert (apart["value"], apart["period"], apart["n"]) == (60.0, "2001", 5)
    # negative control: without the gap, one episode fills the list
    together = figures.extremes(x, k=3, gap=1)
    assert [v["period"] for v in together["values"]] == ["2001", "2002", "2000"]
    assert [v["period"] for v in figures.extremes(x, k=2, highest=False)["values"]] == ["2015", "2010"]


def test_trend_starts_at_since():
    x = s({"1999": 1.0, "2000": 2.0, "2001": 3.0})
    assert figures.trend(x, since="2000")["periods"] == ["2000", "2001"]
    assert figures.trend(x)["n"] == 3


# ── sections ────────────────────────────────────────────────────────────────────────────────────────────────

TEMPLATE = """
id = "toy"
title = "Toy"
order = 1
dimension = "toys"
about = "An invented section."
[measures]
level = "An invented level"
level_lower = "Its lower bound"
level_upper = "Its upper bound"
rate = "An invented rate"
[[figures]]
id = "level"
label = "Level"
unit = "units"
measure = "level"
bounds = ["level_lower", "level_upper"]
shell = "latest"
[[figures]]
id = "rate_mean_2"
label = "Rate, 2-year mean"
unit = "%"
measure = "rate"
shell = "mean"
args = { k = 2 }
"""

BINDING = {
    "project": "toy",
    "sections": ["toy"],
    "datasets": {"src": {"publisher": "Nobody", "licence": "none", "attribution": "invented"}},
    "measures": {"level": {"dataset": "src", "series": "L"}, "level_lower": {"dataset": "src", "series": "LL"},
                 "level_upper": {"dataset": "src", "series": "LU"}, "rate": {"dataset": "src", "series": "R"}},
}


def values(rows=None):
    base = [("L", "AAA", "2021", 10.0), ("LL", "AAA", "2021", 8.0), ("LU", "AAA", "2021", 12.0),
            ("R", "AAA", "2020", 1.0), ("R", "AAA", "2021", 2.0), ("L", "BBB", "2020", 7.0)]
    return table([{"DATASET": "src-2026-01-01", "SERIES": a, "REF_AREA": b, "TIME_PERIOD": c, "OBS_VALUE": d,
                   "EDITION": "e", "DERIVED": False} for a, b, c, d in (rows or base)])


@pytest.fixture
def folder(tmp_path):
    (tmp_path / "toy.toml").write_text(TEMPLATE, encoding="utf-8")
    return tmp_path


def test_a_document_carries_every_area_section_and_figure(folder):
    doc = sections.build(BINDING, {"src-2026-01-01": values()}, ["AAA", "BBB"], folder)
    sections.check(doc)
    assert doc["areas"]["AAA"]["toy"]["level"] == {"value": 10.0, "period": "2021", "n": 1, "lower": 8.0,
                                                   "upper": 12.0}
    assert doc["areas"]["AAA"]["toy"]["rate_mean_2"] == {"value": 1.5, "period": "2020/2021", "n": 2}
    assert doc["areas"]["BBB"]["toy"]["rate_mean_2"] == {"value": None, "period": None, "n": 0}
    level, rate = doc["sections"][0]["figures"]
    assert (level["derived"], rate["derived"]) == (False, True)
    assert (rate["dataset"], rate["series"]) == ("src-2026-01-01", "R")
    assert doc["datasets"] == [{"name": "src-2026-01-01", "publisher": "Nobody", "licence": "none",
                                "attribution": "invented"}]


def test_outputs_are_stored_at_three_decimals(folder):
    doc = sections.build(BINDING, {"src-2026-01-01": values([("L", "AAA", "2021", 1.23456),
                                                              ("R", "AAA", "2021", 1.0)])}, ["AAA"], folder)
    assert doc["areas"]["AAA"]["toy"]["level"]["value"] == 1.235


def test_a_measure_neither_bound_nor_explained_is_refused(folder):
    partial = BINDING | {"measures": {k: v for k, v in BINDING["measures"].items() if k != "rate"}}
    with pytest.raises(SectionError, match="neither bound nor listed"):
        sections.build(partial, {"src-2026-01-01": values()}, ["AAA"], folder)
    explained = partial | {"unbound": {"rate": "the toy publisher has no rate"}}
    doc = sections.build(explained, {"src-2026-01-01": values()}, ["AAA"], folder)
    sections.check(doc)
    assert "rate_mean_2" not in doc["areas"]["AAA"]["toy"]
    assert doc["sections"][0]["figures"][1]["unbound"] == "the toy publisher has no rate"


def test_a_dataset_key_must_match_exactly_one_dataset(folder):
    with pytest.raises(SectionError, match="exactly one"):
        sections.build(BINDING, {"src-2026-01-01": values(), "src-2026-02-01": values()}, ["AAA"], folder)
    with pytest.raises(SectionError, match="exactly one"):
        sections.build(BINDING, {"other-2026-01-01": values()}, ["AAA"], folder)


def test_two_values_for_one_period_stop_until_a_breakdown_is_chosen():
    rows = table([{"DATASET": "d", "SERIES": "L", "REF_AREA": "AAA", "TIME_PERIOD": "2021", "OBS_VALUE": v,
                   "EDITION": "e", "DERIVED": False, "SEX": sex} for v, sex in ((1.0, "F"), (2.0, "M"))])
    with pytest.raises(SectionError, match="more than one value"):
        sections.series(rows, {"series": "L"}, "AAA")
    assert sections.series(rows, {"series": "L", "where": {"SEX": "M"}}, "AAA").tolist() == [2.0]


@pytest.mark.parametrize("damage", ["drop section", "infinite value", "value without period", "wrong format"])
def test_the_output_contract_catches_a_damaged_document(folder, damage):
    doc = sections.build(BINDING, {"src-2026-01-01": values()}, ["AAA"], folder)
    sections.check(doc)  # the control: undamaged, it passes
    record = doc["areas"]["AAA"]["toy"]["level"]
    if damage == "drop section":
        del doc["areas"]["AAA"]["toy"]
    elif damage == "infinite value":
        record["value"] = math.inf
    elif damage == "value without period":
        record["period"] = None
    else:
        doc["format"] = "something/0"
    with pytest.raises(SectionError):
        sections.check(doc)


def test_a_template_naming_an_unknown_shell_or_measure_is_refused(tmp_path):
    (tmp_path / "bad.toml").write_text(TEMPLATE.replace('shell = "mean"', 'shell = "median"'), encoding="utf-8")
    with pytest.raises(SectionError, match="unknown shell"):
        sections.template("bad", tmp_path)
    (tmp_path / "bad.toml").write_text(TEMPLATE.replace('measure = "rate"', 'measure = "speed"'), encoding="utf-8")
    with pytest.raises(SectionError, match="undeclared measure"):
        sections.template("bad", tmp_path)


def test_a_template_without_its_dimension_is_refused(tmp_path):
    (tmp_path / "bad.toml").write_text(TEMPLATE.replace('dimension = "toys"\n', ""), encoding="utf-8")
    with pytest.raises(SectionError, match="dimension"):
        sections.template("bad", tmp_path)


def test_every_shipped_template_loads():
    names = sorted(p.stem for p in sections.TEMPLATES.glob("*.toml"))
    assert names, "no templates shipped"
    for name in names:
        t = sections.template(name)
        assert t["id"] == name and t["figures"]
        assert t["dimension"] in {"stability", "economy", "finance"}
