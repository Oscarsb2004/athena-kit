"""Sections (P54): figures grouped under a heading, with a preset input and output, shared by every project.

A **template** (a TOML file in this folder) is one section: its title, the dimension it belongs to (economy,
finance, stability...; P64), the measures it reads, and its figures. Each
figure names a measure, a shell from `athena.figures` and the shell's arguments. Adding or removing a section is
adding or removing one file. Templates name subjects; shells never do (P38).

A **binding** (one TOML file per project) says which series fills each measure in that project:

    project = "asi"
    sections = ["output", "prices"]
    [datasets.wdi]                      # matched to the dataset named on the command line, wdi-YYYY-MM-DD
    publisher = "World Bank"
    licence = "CC BY 4.0"
    attribution = "The World Bank: World Development Indicators"
    [measures]
    inflation = { dataset = "wdi", series = "FP.CPI.TOTL.ZG" }
    [unbound]                           # a measure the project cannot fill, with the reason; never silently empty
    policy_rate = "not in WDI"

The input is common-format values. The output is one document, format `athena.sections/1`: the datasets with their
terms, the sections with each figure's source, and for each area each section's figure records.
"""

from __future__ import annotations

import math
import tomllib
from pathlib import Path

import pandas as pd

from athena import figures
from athena.table import round_half_up

FORMAT = "athena.sections/1"
TEMPLATES = Path(__file__).parent
DECIMALS = 3  # outputs are stored at three decimals (P33)
AS_PRINTED = {"latest", "first", "trend", "extremes"}  # shells that pass the publisher's values through unchanged


class SectionError(ValueError):
    pass


def template(name: str, folder: Path = TEMPLATES) -> dict:
    path = folder / f"{name}.toml"
    if not path.exists():
        raise SectionError(f"no section template named {name!r}")
    t = tomllib.loads(path.read_text(encoding="utf-8"))
    missing = {"id", "title", "order", "dimension", "about", "measures", "figures"} - t.keys()
    if missing:
        raise SectionError(f"{name}: the template lacks {sorted(missing)}")
    for f in t["figures"]:
        if f["shell"] not in figures.SHELLS:
            raise SectionError(f"{name}: figure {f['id']} names an unknown shell {f['shell']!r}")
        for m in [f["measure"], *f.get("bounds", [])]:
            if m not in t["measures"]:
                raise SectionError(f"{name}: figure {f['id']} reads an undeclared measure {m!r}")
    return t


def binding(path: Path) -> dict:
    return tomllib.loads(path.read_text(encoding="utf-8"))


def resolve(b: dict, names: list[str], folder: Path = TEMPLATES) -> tuple[list[dict], dict[str, str]]:
    """The binding's templates, and the dataset each of its dataset keys means. Every measure a template declares
    must be bound or listed as unbound with a reason; every dataset key must match exactly one name given."""
    used = {}
    for key in b["datasets"]:
        found = [n for n in names if n.startswith(f"{key}-")]
        if len(found) != 1:
            raise SectionError(f"dataset {key!r} must match exactly one of {names}, matched {found}")
        used[key] = found[0]
    templates = [template(s, folder) for s in b["sections"]]
    missing = sorted({m for t in templates for m in t["measures"]} - set(b["measures"]) - set(b.get("unbound", {})))
    if missing:
        raise SectionError(f"measures neither bound nor listed as unbound: {missing}")
    unknown = sorted({m["dataset"] for m in b["measures"].values()} - set(used))
    if unknown:
        raise SectionError(f"measures use datasets the binding does not describe: {unknown}")
    return templates, used


def series(values: pd.DataFrame, measure: dict, area: str) -> pd.Series:
    """One area's series for a bound measure. A breakdown is chosen with `where`; two values for one period stop."""
    rows = values[(values["SERIES"] == measure["series"]) & (values["REF_AREA"] == area)]
    for column, wanted in measure.get("where", {}).items():
        rows = rows[rows[column] == wanted]
    if rows["TIME_PERIOD"].duplicated().any():
        raise SectionError(f"{measure['series']} has more than one value per period for {area}; add a `where`")
    return figures.prepare(rows.set_index("TIME_PERIOD")["OBS_VALUE"])


def _rounded(record: dict) -> dict:
    out = {}
    for key, v in record.items():
        if isinstance(v, float):
            out[key] = round_half_up(v, DECIMALS)
        elif isinstance(v, list):
            out[key] = [_rounded(x) if isinstance(x, dict) else round_half_up(x, DECIMALS) if isinstance(x, float)
                        else x for x in v]
        else:
            out[key] = v
    return out


def build(b: dict, values: dict[str, pd.DataFrame], areas: list[str], folder: Path = TEMPLATES) -> dict:
    """The document for every area. `values` maps each dataset name given to its values table."""
    templates, used = resolve(b, list(values), folder)
    unbound = b.get("unbound", {})
    sections, by_area = [], {a: {} for a in areas}
    for t in sorted(templates, key=lambda t: t["order"]):
        described = []
        for f in t["figures"]:
            m = b["measures"].get(f["measure"])
            source = {"dataset": used[m["dataset"]], "series": m["series"]} if m else {"unbound": unbound[f["measure"]]}
            described.append({k: f[k] for k in ("id", "label", "unit", "shell", "measure")}
                             | {"args": f.get("args", {}), "derived": f["shell"] not in AS_PRINTED}
                             | ({"note": f["note"]} if "note" in f else {}) | source)
        sections.append({k: t[k] for k in ("id", "title", "order", "dimension", "about")} | {"figures": described})
        for area in areas:
            records = {}
            for f in t["figures"]:
                m = b["measures"].get(f["measure"])
                if m is None:
                    continue
                s = series(values[used[m["dataset"]]], m, area)
                record = figures.SHELLS[f["shell"]](s, **f.get("args", {}))
                for side, key in zip(("lower", "upper"), f.get("bounds", [])):
                    # the publisher's interval for the same period, when it prints one
                    if key not in b["measures"]:
                        continue
                    bound = series(values[used[b["measures"][key]["dataset"]]], b["measures"][key], area)
                    record[side] = float(bound[record["period"]]) if record["period"] in bound.index else None
                records[f["id"]] = _rounded(record)
            by_area[area][t["id"]] = records
    datasets = [{"name": used[k]} | v for k, v in b["datasets"].items()]
    return {"format": FORMAT, "project": b["project"], "datasets": datasets, "sections": sections, "areas": by_area}


def check(doc: dict) -> None:
    """The output contract: every area has every section, and every bound figure a record whose value is a finite
    number or None, with a period and a count."""
    if doc.get("format") != FORMAT:
        raise SectionError(f"not an {FORMAT} document")
    for area, sections in doc["areas"].items():
        for s in doc["sections"]:
            records = sections.get(s["id"])
            if records is None:
                raise SectionError(f"{area} lacks section {s['id']}")
            for f in s["figures"]:
                if "unbound" in f:
                    continue
                r = records.get(f["id"])
                if r is None or not {"value", "period", "n"} <= r.keys():
                    raise SectionError(f"{area} {s['id']}.{f['id']} lacks a figure record")
                v = r["value"]
                if v is not None and not (isinstance(v, (int, float)) and math.isfinite(v)):
                    raise SectionError(f"{area} {s['id']}.{f['id']} has a value that is not a finite number")
                if (v is None) != (r["period"] is None):
                    raise SectionError(f"{area} {s['id']}.{f['id']} has a value without a period, or the reverse")
