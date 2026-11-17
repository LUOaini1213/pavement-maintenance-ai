"""Checks on the committed data, results and generated documents (offline, no model training)."""
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pytest

from pavement_ai import china, config, pipeline, report
from pavement_ai import data as D
from pavement_ai import treatment as T
from pavement_ai.models import GlobalRate
from pavement_ai.optimize import Section, evaluate_plan, plan_benefit
from pavement_ai.report_tables import TABLES
from pavement_ai.validation import mae, split

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))


@pytest.fixture(scope="module")
def results():
    return report.load_results()


@pytest.fixture(scope="module")
def data():
    return D.load()


@pytest.fixture(scope="module")
def iri_pairs(data):
    v = config.VALIDATION
    return D.build_dataset(data, "iri", min_h=v["min_horizon"], max_h=v["max_horizon"])


# ---- data ------------------------------------------------------------------------------------------------------
def test_derived_files_match_their_hashes():
    manifest = json.loads((REPO / "data" / "derived" / "manifest.json").read_text(encoding="utf-8"))
    assert set(manifest["files"]) == {"sections.csv", "periods.csv", "iri.csv", "rut.csv", "crack.csv", "traffic.csv"}
    for name, meta in manifest["files"].items():
        raw = (REPO / "data" / "derived" / name).read_bytes().replace(b"\r\n", b"\n")
        assert hashlib.sha256(raw).hexdigest() == meta["sha256"], name


def test_raw_manifest_records_url_date_and_hash():
    manifest = json.loads((REPO / "data" / "raw_manifest.json").read_text(encoding="utf-8"))
    assert len(manifest["files"]) == 8
    for f in manifest["files"]:
        assert f["file_url"].startswith("https://") and len(f["sha256"]) == 64 and f["retrieved_utc"].startswith("2026-")
    assert not (REPO / "data" / "raw").exists() or "data/raw/" in (REPO / ".gitignore").read_text(encoding="utf-8")


def test_real_pairs_stay_inside_one_surface(data, iri_pairs):
    seg = D.segments(data["periods"], data["sections"])
    resets = seg[seg["event"].isin(["seal", "thin_overlay", "medium_overlay", "thick_overlay", "overlay_unknown"])]
    by_section = {sid: g["t_start"].to_numpy() for sid, g in resets.groupby("section_id")}
    sample = iri_pairs.sample(4000, random_state=0)
    for sid, t0, t1 in zip(sample["section_id"], sample["t0"], sample["t1"]):
        starts = by_section.get(sid)
        if starts is not None:
            # a profile visit can fall in the same days as the works; half a year of slack covers the date coding
            assert not ((starts > t0 + 0.5) & (starts < t1 - 0.5)).any(), sid
    assert (iri_pairs["h"] >= 0.5).all() and (iri_pairs["h"] <= 5.0).all()


# ---- results are what the code computes ------------------------------------------------------------------------
def test_data_summary_is_current(results, data):
    assert json.loads(json.dumps(pipeline.clean(pipeline.data_summary(data)))) == results["data"]


def test_china_view_is_current(results, data):
    assert json.loads(json.dumps(pipeline.china_view(data))) == results["china"]
    assert results["china"]["iri_at_rqi_expressway"]["90"] == pytest.approx(2.234515, abs=1e-5)
    assert results["china"]["rut_mm_at_rdi_80"] == pytest.approx(13.3333, abs=1e-3)
    assert china.rdi(results["china"]["rut_mm_at_rdi_80"]) == pytest.approx(80.0)


def test_treatment_effects_are_current(results, data):
    fresh = T.summarise(T.event_table(data, "iri"), config.VALIDATION["n_boot"], config.VALIDATION["seed"])
    stored = results["treatment_effects"]["iri"]["classes"]
    assert set(fresh) == set(stored)
    for cls in stored:
        for key in ("n_events", "drop_mean", "drop_lo", "drop_hi", "post_fit_intercept", "post_fit_slope",
                    "post_rate_median_all"):
            assert fresh[cls][key] == pytest.approx(stored[cls][key], rel=1e-9, abs=1e-12), (cls, key)


def test_baseline_errors_in_results_are_current(results, iri_pairs):
    v = results["deterioration"]["settings"]
    stored = results["deterioration"]["iri"]
    assert stored["pairs"] == len(iri_pairs)
    err = {"last": [], "linear": [], "exponential": [], "global_rate": []}
    n = 0
    for fold in range(v["folds"]):
        tr, te = split(iri_pairs, fold, v["folds"], v["cutoff_year"])
        test = iri_pairs[te]
        n += int(te.sum())
        err["last"].append(test["pred_last"] - test["y1"])
        err["linear"].append(test["pred_linear"] - test["y1"])
        err["exponential"].append(test["pred_exp"] - test["y1"])
        err["global_rate"].append(GlobalRate().fit(iri_pairs[tr]).predict(test) - test["y1"])
    block = stored["grouped_forward"]["all"]
    assert block["n_pairs"] == n
    for m, parts in err.items():
        assert mae(np.concatenate(parts)) == pytest.approx(block["methods"][m]["mae"], rel=1e-9), m


def test_result_blocks_are_internally_consistent(results):
    det = results["deterioration"]
    for ind in ("iri", "rut", "crack"):
        for scheme in ("grouped", "grouped_forward"):
            for key, b in det[ind][scheme].items():
                if key in ("folds", "test_sections"):
                    continue
                best = min(("last", "linear", "exponential", "global_rate", "markov"), key=lambda m: b["methods"][m]["mae"])
                assert b["best_baseline"] == best
                g = b["gbm_minus_best_baseline_mae"]
                assert g["diff"] == pytest.approx(b["methods"]["gbm"]["mae"] - b["methods"][best]["mae"], abs=1e-12)
                assert g["lo"] <= g["diff"] <= g["hi"]
                assert b["gbm_beats_best_baseline"] == (g["hi"] < 0)
                for m in b["methods"].values():
                    assert m["mae_lo"] <= m["mae"] <= m["mae_hi"] and m["mae"] <= m["rmse"]
        fw = det[ind]["grouped_forward"]
        assert sum(f["test_pairs"] for f in fw["folds"]) == fw["all"]["n_pairs"]
        assert fw["h_0.5_2"]["n_pairs"] + fw["h_2_5"]["n_pairs"] == fw["all"]["n_pairs"]
    # the leaky split must flatter the model: that is the point of showing it
    assert det["iri"]["leaky_random_pairs"]["all"]["methods"]["gbm"]["mae"] < det["iri"]["grouped"]["all"]["methods"]["gbm"]["mae"]


# ---- the plan --------------------------------------------------------------------------------------------------
@pytest.fixture(scope="module")
def network(results):
    detail = json.loads((REPO / "results" / "detail" / "base_plan.json").read_text(encoding="utf-8"))
    o = config.OPTIMISATION
    sections = [Section(s["sid"], s["iri"], s["rate"], o["section_length_lane_km"], s["age"], frozenset(s["eligible"]))
                for s in detail["network_sections"]]
    treatments = pipeline.build_treatments(results["treatment_effects"])
    index = {s.sid: i for i, s in enumerate(sections)}
    names = [t.name for t in treatments]
    plan = {index[sid]: (int(t), names.index(name)) for sid, t, name in detail["base_mip_plan"]}
    return sections, treatments, plan


def test_stored_plan_reproduces_the_reported_figures(results, network):
    sections, treatments, plan = network
    opt = results["optimisation"]
    base = opt["base"]
    horizon = opt["horizon_years"]
    assert len(sections) == opt["network"]["sections"]
    ev = evaluate_plan(sections, treatments, plan, horizon)
    assert plan_benefit(sections, treatments, plan, horizon) == pytest.approx(base["mip"]["iri_years_saved"], rel=1e-9)
    assert ev["mean_iri_final"] == pytest.approx(base["mip"]["mean_iri_final"], rel=1e-9)
    assert ev["treatments"] == base["mip"]["treatments"]
    for spent in ev["spend_by_year"]:
        assert spent <= base["annual_budget"] + 1e-6
    for i, (t, k) in plan.items():                                   # every chosen treatment respects the windows
        assert sections[i].may_receive(treatments[k])
        assert treatments[k].allowed(sections[i].iri0 + sections[i].rate * (t - 1))
    # proven within the gap asked of the solver
    assert base["mip"]["status"] == "Optimal"
    assert base["mip"]["iri_years_saved"] >= base["mip"]["dual_bound"] * (1 - config.OPTIMISATION["mip_rel_gap"]) - 1e-6


def test_rule_plans_are_current_and_never_beat_the_mip(results, network):
    sections, treatments, _ = network
    opt = results["optimisation"]
    horizon = opt["horizon_years"]
    plans = pipeline.rule_plans(sections, treatments, [opt["base"]["annual_budget"]] * horizon)
    for rule, plan in plans.items():
        assert plan_benefit(sections, treatments, plan, horizon) == pytest.approx(opt["base"][rule]["iri_years_saved"], rel=1e-9)
        assert opt["base"][rule]["total_spend"] <= horizon * opt["base"]["annual_budget"] + 1e-6
    for s in opt["sweep"]:
        assert s["mip"]["iri_years_saved"] >= s["worst_first"]["iri_years_saved"] * (1 - 0.01)
        assert s["mip"]["iri_years_saved"] >= s["fixed_cycle"]["iri_years_saved"] * (1 - 0.01)
    saved = [s["mip"]["iri_years_saved"] for s in opt["sweep"]]
    assert all(b >= a * (1 - 0.01) for a, b in zip(saved, saved[1:]))               # more money never hurts
    assert opt["base"]["mip_vs_worst_first"]["benefit_ratio"] == pytest.approx(
        opt["base"]["mip"]["iri_years_saved"] / opt["base"]["worst_first"]["iri_years_saved"])
    assert opt["network"]["rate_model"] == ("gbm" if results["deterioration"]["iri"]["grouped_forward"]["all"][
        "gbm_beats_best_baseline"] else "global_rate")


def test_treatment_inputs_come_from_the_measured_effects_and_cited_costs(results):
    trs = {t.name: t for t in pipeline.build_treatments(results["treatment_effects"])}
    eff = results["treatment_effects"]["iri"]["classes"]
    assert trs["minor_rehab"].cost == pytest.approx(332.0 / 1.609344)             # FHWA C&P 24th ed., Exhibit A-5
    assert trs["major_rehab"].cost == pytest.approx(1160.0 / 1.609344)
    assert trs["preventive"].cost == pytest.approx((29.409 + 249.699) / 2 / 1.609344)   # midpoint, FHWA-HIF-10-020
    assert trs["preventive"].post_a == eff["thin_overlay"]["post_fit_intercept"]
    assert trs["minor_rehab"].post_b == eff["medium_overlay"]["post_fit_slope"]
    assert trs["major_rehab"].rate_after == eff["thick_overlay"]["post_rate_median_all"]
    assert trs["preventive"].min_rqi == 85.0 and trs["minor_rehab"].min_rqi is None
    low = pipeline.build_treatments(results["treatment_effects"], 29.409)[0]
    assert low.cost == pytest.approx(29.409 / 1.609344)


@pytest.mark.parametrize("crack, rut, expected", [
    (0.0, 5.0, {"preventive", "minor_rehab", "major_rehab"}),
    (1.0, 13.0, {"preventive", "minor_rehab", "major_rehab"}),      # PCI exactly 85, RDI 81
    (1.1, 5.0, {"minor_rehab", "major_rehab"}),                     # PCI just under 85
    (0.5, 14.0, {"minor_rehab", "major_rehab"}),                    # rut 14 mm -> RDI 78
    (5.0, 5.0, {"minor_rehab", "major_rehab"}),                     # PCI 70.9
    (6.0, 5.0, {"major_rehab"}),                                    # PCI 68.6: below "average"
    (40.0, 30.0, {"major_rehab"}),
])
def test_eligibility_windows(crack, rut, expected):
    assert pipeline.eligibility(crack, rut) == frozenset(expected)


def test_budget_to_match_interpolates():
    sweep = [{"budget_share": 0.01, "r": {"iri_years_saved": 10.0}}, {"budget_share": 0.03, "r": {"iri_years_saved": 30.0}},
             {"budget_share": 0.05, "r": {"iri_years_saved": 40.0}}]
    assert pipeline.budget_to_match(sweep, "r", 20.0) == pytest.approx(0.02)
    assert pipeline.budget_to_match(sweep, "r", 35.0) == pytest.approx(0.04)
    assert pipeline.budget_to_match(sweep, "r", 50.0) is None


def test_worst_first_rule_picks_by_roughness_band():
    trs = pipeline.build_treatments(report.load_results()["treatment_effects"])
    secs = [Section("rough", 2.6, 0.0), Section("mid", 1.6, 0.0), Section("smooth", 1.2, 0.0),
            Section("mid_cracked", 1.7, 0.0, eligible=frozenset({"major_rehab"}))]
    plans = pipeline.rule_plans(secs, trs, [1e9])
    assert plans["worst_first"] == {0: (1, 2), 3: (1, 2), 1: (1, 1)}       # thick, thick (resurfacing not allowed), resurface
    old = [Section("old", 1.0, 0.0, age=9.0), Section("young", 1.0, 0.0, age=2.0)]
    assert pipeline.rule_plans(old, trs, [1e9])["fixed_cycle"] == {0: (1, 0)}


def test_clean_makes_strict_json():
    out = pipeline.clean({"a": np.float64(1.5), "b": float("nan"), "c": np.int64(3), "d": [np.bool_(True), None], 1: "x"})
    assert out == {"a": 1.5, "b": None, "c": 3, "d": [True, None], "1": "x"}
    assert json.dumps(out, allow_nan=False)


# ---- generated documents -----------------------------------------------------------------------------------------
def test_readme_and_brief_are_regenerated_from_results():
    import make_report
    built = make_report.build()
    for target, text in built.items():
        assert (REPO / target).read_text(encoding="utf-8") == text, f"{target} is stale: run scripts/make_report.py"


def test_every_number_in_readme_and_brief_is_in_results(results):
    for target in ("README.md", "docs/brief.md"):
        text = (REPO / target).read_text(encoding="utf-8")
        assert report.unsupported_numbers(text, results) == [], target
        assert len(report.NUMBER.findall(text)) > 100


def test_templates_carry_no_numbers_of_their_own():
    for template in ("docs/README.template.md", "docs/brief.template.md"):
        assert report.template_digits((REPO / template).read_text(encoding="utf-8")) == [], template


def test_readme_first_line_and_required_sections():
    lines = (REPO / "README.md").read_text(encoding="utf-8").splitlines()
    assert lines[0] == "Personal desk study on public data; not a real maintenance plan or engineering advice."
    text = "\n".join(lines)
    for needle in ("## 中文摘要", "## Limitations", "## Inputs: real, calibrated or assumption", "| assumption |",
                   "| real |", "| calibrated |", "docs/sources.md"):
        assert needle in text, needle


def test_verdict_words_follow_the_interval(results):
    text = TABLES["verdicts"](results)
    b = results["deterioration"]["rut"]["grouped_forward"]["all"]["gbm_minus_best_baseline_mae"]
    row = next(line for line in text.splitlines() if line.startswith("| rut depth (mm) | site-grouped + forward"))
    expected = "boosting is better" if b["hi"] < 0 else "boosting is worse" if b["lo"] > 0 else "no detectable difference"
    assert row.rstrip(" |").endswith(expected)


def test_reported_test_count_is_current(request, results):
    if request.config.option.file_or_dir or request.config.option.keyword or request.config.option.markexpr:
        pytest.skip("only meaningful when the whole suite is collected")
    assert results["mutation"]["tests"] == request.session.testscollected


def test_no_local_paths_or_personal_data_in_tracked_text():
    bad = ["C:" + "\\\\Users", "/c/" + "Users", "C:/" + "Users", "/home/", "@gmail", "@qq.", "@u.nus"]
    for path in list(REPO.glob("*.md")) + list((REPO / "docs").glob("*.md")) + list((REPO / "src").rglob("*.py")) + \
            list((REPO / "scripts").glob("*.py")) + list((REPO / "results").glob("*.json")) + [REPO / "data" / "raw_manifest.json"]:
        text = path.read_text(encoding="utf-8")
        for needle in bad:
            assert needle not in text, (path.name, needle)
