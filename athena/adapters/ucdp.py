"""UCDP's Country-Year Dataset on Organized Violence within Country Borders, read whole.

One row per country and year, every year present, so a year without organised violence is recorded as 0 deaths,
not left out. Every numeric column is a series under its own name: the counts of state-based, non-state and one-sided
violence, each with its best, high and low estimates, the dyad counts and the 0/1 flags. The text columns (the
government's name, the dyad ids and names) go to the `records` table beside the year they describe.

UCDP keys countries by Gleditsch-Ward code. `ucdp_countries.csv` maps each code to ISO3: by name through the World
Bank's country table where the names agree, by a written alias where they do not (Ivory Coast, DR Congo (Zaire)).
UCDP keeps one code across a change of state, so the Soviet Union's years sit under RUS, Yugoslavia's under SRB and
North Yemen's under YEM; states that ended before 1993 take their ISO 3166-3 codes (Czechoslovakia CSHH, the GDR
DDDE, South Yemen YDYE). A code not in the file, or one whose name has changed, stops the read.

CC BY 4.0 for every UCDP dataset (read 2026-10-18): free to use and redistribute, citing the publications listed with
each dataset.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pandas as pd

from athena.table import table

CROSSWALK = Path(__file__).with_name("ucdp_countries.csv")
IDS = ["country", "country_id", "year", "region", "Version"]
TEXT = ("govt_name",)


def is_text(column: str) -> bool:
    return column in TEXT or column.endswith(("_dyad_ids", "_dyad_names"))


def read(data: bytes) -> pd.DataFrame:
    """The one CSV in the download."""
    archive = zipfile.ZipFile(io.BytesIO(data))
    files = [n for n in archive.namelist() if n.lower().endswith(".csv")]
    if len(files) != 1:
        raise ValueError(f"expected one CSV in the download, found {files}")
    return pd.read_csv(archive.open(files[0]), dtype={c: str for c in ("country", "region")},
                       keep_default_na=False, na_values={"Version": [""]})


def ingest(data: bytes, edition: str, crosswalk: pd.DataFrame | None = None
           ) -> tuple[str, dict[str, pd.DataFrame], list[str]]:
    name = f"ucdp-cy-{edition}"
    frame = read(data)
    crosswalk = pd.read_csv(CROSSWALK, dtype=str, keep_default_na=False) if crosswalk is None else crosswalk
    missing = sorted(set(IDS) - set(frame.columns))
    if missing:
        raise ValueError(f"missing columns {missing}")
    versions = {f"{v:g}" for v in frame["Version"].unique()}
    if versions != {edition}:
        raise ValueError(f"the file says version {sorted(versions)}, the source list says {edition}")

    seen = frame[["country_id", "country"]].drop_duplicates().astype(str)
    known = seen.merge(crosswalk, on="country_id", how="left", suffixes=("", "_listed"))
    unmapped = known[known["iso3"].isna()]
    renamed = known[known["iso3"].notna() & (known["country"] != known["country_listed"])]
    if len(unmapped) or len(renamed):
        raise ValueError("not in ucdp_countries.csv: "
                         + "; ".join(f"{r.country_id} {r.country}" for r in unmapped.itertuples())
                         + " | renamed since: "
                         + "; ".join(f"{r.country_id} {r.country_listed} -> {r.country}" for r in renamed.itertuples()))
    iso3 = frame["country_id"].astype(str).map(dict(zip(crosswalk["country_id"], crosswalk["iso3"])))

    text = [c for c in frame.columns if is_text(c)]
    measures = [c for c in frame.columns if c not in IDS and c not in text]
    odd = [c for c in measures if not pd.api.types.is_numeric_dtype(frame[c])]
    if odd:
        raise ValueError(f"columns neither numeric nor known text: {odd}")

    long = frame.assign(REF_AREA=iso3).melt(id_vars=["REF_AREA", "year"], value_vars=measures,
                                             var_name="SERIES", value_name="OBS_VALUE").dropna(subset=["OBS_VALUE"])
    values = table(pd.DataFrame({
        "DATASET": name, "SERIES": long["SERIES"], "REF_AREA": long["REF_AREA"],
        "TIME_PERIOD": long["year"].astype(str), "OBS_VALUE": long["OBS_VALUE"].astype(float),
        "EDITION": edition, "DERIVED": False}))
    records = frame[["year"] + text].assign(REF_AREA=iso3).fillna("")
    records = records[["REF_AREA", "year"] + text].rename(columns={"year": "TIME_PERIOD"}).astype(str)
    areas = seen.merge(crosswalk[["country_id", "iso3", "how"]], on="country_id").merge(
        frame[["country_id", "region"]].astype(str).drop_duplicates(), on="country_id")
    codebook = pd.DataFrame({"series": measures})
    report = [f"{name}: UCDP Country-Year Dataset on Organized Violence within Country Borders, version {edition}",
              f"  {len(values):,} values, {len(measures)} series, {values['REF_AREA'].nunique()} countries, "
              f"years {values['TIME_PERIOD'].min()}-{values['TIME_PERIOD'].max()}",
              f"  {(areas['how'] == 'alias').sum()} of {len(areas)} countries matched by a written alias, "
              f"the rest by name",
              f"  text columns kept in records: {text}"]
    return name, {"values": values, "codebook": codebook, "areas": areas, "records": records.sort_values(
        ["REF_AREA", "TIME_PERIOD"], ignore_index=True)}, report
