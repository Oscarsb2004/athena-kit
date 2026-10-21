"""The generic parts: fetch and the common format. Each check has a negative control. (Aggregation and the
comparison with publishers moved to the MDG project, their only user, on 2026-10-19.)"""

import hashlib

import numpy as np
import pandas as pd
import pandera.errors
import pytest

from athena.fetch import Fetcher, SourceChanged
from athena.table import canonical_hash, round_half_up, table
from fixtures import Session

ROW = {"DATASET": "d", "SERIES": "x", "REF_AREA": "AAA", "TIME_PERIOD": "2015", "OBS_VALUE": 1.5,
       "UNIT_MEASURE": "percent", "EDITION": "e", "DERIVED": True}


# ── fetch ───────────────────────────────────────────────────────────────────────────────────────────────────

def test_a_first_fetch_is_locked_and_a_changed_source_is_refused(tmp_path):
    lock = tmp_path / "sources.lock"
    Fetcher(lock, Session({"u": b"one"})).get("u")
    assert Fetcher(lock, Session({"u": b"one"})).get("u") == b"one"
    assert hashlib.sha256(b"one").hexdigest() in lock.read_text()
    with pytest.raises(SourceChanged, match="the lock says"):
        Fetcher(lock, Session({"u": b"two"})).get("u")


# ── the common format ───────────────────────────────────────────────────────────────────────────────────────

def test_the_format_accepts_a_valid_row_and_sorts_by_key():
    frame = table([ROW | {"REF_AREA": "BBB"}, ROW])
    assert list(frame["REF_AREA"]) == ["AAA", "BBB"]


@pytest.mark.parametrize("bad", [ROW | {"EXTRA": 1}, ROW | {"OBS_VALUE": np.inf}])
def test_the_format_refuses_an_unknown_column_and_an_infinite_value(bad):
    with pytest.raises((pandera.errors.SchemaError, pandera.errors.SchemaErrors)):
        table([bad])


def test_the_format_refuses_a_key_twice():
    with pytest.raises(pandera.errors.SchemaError):
        table([ROW, ROW])


def test_the_hash_ignores_row_order_and_the_sign_of_zero():
    a = table([ROW, ROW | {"REF_AREA": "BBB", "OBS_VALUE": 0.0}])
    b = table([ROW | {"REF_AREA": "BBB", "OBS_VALUE": -0.0}, ROW])
    assert canonical_hash(a) == canonical_hash(b)
    assert canonical_hash(a) != canonical_hash(table([ROW | {"OBS_VALUE": 1.5000001}, ROW | {"REF_AREA": "BBB"}]))


# ── rounding and comparison ─────────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("value, decimals, expected",
                         [(2.25, 1, 2.3), (-2.25, 1, -2.3), (0.125, 2, 0.13), (22.14951, 1, 22.1), (26.35, 1, 26.4)])
def test_half_up_on_the_number_as_written(value, decimals, expected):
    assert round_half_up(value, decimals) == expected
