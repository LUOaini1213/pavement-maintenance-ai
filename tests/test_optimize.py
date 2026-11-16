"""Hand-checked cases for the trajectory simulator, the MIP and the rule-based plans."""
import itertools

import numpy as np
import pytest

from pavement_ai import china
from pavement_ai.optimize import (Section, Treatment, evaluate_plan, greedy_rule, options, plan_benefit, pre_value,
                                  solve_mip, trajectory)

A = Treatment("light", cost=4.0, post_a=1.0, post_b=0.0, rate_after=None)
B = Treatment("heavy", cost=10.0, post_a=0.5, post_b=0.0, rate_after=None)


def test_trajectory_do_nothing_is_linear():
    sec = Section("s", iri0=2.0, rate=0.1)
    assert trajectory(sec, 4) == pytest.approx([2.1, 2.2, 2.3, 2.4])
    assert pre_value(sec, 1) == pytest.approx(2.0)
    assert pre_value(sec, 3) == pytest.approx(2.2)


def test_trajectory_with_treatment_hand_values():
    # treated in year 2: IRI before = 2.1, after = 0.6 + 0.2 * 2.1 = 1.02, then +0.05 a year
    sec = Section("s", iri0=2.0, rate=0.1)
    tr = Treatment("x", cost=1.0, post_a=0.6, post_b=0.2, rate_after=0.05)
    assert trajectory(sec, 4, 2, tr) == pytest.approx([2.1, 1.02, 1.07, 1.12])
    # same treatment but the section keeps its own rate afterwards
    keep = Treatment("x", cost=1.0, post_a=0.6, post_b=0.2, rate_after=None)
    assert trajectory(sec, 4, 2, keep) == pytest.approx([2.1, 1.02, 1.12, 1.22])
    # benefit = (2.2 - 1.02) + (2.3 - 1.07) + (2.4 - 1.12) = 3.69
    assert plan_benefit([sec], [tr], {0: (2, 0)}, 4) == pytest.approx(3.69)


def test_treatment_never_makes_a_section_rougher_and_respects_the_floor():
    tr = Treatment("x", cost=1.0, post_a=1.2, post_b=0.0, rate_after=None)
    assert tr.post(0.9) == pytest.approx(0.9)          # already smoother than what the treatment delivers
    assert tr.post(3.0) == pytest.approx(1.2)
    low = Treatment("y", cost=1.0, post_a=0.1, post_b=0.0, rate_after=None, floor=0.5)
    assert low.post(2.0) == pytest.approx(0.5)


def test_applicability_window_uses_rqi():
    tr = Treatment("thin", cost=1.0, post_a=0.8, post_b=0.0, rate_after=None, min_rqi=85.0)
    # (100/85 - 1) / 0.026 = 6.78733, ln = 1.915057, / 0.65 = 2.946242 m/km
    limit = china.iri_for_rqi(85.0)
    assert limit == pytest.approx(2.946242, abs=1e-5)
    assert tr.allowed(limit - 0.01) and not tr.allowed(limit + 0.01)
    sec = Section("s", iri0=limit + 0.5, rate=0.0)
    assert options([sec], [tr], 3) == []


def test_options_cost_scales_with_length():
    sec = Section("s", iri0=2.0, rate=0.0, length=2.5)
    opts = options([sec], [A], 1)
    assert len(opts) == 1
    assert opts[0]["cost"] == pytest.approx(10.0)
    assert opts[0]["benefit"] == pytest.approx((2.0 - 1.0) * 2.5)


def test_mip_hand_case_beats_worst_first():
    # benefits in the single year: light 2.0 / 1.0 / 0.5, heavy 2.5 / 1.5 / 1.0; budget 10.
    # heavy on the worst section uses all the money (2.5); light on the two worst costs 8 and gives 3.0.
    secs = [Section("a", 3.0, 0.0), Section("b", 2.0, 0.0), Section("c", 1.5, 0.0)]
    res = solve_mip(secs, [A, B], [10.0])
    assert res["status"] == "Optimal"
    assert res["plan"] == {0: (1, 0), 1: (1, 0)}
    assert res["objective"] == pytest.approx(3.0)
    wf = greedy_rule(secs, [A, B], [10.0], "worst", lambda s, cur, age: 1 if cur >= 2.5 else 0)
    assert wf["plan"] == {0: (1, 1)}
    assert plan_benefit(secs, [A, B], wf["plan"], 1) == pytest.approx(2.5)


def test_mip_respects_each_years_budget_and_one_treatment_per_section():
    secs = [Section(str(i), 2.0 + 0.2 * i, 0.05) for i in range(6)]
    budgets = [8.0, 4.0, 0.0]
    res = solve_mip(secs, [A, B], budgets)
    ev = evaluate_plan(secs, [A, B], res["plan"], 3)
    for spent, cap in zip(ev["spend_by_year"], budgets):
        assert spent <= cap + 1e-9
    assert ev["spend_by_year"][2] == 0.0
    assert ev["treated_sections"] == len(res["plan"]) <= 3
    assert res["objective"] == pytest.approx(plan_benefit(secs, [A, B], res["plan"], 3))


def brute_force(secs, treatments, budgets):
    horizon = len(budgets)
    opts = options(secs, treatments, horizon)
    per_section = [[None] + [o for o in opts if o["i"] == i] for i in range(len(secs))]
    best = 0.0
    for combo in itertools.product(*per_section):
        spend = [0.0] * horizon
        gain = 0.0
        for o in combo:
            if o is not None:
                spend[o["t"] - 1] += o["cost"]
                gain += o["benefit"]
        if all(s <= b + 1e-9 for s, b in zip(spend, budgets)):
            best = max(best, gain)
    return best


@pytest.mark.parametrize("seed", [0, 1, 2, 3])
def test_mip_matches_brute_force_on_small_networks(seed):
    rng = np.random.default_rng(seed)
    secs = [Section(str(i), float(rng.uniform(1.0, 3.5)), float(rng.uniform(0.0, 0.15)),
                    length=float(rng.choice([0.5, 1.0, 2.0]))) for i in range(5)]
    trs = [Treatment("p", 3.0, 0.2, 0.7, 0.03, min_rqi=85.0), Treatment("m", 7.0, 0.9, 0.1, 0.05),
           Treatment("M", 15.0, 0.7, 0.0, 0.04)]
    budgets = [9.0, 6.0]
    res = solve_mip(secs, trs, budgets)
    assert res["objective"] == pytest.approx(brute_force(secs, trs, budgets), abs=1e-6)
    assert res["mip_gap"] <= 1e-6


def test_worst_first_order_and_skip_when_unaffordable():
    secs = [Section("a", 3.0, 0.0), Section("b", 2.8, 0.0), Section("c", 1.2, 0.0)]
    # worst gets heavy (10) -> money left 2, second is skipped (heavy does not fit), third gets nothing (choose None)
    plan = greedy_rule(secs, [A, B], [12.0], "worst", lambda s, cur, age: 1 if cur >= 2.5 else None)["plan"]
    assert plan == {0: (1, 1)}
    # with light for the smooth one the leftover is still too small (4 > 2)
    plan = greedy_rule(secs, [A, B], [12.0], "worst", lambda s, cur, age: 1 if cur >= 2.5 else 0)["plan"]
    assert plan == {0: (1, 1)}
    plan = greedy_rule(secs, [A, B], [14.0], "worst", lambda s, cur, age: 1 if cur >= 2.5 else 0)["plan"]
    assert plan == {0: (1, 1), 2: (1, 0)}


def test_worst_first_uses_current_condition_in_later_years():
    # b starts smoother but deteriorates fast: in year 2 it is the worst one
    secs = [Section("a", 2.0, 0.0), Section("b", 1.8, 0.5)]
    plan = greedy_rule(secs, [A], [0.0, 4.0], "worst", lambda s, cur, age: 0)["plan"]
    assert plan == {1: (2, 0)}


def test_fixed_cycle_takes_oldest_first_and_waits_for_the_cycle():
    secs = [Section("a", 1.0, 0.0, age=2.0), Section("b", 1.1, 0.0, age=7.0), Section("c", 3.0, 0.0, age=5.0)]
    rule = dict(order="oldest", choose=lambda s, cur, age: 0, eligible=lambda s, cur, age: age >= 6.0)
    plan = greedy_rule(secs, [A], [4.0, 4.0, 4.0], **rule)["plan"]
    # year 1: only b is 6+ years old; year 2: c reaches 6; a reaches 6 only after year 4
    assert plan == {1: (1, 0), 2: (2, 0)}


def test_evaluate_plan_hand_values():
    secs = [Section("a", 3.0, 0.1), Section("b", 1.0, 0.1, length=3.0)]
    ev = evaluate_plan(secs, [A], {0: (1, 0)}, 2)
    # a: [1.0, 1.1]; b: [1.1, 1.2]; length-weighted means: (1.0 + 3.3) / 4 and (1.1 + 3.6) / 4
    assert ev["mean_iri_by_year"] == pytest.approx([1.075, 1.175])
    assert ev["mean_iri_horizon"] == pytest.approx(1.125)
    assert ev["mean_iri_final"] == pytest.approx(1.175)
    assert ev["spend_by_year"] == [4.0, 0.0] and ev["total_spend"] == 4.0
    assert ev["treatments"] == {"light": 1} and ev["treated_sections"] == 1
    assert ev["treatments_by_year"] == [{"light": 1}, {"light": 0}]
    assert ev["share_rqi_ge_90_final"] == pytest.approx(1.0)
    assert ev["share_iri_le_1p5_final"] == pytest.approx(1.0)
    assert ev["max_iri_final"] == pytest.approx(1.2)
    nothing = evaluate_plan(secs, [A], {}, 2)
    # a ends at 3.2 m/km: RQI = 100 / (1 + 0.026 exp(2.08)) = 82.8 -> not excellent; a is 1 of 4 lane-km
    assert nothing["share_rqi_ge_90_final"] == pytest.approx(0.75)
    assert nothing["share_iri_le_1p5_final"] == pytest.approx(0.75)
    assert nothing["mean_iri_by_year"] == pytest.approx([(3.1 + 3.3) / 4, (3.2 + 3.6) / 4])


def test_section_eligibility_limits_the_options_and_the_rules():
    only_heavy = Section("a", 3.0, 0.0, eligible=frozenset({"heavy"}))
    anything = Section("b", 3.0, 0.0)
    assert {o["k"] for o in options([only_heavy], [A, B], 1)} == {1}
    assert {o["k"] for o in options([anything], [A, B], 1)} == {0, 1}
    assert only_heavy.may_receive(B) and not only_heavy.may_receive(A) and anything.may_receive(A)
    # the rule asks for the light treatment; the section that may not have it is passed over
    plan = greedy_rule([only_heavy, anything], [A, B], [20.0], "worst", lambda s, cur, age: 0)["plan"]
    assert plan == {1: (1, 0)}
    res = solve_mip([only_heavy, anything], [A, B], [14.0])
    assert res["plan"] == {0: (1, 1), 1: (1, 0)} and res["objective"] == pytest.approx(2.5 + 2.0)
