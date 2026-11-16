"""Leakage-free evaluation: site-grouped folds, an optional time cut, and site-cluster bootstrap intervals."""
from __future__ import annotations

import zlib

import numpy as np
import pandas as pd


def fold_of(site_id: str, k: int = 5) -> int:
    """Deterministic fold of a site (state + project), identical on every platform."""
    return zlib.crc32(str(site_id).encode("utf-8")) % k


def split(pairs: pd.DataFrame, fold: int, k: int = 5, cutoff: float | None = None) -> tuple[np.ndarray, np.ndarray]:
    """Boolean masks (train, test).

    Sites of the test fold never appear in training. With `cutoff` (a decimal year) training pairs must END before
    it and test pairs must START at or after it, so the model is also tested forward in time.
    """
    f = pairs["site_id"].map(lambda s: fold_of(s, k)).to_numpy()
    train = f != fold
    test = f == fold
    if cutoff is not None:
        train = train & (pairs["t1"].to_numpy() < cutoff)
        test = test & (pairs["t0"].to_numpy() >= cutoff)
    return train, test


def mae(err) -> float:
    return float(np.mean(np.abs(err)))


def rmse(err) -> float:
    return float(np.sqrt(np.mean(np.square(err))))


def cluster_bootstrap(errors: dict, groups, n_boot: int = 1000, seed: int = 0, level: float = 0.95) -> dict:
    """MAE and RMSE of each method with percentile intervals from resampling whole sites with replacement.

    Also returns, for every pair of methods (a, b), the interval of MAE(a) - MAE(b) on the same resamples.
    """
    names = list(errors)
    codes, _ = pd.factorize(np.asarray(groups))
    g = int(codes.max()) + 1
    n = np.bincount(codes, minlength=g).astype(float)
    abs_sum = np.stack([np.bincount(codes, weights=np.abs(errors[m]), minlength=g) for m in names], axis=1)
    sq_sum = np.stack([np.bincount(codes, weights=np.square(errors[m]), minlength=g) for m in names], axis=1)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, g, size=(n_boot, g))
    nb = n[idx].sum(axis=1)
    mae_b = abs_sum[idx].sum(axis=1) / nb[:, None]
    rmse_b = np.sqrt(sq_sum[idx].sum(axis=1) / nb[:, None])
    a = (1.0 - level) / 2.0
    out = {"n_pairs": int(n.sum()), "n_sites": g, "methods": {}, "mae_diff": {}}
    for j, m in enumerate(names):
        out["methods"][m] = {
            "mae": mae(errors[m]), "mae_lo": float(np.quantile(mae_b[:, j], a)),
            "mae_hi": float(np.quantile(mae_b[:, j], 1 - a)),
            "rmse": rmse(errors[m]), "rmse_lo": float(np.quantile(rmse_b[:, j], a)),
            "rmse_hi": float(np.quantile(rmse_b[:, j], 1 - a)),
        }
    for i, mi in enumerate(names):
        for j, mj in enumerate(names):
            if i < j:
                d = mae_b[:, i] - mae_b[:, j]
                out["mae_diff"][f"{mi}-{mj}"] = {"diff": mae(errors[mi]) - mae(errors[mj]),
                                                 "lo": float(np.quantile(d, a)), "hi": float(np.quantile(d, 1 - a))}
    return out
