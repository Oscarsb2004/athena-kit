"""Ingest a project's sources into the store, each database whole (P37, P38).

A project keeps two files in its own folder:
- `sources.toml`: every source it reads, one table each, with its `url` (or a `url` template with `{table}`), its
  `kind`, its `edition` where the publisher names one, and its `terms` as read and dated;
- `sources.lock`: the SHA-256 of every address fetched, written on first use and checked ever after (athena.fetch),
  so a source whose bytes change is refused, never silently used.

`Project` reads them. `Ingest` runs one source: it fetches what the source's kind needs through the project's lock,
runs that kind's adapter, and writes the dataset (or geodataset) to the store. Each kind is one adapter; a project
can add kinds of its own (the ASI adds its frozen pull).

    python -m athena.ingest <project folder> <source key> [<source key> ...]
"""

from __future__ import annotations

import sys
import tomllib
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from athena import dataset
from athena.component import Component
from athena.fetch import Fetcher

Get = Callable[[str], bytes]


@dataclass(frozen=True)
class Result:
    """What an adapter returns: a dataset's name, its tables and its report, and layers for geodata."""

    name: str
    tables: dict[str, pd.DataFrame]
    report: list[str]
    layers: dict | None = None


class Project:
    """A project's sources and lock, both in its own folder."""

    def __init__(self, root: Path):
        self.root = Path(root)
        self.lock = self.root / "sources.lock"
        with (self.root / "sources.toml").open("rb") as f:
            self.sources: dict[str, dict] = tomllib.load(f)

    def source(self, key: str) -> dict:
        if key not in self.sources:
            raise KeyError(f"{key!r} is not in {self.root / 'sources.toml'}")
        return self.sources[key]

    def fetcher(self, session=None) -> Fetcher:
        return Fetcher(self.lock, session)


# ── the kinds: one adapter each; imported only when used, so the [geo] extra stays optional ──────────────────────

def _worldbank(src: dict, get: Get) -> Result:
    from athena.adapters import worldbank
    return Result(*worldbank.ingest(get(src["url"]), src["database"]))


def _weo(src: dict, get: Get) -> Result:
    from athena.adapters import imf_weo
    return Result(*imf_weo.ingest(get(src["url"]), src["edition"]))


def _hdr(src: dict, get: Get) -> Result:
    from athena.adapters import undp_hdr
    return Result(*undp_hdr.ingest(get(src["url"]), get(src["metadata_url"]), src["edition"]))


def _cpi(src: dict, get: Get) -> Result:
    from athena.adapters import ti_cpi
    return Result(*ti_cpi.ingest(get(src["url"]), src["edition"]))


def _ucdp(src: dict, get: Get) -> Result:
    from athena.adapters import ucdp
    return Result(*ucdp.ingest(get(src["url"]), src["edition"]))


def _wikidata(src: dict, get: Get) -> Result:
    from athena import commons
    from athena.adapters import wikidata_states as w
    return Result(*w.ingest(get(commons.sparql_url(w.membership_query(src["edition"]))),
                            get(commons.sparql_url(w.attributes_query(src["edition"]))), src["edition"]))


def _glottolog(src: dict, get: Get) -> Result:
    from athena.adapters import glottolog
    return Result(*glottolog.ingest({t: get(src["url"].format(table=t)) for t in glottolog.TABLES}, src["edition"]))


def _usgs(src: dict, get: Get) -> Result:
    from athena.adapters import usgs_africa_gis
    name, layers, tables, report = usgs_africa_gis.ingest(get(src["url"]))
    return Result(name, tables, report, layers)


def _grid(src: dict, get: Get) -> Result:
    from athena.adapters import wb_africa_grid
    name, layers, tables, report = wb_africa_grid.ingest(get(src["url"]))
    return Result(name, tables, report, layers)


KINDS: dict[str, Callable[[dict, Get], Result]] = {
    "worldbank-bulk": _worldbank, "imf-weo": _weo, "undp-hdr": _hdr, "ti-cpi": _cpi, "ucdp": _ucdp,
    "wikidata-sparql": _wikidata, "glottolog-cldf": _glottolog, "usgs-africa-gis": _usgs, "wb-africa-grid": _grid,
}


class Ingest(Component):
    """Fetch one of a project's sources through its lock, run its kind's adapter, and write the dataset (an I/O
    component: it reads the network or the fetch cache, and writes the store)."""

    section = "02 Inputs and Sources"

    @dataclass(frozen=True)
    class Input:
        project: Project
        key: str

    @dataclass(frozen=True)
    class Output:
        name: str
        report: list[str]
        path: Path

    def __init__(self, kinds: dict[str, Callable[[dict, Get], Result]] | None = None, session=None,
                 root: Path = dataset.ROOT):
        self.kinds = KINDS | (kinds or {})
        self.session, self.root = session, root

    def run(self, inp: Input) -> Output:
        src = inp.project.source(inp.key)
        kind = src.get("kind")
        if kind not in self.kinds:
            raise ValueError(f"{inp.key}: no adapter for kind {kind!r}; known: {sorted(self.kinds)}")
        result = self.kinds[kind](src, inp.project.fetcher(self.session).get)
        if result.layers is not None:
            from athena import geo
            path = geo.write(result.name, result.layers, result.tables, result.report, self.root)
        else:
            path = dataset.write(result.name, result.tables, result.report, self.root)
        return self.Output(result.name, result.report, path)


@dataclass
class Batch:
    """Several sources of one project, in order; each report printed as it is written."""

    project: Project
    keys: list[str] = field(default_factory=list)

    def run(self, ingest: Ingest | None = None) -> list[str]:
        ingest = ingest or Ingest()
        lines: list[str] = []
        for key in self.keys:
            lines += ingest.run(Ingest.Input(self.project, key)).report
        return lines


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    print("\n".join(Batch(Project(Path(argv[0])), argv[1:]).run()))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
