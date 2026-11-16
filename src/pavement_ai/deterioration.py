"""Part A: compare forecasting methods for one indicator under leakage-free validation."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .data import INDICATORS
from .models import BoostedIncrement, GlobalRate, MarkovChain
from .validation import cluster_bootstrap, split

BASELINES = ["last", "linear", "exponential", "global_rate", "markov"]
ML = "gbm"
HORIZON_BINS = {"h_0.5_2": (0.5, 2.0), "h_2_5": (2.0, 5.0)}


def extra_features(indicator: str) -> list[str]:
    return [f"{k}_0" for k in INDICATORS if k != indicator]


def out_of_fold(pairs: pd.DataFrame, indicator: str, k: int = 5, cutoff: float | None = None,
                gbm_params: dict | None = None) -> tuple[dict, np.ndarray, list]:
    """Predictions of every method for the test pairs of each fold. Returns (predictions, tested mask, fold sizes)."""
    spec = INDICATORS[indicator]
    preds = {m: np.full(len(pairs), np.nan) for m in BASELINES + [ML]}
    tested = np.zeros(len(pairs), dtype=bool)
    sizes = []
    for fold in range(k):
        tr, te = split(pairs, fold, k, cutoff)
        if te.sum() == 0 or tr.sum() == 0:
            continue
        train, test = pairs[tr], pairs[te]
        preds["last"][te] = test["pred_last"].to_numpy()
        preds["linear"][te] = test["pred_linear"].to_numpy()
        preds["exponential"][te] = test["pred_exp"].to_numpy()
        preds["global_rate"][te] = np.clip(GlobalRate().fit(train).predict(test), spec["lo"], spec["hi"])
        preds["markov"][te] = MarkovChain(spec["edges"]).fit(train).predict(test)
        gbm = BoostedIncrement(extra_features(indicator), spec["lo"], spec["hi"], **(gbm_params or {}))
        preds[ML][te] = gbm.fit(train).predict(test)
        tested |= te
        sizes.append({"fold": fold, "train_pairs": int(tr.sum()), "test_pairs": int(te.sum()),
                      "train_sites": int(train["site_id"].nunique()), "test_sites": int(test["site_id"].nunique())})
    return preds, tested, sizes


def summarise(pairs: pd.DataFrame, preds: dict, tested: np.ndarray, n_boot: int = 1000, seed: int = 0) -> dict:
    """Errors with site-cluster bootstrap intervals, overall and by horizon; names the best baseline."""
    y = pairs["y1"].to_numpy()
    site = pairs["site_id"].to_numpy()
    h = pairs["h"].to_numpy()

    def block(mask: np.ndarray) -> dict:
        errors = {m: preds[m][mask] - y[mask] for m in preds}
        res = cluster_bootstrap(errors, site[mask], n_boot=n_boot, seed=seed)
        best = min(BASELINES, key=lambda m: res["methods"][m]["mae"])
        key = f"{best}-{ML}" if f"{best}-{ML}" in res["mae_diff"] else None
        d = res["mae_diff"][key]
        gain = {"diff": -d["diff"], "lo": -d["hi"], "hi": -d["lo"]}          # MAE(gbm) - MAE(best baseline)
        res["best_baseline"] = best
        res["gbm_minus_best_baseline_mae"] = gain
        res["gbm_mae_change_pct"] = 100.0 * gain["diff"] / res["methods"][best]["mae"]
        res["gbm_beats_best_baseline"] = bool(gain["hi"] < 0.0)
        res["mae_diff"] = {k: v for k, v in res["mae_diff"].items() if k.endswith("-" + ML)}
        return res

    out = {"all": block(tested)}
    for name, (lo, hi) in HORIZON_BINS.items():
        m = tested & (h > lo if lo > 0.5 else h >= lo) & (h <= hi)
        if m.sum() > 0:
            out[name] = block(m)
    return out


def evaluate(pairs: pd.DataFrame, indicator: str, k: int = 5, cutoff: float | None = None, n_boot: int = 1000,
             seed: int = 0, gbm_params: dict | None = None) -> dict:
    preds, tested, sizes = out_of_fold(pairs, indicator, k, cutoff, gbm_params)
    res = summarise(pairs, preds, tested, n_boot, seed)
    res["folds"] = sizes
    res["test_sections"] = int(pairs.loc[tested, "section_id"].nunique())
    return res
