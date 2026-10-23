# athena-kit

The public parts of **Athena**: what anyone needs to run a project built with it. Published statistics are fetched
once and hash-locked, read whole by one adapter per database into one common format, and kept in a local store. Each
project lives in its own repository, lists its own sources and installs this package.

Athena's own system (the library tooling, the Stewards, the agents) is private and builds on this same package.

## What is in it

| Module | What it does |
| --- | --- |
| `athena.fetch` | Fetch once, keep forever: a cached session that never expires, and a lock of every address's SHA-256; changed bytes are refused |
| `athena.table` | The common format: one long table with SDMX column names, checked by pandera; rounding once, half up |
| `athena.dataset`, `athena.geo` | Datasets and geodata (GeoParquet) in the store, `ATHENA_STORE` (default `C:\AthenaStore`) |
| `athena.sections`, `athena.figures` | Shared section templates and the figure shells that fill them |
| `athena.commons` | Wikidata's query service and Wikimedia Commons, with each file's licence |
| `athena.adapters` | One adapter per database, each pure: the World Bank's bulk downloads, the IMF WEO, UNDP's HDR, TI's CPI, UCDP, USGS's Africa GIS, the World Bank grid map, Wikidata, Glottolog, any IMF SDMX dataflow (the PPI first), any FAOSTAT bulk domain (producer prices first), IMF PortWatch (ports, chokepoints and their daily activity), NGA's World Port Index, UCDP's georeferenced events (GED and the monthly Candidate events) |
| `athena.ingest` | Ingest a project's sources: its own `sources.toml` and `sources.lock`, each source's kind run by its adapter |
| `athena.component`, `athena.components` | The component standard, and the check of a project's `components.yaml` |

## Using it in a project

```bash
python -m pip install "athena-kit @ git+https://github.com/Oscarsb2004/athena-kit@v0.1.1"
python -m athena.ingest . wdi-bulk wgi-bulk        # from the project's folder: its sources, its lock
python -m athena.components check .                # the project's component manifest against its code
```

A project's `sources.toml` lists each source with its `url`, `kind`, `edition` and `terms`; its `sources.lock` is
written on first use and committed.

## The component standard

New code is written as components. A component is a class with:
- a `section`;
- frozen `Input` and `Output` dataclasses;
- one `run(inp) -> Output`, and no hidden I/O;
- a synthetic test with a negative control.

Working code written before the standard is listed as `legacy` in the project's manifest, with its inputs and
outputs. See `athena/component.py`.

## Licence

**PolyForm Noncommercial License 1.0.0** ([LICENSE.md](LICENSE.md)). You may run, study and change this software
for any non-commercial purpose. Commercial use needs the author's permission. See [NOTICE](NOTICE).

The data each adapter reads keeps its publisher's licence: a project reads and dates those terms before use.

Copied from athena-core at commit `3d0af72` (2026-10-20), whose history holds these files' earlier changes.
