"""Figure shells: one series in, one figure out (P54). No shell names a subject (P38).

The input is one series from the common format: OBS_VALUE indexed by TIME_PERIOD, for one area. Missing values are
dropped and the periods sorted before a shell sees them. The output is a figure record:

    value    the figure, or None when the series cannot give it
    period   the period it describes: "2024", or "2022/2024" for a window (SDMX's range form)
    n        how many observations it used (P46: every figure carries its count)

`extremes` adds `values` (a list of {value, period}) and `trend` adds `periods` and `values`. A window is the last k
observations, so a gap in the data shows in the period range rather than being filled. Nothing is imputed.
"""

from __future__ import annotations

import math
import statistics

import pandas as pd

EMPTY = {"value": None, "period": None, "n": 0}


def prepare(series: pd.Series) -> pd.Series:
    """Values indexed by period: missing values dropped, sorted by period."""
    return series.dropna().sort_index()


def _window(s: pd.Series, k: int) -> pd.Series:
    if k < 1:
        raise ValueError("a window needs at least one period")
    return s.iloc[-k:]


def _range(s: pd.Series) -> str:
    return s.index[0] if len(s) == 1 else f"{s.index[0]}/{s.index[-1]}"


def latest(s: pd.Series) -> dict:
    """The most recent value."""
    if s.empty:
        return dict(EMPTY)
    return {"value": float(s.iloc[-1]), "period": s.index[-1], "n": 1}


def first(s: pd.Series) -> dict:
    """The earliest value: with a binding's `where`, the first year of a publisher's projections."""
    if s.empty:
        return dict(EMPTY)
    return {"value": float(s.iloc[0]), "period": s.index[0], "n": 1}


def mean(s: pd.Series, k: int) -> dict:
    """The mean of the last k observations. Fewer than k gives no value."""
    w = _window(s, k)
    if len(w) < k:
        return EMPTY | {"n": len(w)}
    return {"value": math.fsum(w) / k, "period": _range(w), "n": k}


def spread(s: pd.Series, k: int) -> dict:
    """The sample standard deviation of the last k observations. Fewer than k, or k < 2, gives no value."""
    w = _window(s, k)
    if k < 2 or len(w) < k:
        return EMPTY | {"n": len(w)}
    return {"value": statistics.stdev(w.tolist()), "period": _range(w), "n": k}


def change(s: pd.Series, k: int) -> dict:
    """The latest value less the value k observations before it."""
    if len(s) <= k:
        return EMPTY | {"n": len(s)}
    w = s.iloc[-k - 1:]
    return {"value": float(w.iloc[-1] - w.iloc[0]), "period": _range(w), "n": 2}


def growth(s: pd.Series, k: int) -> dict:
    """Compound growth per period over the last k periods, in percent. Needs positive values at both ends."""
    if len(s) <= k:
        return EMPTY | {"n": len(s)}
    w = s.iloc[-k - 1:]
    first, last = float(w.iloc[0]), float(w.iloc[-1])
    if first <= 0 or last <= 0:
        return EMPTY | {"n": 2}
    return {"value": ((last / first) ** (1 / k) - 1) * 100, "period": _range(w), "n": 2}


def _positions(periods: pd.Index) -> list[int]:
    """Years where every period is a year, otherwise the order of observation."""
    if all(isinstance(p, str) and len(p) == 4 and p.isdigit() for p in periods):
        return [int(p) for p in periods]
    return list(range(len(periods)))


def extremes(s: pd.Series, k: int = 3, gap: int = 1, highest: bool = True) -> dict:
    """The k highest (or lowest) values, each at least `gap` periods from any chosen before it, so one long episode
    counts once. Ties go to the earlier period. `n` is how many observations were searched."""
    if s.empty:
        return dict(EMPTY) | {"values": []}
    where = dict(zip(s.index, _positions(s.index)))
    order = sorted(s.items(), key=lambda item: (-item[1] if highest else item[1], where[item[0]]))
    chosen: list[tuple[str, float]] = []
    for period, value in order:
        if all(abs(where[period] - where[p]) >= gap for p, _ in chosen):
            chosen.append((period, float(value)))
        if len(chosen) == k:
            break
    return {"value": chosen[0][1], "period": chosen[0][0], "n": len(s), "searched": _range(s),
            "values": [{"value": v, "period": p} for p, v in chosen]}


def trend(s: pd.Series, since: str | None = None) -> dict:
    """The series itself, from `since` on, for a small chart."""
    w = s[s.index >= since] if since else s
    if w.empty:
        return dict(EMPTY) | {"periods": [], "values": []}
    return {"value": float(w.iloc[-1]), "period": _range(w), "n": len(w),
            "periods": list(w.index), "values": [float(v) for v in w]}


SHELLS = {f.__name__: f for f in (latest, first, mean, spread, change, growth, extremes, trend)}
