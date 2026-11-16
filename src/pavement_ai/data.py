"""Load the committed LTPP extracts and turn them into forecasting pairs.

A *segment* is the life of one surface: it starts at the original construction or at an event that renews the
surface (seal coat or overlay, see events.py) and ends at the next such event. Routine work (crack sealing,
patching) does not start a new segment. A *pair* is (origin visit, later visit) inside one segment, so nothing a
model is asked to predict straddles a treatment.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from .events import ORIGINAL, RESETTING

REPO = Path(__file__).resolve().parents[2]
DERIVED = REPO / "data" / "derived"

# value column, physical clipping range for predictions, offset used by the exponential-trend baseline
INDICATORS = {
    "iri": {"file": "iri.csv", "col": "iri", "unit": "m/km", "lo": 0.3, "hi": 10.0, "log_offset": 0.0,
            "edges": [0.75, 1.0, 1.25, 1.5, 2.0, 2.7]},
    "rut": {"file": "rut.csv", "col": "rut_mm", "unit": "mm", "lo": 0.0, "hi": 40.0, "log_offset": 1.0,
            "edges": [2.5, 4.5, 6.5, 9.5, 14.5]},
    "crack": {"file": "crack.csv", "col": "crack_pct", "unit": "%", "lo": 0.0, "hi": 100.0, "log_offset": 1.0,
              "edges": [0.5, 5.0, 10.0, 20.0, 35.0]},
}
NEW_BUILD_SPS = {"1", "2", "8", "9N"}      # SPS experiments whose first construction number is the build itself


def decimal_year(dates) -> np.ndarray:
    d = pd.to_datetime(pd.Series(dates))
    return (d.dt.year + (d.dt.dayofyear - 1) / 365.25).to_numpy(dtype=float)


def load(derived: Path = DERIVED) -> dict:
    out = {name: pd.read_csv(derived / f"{name}.csv", dtype={"section_id": str, "site_id": str, "experiment": str,
                                                              "work_codes": str})
           for name in ["sections", "periods", "iri", "rut", "crack", "traffic"]}
    return out


def segments(periods: pd.DataFrame, sections: pd.DataFrame) -> pd.DataFrame:
    """One row per (section_id, cn) with the segment it belongs to and that segment's start and opening event."""
    p = periods.sort_values(["section_id", "cn"]).reset_index(drop=True).copy()
    p["t_start"] = decimal_year(p["start"])
    resets = p["event"].isin(RESETTING)
    p["seg"] = resets.groupby(p["section_id"]).cumsum().astype("int64")
    first = p[resets].set_index(["section_id", "seg"])
    sec = sections.set_index("section_id")
    opened = pd.Series(decimal_year(sec["opened"]), index=sec.index)
    new_build = (sec["gps_sps"] == "S") & sec["experiment"].isin(NEW_BUILD_SPS)
    seg_event, seg_start, seg_overlay = [], [], []
    for sid, seg in zip(p["section_id"], p["seg"]):
        row = first.loc[(sid, seg)]
        ev = row["event"]
        start = row["t_start"]
        if ev == ORIGINAL:
            if sid in opened.index and np.isfinite(opened[sid]):
                start = opened[sid]
            elif not (sid in new_build.index and bool(new_build[sid])):
                start = np.nan                      # monitoring start, not construction: age unknown
        seg_event.append(ev)
        seg_start.append(start)
        seg_overlay.append(row["overlay_mm"])
    p["seg_event"], p["seg_start"], p["seg_overlay_mm"] = seg_event, seg_start, seg_overlay
    return p


def series(data: dict, indicator: str) -> pd.DataFrame:
    """Observations of one indicator with segment, structure and site attributes attached."""
    spec = INDICATORS[indicator]
    obs = data[indicator][["section_id", "date", "cn", spec["col"]]].rename(columns={spec["col"]: "y"}).copy()
    obs["t"] = decimal_year(obs["date"])
    seg = segments(data["periods"], data["sections"])
    keep = ["section_id", "cn", "seg", "seg_event", "seg_start", "seg_overlay_mm", "family", "ac_mm",
            "unbound_base_mm", "bound_base_mm", "pcc_mm"]
    out = obs.merge(seg[keep], on=["section_id", "cn"], how="inner")
    out = out.merge(data["sections"].drop(columns=["opened", "lat", "lon"]), on="section_id", how="left")
    out["age"] = out["t"] - out["seg_start"]
    out.loc[out["age"] < 0, "age"] = np.nan
    return out.sort_values(["section_id", "t"]).reset_index(drop=True)


def ols_line(t: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    """Least-squares intercept and slope of y on t (slope 0 when all t are equal)."""
    t = np.asarray(t, dtype=float)
    y = np.asarray(y, dtype=float)
    tm, ym = t.mean(), y.mean()
    sxx = float(((t - tm) ** 2).sum())
    if sxx <= 0.0:
        return float(ym), 0.0
    b = float(((t - tm) * (y - ym)).sum() / sxx)
    return float(ym - b * tm), b


def make_pairs(ser: pd.DataFrame, indicator: str, min_h: float = 0.5, max_h: float = 5.0,
               min_span: float = 1.0) -> pd.DataFrame:
    """All (origin, target) pairs inside a segment with min_h <= horizon <= max_h years.

    The own-history trend predictions use only visits up to and including the origin.
    """
    spec = INDICATORS[indicator]
    off, lo, hi = spec["log_offset"], spec["lo"], spec["hi"]
    static = [c for c in ser.columns if c not in ("date", "cn", "y", "t", "age")]
    rows = []
    for (_sid, _seg), g in ser.groupby(["section_id", "seg"], sort=False):
        t = g["t"].to_numpy()
        y = g["y"].to_numpy()
        age = g["age"].to_numpy()
        base = g.iloc[0][static].to_dict()
        for i in range(len(t)):
            n_hist = i + 1
            span = t[i] - t[0]
            has_trend = n_hist >= 2 and span >= min_span
            if has_trend:
                a, b = ols_line(t[:n_hist], y[:n_hist])
                al, bl = ols_line(t[:n_hist], np.log(y[:n_hist] + off + 1e-9))
            for j in range(i + 1, len(t)):
                h = t[j] - t[i]
                if h < min_h:
                    continue
                if h > max_h:
                    break
                if has_trend:
                    p_lin = a + b * t[j]
                    p_exp = float(np.exp(min(al + bl * t[j], 50.0)) - off)
                    slope = b
                else:
                    p_lin = p_exp = y[i]
                    slope = np.nan
                rows.append({**base, "t0": t[i], "t1": t[j], "h": h, "y0": y[i], "y1": y[j], "age0": age[i],
                             "n_hist": n_hist, "hist_span": span, "hist_slope": slope,
                             "pred_last": y[i], "pred_linear": float(np.clip(p_lin, lo, hi)),
                             "pred_exp": float(np.clip(p_exp, lo, hi))})
    return pd.DataFrame(rows)


def add_asof(pairs: pd.DataFrame, other: pd.DataFrame, name: str, tolerance: float = 2.0) -> pd.DataFrame:
    """Attach the latest value of another indicator measured at or before t0 (same section and segment)."""
    left = pairs[["section_id", "seg", "t0"]].copy()
    left["_row"] = np.arange(len(left))
    right = other[["section_id", "seg", "t", "y"]].rename(columns={"y": name})
    left = left.sort_values("t0")
    right = right.sort_values("t")
    m = pd.merge_asof(left, right, left_on="t0", right_on="t", by=["section_id", "seg"], direction="backward",
                      tolerance=tolerance)
    out = pairs.copy()
    out[name] = m.sort_values("_row")[name].to_numpy()
    return out


def add_traffic(pairs: pd.DataFrame, traffic: pd.DataFrame) -> pd.DataFrame:
    """Mean annual kESAL and truck AADT of the LTPP lane over the years up to the origin year (no look-ahead)."""
    tr = traffic.sort_values(["section_id", "year"]).copy()
    tr["year"] = tr["year"].astype("int64")
    for c in ["kesal", "aadtt"]:
        tr[c + "_mean"] = tr.groupby("section_id")[c].transform(lambda s: s.expanding().mean())
    left = pairs[["section_id", "t0"]].copy()
    left["_row"] = np.arange(len(left))
    left["year"] = np.floor(left["t0"]).astype("int64")
    m = pd.merge_asof(left.sort_values("year"), tr[["section_id", "year", "kesal_mean", "aadtt_mean"]].sort_values("year"),
                      on="year", by="section_id", direction="backward")
    m = m.sort_values("_row")
    out = pairs.copy()
    out["kesal"] = m["kesal_mean"].to_numpy()
    out["aadtt"] = m["aadtt_mean"].to_numpy()
    return out


def build_dataset(data: dict, indicator: str, **kw) -> pd.DataFrame:
    """Pairs of one indicator with the other indicators and traffic attached as features."""
    sers = {k: series(data, k) for k in INDICATORS}
    pairs = make_pairs(sers[indicator], indicator, **kw)
    for other in INDICATORS:
        if other != indicator:
            pairs = add_asof(pairs, sers[other], f"{other}_0")
    return add_traffic(pairs, data["traffic"])
