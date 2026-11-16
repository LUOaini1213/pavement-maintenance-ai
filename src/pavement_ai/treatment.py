"""Before/after effect of recorded treatments on one indicator.

For every surface-renewing event the last measurement on the old surface (at most `max_pre` years before the event)
is compared with the first measurement on the new surface (at most `max_post` years after it). Deterioration rates
are least-squares slopes of the measurements on each surface.

These are observational before/after differences, not causal effects: agencies choose what to treat and when, the
"before" value is taken at a high point (regression to the mean), and some deterioration happens between the last
"before" visit and the event.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .data import ols_line, segments, series
from .events import ORIGINAL

CLASSES = ["seal", "thin_overlay", "medium_overlay", "thick_overlay"]


def segment_rate(t: np.ndarray, y: np.ndarray, min_obs: int = 3, min_span: float = 2.0) -> float:
    """Least-squares slope per year, NaN when the segment is too short to carry one."""
    if len(t) < min_obs or (t.max() - t.min()) < min_span:
        return float("nan")
    return ols_line(t, y)[1]


def event_table(data: dict, indicator: str, max_pre: float = 3.0, max_post: float = 2.0) -> pd.DataFrame:
    ser = series(data, indicator)
    seg = segments(data["periods"], data["sections"])
    starts = seg[(seg["event"] == seg["seg_event"]) & (seg["event"] != ORIGINAL)]
    starts = starts.drop_duplicates(["section_id", "seg"])
    by = {key: g for key, g in ser.groupby(["section_id", "seg"], sort=False)}
    site = data["sections"].set_index("section_id")["site_id"]
    exper = data["sections"].set_index("section_id")
    rows = []
    for r in starts.itertuples(index=False):
        before = by.get((r.section_id, r.seg - 1))
        after = by.get((r.section_id, r.seg))
        if before is None or after is None:
            continue
        tb, yb = before["t"].to_numpy(), before["y"].to_numpy()
        ta, ya = after["t"].to_numpy(), after["y"].to_numpy()
        t_event = r.t_start
        if not np.isfinite(t_event) or t_event - tb[-1] > max_pre or ta[0] - t_event > max_post:
            continue
        rows.append({"section_id": r.section_id, "site_id": site[r.section_id], "event": r.event,
                     "overlay_mm": r.overlay_mm, "t_event": t_event, "pre": yb[-1], "post": ya[0],
                     "drop": yb[-1] - ya[0], "pre_rate": segment_rate(tb, yb), "post_rate": segment_rate(ta, ya),
                     "designed": bool(exper.at[r.section_id, "gps_sps"] == "S"
                                      and exper.at[r.section_id, "experiment"] in ("3", "5"))})
    return pd.DataFrame(rows)


def _boot_mean(values: np.ndarray, groups: np.ndarray, n_boot: int, seed: int) -> tuple[float, float]:
    codes, _ = pd.factorize(groups)
    g = int(codes.max()) + 1
    s = np.bincount(codes, weights=values, minlength=g)
    n = np.bincount(codes, minlength=g).astype(float)
    idx = np.random.default_rng(seed).integers(0, g, size=(n_boot, g))
    m = s[idx].sum(axis=1) / n[idx].sum(axis=1)
    return float(np.quantile(m, 0.025)), float(np.quantile(m, 0.975))


def summarise(events: pd.DataFrame, n_boot: int = 1000, seed: int = 0) -> dict:
    out = {}
    for cls in CLASSES:
        e = events[events["event"] == cls]
        if len(e) < 5:
            continue
        lo, hi = _boot_mean(e["drop"].to_numpy(), e["site_id"].to_numpy(), n_boot, seed)
        a, b = ols_line(e["pre"].to_numpy(), e["post"].to_numpy())
        both = e.dropna(subset=["pre_rate", "post_rate"])
        res = {
            "n_events": int(len(e)), "n_sites": int(e["site_id"].nunique()),
            "share_designed_experiment": float(e["designed"].mean()),
            "median_overlay_mm": float(e["overlay_mm"].median()) if cls != "seal" and e["overlay_mm"].notna().any() else None,
            "pre_median": float(e["pre"].median()), "post_median": float(e["post"].median()),
            "drop_mean": float(e["drop"].mean()), "drop_lo": lo, "drop_hi": hi,
            "drop_median": float(e["drop"].median()),
            "post_fit_intercept": a, "post_fit_slope": b,
            "n_with_rates": int(len(both)),
        }
        if len(both) >= 5:
            d = (both["post_rate"] - both["pre_rate"]).to_numpy()
            rlo, rhi = _boot_mean(d, both["site_id"].to_numpy(), n_boot, seed)
            res.update({"pre_rate_median": float(both["pre_rate"].median()),
                        "post_rate_median": float(both["post_rate"].median()),
                        "rate_change_mean": float(d.mean()), "rate_change_lo": rlo, "rate_change_hi": rhi})
        post_only = e.dropna(subset=["post_rate"])
        res["post_rate_median_all"] = float(post_only["post_rate"].median()) if len(post_only) else None
        res["n_post_rate"] = int(len(post_only))
        out[cls] = res
    return out
