"""Tables and result-dependent sentences of README.md and docs/brief.md, built from results/*.json."""
from __future__ import annotations

from .report import fmt

INDICATOR_LABEL = {"iri": "IRI (m/km)", "rut": "rut depth (mm)", "crack": "cracking (%)"}
INDICATOR_SPEC = {"iri": ".3f", "rut": ".2f", "crack": ".2f"}
METHOD_LABEL = {"last": "last value", "linear": "own linear trend", "exponential": "own exponential trend",
                "global_rate": "last value + network median rate", "markov": "Markov chain on condition states",
                "gbm": "gradient boosting (absolute-error loss)", "gbm_l2": "gradient boosting (squared-error loss)"}
CLASS_LABEL = {"seal": "seal coat / surface treatment", "thin_overlay": "thin overlay (up to 40 mm)",
               "medium_overlay": "medium overlay (over 40, under 75 mm)",
               "thick_overlay": "thick overlay (75 mm or more) or reconstruction"}
LEVEL_LABEL = {"preventive": "preventive (thin overlay)", "minor_rehab": "minor rehabilitation (resurfacing)",
               "major_rehab": "major rehabilitation (thick overlay / reconstruction)"}
STRATEGY_LABEL = {"do_nothing": "do nothing", "mip": "MIP (HiGHS)", "worst_first": "worst-first rule",
                  "fixed_cycle": "fixed-cycle rule"}
GRADES = ["excellent", "good", "average", "poor", "failed"]


def _row(cells) -> str:
    return "| " + " | ".join(cells) + " |"


def _table(header, rows) -> str:
    return "\n".join([_row(header), _row(["---"] * len(header))] + [_row(r) for r in rows])


def _ci(block: dict, key: str, spec: str) -> str:
    return f"{fmt(block[key], spec)} ({fmt(block[key + '_lo'], spec)} to {fmt(block[key + '_hi'], spec)})"


def forecast_table(scheme: str):
    def build(res: dict) -> str:
        det = res["deterioration"]
        header = ["method"] + [f"{INDICATOR_LABEL[i]}: MAE" for i in INDICATOR_LABEL]
        rows = []
        for m in det["settings"]["methods"]:
            rows.append([METHOD_LABEL[m]] + [_ci(det[i][scheme]["all"]["methods"][m], "mae", INDICATOR_SPEC[i])
                                             for i in INDICATOR_LABEL])
        sizes = ["test pairs / sites"] + [f"{fmt(det[i][scheme]['all']['n_pairs'], ',d')} / "
                                          f"{fmt(det[i][scheme]['all']['n_sites'], ',d')}" for i in INDICATOR_LABEL]
        return _table(header, rows + [sizes])
    return build


def _verdict(block: dict) -> str:
    g = block["gbm_minus_best_baseline_mae"]
    if g["hi"] < 0:
        return "boosting is better"
    if g["lo"] > 0:
        return "boosting is worse"
    return "no detectable difference"


def verdict_table(res: dict) -> str:
    det = res["deterioration"]
    header = ["indicator", "validation", "horizon (years)", "best baseline", "its MAE", "boosting MAE",
              "boosting minus baseline (interval)", "change", "verdict"]
    bins = det["settings"]["horizon_bins"]
    rows = []
    for ind in INDICATOR_LABEL:
        spec = INDICATOR_SPEC[ind]
        for scheme, label in (("grouped_forward", "site-grouped + forward in time"), ("grouped", "site-grouped")):
            for key in ("all", "short", "long"):
                b = det[ind][scheme][bins[key]["key"]]
                g = b["gbm_minus_best_baseline_mae"]
                rows.append([INDICATOR_LABEL[ind], label, f"{fmt(bins[key]['from'], '.1f')} to {fmt(bins[key]['to'], '.0f')}",
                             METHOD_LABEL[b["best_baseline"]], fmt(b["methods"][b["best_baseline"]]["mae"], spec),
                             fmt(b["methods"]["gbm"]["mae"], spec),
                             f"{fmt(g['diff'], '+' + spec)} ({fmt(g['lo'], '+' + spec)} to {fmt(g['hi'], '+' + spec)})",
                             fmt(b["gbm_mae_change_pct"], "+.1f") + " %", _verdict(b)])
    return _table(header, rows)


def verdict_sentence(res: dict) -> str:
    """One plain sentence per indicator for the forward validation (the headline)."""
    det = res["deterioration"]
    out = []
    for ind in INDICATOR_LABEL:
        b = det[ind]["grouped_forward"]["all"]
        spec = INDICATOR_SPEC[ind]
        g = b["gbm_minus_best_baseline_mae"]
        word = {"boosting is better": "beats", "boosting is worse": "is worse than",
                "no detectable difference": "is not distinguishable from"}[_verdict(b)]
        out.append(f"- **{INDICATOR_LABEL[ind]}**: gradient boosting (MAE {fmt(b['methods']['gbm']['mae'], spec)}) {word} "
                   f"the best naive baseline, {METHOD_LABEL[b['best_baseline']]} (MAE "
                   f"{fmt(b['methods'][b['best_baseline']]['mae'], spec)}); difference {fmt(g['diff'], '+' + spec)}, "
                   f"interval {fmt(g['lo'], '+' + spec)} to {fmt(g['hi'], '+' + spec)}.")
    return "\n".join(out)


def verdict_sentence_zh(res: dict) -> str:
    det = res["deterioration"]
    name = {"iri": "IRI（m/km）", "rut": "车辙深度（mm）", "crack": "裂缝率（%）"}
    base = {"last": "末次观测值", "linear": "本路段线性外推", "exponential": "本路段指数外推",
            "global_rate": "末次值＋路网中位衰变速率", "markov": "马尔可夫链"}
    out = []
    for ind in INDICATOR_LABEL:
        b = det[ind]["grouped_forward"]["all"]
        spec = INDICATOR_SPEC[ind]
        g = b["gbm_minus_best_baseline_mae"]
        word = {"boosting is better": "优于", "boosting is worse": "不如",
                "no detectable difference": "与之无法区分："}[_verdict(b)]
        out.append(f"- {name[ind]}：梯度提升 MAE {fmt(b['methods']['gbm']['mae'], spec)}，{word}最优朴素基线"
                   f"「{base[b['best_baseline']]}」（MAE {fmt(b['methods'][b['best_baseline']]['mae'], spec)}），"
                   f"差值 {fmt(g['diff'], '+' + spec)}（区间 {fmt(g['lo'], '+' + spec)} 至 {fmt(g['hi'], '+' + spec)}）。")
    return "\n".join(out)


def leaky_table(res: dict) -> str:
    det = res["deterioration"]["iri"]
    header = ["how the IRI pairs are split", "best baseline MAE", "boosting MAE", "boosting vs baseline"]
    rows = []
    for scheme, label in (("leaky_random_pairs", "at random, pair by pair (leaky: wrong)"),
                          ("grouped", "by site (no section on both sides)"),
                          ("grouped_forward", "by site and forward in time")):
        b = det[scheme]["all"]
        rows.append([label, fmt(b["methods"][b["best_baseline"]]["mae"], ".3f"), fmt(b["methods"]["gbm"]["mae"], ".3f"),
                     fmt(b["gbm_mae_change_pct"], "+.1f") + " %"])
    return _table(header, rows)


def treatment_table(indicator: str):
    spec = {"iri": ".2f", "rut": ".1f", "crack": ".1f"}[indicator]
    rate = {"iri": ".3f", "rut": ".2f", "crack": ".2f"}[indicator]

    def build(res: dict) -> str:
        cls = res["treatment_effects"][indicator]["classes"]
        header = ["treatment class", "events / sites", "median thickness (mm)", "median before", "median after",
                  "mean drop (interval)", "rate before -> after (per year)", "mean rate change (interval)"]
        rows = []
        for c in CLASS_LABEL:
            if c not in cls:
                continue
            e = cls[c]
            thick = "n/a" if e["median_overlay_mm"] is None else fmt(e["median_overlay_mm"], ".0f")
            if "rate_change_mean" in e:
                rates = f"{fmt(e['pre_rate_median'], rate)} -> {fmt(e['post_rate_median'], rate)}"
                change = (f"{fmt(e['rate_change_mean'], '+' + rate)} ({fmt(e['rate_change_lo'], '+' + rate)} to "
                          f"{fmt(e['rate_change_hi'], '+' + rate)})")
            else:
                rates = change = "n/a"
            rows.append([CLASS_LABEL[c], f"{fmt(e['n_events'], ',d')} / {fmt(e['n_sites'], ',d')}", thick,
                         fmt(e["pre_median"], spec), fmt(e["post_median"], spec),
                         f"{fmt(e['drop_mean'], '+' + spec)} ({fmt(e['drop_lo'], '+' + spec)} to {fmt(e['drop_hi'], '+' + spec)})",
                         rates, change])
        return _table(header, rows)
    return build


def treatments_used_table(res: dict) -> str:
    header = ["treatment level", "LTPP effect class", "IRI after treatment (m/km)", "IRI growth after (m/km per year)",
              "cost (thousand USD per lane-km)", "allowed when"]
    o = res["inputs"]["optimisation"]
    rows = []
    for t in res["optimisation"]["treatments"]:
        when = {"preventive": f"PCI and RQI at least {fmt(o['preventive_min_pci'], '.0f')}, RDI at least "
                              f"{fmt(o['preventive_min_rdi'], '.0f')}",
                "minor_rehab": f"PCI at least {fmt(o['minor_rehab_min_pci'], '.0f')}",
                "major_rehab": "always"}[t["name"]]
        rows.append([LEVEL_LABEL[t["name"]], CLASS_LABEL[t["effect_class"]],
                     f"{fmt(t['post_intercept'], '.3f')} + {fmt(t['post_slope'], '.3f')} x IRI before",
                     fmt(t["rate_after"], ".3f"), fmt(t["cost_per_lane_km"], ".1f"), when])
    return _table(header, rows)


def plan_table(res: dict) -> str:
    base = res["optimisation"]["base"]
    header = ["strategy", "IRI-years saved", "mean IRI after the plan (m/km)", "share of length at or below the trigger",
              "sections treated (preventive / minor / major)", "spend (million USD)"]
    rows = []
    for s in STRATEGY_LABEL:
        e = base[s]
        t = e["treatments"]
        rows.append([STRATEGY_LABEL[s], fmt(e["iri_years_saved"], ".1f"), fmt(e["mean_iri_final"], ".3f"),
                     fmt(e["share_iri_le_1p5_final"], "pct1") + " %",
                     f"{fmt(e['treated_sections'], 'd')} ({fmt(t['preventive'], 'd')} / {fmt(t['minor_rehab'], 'd')} / "
                     f"{fmt(t['major_rehab'], 'd')})", fmt(e["total_spend_million"], ".2f")])
    return _table(header, rows)


def sweep_table(res: dict) -> str:
    header = ["annual budget (% of resurfacing everything)", "MIP: IRI-years saved", "worst-first", "fixed-cycle",
              "MIP / worst-first", "MIP: mean IRI after (m/km)", "worst-first: mean IRI after"]
    rows = []
    for s in res["optimisation"]["sweep"]:
        ratio = "n/a" if s["benefit_ratio_vs_worst_first"] is None else fmt(s["benefit_ratio_vs_worst_first"], ".2f")
        rows.append([fmt(s["budget_share"], "pct1"), fmt(s["mip"]["iri_years_saved"], ".1f"),
                     fmt(s["worst_first"]["iri_years_saved"], ".1f"), fmt(s["fixed_cycle"]["iri_years_saved"], ".1f"),
                     ratio, fmt(s["mip"]["mean_iri_final"], ".3f"), fmt(s["worst_first"]["mean_iri_final"], ".3f")])
    return _table(header, rows)


def grade_table(res: dict) -> str:
    net = res["optimisation"]["network"]
    zh = res["china"]["grade_names_zh"]
    header = ["index"] + [f"{g} ({zh[g]})" for g in GRADES]
    rows = [[label] + [fmt(net[key][g], "pct1") + " %" for g in GRADES]
            for label, key in (("RQI from IRI", "rqi_grade_shares"), ("RDI from rut depth", "rdi_grade_shares"),
                               ("PCI from cracking percent (approximation)", "pci_grade_shares"))]
    return _table(header, rows)


def inputs_table(res: dict) -> str:
    return _table(["input", "kind", "basis"], [[r["input"], r["kind"], r["basis"]] for r in res["inputs"]["inputs"]])


def yearly_plan_table(res: dict) -> str:
    """Brief: treatments and spend of the MIP plan by year (bilingual header)."""
    e = res["optimisation"]["base"]["mip"]
    header = ["year 年", "preventive 预防养护", "minor rehab 中修", "major rehab 大修", "spend 支出 (million USD)"]
    rows = []
    for y, (counts, spend) in enumerate(zip(e["treatments_by_year"], e["spend_by_year_million"])):
        rows.append([fmt(res["optimisation"]["years"][y], "d"), fmt(counts["preventive"], "d"),
                     fmt(counts["minor_rehab"], "d"), fmt(counts["major_rehab"], "d"), fmt(spend, ".2f")])
    return _table(header, rows)


TABLES = {
    "forecast_forward": forecast_table("grouped_forward"),
    "forecast_grouped": forecast_table("grouped"),
    "verdicts": verdict_table,
    "verdict_sentences": verdict_sentence,
    "verdict_sentences_zh": verdict_sentence_zh,
    "leaky": leaky_table,
    "treatment_iri": treatment_table("iri"),
    "treatment_rut": treatment_table("rut"),
    "treatment_crack": treatment_table("crack"),
    "treatments_used": treatments_used_table,
    "plan": plan_table,
    "sweep": sweep_table,
    "grades": grade_table,
    "inputs": inputs_table,
    "yearly_plan": yearly_plan_table,
}
