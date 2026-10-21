"""Datasets in the store (P40): a folder of CSV tables and the report of the ingest that wrote them.

A values table is always in the common format; other tables (a codebook, a membership list) are plain CSV.
Values are written in full precision, so reading a dataset back gives exactly what was written.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from athena.fetch import STORE
from athena.table import NUMBERS, table

ROOT = STORE / "datasets"


def write(name: str, tables: dict[str, pd.DataFrame], report: list[str], root: Path = ROOT) -> Path:
    folder = root / name
    folder.mkdir(parents=True, exist_ok=True)
    for file, frame in tables.items():
        frame.to_csv(folder / f"{file}.csv", index=False, lineterminator="\n")
    (folder / "report.txt").write_text("\n".join(report) + "\n", encoding="utf-8", newline="\n")
    return folder


def load(name: str, file: str = "values", root: Path = ROOT) -> pd.DataFrame:
    """A table as written. A values table comes back validated, with numbers as floats.

    Numbers are parsed with `float_precision="round_trip"`, which rounds correctly. pandas' default parser does
    not: it reads 0.00952819999999999 as 0.0095281999999999, a different double."""
    path = root / name / f"{file}.csv"
    if file != "values":
        return pd.read_csv(path, dtype=str, keep_default_na=False)
    header = pd.read_csv(path, nrows=0).columns
    frame = pd.read_csv(path, dtype={c: float if c in NUMBERS else str for c in header}, keep_default_na=False,
                        na_values=dict.fromkeys(NUMBERS, [""]), float_precision="round_trip")
    frame["DERIVED"] = frame["DERIVED"] == "True"
    return table(frame)
