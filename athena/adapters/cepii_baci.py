"""CEPII's BACI, read whole: world trade by exporter, importer and product (HS 6-digit), one release in one HS
revision. The zip holds one CSV per year (`t, i, j, k, v, q`: year, exporter, importer, product, value in thousands of
current US dollars, quantity in metric tons), the country codes and the product codes.

One large table, `flows`, written year by year as Parquet (it is too large to hold at once): every published column
under its own name, `k` kept as text so a code keeps its leading zero, `q` empty where BACI gives none. Beside it, the
`countries` and `products` tables as published. A zip without the expected files or columns stops the ingest.

Terms: Etalab Open Licence 2.0 (cepii.fr, BACI's page, read 2026-10-23): free reuse, commercial or not, including
derived data, acknowledging CEPII as the source and the date of the release's last update. Cite Gaulier and Zignago
(2010), CEPII Working Paper 2010-23.
"""

from __future__ import annotations

import io
import re
import zipfile
from collections.abc import Iterator

import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.csv as pacsv

COLUMNS = ["t", "i", "j", "k", "v", "q"]
TYPES = {"t": pa.int16(), "i": pa.int32(), "j": pa.int32()}


def yr(member: str) -> str:
    """A year file's year, from its name."""
    return re.search(r"_Y(\d{4})_", member).group(1)


def _year(z: zipfile.ZipFile, member: str) -> pa.Table:
    """One year's flows: the codes as integers, `k` as text, `v` and `q` as numbers once their padding is trimmed."""
    with z.open(member) as f:
        table = pacsv.read_csv(f, convert_options=pacsv.ConvertOptions(
            column_types={c: pa.string() for c in COLUMNS}, strings_can_be_null=False))
    missing = [c for c in COLUMNS if c not in table.column_names]
    if missing:
        raise ValueError(f"{member}: columns missing: {missing}")
    out = {}
    for c in COLUMNS:
        col = pc.utf8_trim_whitespace(table[c])
        if c == "k":
            out[c] = col
        elif c in TYPES:
            out[c] = pc.cast(col, TYPES[c])
        else:
            empty = pc.or_(pc.equal(col, ""), pc.equal(col, "NA"))
            out[c] = pc.cast(pc.if_else(empty, pa.scalar(None, pa.string()), col), pa.float64())
    return pa.table(out)


def ingest(data: bytes, edition: str) -> tuple[str, dict[str, pd.DataFrame], list[str], dict[str, Iterator[pa.Table]]]:
    z = zipfile.ZipFile(io.BytesIO(data))
    names = z.namelist()
    years = sorted(n for n in names if re.fullmatch(r"BACI_HS\d\d_Y\d{4}_V\w+\.csv", n))
    countries = [n for n in names if n.startswith("country_codes")]
    products = [n for n in names if n.startswith("product_codes")]
    if not years or len(countries) != 1 or len(products) != 1:
        raise ValueError(f"not a BACI release: {names[:6]}")
    hs = re.match(r"BACI_(HS\d\d)_", years[0]).group(1)
    read = lambda n: pd.read_csv(z.open(n), dtype=str, keep_default_na=False, encoding="utf-8")  # noqa: E731
    tables = {"countries": read(countries[0]), "products": read(products[0])}
    name = f"baci-{hs.lower()}-{edition}"
    report = [f"{name}: CEPII BACI {edition}, {hs}, {len(years)} years "
              f"({yr(years[0])} to {yr(years[-1])}); {len(tables['countries'])} countries, "
              f"{len(tables['products'])} products"]

    def flows() -> Iterator[pa.Table]:
        total = 0
        for member in years:
            year = _year(z, member)
            total += year.num_rows
            report.append(f"  {yr(member)}: {year.num_rows:,} flows, {pc.sum(year['v']).as_py():,.0f} thousand US$, "
                          f"{year['q'].null_count:,} without a quantity")
            yield year
        report.append(f"{total:,} flows in all")

    return name, tables, report, {"flows": flows()}
