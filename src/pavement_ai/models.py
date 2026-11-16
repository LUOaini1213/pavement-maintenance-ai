"""Forecasting methods: naive baselines, a Markov chain on condition states, and gradient boosting.

Every method predicts the value at the target visit of a pair (see data.make_pairs). The two own-history trend
baselines (linear, exponential) are already columns of the pairs; the methods here need fitting on training pairs.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

NUMERIC_FEATURES = ["y0", "h", "hist_slope", "n_hist", "hist_span", "age0", "seg_overlay_mm", "ac_mm",
                    "unbound_base_mm", "bound_base_mm", "pcc_mm", "kesal", "aadtt", "precip_mm", "temp_c",
                    "freeze_index", "freeze_thaw", "days_above_32c"]
EVENT_LEVELS = ["original", "seal", "thin_overlay", "medium_overlay", "thick_overlay", "overlay_unknown"]
HGB_PARAMS = dict(max_iter=300, learning_rate=0.05, max_leaf_nodes=31, min_samples_leaf=40, l2_regularization=1.0,
                  random_state=0)


class GlobalRate:
    """Last value plus one network-wide annual rate (the median rate of the training pairs)."""

    def fit(self, pairs: pd.DataFrame) -> "GlobalRate":
        self.rate_ = float(np.median((pairs["y1"] - pairs["y0"]) / pairs["h"])) if len(pairs) else 0.0
        return self

    def predict(self, pairs: pd.DataFrame) -> np.ndarray:
        return (pairs["y0"] + self.rate_ * pairs["h"]).to_numpy(dtype=float)


class MarkovChain:
    """Homogeneous Markov chain on condition states with a one-year step.

    States are the intervals between `edges`. The transition matrix is counted from training pairs whose horizon
    is about one year; a state never seen as an origin keeps itself. The forecast for h years is the expected
    state value after round(h) steps (at least one step).
    """

    def __init__(self, edges, year_window=(0.75, 1.25)):
        self.edges = np.asarray(edges, dtype=float)
        self.year_window = year_window

    def state(self, y) -> np.ndarray:
        return np.searchsorted(self.edges, np.asarray(y, dtype=float), side="right")

    def fit(self, pairs: pd.DataFrame) -> "MarkovChain":
        k = len(self.edges) + 1
        one = pairs[(pairs["h"] >= self.year_window[0]) & (pairs["h"] <= self.year_window[1])]
        counts = np.zeros((k, k))
        np.add.at(counts, (self.state(one["y0"]), self.state(one["y1"])), 1.0)
        self.counts_ = counts
        row = counts.sum(axis=1, keepdims=True)
        self.P_ = np.where(row > 0, counts / np.where(row > 0, row, 1.0), np.eye(k))
        mids = np.concatenate([[self.edges[0]], (self.edges[:-1] + self.edges[1:]) / 2.0, [self.edges[-1]]])
        values = np.concatenate([pairs["y0"].to_numpy(dtype=float), pairs["y1"].to_numpy(dtype=float)])
        st = self.state(values)
        self.means_ = np.array([values[st == s].mean() if (st == s).any() else mids[s] for s in range(k)])
        return self

    def predict(self, pairs: pd.DataFrame) -> np.ndarray:
        s0 = self.state(pairs["y0"])
        steps = np.maximum(1, np.rint(pairs["h"].to_numpy(dtype=float)).astype(int))
        out = np.empty(len(pairs))
        for n in np.unique(steps):
            ev = np.linalg.matrix_power(self.P_, int(n)) @ self.means_
            m = steps == n
            out[m] = ev[s0[m]]
        return out


def feature_frame(pairs: pd.DataFrame, extra: list[str]) -> pd.DataFrame:
    """Model inputs. Missing values stay NaN (the boosting model handles them natively)."""
    cols = [c for c in NUMERIC_FEATURES + list(extra) if c in pairs.columns]
    X = pairs[cols].astype(float).copy()
    codes = pd.Categorical(pairs["seg_event"], categories=EVENT_LEVELS).codes.astype(float)
    X["event_code"] = np.where(codes < 0, np.nan, codes)
    X["on_pcc"] = pairs["family"].astype(str).str.endswith("PCC").to_numpy(dtype=float)
    return X


class BoostedIncrement:
    """Gradient boosting (scikit-learn HistGradientBoostingRegressor) on the increment y1 - y0."""

    def __init__(self, extra_features: list[str] | None = None, lo: float = -np.inf, hi: float = np.inf, **params):
        self.extra = list(extra_features or [])
        self.lo, self.hi = lo, hi
        self.params = {**HGB_PARAMS, **params}

    def fit(self, pairs: pd.DataFrame) -> "BoostedIncrement":
        X = feature_frame(pairs, self.extra)
        self.columns_ = list(X.columns)
        cat = [c == "event_code" for c in self.columns_]
        self.model_ = HistGradientBoostingRegressor(categorical_features=cat, **self.params)
        self.model_.fit(X.to_numpy(), (pairs["y1"] - pairs["y0"]).to_numpy(dtype=float))
        return self

    def predict(self, pairs: pd.DataFrame) -> np.ndarray:
        X = feature_frame(pairs, self.extra)[self.columns_].to_numpy()
        return np.clip(pairs["y0"].to_numpy(dtype=float) + self.model_.predict(X), self.lo, self.hi)
