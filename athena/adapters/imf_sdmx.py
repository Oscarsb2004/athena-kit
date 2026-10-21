"""An IMF dataflow, read whole from the IMF's SDMX 3.0 API (api.imf.org), as SDMX-JSON 2.0.

The data document holds one entry per series, keyed by the positions of its dimensions' codes, and each series its
observations by time position. Attribute values are indices into the attribute's declared values, or the value
itself where the attribute lists none. The structure document (the dataflow with `references=all`) holds the code
lists; the source names which code list labels each dimension, and every code the data uses must have its label
there, or the ingest stops.

    SERIES       the codes of every series dimension except the area, joined by "." (PPI.YOY_PCH_PT.A)
    REF_AREA     the area dimension's code (the IMF's ISO 3166 alpha-3 codes for countries)
    UNIT_MEASURE the transformation's label, with the index's reference period where it has one

Cite as "Source: International Monetary Fund, <dataflow name>" (IMF data terms, read 2026-10-18). The whole
dataflow is fetched once, as one document.
"""

from __future__ import annotations

import json

import pandas as pd

from athena.table import table

AREA = "COUNTRY"


def _labels(structure: dict, codelists: dict[str, str]) -> dict[str, dict[str, str]]:
    """Dimension -> code -> label, from the code lists the source names."""
    found = {c["id"]: c for c in structure["data"]["codelists"]}
    missing = sorted(set(codelists.values()) - set(found))
    if missing:
        raise ValueError(f"the structure lacks code lists {missing}")
    return {dim: {code["id"]: code.get("name", code["id"]) for code in found[cl].get("codes", [])}
            for dim, cl in codelists.items()}


def _value(attribute: dict, raw):
    """An attribute's value: by its index into the declared values, or as given where none are declared."""
    values = attribute.get("values") or []
    if isinstance(raw, int) and not isinstance(raw, bool) and values:
        v = values[raw]
        return v.get("id", v.get("value", v.get("name")))
    return raw


def ingest(data: bytes, structure: bytes, dataflow: str, edition: str, codelists: dict[str, str]
           ) -> tuple[str, dict[str, pd.DataFrame], list[str]]:
    """The dataset's name, its tables (values and codebook) and the report."""
    name = f"{dataflow.lower()}-{edition}"
    doc, struct = json.loads(data), json.loads(structure)
    shape = doc["data"]["structures"][0]
    dims = shape["dimensions"]["series"]
    time = shape["dimensions"]["observation"][0]
    if AREA not in [d["id"] for d in dims]:
        raise ValueError(f"{dataflow}: no {AREA} dimension")
    others = [d["id"] for d in dims if d["id"] != AREA]
    labels = _labels(struct, codelists)
    unlabelled = sorted(set(others) - set(labels))
    if unlabelled:
        raise ValueError(f"{dataflow}: no code list named for {unlabelled}")
    s_attrs, o_attrs = shape["attributes"].get("series", []), shape["attributes"].get("observation", [])
    rows, books, empty, unknown = [], {}, 0, set()
    for key, series in doc["data"]["dataSets"][0]["series"].items():
        codes = {d["id"]: d["values"][int(i)]["id"] for d, i in zip(dims, key.split(":"))}
        for dim in others:
            if codes[dim] not in labels[dim]:
                unknown.add((dim, codes[dim]))
        attrs = {a["id"]: _value(a, v) for a, v in zip(s_attrs, series.get("attributes") or [])}
        sid = ".".join(codes[d] for d in others)
        transform = labels.get("TYPE_OF_TRANSFORMATION", {}).get(codes.get("TYPE_OF_TRANSFORMATION", ""), "")
        reference = attrs.get("REFERENCE_PERIOD") or ""
        unit = f"{transform}, {reference}" if reference else transform
        books.setdefault(sid, {"SERIES": sid} | {f"{d}": codes[d] for d in others}
                         | {f"{d}_LABEL": labels[d].get(codes[d], "") for d in others})
        for t, obs in series.get("observations", {}).items():
            value = obs[0] if obs else None
            if value is None or value == "":
                empty += 1
                continue
            o = {a["id"]: _value(a, v) for a, v in zip(o_attrs, obs[1:])}
            rows.append({"DATASET": name, "SERIES": sid, "REF_AREA": codes[AREA],
                         "TIME_PERIOD": time["values"][int(t)].get("value", time["values"][int(t)].get("id")),
                         "OBS_VALUE": float(value), "UNIT_MEASURE": unit, "OBS_STATUS": str(o.get("STATUS") or ""),
                         "EDITION": edition, "DERIVED": False})
    if unknown:
        raise ValueError(f"{dataflow}: codes without a label in their code list: {sorted(unknown)}")
    values = table(rows)
    codebook = pd.DataFrame(sorted(books.values(), key=lambda b: b["SERIES"]))
    report = [f"{name}: IMF {dataflow} dataflow, fetched {edition}",
              f"  {len(values):,} values, {values['SERIES'].nunique()} series, {values['REF_AREA'].nunique()} areas, "
              f"{values['TIME_PERIOD'].min()} to {values['TIME_PERIOD'].max()}",
              f"  observations without a value, left out: {empty:,}"]
    return name, {"values": values, "codebook": codebook}, report
