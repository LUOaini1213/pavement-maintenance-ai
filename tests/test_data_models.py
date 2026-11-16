"""Hand-checked cases for segments, pairs, baselines, the Markov chain, validation splits and treatment effects."""
import numpy as np
import pandas as pd
import pytest

from pavement_ai import data as D
from pavement_ai import deterioration as A
from pavement_ai import treatment as T
from pavement_ai.models import BoostedIncrement, GlobalRate, MarkovChain, feature_frame
from pavement_ai.validation import cluster_bootstrap, fold_of, mae, rmse, split

JUL2 = 182 / 365.25          # 2 July is day 183 of a non-leap year


def test_decimal_year():
    assert D.decimal_year(["1998-01-01", "1985-07-02"]) == pytest.approx([1998.0, 1985 + JUL2])
    assert np.isnan(D.decimal_year([np.nan])[0])


def test_ols_line_hand_values():
    # t = 0, 1, 2 ; y = 1, 2, 4 : slope = (1.3333 + 1.6667) / 2 = 1.5 ; intercept = 2.3333 - 1.5
    a, b = D.ols_line(np.array([0.0, 1.0, 2.0]), np.array([1.0, 2.0, 4.0]))
    assert (a, b) == pytest.approx((0.833333, 1.5), abs=1e-6)
    assert D.ols_line(np.array([3.0, 3.0]), np.array([1.0, 2.0])) == pytest.approx((1.5, 0.0))


def test_segments_split_only_at_surface_renewals(toy):
    seg = D.segments(toy["periods"], toy["sections"])
    a = seg[seg["section_id"] == "01-0001"]
    assert a["seg"].tolist() == [1, 1, 2]                                   # crack sealing does not open a segment
    assert a["seg_event"].tolist() == ["original", "original", "thick_overlay"]
    assert a["seg_start"].tolist() == pytest.approx([1985 + JUL2, 1985 + JUL2, 1993 + JUL2])   # opened date, overlay date
    assert a["seg_overlay_mm"].tolist()[2] == 100.0
    b = seg[seg["section_id"] == "01-0002"]
    assert b["seg"].tolist() == [1, 2]
    assert np.isnan(b["seg_start"].iloc[0])        # GPS section without an opening date: age unknown
    assert b["seg_start"].iloc[1] == pytest.approx(1993 + JUL2)


def test_new_build_sps_uses_first_construction_date_as_age_origin(toy):
    toy["sections"].loc[1, ["gps_sps", "experiment"]] = ["S", "1"]
    seg = D.segments(toy["periods"], toy["sections"])
    assert seg[seg["section_id"] == "01-0002"]["seg_start"].iloc[0] == pytest.approx(1987.0)
    toy["sections"].loc[1, ["gps_sps", "experiment"]] = ["S", "5"]            # overlay experiment: not a new build
    seg = D.segments(toy["periods"], toy["sections"])
    assert np.isnan(seg[seg["section_id"] == "01-0002"]["seg_start"].iloc[0])


def test_series_age(toy):
    ser = D.series(toy, "iri")
    assert len(ser) == 10
    first = ser[(ser["section_id"] == "01-0001")].iloc[0]
    assert first["age"] == pytest.approx(1991.0 - (1985 + JUL2))
    after = ser[(ser["section_id"] == "01-0001") & (ser["seg"] == 2)].iloc[0]
    assert after["age"] == pytest.approx(1994.0 - (1993 + JUL2))
    assert after["ac_mm"] == 250.0 and after["seg_event"] == "thick_overlay"


def test_pairs_never_cross_a_treatment_and_trends_use_history_only(toy):
    pairs = D.make_pairs(D.series(toy, "iri"), "iri")
    assert len(pairs) == 9                                   # 3 + 3 for 01-0001, 0 + 3 for 01-0002
    assert (pairs["t1"] > pairs["t0"]).all()
    a1 = pairs[(pairs["section_id"] == "01-0001") & (pairs["seg"] == 1)].sort_values(["t0", "t1"])
    assert a1[["t0", "t1"]].values.tolist() == [[1991.0, 1992.0], [1991.0, 1993.0], [1992.0, 1993.0]]
    assert a1["y1"].max() == pytest.approx(1.4)              # 0.8 after the overlay is never a target here
    # origin 1991: a single visit, no trend -> every baseline equals the last value
    assert a1["pred_linear"].tolist()[:2] == pytest.approx([1.0, 1.0])
    assert a1["pred_exp"].tolist()[:2] == pytest.approx([1.0, 1.0])
    assert np.isnan(a1["hist_slope"].iloc[0]) and a1["n_hist"].tolist() == [1, 1, 2]
    # origin 1992: line through (1991, 1.0), (1992, 1.2) -> 1.4 ; exponential x1.2 a year -> 1.44
    last = a1.iloc[2]
    assert last["pred_linear"] == pytest.approx(1.4)
    assert last["pred_exp"] == pytest.approx(1.44)
    assert last["hist_slope"] == pytest.approx(0.2) and last["pred_last"] == pytest.approx(1.2)
    a2 = pairs[(pairs["section_id"] == "01-0001") & (pairs["seg"] == 2)].sort_values(["t0", "t1"]).iloc[2]
    assert a2["pred_linear"] == pytest.approx(0.90)
    assert a2["pred_exp"] == pytest.approx(0.85 * 0.85 / 0.80)
    assert a2["age0"] == pytest.approx(1995.0 - (1993 + JUL2))


def test_three_point_trend_hand_values():
    ser = pd.DataFrame({"section_id": "x", "site_id": "x", "seg": 1, "date": "", "cn": 1,
                        "t": [0.0, 1.0, 2.0, 4.0], "y": [1.0, 1.1, 1.3, 1.6], "age": np.nan})
    pairs = D.make_pairs(ser, "iri")
    assert len(pairs) == 6
    p = pairs[(pairs["t0"] == 2.0) & (pairs["t1"] == 4.0)].iloc[0]
    # OLS on (0, 1.0), (1, 1.1), (2, 1.3): slope 0.15, intercept 0.98333 -> 1.58333 at t = 4
    assert p["hist_slope"] == pytest.approx(0.15)
    assert p["pred_linear"] == pytest.approx(1.583333, abs=1e-6)
    q = pairs[(pairs["t0"] == 1.0) & (pairs["t1"] == 4.0)].iloc[0]
    assert q["pred_exp"] == pytest.approx(1.1 ** 4, abs=1e-9)       # 1.0 x 1.1^4 = 1.4641


def test_horizon_limits_and_clipping():
    ser = pd.DataFrame({"section_id": "x", "site_id": "x", "seg": 1, "date": "", "cn": 1,
                        "t": [2000.0, 2000.3, 2001.0, 2006.5], "y": [1.0, 1.0, 3.0, 3.0], "age": np.nan})
    pairs = D.make_pairs(ser, "iri")
    # 2000 -> 2000.3 is shorter than half a year, anything to 2006.5 is longer than five years
    assert sorted(zip(pairs["t0"], pairs["t1"])) == [(2000.0, 2001.0), (2000.3, 2001.0)]
    steep = pd.DataFrame({"section_id": "x", "site_id": "x", "seg": 1, "date": "", "cn": 1,
                          "t": [0.0, 1.0, 5.0], "y": [1.0, 4.0, 4.0], "age": np.nan})
    p = D.make_pairs(steep, "iri").query("t0 == 1.0").iloc[0]
    assert p["pred_linear"] == pytest.approx(10.0)                 # 1 + 3 x 5 = 16 clipped to the 10 m/km cap
    assert p["pred_exp"] == pytest.approx(10.0)                    # 4^5 clipped
    down = pd.DataFrame({"section_id": "x", "site_id": "x", "seg": 1, "date": "", "cn": 1,
                         "t": [0.0, 1.0, 5.0], "y": [3.0, 1.0, 1.0], "age": np.nan})
    assert D.make_pairs(down, "iri").query("t0 == 1.0").iloc[0]["pred_linear"] == pytest.approx(0.3)   # floor


def test_asof_features_and_traffic_do_not_look_ahead(toy):
    ds = D.build_dataset(toy, "iri")
    a = ds[ds["section_id"] == "01-0001"].sort_values(["t0", "t1"])
    by_origin = a.drop_duplicates("t0").set_index("t0")
    # rut: 4.0 measured June 1990 is the latest one before the 1991 and 1992 origins; the June 1992 value (6.0)
    # is after the 1992 origin; nothing measured yet on the new surface at the 1994 and 1995 origins
    assert by_origin.loc[1991.0, "rut_0"] == 4.0 and by_origin.loc[1992.0, "rut_0"] == 4.0
    assert np.isnan(by_origin.loc[1994.0, "rut_0"]) and np.isnan(by_origin.loc[1995.0, "rut_0"])
    assert np.isnan(by_origin.loc[1991.0, "crack_0"]) and by_origin.loc[1992.0, "crack_0"] == 3.0
    assert np.isnan(by_origin.loc[1994.0, "crack_0"]) and by_origin.loc[1995.0, "crack_0"] == 0.0
    # traffic: mean of the years up to the origin year, missing years skipped
    assert by_origin.loc[1991.0, "kesal"] == pytest.approx(150.0) and by_origin.loc[1991.0, "aadtt"] == pytest.approx(510.0)
    assert by_origin.loc[1992.0, "kesal"] == pytest.approx(150.0) and by_origin.loc[1992.0, "aadtt"] == pytest.approx(520.0)
    assert by_origin.loc[1994.0, "kesal"] == pytest.approx(200.0) and by_origin.loc[1994.0, "aadtt"] == pytest.approx(530.0)
    assert by_origin.loc[1995.0, "kesal"] == pytest.approx(250.0) and by_origin.loc[1995.0, "aadtt"] == pytest.approx(544.0)
    assert ds[ds["section_id"] == "01-0002"]["kesal"].isna().all()


def test_asof_tolerance_is_two_years(toy):
    toy["rut"].loc[0, "date"] = "1988-06-01"            # 2.6 years before the 1991 origin: too old to use
    ds = D.build_dataset(toy, "iri")
    assert ds[(ds["section_id"] == "01-0001") & (ds["t0"] == 1991.0)]["rut_0"].isna().all()


# ---- models -----------------------------------------------------------------------------------------------------
def _pairs(rows):
    return pd.DataFrame(rows, columns=["y0", "y1", "h"])


def test_global_rate_is_the_median_annual_rate():
    m = GlobalRate().fit(_pairs([(1.0, 1.1, 1.0), (1.0, 1.6, 2.0), (2.0, 2.4, 2.0), (1.0, 5.0, 1.0), (1.0, 0.5, 5.0)]))
    assert m.rate_ == pytest.approx(0.2)                 # rates 0.1, 0.3, 0.2, 4.0, -0.1
    assert m.predict(_pairs([(1.0, 0.0, 2.0), (3.0, 0.0, 0.5)])) == pytest.approx([1.4, 3.1])


def test_markov_chain_hand_values():
    train = _pairs([(0.5, 0.6, 1.0), (0.5, 1.5, 1.0), (1.5, 1.5, 1.0), (1.5, 2.5, 1.0), (1.5, 2.5, 1.2),
                    (2.5, 2.5, 3.0)])
    mk = MarkovChain([1.0, 2.0]).fit(train)
    assert mk.state([0.99, 1.0, 1.99, 2.0]).tolist() == [0, 1, 1, 2]
    # the three-year pair is not a one-year transition; state 2 is never an origin, so it keeps itself
    assert mk.counts_.tolist() == [[1.0, 1.0, 0.0], [0.0, 1.0, 2.0], [0.0, 0.0, 0.0]]
    assert mk.P_ == pytest.approx(np.array([[0.5, 0.5, 0.0], [0.0, 1 / 3, 2 / 3], [0.0, 0.0, 1.0]]))
    assert mk.means_ == pytest.approx([1.6 / 3, 1.5, 2.5])
    one = 0.5 * 1.6 / 3 + 0.5 * 1.5                                 # 1.016667
    two = 0.25 * 1.6 / 3 + (0.25 + 0.5 / 3) * 1.5 + (1 / 3) * 2.5   # 1.591667
    pred = mk.predict(_pairs([(0.5, 0, 1.0), (0.5, 0, 2.0), (0.5, 0, 0.5), (0.7, 0, 2.4), (2.2, 0, 4.0), (1.2, 0, 1.4)]))
    assert pred == pytest.approx([one, two, one, two, 2.5, 1.5 / 3 + 2.5 * 2 / 3])


def test_markov_window_excludes_other_horizons():
    train = _pairs([(0.5, 1.5, 0.74), (0.5, 1.5, 1.26), (0.5, 0.5, 0.75), (0.5, 0.5, 1.25)])
    mk = MarkovChain([1.0]).fit(train)
    assert mk.counts_.tolist() == [[2.0, 0.0], [0.0, 0.0]]


def _feature_pairs(n=400, seed=0):
    rng = np.random.default_rng(seed)
    df = pd.DataFrame({"y0": rng.uniform(0.8, 2.5, n), "h": rng.uniform(0.5, 5.0, n),
                       "kesal": rng.uniform(10, 1000, n)})
    for c in ["hist_slope", "n_hist", "hist_span", "age0", "seg_overlay_mm", "ac_mm", "unbound_base_mm",
              "bound_base_mm", "pcc_mm", "aadtt", "precip_mm", "temp_c", "freeze_index", "freeze_thaw",
              "days_above_32c"]:
        df[c] = np.nan
    df["seg_event"] = "original"
    df["family"] = "ACUB"
    df["y1"] = df["y0"] + 0.0004 * df["kesal"] * df["h"]            # rate driven by traffic only
    return df


def test_feature_frame_encodes_event_and_family():
    df = _feature_pairs(4)
    df["seg_event"] = ["original", "seal", "thick_overlay", "something_else"]
    df["family"] = ["ACUB", "ACPCC", "ACATB", "ACPCC"]
    X = feature_frame(df, ["rut_0"])
    assert X["event_code"].tolist()[:3] == [0.0, 1.0, 4.0] and np.isnan(X["event_code"].iloc[3])
    assert X["on_pcc"].tolist() == [0.0, 1.0, 0.0, 1.0]
    assert "rut_0" not in X.columns and "kesal" in X.columns          # an absent extra column is simply left out


def test_boosting_learns_a_traffic_driven_rate_that_a_global_rate_cannot():
    train, test = _feature_pairs(1500, 0), _feature_pairs(300, 1)
    gbm = BoostedIncrement([], lo=0.3, hi=10.0, max_iter=150).fit(train)
    err_gbm = mae(gbm.predict(test) - test["y1"])
    err_rate = mae(GlobalRate().fit(train).predict(test) - test["y1"])
    assert err_gbm < 0.08 and err_rate > 0.25
    assert gbm.predict(test).min() >= 0.3 and gbm.predict(test).max() <= 10.0


def test_boosting_predicts_the_increment_on_top_of_the_last_value():
    train = _feature_pairs(600, 0)
    train["y1"] = train["y0"] + 0.5                                   # constant increment
    gbm = BoostedIncrement([], max_iter=50).fit(train)
    test = _feature_pairs(50, 2)
    assert gbm.predict(test) == pytest.approx(test["y0"].to_numpy() + 0.5, abs=1e-6)
    clipped = BoostedIncrement([], lo=0.0, hi=1.0, max_iter=50).fit(train).predict(test)
    assert clipped.max() <= 1.0


# ---- validation ---------------------------------------------------------------------------------------------------
def test_fold_assignment_is_stable_and_site_disjoint():
    assert [fold_of(s) for s in ["48-10", "01-00", "30-01"]] == [fold_of(s) for s in ["48-10", "01-00", "30-01"]]
    assert [fold_of(s) for s in ["48-10", "01-00", "30-01"]] == [0, 0, 3]      # CRC-32 of the site id, modulo 5
    sites = [f"{i:02d}-{j:02d}" for i in range(1, 30) for j in range(4)]
    assert set(fold_of(s) for s in sites) == {0, 1, 2, 3, 4}
    pairs = pd.DataFrame({"site_id": np.repeat(sites, 3), "t0": np.tile([1995.0, 1999.5, 2001.0], len(sites)),
                          "t1": np.tile([1996.0, 2000.5, 2003.0], len(sites))})
    seen = np.zeros(len(pairs), dtype=int)
    for fold in range(5):
        tr, te = split(pairs, fold)
        assert not set(pairs.loc[tr, "site_id"]) & set(pairs.loc[te, "site_id"])
        assert (tr | te).all()
        seen += te
    assert (seen == 1).all()                                          # every pair is tested exactly once


def test_time_cut_keeps_training_before_and_testing_after():
    sites = [f"{i:02d}-00" for i in range(40)]
    pairs = pd.DataFrame({"site_id": np.repeat(sites, 3), "t0": np.tile([1995.0, 1999.5, 2000.0], len(sites)),
                          "t1": np.tile([1996.0, 2000.5, 2003.0], len(sites))})
    tr, te = split(pairs, 0, cutoff=2000.0)
    assert (pairs.loc[tr, "t1"] < 2000.0).all() and set(pairs.loc[tr, "t1"]) == {1996.0}
    assert (pairs.loc[te, "t0"] >= 2000.0).all() and set(pairs.loc[te, "t0"]) == {2000.0}
    assert not set(pairs.loc[tr, "site_id"]) & set(pairs.loc[te, "site_id"])
    assert te.sum() > 0 and tr.sum() > 0


def test_error_metrics_hand_values():
    e = np.array([1.0, -1.0, 2.0, -2.0])
    assert mae(e) == pytest.approx(1.5) and rmse(e) == pytest.approx(np.sqrt(2.5))


def test_cluster_bootstrap_point_values_and_degenerate_interval():
    # two sites with identical error content: every resample of sites gives the same MAE, so the interval collapses
    errors = {"m1": np.array([1.0, -2.0, 1.0, -2.0]), "m2": np.zeros(4)}
    res = cluster_bootstrap(errors, np.array(["a", "a", "b", "b"]), n_boot=200, seed=1)
    assert res["n_pairs"] == 4 and res["n_sites"] == 2
    m1 = res["methods"]["m1"]
    assert (m1["mae"], m1["mae_lo"], m1["mae_hi"]) == pytest.approx((1.5, 1.5, 1.5))
    assert m1["rmse"] == pytest.approx(np.sqrt(2.5)) and m1["rmse_lo"] == pytest.approx(np.sqrt(2.5))
    assert res["mae_diff"]["m1-m2"] == pytest.approx({"diff": 1.5, "lo": 1.5, "hi": 1.5})


def test_cluster_bootstrap_interval_reflects_between_site_spread():
    rng = np.random.default_rng(0)
    groups = np.repeat(np.arange(50), 10)
    site_level = np.repeat(rng.uniform(0.0, 2.0, 50), 10)             # error size differs by site
    res = cluster_bootstrap({"m": site_level}, groups, n_boot=500, seed=0)["methods"]["m"]
    assert res["mae_lo"] < res["mae"] < res["mae_hi"]
    assert res["mae_hi"] - res["mae_lo"] > 0.15                        # ~ 4 x 0.58 / sqrt(50) = 0.33
    assert res["mae_hi"] - res["mae_lo"] < 0.6


# ---- method comparison ----------------------------------------------------------------------------------------------
def _comparison(gbm_error):
    y = np.array([1.0, 2.0, 3.0, 4.0])
    pairs = pd.DataFrame({"y1": y, "site_id": ["a", "a", "b", "b"], "h": [1.0, 2.0, 2.5, 4.0],
                          "section_id": ["a1", "a1", "b1", "b1"]})
    preds = {"last": y + 0.5, "linear": y + 1.0, "exponential": y + 1.0, "global_rate": y + 0.2, "markov": y + 2.0,
             "gbm": y + gbm_error, "gbm_l2": y + 0.4}
    return A.summarise(pairs, preds, np.ones(4, dtype=bool), n_boot=100)


def test_summarise_names_best_baseline_and_sign_of_the_gain():
    res = _comparison(0.1)
    assert res["all"]["best_baseline"] == "global_rate"
    assert res["all"]["gbm_minus_best_baseline_mae"] == pytest.approx({"diff": -0.1, "lo": -0.1, "hi": -0.1})
    assert res["all"]["gbm_mae_change_pct"] == pytest.approx(-50.0)
    assert res["all"]["gbm_beats_best_baseline"] is True
    assert res["h_0.5_2"]["n_pairs"] == 2 and res["h_2_5"]["n_pairs"] == 2      # h = 2.0 belongs to the short bin
    assert set(res["all"]["mae_diff"]) == {"last-gbm", "linear-gbm", "exponential-gbm", "global_rate-gbm", "markov-gbm",
                                           "gbm-gbm_l2"}
    assert res["all"]["mae_diff"]["gbm-gbm_l2"]["diff"] == pytest.approx(-0.3)
    assert res["all"]["methods"]["gbm_l2"]["mae"] == pytest.approx(0.4)


def test_summarise_says_so_when_boosting_is_worse():
    res = _comparison(0.3)
    assert res["all"]["gbm_minus_best_baseline_mae"]["diff"] == pytest.approx(0.1)
    assert res["all"]["gbm_mae_change_pct"] == pytest.approx(50.0)
    assert res["all"]["gbm_beats_best_baseline"] is False


def test_out_of_fold_predictions_cover_only_test_pairs(toy):
    ds = D.build_dataset(toy, "iri")
    extra = pd.concat([ds.assign(site_id=f"{i:02d}-00", section_id=f"{i:02d}-0001") for i in range(2, 30)])
    preds, tested, sizes = A.out_of_fold(extra, "iri", gbm_params={"max_iter": 5, "min_samples_leaf": 2})
    assert tested.all() and not np.isnan(preds["gbm"]).any()
    assert sum(s["test_pairs"] for s in sizes) == len(extra)
    assert preds["last"] == pytest.approx(extra["pred_last"].to_numpy())
    assert preds["linear"] == pytest.approx(extra["pred_linear"].to_numpy())
    preds, tested, sizes = A.out_of_fold(extra, "iri", cutoff=1994.0, gbm_params={"max_iter": 5, "min_samples_leaf": 2})
    assert (extra.loc[tested, "t0"] >= 1994.0).all() and tested.sum() == (extra["t0"] >= 1994.0).sum()
    assert np.isnan(preds["gbm"][~tested]).all() and np.isnan(preds["gbm_l2"][~tested]).all()
    assert not np.isnan(preds["gbm_l2"][tested]).any()


# ---- treatment effects ----------------------------------------------------------------------------------------------
def test_segment_rate():
    assert T.segment_rate(np.array([0.0, 1.0, 2.0]), np.array([1.0, 1.2, 1.4])) == pytest.approx(0.2)
    assert np.isnan(T.segment_rate(np.array([0.0, 2.0]), np.array([1.0, 1.4])))            # two visits only
    assert np.isnan(T.segment_rate(np.array([0.0, 0.5, 1.9]), np.array([1.0, 1.2, 1.4])))  # shorter than two years


def test_event_table_hand_values(toy):
    ev = T.event_table(toy, "iri")
    assert len(ev) == 1                                   # the seal on 01-0002 has no visit in the three years before
    e = ev.iloc[0]
    assert (e["section_id"], e["event"], e["overlay_mm"]) == ("01-0001", "thick_overlay", 100.0)
    assert (e["pre"], e["post"]) == (1.4, 0.8) and e["drop"] == pytest.approx(0.6)
    assert e["pre_rate"] == pytest.approx(0.2) and e["post_rate"] == pytest.approx(0.05)
    assert e["t_event"] == pytest.approx(1993 + JUL2) and not e["designed"]
    assert len(T.event_table(toy, "iri", max_pre=6.0)) == 2
    assert len(T.event_table(toy, "iri", max_post=0.4)) == 0


def test_treatment_summary_hand_values():
    ev = pd.DataFrame({
        "event": ["thin_overlay"] * 8, "site_id": ["a", "a", "b", "b", "c", "c", "d", "d"], "overlay_mm": [30.0] * 8,
        "pre": [1.0, 2.0] * 4, "post": [0.9, 1.3] * 4,
        "pre_rate": [0.10] * 4 + [np.nan] + [0.10] * 3, "post_rate": [0.04] * 5 + [np.nan] + [0.04] * 2,
        "designed": [True] + [False] * 7})
    ev["drop"] = ev["pre"] - ev["post"]
    res = T.summarise(ev, n_boot=100)["thin_overlay"]
    assert res["n_events"] == 8 and res["n_sites"] == 4 and res["share_designed_experiment"] == pytest.approx(1 / 8)
    # every site holds the same two events, so the bootstrap interval of the mean drop collapses onto 0.4
    assert res["drop_mean"] == pytest.approx(0.4) and res["drop_lo"] == pytest.approx(0.4) and res["drop_hi"] == pytest.approx(0.4)
    assert res["drop_median"] == pytest.approx(0.4) and res["pre_median"] == pytest.approx(1.5)
    assert res["post_median"] == pytest.approx(1.1) and res["median_overlay_mm"] == 30.0
    # post = 0.5 + 0.4 x pre goes through both points
    assert res["post_fit_intercept"] == pytest.approx(0.5) and res["post_fit_slope"] == pytest.approx(0.4)
    assert res["n_with_rates"] == 6 and res["rate_change_mean"] == pytest.approx(-0.06)
    assert res["pre_rate_median"] == pytest.approx(0.10) and res["post_rate_median"] == pytest.approx(0.04)
    assert res["n_post_rate"] == 7 and res["post_rate_median_all"] == pytest.approx(0.04)
    assert "seal" not in T.summarise(ev)                    # classes with fewer than five events are left out
