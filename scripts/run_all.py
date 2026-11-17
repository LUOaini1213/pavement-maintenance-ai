"""Recompute results/*.json and the figures from the committed extracts in data/derived/.

    python scripts/run_all.py                 # everything (the method comparison takes a while: 70 model fits)
    python scripts/run_all.py opt china       # only some parts: data, det, te, china, opt, fig

Then run scripts/make_report.py to rebuild README.md and docs/brief.md from the results.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from pavement_ai import config, events, pipeline  # noqa: E402
from pavement_ai import data as D  # noqa: E402

RESULTS = REPO / "results"


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def read(name: str) -> dict:
    return json.loads((RESULTS / f"{name}.json").read_text(encoding="utf-8"))


def write_optimisation(opt: dict) -> None:
    """The section list and the base plan go to results/detail/ (kept out of the pool the README numbers are
    checked against, which is results/*.json)."""
    detail = {"network_sections": opt.pop("network_sections"), "base_mip_plan": opt.pop("base_mip_plan")}
    pipeline.write_json("optimisation", opt)
    pipeline.write_json("base_plan", detail, RESULTS / "detail")


def figures() -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    (RESULTS / "figures").mkdir(parents=True, exist_ok=True)
    opt, det = read("optimisation"), read("deterioration")
    fig, ax = plt.subplots(1, 2, figsize=(10, 3.8))
    x = [100 * s["budget_share"] for s in opt["sweep"]]
    for key, label, style in (("mip", "MIP (HiGHS)", "o-"), ("worst_first", "worst-first rule", "s--"),
                              ("fixed_cycle", "fixed-cycle rule", "^:")):
        ax[0].plot(x, [s[key]["mean_iri_final"] for s in opt["sweep"]], style, label=label)
        ax[1].plot(x, [s[key]["iri_years_saved"] for s in opt["sweep"]], style, label=label)
    ax[0].set_ylabel("network mean IRI after 5 years (m/km)")
    ax[1].set_ylabel("IRI-years saved vs doing nothing (m/km x lane-km x yr)")
    for a in ax:
        a.set_xlabel("annual budget (% of the cost of resurfacing the whole network)")
        a.grid(alpha=0.3)
        a.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(RESULTS / "figures" / "budget_tradeoff.png", dpi=130)
    plt.close(fig)

    fig, ax = plt.subplots(1, 3, figsize=(11, 3.6))
    for a, ind in zip(ax, D.INDICATORS):
        block = det[ind]["grouped_forward"]["all"]["methods"]
        names = list(block)
        vals = [block[m]["mae"] for m in names]
        err = [[block[m]["mae"] - block[m]["mae_lo"] for m in names], [block[m]["mae_hi"] - block[m]["mae"] for m in names]]
        a.bar(range(len(names)), vals, yerr=err, color=["#888"] * (len(names) - 2) + ["#c33", "#e99"], capsize=3)
        a.set_xticks(range(len(names)))
        a.set_xticklabels(names, rotation=40, ha="right", fontsize=8)
        a.set_title(f"{ind} ({D.INDICATORS[ind]['unit']}): MAE, forward validation", fontsize=9)
        a.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(RESULTS / "figures" / "forecast_mae.png", dpi=130)
    plt.close(fig)


def main(parts: list[str]) -> None:
    todo = set(parts) or {"data", "det", "te", "china", "opt", "fig"}
    data = D.load()
    if "data" in todo:
        pipeline.write_json("data", pipeline.clean(pipeline.data_summary(data)))
        pipeline.write_json("inputs", {"inputs": [{"input": a, "kind": b, "basis": c} for a, b, c in config.INPUT_TABLE],
                                       "python": "3.11", "costs": config.COSTS, "optimisation": config.OPTIMISATION,
                                       "event_classes": {"thin_overlay_max_mm": events.THIN_OVERLAY_MAX_MM,
                                                         "thick_overlay_min_mm": events.THICK_OVERLAY_MIN_MM}})
        log("data summary written")
    if "det" in todo:
        det, _ = pipeline.deterioration(data, log)
        pipeline.write_json("deterioration", det)
    if "te" in todo:
        pipeline.write_json("treatment_effects", pipeline.treatment_effects(data))
        log("treatment effects written")
    if "china" in todo:
        pipeline.write_json("china", pipeline.china_view(data))
        log("china view written")
    if "opt" in todo:
        v = config.VALIDATION
        pairs = D.build_dataset(data, "iri", min_h=v["min_horizon"], max_h=v["max_horizon"])
        log("IRI pairs built")
        write_optimisation(pipeline.optimisation(data, pairs, read("deterioration"), read("treatment_effects")))
        log("optimisation written")
    if "fig" in todo:
        figures()
        log("figures written")


if __name__ == "__main__":
    main(sys.argv[1:])
