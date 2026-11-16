"""Compute every results/*.json file from data/derived/ (see scripts/run_all.py)."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from . import china, config
from . import data as D
from . import deterioration as A
from . import treatment as T
from .models import BoostedIncrement, GlobalRate, feature_frame
from .optimize import Section, Treatment, evaluate_plan, greedy_rule, plan_benefit, solve_mip

REPO = Path(__file__).resolve().parents[2]
RESULTS = REPO / "results"


def write_json(name: str, obj: dict, folder: Path = RESULTS) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    text = json.dumps(obj, indent=1, ensure_ascii=False, allow_nan=False) + "\n"
    (folder / f"{name}.json").write_text(text, encoding="utf-8", newline="\n")


def clean(obj):
    """NaN -> None and numpy scalars -> Python numbers, so the JSON is strict."""
    if isinstance(obj, dict):
        return {str(k): clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [clean(v) for v in obj]
    if isinstance(obj, (np.bool_, bool)):
        return bool(obj)
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating, float)):
        return None if not np.isfinite(obj) else float(obj)
    return obj


# ---- data summary ---------------------------------------------------------------------------------------------
def data_summary(data: dict) -> dict:
    manifest = json.loads((REPO / "data" / "raw_manifest.json").read_text(encoding="utf-8"))
    out = {
        "dataset": manifest["dataset"], "citation": manifest["citation"], "landing_page": manifest["landing_page"],
        "raw_files": len(manifest["files"]), "raw_bytes": int(sum(f["bytes"] for f in manifest["files"])),
        "retrieved": sorted({f["retrieved_utc"][:10] for f in manifest["files"]})[0],
        "sections": int(len(data["sections"])), "sites": int(data["sections"]["site_id"].nunique()),
        "sections_with_climate": int(data["sections"]["precip_mm"].notna().sum()),
        "events": {k: int(v) for k, v in data["periods"]["event"].value_counts().items()},
        "indicators": {},
    }
    for name, spec in D.INDICATORS.items():
        df = data[name]
        out["indicators"][name] = {
            "unit": spec["unit"], "visits": int(len(df)), "sections": int(df["section_id"].nunique()),
            "first_year": int(df["date"].min()[:4]), "last_year": int(df["date"].max()[:4]),
            "median": float(df[spec["col"]].median()),
        }
    return out


# ---- part A ---------------------------------------------------------------------------------------------------
def deterioration(data: dict, log=print) -> tuple[dict, dict]:
    v = config.VALIDATION
    out = {"settings": {**v, "methods": A.BASELINES + [A.ML, A.ML_L2], "features": {}}}
    datasets = {}
    for ind in D.INDICATORS:
        pairs = D.build_dataset(data, ind, min_h=v["min_horizon"], max_h=v["max_horizon"])
        datasets[ind] = pairs
        out["settings"]["features"][ind] = list(feature_frame(pairs.head(5), A.extra_features(ind)).columns)
        res = {"pairs": int(len(pairs)), "sections": int(pairs["section_id"].nunique()),
               "sites": int(pairs["site_id"].nunique()),
               "median_annual_rate": float(np.median((pairs["y1"] - pairs["y0"]) / pairs["h"]))}
        res["grouped"] = A.evaluate(pairs, ind, v["folds"], None, v["n_boot"], v["seed"])
        log(f"{ind} grouped done")
        res["grouped_forward"] = A.evaluate(pairs, ind, v["folds"], v["cutoff_year"], v["n_boot"], v["seed"])
        log(f"{ind} grouped_forward done")
        if ind == "iri":
            res["leaky_random_pairs"] = A.evaluate(pairs, ind, v["folds"], None, v["n_boot"], v["seed"], leaky=True)
            log(f"{ind} leaky done")
        out[ind] = res
    return clean(out), datasets


# ---- treatment effects ------------------------------------------------------------------------------------------
def treatment_effects(data: dict) -> dict:
    v = config.VALIDATION
    out = {"settings": {"max_years_before": 3.0, "max_years_after": 2.0, "min_visits_for_rate": 3,
                        "min_span_for_rate": 2.0}}
    for ind in D.INDICATORS:
        events = T.event_table(data, ind)
        out[ind] = {"events": int(len(events)), "classes": T.summarise(events, v["n_boot"], v["seed"])}
    return clean(out)


# ---- part C -------------------------------------------------------------------------------------------------------
def china_view(data: dict) -> dict:
    min_year = str(config.OPTIMISATION["network_min_last_visit_year"])
    last_iri = data["iri"].sort_values("date").groupby("section_id").tail(1)
    last_rut = data["rut"].sort_values("date").groupby("section_id").tail(1)
    net_iri = last_iri[last_iri["date"] >= min_year]["iri"]
    net_rut = last_rut[last_rut["date"] >= min_year]["rut_mm"]
    limits = {str(int(lim)): china.iri_for_rqi(lim) for lim, _ in china.GRADE_LIMITS}
    limits["85"] = china.iri_for_rqi(85.0)
    return clean({
        "rqi_coefficients": china.RQI_COEFFICIENTS,
        "rdi_parameters": {"a0": china.RDI_A0, "a1": china.RDI_A1, "rda_mm": china.RDI_RDA, "rdb_mm": china.RDI_RDB},
        "grade_limits": {name: lim for lim, name in china.GRADE_LIMITS},
        "grade_names_zh": china.GRADE_ZH,
        "preventive_windows_expressway": china.PREVENTIVE_WINDOWS_EXPRESSWAY,
        "iri_at_rqi_expressway": limits,
        "iri_at_rqi_other": {str(int(lim)): china.iri_for_rqi(lim, "other") for lim, _ in china.GRADE_LIMITS},
        "pci_parameters_asphalt": {"a0": china.PCI_A0_ASPHALT, "a1": china.PCI_A1_ASPHALT},
        "distress_ratio_at_pci": {"85": china.dr_for_pci(85.0), "70": china.dr_for_pci(70.0)},
        "rut_mm_at_rdi_80": 10.0 + 10.0 / china.RDI_A1,
        "all_visits": {
            "n_iri": int(len(data["iri"])),
            "rqi_grade_shares": china.grade_shares(china.rqi(v) for v in data["iri"]["iri"]),
            "n_rut": int(len(data["rut"])),
            "rdi_grade_shares": china.grade_shares(china.rdi(v) for v in data["rut"]["rut_mm"]),
        },
        "network_latest": {
            "n_iri": int(len(net_iri)), "median_iri": float(net_iri.median()),
            "median_rqi": float(np.median([china.rqi(v) for v in net_iri])),
            "min_rqi": float(min(china.rqi(v) for v in net_iri)),
            "rqi_grade_shares": china.grade_shares(china.rqi(v) for v in net_iri),
            "n_rut": int(len(net_rut)),
            "rdi_grade_shares": china.grade_shares(china.rdi(v) for v in net_rut),
        },
        "sources": china.SOURCES,
    })


# ---- part B -------------------------------------------------------------------------------------------------------
def build_treatments(effects: dict, preventive_per_lane_mile: float | None = None) -> list[Treatment]:
    o = config.OPTIMISATION
    out = []
    for level in ("preventive", "minor_rehab", "major_rehab"):
        c = config.COSTS[level]
        per_mile = c.get("per_lane_mile", (c.get("low_per_lane_mile", 0) + c.get("high_per_lane_mile", 0)) / 2.0)
        if level == "preventive" and preventive_per_lane_mile is not None:
            per_mile = preventive_per_lane_mile
        e = effects["iri"]["classes"][config.EFFECT_CLASS[level]]
        out.append(Treatment(level, per_mile / config.LANE_MILE_KM, e["post_fit_intercept"], e["post_fit_slope"],
                             e["post_rate_median_all"],
                             o["preventive_min_rqi"] if level == "preventive" else None, o["treatment_floor_iri"]))
    return out


def last_on_surface(data: dict, indicator: str) -> dict:
    """Latest value of an indicator on each surface: {(section_id, seg): value}."""
    ser = D.series(data, indicator)
    last = ser.groupby(["section_id", "seg"], sort=False).tail(1)
    return {(sid, int(seg)): float(y) for sid, seg, y in zip(last["section_id"], last["seg"], last["y"])}


def eligibility(crack_pct: float, rut_mm: float) -> frozenset:
    """Treatment levels a section may receive, from its PCI (cracking) and RDI (rutting)."""
    o = config.OPTIMISATION
    pci, rdi = china.pci(crack_pct), china.rdi(rut_mm)
    names = {"major_rehab"}
    if pci >= o["minor_rehab_min_pci"]:
        names.add("minor_rehab")
    if pci >= o["preventive_min_pci"] and rdi >= o["preventive_min_rdi"]:
        names.add("preventive")
    return frozenset(names)


def build_network(data: dict, pairs: pd.DataFrame, rate_model: str) -> tuple[list[Section], dict]:
    o = config.OPTIMISATION
    latest = D.build_dataset(data, "iri", latest_horizon=float(o["horizon_years"]))
    year = np.floor(latest["t0"]).astype(int)
    latest = latest[year >= o["network_min_last_visit_year"]].reset_index(drop=True)
    candidates = len(latest)
    rut, crack = last_on_surface(data, "rut"), last_on_surface(data, "crack")
    keys = list(zip(latest["section_id"], latest["seg"].astype(int)))
    latest["rut_last"] = [rut.get(k, np.nan) for k in keys]
    latest["crack_last"] = [crack.get(k, np.nan) for k in keys]
    latest = latest.dropna(subset=["rut_last", "crack_last"]).reset_index(drop=True)
    global_rate = max(0.0, GlobalRate().fit(pairs).rate_)
    if rate_model == "gbm":
        spec = D.INDICATORS["iri"]
        gbm = BoostedIncrement(A.extra_features("iri"), spec["lo"], spec["hi"], loss="absolute_error").fit(pairs)
        rate = np.maximum(0.0, (gbm.predict(latest) - latest["y0"].to_numpy()) / o["horizon_years"])
    else:
        rate = np.full(len(latest), global_rate)
    age = latest["age0"].fillna(latest["hist_span"]).to_numpy()
    elig = [eligibility(c, r) for c, r in zip(latest["crack_last"], latest["rut_last"])]
    sections = [Section(sid, float(y0), float(r), o["section_length_lane_km"], float(a), e)
                for sid, y0, r, a, e in zip(latest["section_id"], latest["y0"], rate, age, elig)]
    pci = np.array([china.pci(c) for c in latest["crack_last"]])
    rdi = np.array([china.rdi(r) for r in latest["rut_last"]])
    rqi = np.array([china.rqi(v) for v in latest["y0"]])
    info = {"candidates": candidates, "sections": len(sections),
            "excluded_without_rut_or_cracking": candidates - len(sections),
            "lane_km": float(sum(s.length for s in sections)),
            "mean_iri": float(np.mean([s.iri0 for s in sections])), "max_iri": float(max(s.iri0 for s in sections)),
            "share_iri_above_1p5": float(np.mean([s.iri0 > 1.5 for s in sections])),
            "median_cracking_pct": float(latest["crack_last"].median()), "median_rut_mm": float(latest["rut_last"].median()),
            "rqi_grade_shares": china.grade_shares(rqi), "pci_grade_shares": china.grade_shares(pci),
            "rdi_grade_shares": china.grade_shares(rdi),
            "share_eligible_preventive": float(np.mean(["preventive" in e for e in elig])),
            "share_eligible_minor_rehab": float(np.mean(["minor_rehab" in e for e in elig])),
            "rate_model": rate_model, "global_rate": global_rate,
            "rate_median": float(np.median(rate)), "rate_p90": float(np.quantile(rate, 0.9)),
            "median_age": float(np.median(age))}
    return sections, info


def rule_plans(sections: list[Section], treatments: list[Treatment], budgets: list[float]) -> dict:
    o = config.OPTIMISATION
    wf = o["worst_first"]

    def by_condition(sec, cur, age):
        if cur >= wf["major_iri"]:
            return 2
        if cur >= wf["trigger_iri"]:
            return 1 if sec.may_receive(treatments[1]) else 2
        return None

    worst = greedy_rule(sections, treatments, budgets, "worst", by_condition)["plan"]
    cycle = greedy_rule(sections, treatments, budgets, "oldest", lambda s, cur, age: 0,
                        eligible=lambda s, cur, age: age >= o["fixed_cycle_years"])["plan"]
    return {"worst_first": worst, "fixed_cycle": cycle}


def compare(sections: list[Section], treatments: list[Treatment], annual_budget: float) -> dict:
    horizon = config.OPTIMISATION["horizon_years"]
    budgets = [annual_budget] * horizon
    mip = solve_mip(sections, treatments, budgets)
    plans = {"do_nothing": {}, "mip": mip["plan"], **rule_plans(sections, treatments, budgets)}
    out = {"annual_budget": annual_budget}
    for name, plan in plans.items():
        ev = evaluate_plan(sections, treatments, plan, horizon)
        ev["iri_years_saved"] = plan_benefit(sections, treatments, plan, horizon)
        out[name] = ev
    out["mip"].update({"status": mip["status"], "mip_gap": mip["mip_gap"], "binary_variables": mip["n_vars"],
                       "constraints": mip["n_rows"]})
    for rule in ("worst_first", "fixed_cycle"):
        base = out[rule]["iri_years_saved"]
        out[f"mip_vs_{rule}"] = {
            "benefit_ratio": out["mip"]["iri_years_saved"] / base if base > 0 else None,
            "extra_iri_years_saved": out["mip"]["iri_years_saved"] - base,
            "mean_iri_final_diff": out["mip"]["mean_iri_final"] - out[rule]["mean_iri_final"],
            "sections_in_both": len(set(mip["plan"]) & set(plans[rule])),
        }
    return out


def budget_to_match(sweep: list[dict], rule: str, target: float) -> float | None:
    """Budget share at which `rule` saves as many IRI-years as `target`, by linear interpolation on the sweep."""
    pts = [(s["budget_share"], s[rule]["iri_years_saved"]) for s in sweep]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if y0 <= target <= y1 and y1 > y0:
            return x0 + (x1 - x0) * (target - y0) / (y1 - y0)
    return None


def optimisation(data: dict, pairs: pd.DataFrame, det: dict, effects: dict) -> dict:
    o = config.OPTIMISATION
    beats = det["iri"]["grouped_forward"]["all"]["gbm_beats_best_baseline"]
    rate_model = "gbm" if beats else "global_rate"
    sections, info = build_network(data, pairs, rate_model)
    treatments = build_treatments(effects)
    resurfacing_all = treatments[1].cost * info["lane_km"]
    out = {
        "horizon_years": o["horizon_years"], "network": info,
        "rate_model_reason": "boosting beat the best baseline under forward validation" if beats else
                             "boosting did not beat the best baseline under forward validation, so the baseline's "
                             "network-wide rate is used",
        "resurfacing_whole_network": resurfacing_all,
        "treatments": [{"name": t.name, "effect_class": config.EFFECT_CLASS[t.name],
                        "cost_per_lane_km": t.cost, "cost_per_lane_mile": t.cost * config.LANE_MILE_KM,
                        "post_intercept": t.post_a, "post_slope": t.post_b, "rate_after": t.rate_after,
                        "min_rqi": t.min_rqi, "source": config.COSTS[t.name]["source"],
                        "url": config.COSTS[t.name]["url"], "dollar_year": config.COSTS[t.name]["dollar_year"]}
                       for t in treatments],
        "rules": {"worst_first": o["worst_first"], "fixed_cycle_years": o["fixed_cycle_years"]},
    }
    sweep = []
    for share in o["budget_shares"]:
        res = compare(sections, treatments, share * resurfacing_all)
        res["budget_share"] = share
        sweep.append(res)
        if share == o["base_budget_share"]:
            out["base"] = res
    out["sweep"] = [{"budget_share": s["budget_share"], "annual_budget": s["annual_budget"],
                     **{k: {"iri_years_saved": s[k]["iri_years_saved"], "mean_iri_final": s[k]["mean_iri_final"],
                            "mean_iri_horizon": s[k]["mean_iri_horizon"], "total_spend": s[k]["total_spend"],
                            "treated_sections": s[k]["treated_sections"],
                            "share_iri_le_1p5_final": s[k]["share_iri_le_1p5_final"]}
                        for k in ("mip", "worst_first", "fixed_cycle")},
                     "benefit_ratio_vs_worst_first": s["mip_vs_worst_first"]["benefit_ratio"]} for s in sweep]
    match = budget_to_match(out["sweep"], "worst_first", out["base"]["mip"]["iri_years_saved"])
    out["worst_first_budget_share_to_match_mip_base"] = match
    out["worst_first_budget_multiple_to_match_mip_base"] = None if match is None else match / o["base_budget_share"]

    # sensitivity 1: the price of the thin overlay at both ends of the published range
    out["preventive_cost_sensitivity"] = []
    for label in ("low_per_lane_mile", "high_per_lane_mile"):
        per_mile = config.COSTS["preventive"][label]
        res = compare(sections, build_treatments(effects, per_mile), o["base_budget_share"] * resurfacing_all)
        out["preventive_cost_sensitivity"].append({
            "case": label.split("_")[0], "cost_per_lane_mile": per_mile,
            "mip_iri_years_saved": res["mip"]["iri_years_saved"],
            "worst_first_iri_years_saved": res["worst_first"]["iri_years_saved"],
            "benefit_ratio": res["mip_vs_worst_first"]["benefit_ratio"], "mip_treatments": res["mip"]["treatments"]})

    # sensitivity 2: the other rate model (section-specific boosting rates, or the single network rate)
    other = "global_rate" if rate_model == "gbm" else "gbm"
    alt_sections, alt_info = build_network(data, pairs, other)
    alt = compare(alt_sections, treatments, o["base_budget_share"] * resurfacing_all)
    base_plan = solve_mip(sections, treatments, [o["base_budget_share"] * resurfacing_all] * o["horizon_years"])["plan"]
    alt_plan = solve_mip(alt_sections, treatments, [o["base_budget_share"] * resurfacing_all] * o["horizon_years"])["plan"]
    ids = lambda secs, plan: {secs[i].sid for i in plan}          # noqa: E731
    a, b = ids(sections, base_plan), ids(alt_sections, alt_plan)
    out["rate_model_sensitivity"] = {
        "other_rate_model": other, "rate_median": alt_info["rate_median"], "rate_p90": alt_info["rate_p90"],
        "benefit_ratio_vs_worst_first": alt["mip_vs_worst_first"]["benefit_ratio"],
        "mip_treatments": alt["mip"]["treatments"],
        "sections_treated_in_both_plans": len(a & b), "sections_treated_in_either_plan": len(a | b),
        "plan_overlap": len(a & b) / len(a | b) if (a | b) else None,
    }
    return clean(out)
