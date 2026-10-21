"""athena.ingest: a project's own sources and lock, the kinds, and what a project may add. No publisher content is
used. Each rule has a negative control."""

import pytest

import fixtures
from athena import dataset
from athena.fetch import SourceChanged
from athena.ingest import Ingest, Project, Result
from athena.table import table


def project(tmp_path, body: str) -> Project:
    (tmp_path / "sources.toml").write_text(body, encoding="utf-8")
    return Project(tmp_path)


def toy(src, get):
    """A project's own kind: one value per byte of the source."""
    data = get(src["url"])
    rows = [{"DATASET": "toy-1", "SERIES": "s", "REF_AREA": "AAA", "TIME_PERIOD": str(2000 + i),
             "OBS_VALUE": float(b), "EDITION": "1", "DERIVED": False} for i, b in enumerate(data)]
    return Result("toy-1", {"values": table(rows)}, [f"toy-1: {len(rows)} values"])


def test_a_project_kind_is_run_through_the_projects_own_lock(tmp_path):
    p = project(tmp_path, '[toy]\nurl = "https://example.org/t"\nkind = "toy"\n')
    out = Ingest({"toy": toy}, fixtures.Session({"https://example.org/t": b"\x01\x02"}), tmp_path / "ds").run(
        Ingest.Input(p, "toy"))
    assert out.name == "toy-1" and len(dataset.load("toy-1", root=tmp_path / "ds")) == 2
    assert "https://example.org/t" in (tmp_path / "sources.lock").read_text()


def test_changed_bytes_are_refused_by_the_lock(tmp_path):
    p = project(tmp_path, '[toy]\nurl = "https://example.org/t"\nkind = "toy"\n')
    Ingest({"toy": toy}, fixtures.Session({"https://example.org/t": b"\x01"}), tmp_path / "ds").run(Ingest.Input(p, "toy"))
    with pytest.raises(SourceChanged):  # negative control: the same address, other bytes
        Ingest({"toy": toy}, fixtures.Session({"https://example.org/t": b"\x09"}), tmp_path / "ds").run(
            Ingest.Input(p, "toy"))


def test_an_unknown_kind_or_key_stops_with_its_name(tmp_path):
    p = project(tmp_path, '[odd]\nurl = "https://example.org/o"\nkind = "unheard-of"\n')
    with pytest.raises(ValueError, match="no adapter for kind 'unheard-of'"):
        Ingest().run(Ingest.Input(p, "odd"))
    with pytest.raises(KeyError, match="'missing' is not in"):
        p.source("missing")
