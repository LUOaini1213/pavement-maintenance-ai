"""Part B: multi-year network-level treatment selection under annual budgets.

Model (one decision per section inside the planning horizon):

    x[i,t,k] = 1  if section i receives treatment k in year t
    max  sum b[i,t,k] x[i,t,k]
    s.t. sum_{t,k} x[i,t,k] <= 1                      for every section i
         sum_{i,k} cost[i,k] x[i,t,k] <= budget[t]    for every year t
         x binary

b[i,t,k] is the reduction of the section's length-weighted IRI summed over the years of the horizon, compared with
doing nothing. Because a section is treated at most once, its whole trajectory is known for each (t, k) and the
model stays linear. It is solved with HiGHS (highspy). The same simulator scores the rule-based plans.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .china import rqi


@dataclass(frozen=True)
class Treatment:
    name: str
    cost: float                 # per lane-km
    post_a: float               # IRI after = post_a + post_b * IRI before (never above the IRI before)
    post_b: float
    rate_after: float | None    # annual IRI growth after treatment; None keeps the section's own rate
    min_rqi: float | None = None   # treatment allowed only while RQI(before) >= min_rqi
    floor: float = 0.5          # lowest IRI a treatment can deliver, m/km

    def post(self, pre: float) -> float:
        return float(min(pre, max(self.floor, self.post_a + self.post_b * pre)))

    def allowed(self, pre: float) -> bool:
        return self.min_rqi is None or rqi(pre) >= self.min_rqi


@dataclass(frozen=True)
class Section:
    sid: str
    iri0: float
    rate: float                 # do-nothing annual IRI growth, m/km per year
    length: float = 1.0         # lane-km
    age: float = 0.0            # years since the surface was last renewed, at the start of the plan
    eligible: frozenset | None = None   # names of the treatments this section may receive (None = any)

    def may_receive(self, tr: "Treatment") -> bool:
        return self.eligible is None or tr.name in self.eligible


def trajectory(sec: Section, horizon: int, year: int | None = None, tr: Treatment | None = None) -> np.ndarray:
    """IRI at the end of years 1..horizon. A treatment in `year` acts on the IRI at the end of the year before."""
    out = np.empty(horizon)
    s, r = sec.iri0, sec.rate
    for y in range(1, horizon + 1):
        if tr is not None and y == year:
            s = tr.post(s)
            if tr.rate_after is not None:
                r = tr.rate_after
        else:
            s = s + r
        out[y - 1] = s
    return out


def pre_value(sec: Section, year: int) -> float:
    """IRI at the end of the year before `year` when nothing has been done."""
    return sec.iri0 + sec.rate * (year - 1)


def options(sections: list[Section], treatments: list[Treatment], horizon: int) -> list[dict]:
    """Every allowed (section, year, treatment) with its cost and benefit."""
    out = []
    for i, sec in enumerate(sections):
        base = trajectory(sec, horizon)
        for t in range(1, horizon + 1):
            pre = pre_value(sec, t)
            for k, tr in enumerate(treatments):
                if not (sec.may_receive(tr) and tr.allowed(pre)):
                    continue
                gain = float((base - trajectory(sec, horizon, t, tr)).sum() * sec.length)
                out.append({"i": i, "t": t, "k": k, "cost": tr.cost * sec.length, "benefit": gain})
    return out


def solve_mip(sections: list[Section], treatments: list[Treatment], budgets: list[float],
              mip_rel_gap: float = 1e-6, time_limit: float = 600.0) -> dict:
    import highspy
    from scipy.sparse import csc_matrix

    horizon = len(budgets)
    opts = [o for o in options(sections, treatments, horizon) if o["benefit"] > 0.0]
    n, m = len(opts), len(sections) + horizon
    if n == 0:
        return {"plan": {}, "objective": 0.0, "status": "no_options", "mip_gap": 0.0, "n_vars": 0, "n_rows": m}
    rows = np.concatenate([[o["i"] for o in opts], [len(sections) + o["t"] - 1 for o in opts]])
    cols = np.concatenate([np.arange(n), np.arange(n)])
    vals = np.concatenate([np.ones(n), [o["cost"] for o in opts]])
    a = csc_matrix((vals, (rows, cols)), shape=(m, n))
    lp = highspy.HighsLp()
    lp.num_col_, lp.num_row_ = n, m
    lp.col_cost_ = np.array([o["benefit"] for o in opts], dtype=float)
    lp.col_lower_, lp.col_upper_ = np.zeros(n), np.ones(n)
    lp.row_lower_ = np.full(m, -highspy.kHighsInf)
    lp.row_upper_ = np.concatenate([np.ones(len(sections)), np.asarray(budgets, dtype=float)])
    lp.a_matrix_.format_ = highspy.MatrixFormat.kColwise
    lp.a_matrix_.start_ = a.indptr
    lp.a_matrix_.index_ = a.indices
    lp.a_matrix_.value_ = a.data
    lp.integrality_ = [highspy.HighsVarType.kInteger] * n
    lp.sense_ = highspy.ObjSense.kMaximize
    h = highspy.Highs()
    h.setOptionValue("output_flag", False)
    h.setOptionValue("mip_rel_gap", mip_rel_gap)
    h.setOptionValue("time_limit", time_limit)
    h.setOptionValue("random_seed", 0)
    h.setOptionValue("threads", 1)
    h.passModel(lp)
    h.run()
    x = np.asarray(h.getSolution().col_value)
    info = h.getInfo()
    plan = {opts[j]["i"]: (opts[j]["t"], opts[j]["k"]) for j in np.flatnonzero(x > 0.5)}
    return {"plan": plan, "objective": float(info.objective_function_value),
            "status": h.modelStatusToString(h.getModelStatus()), "mip_gap": float(info.mip_gap),
            "dual_bound": float(info.mip_dual_bound), "n_vars": n, "n_rows": m}


def greedy_rule(sections: list[Section], treatments: list[Treatment], budgets: list[float], order: str,
                choose, eligible=None) -> dict:
    """Year-by-year rule: rank the untreated sections, give each the treatment `choose` names, stop when the
    year's money is gone (a section that does not fit is skipped and the next one is tried).

    order = "worst"  : highest current IRI first (worst-first)
    order = "oldest" : oldest surface first (fixed cycle)
    choose(section, current_iri, current_age) -> index of the treatment, or None for nothing
    eligible(section, current_iri, current_age) -> bool, optional extra filter
    """
    plan: dict[int, tuple[int, int]] = {}
    for t in range(1, len(budgets) + 1):
        left = budgets[t - 1]
        cand = []
        for i, sec in enumerate(sections):
            if i in plan:
                continue
            cur, age = pre_value(sec, t), sec.age + (t - 1)
            if eligible is not None and not eligible(sec, cur, age):
                continue
            cand.append((-(cur if order == "worst" else age), i, cur, age))
        for _key, i, cur, age in sorted(cand):
            k = choose(sections[i], cur, age)
            if k is None or not (sections[i].may_receive(treatments[k]) and treatments[k].allowed(cur)):
                continue
            cost = treatments[k].cost * sections[i].length
            if cost <= left + 1e-9:
                plan[i] = (t, k)
                left -= cost
    return {"plan": plan}


def evaluate_plan(sections: list[Section], treatments: list[Treatment], plan: dict, horizon: int) -> dict:
    """Network indicators of a plan: IRI by year, spend by year, treatments by type, RQI grade shares at the end."""
    traj = np.stack([trajectory(sec, horizon, *(plan[i][0], treatments[plan[i][1]]) if i in plan else (None, None))
                     for i, sec in enumerate(sections)])
    length = np.array([s.length for s in sections])
    mean_by_year = (traj * length[:, None]).sum(axis=0) / length.sum()
    spend = np.zeros(horizon)
    count = {tr.name: 0 for tr in treatments}
    by_year = [{tr.name: 0 for tr in treatments} for _ in range(horizon)]
    for i, (t, k) in plan.items():
        spend[t - 1] += treatments[k].cost * sections[i].length
        count[treatments[k].name] += 1
        by_year[t - 1][treatments[k].name] += 1
    end_rqi = np.array([rqi(v) for v in traj[:, -1]])
    return {
        "mean_iri_by_year": [float(v) for v in mean_by_year],
        "mean_iri_horizon": float(mean_by_year.mean()),
        "mean_iri_final": float(mean_by_year[-1]),
        "spend_by_year": [float(v) for v in spend],
        "total_spend": float(spend.sum()),
        "treated_sections": int(len(plan)),
        "treatments": count,
        "treatments_by_year": by_year,
        "share_rqi_ge_90_final": float((length * (end_rqi >= 90.0)).sum() / length.sum()),
        "share_iri_le_1p5_final": float((length * (traj[:, -1] <= 1.5)).sum() / length.sum()),
        "max_iri_final": float(traj[:, -1].max()),
    }


def plan_benefit(sections: list[Section], treatments: list[Treatment], plan: dict, horizon: int) -> float:
    """Length-weighted IRI-years saved against doing nothing (the MIP objective of a plan)."""
    total = 0.0
    for i, (t, k) in plan.items():
        sec = sections[i]
        total += float((trajectory(sec, horizon) - trajectory(sec, horizon, t, treatments[k])).sum() * sec.length)
    return total
