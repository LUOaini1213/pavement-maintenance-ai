"""Mutation test of the test suite.

Each mutant is one deliberate bug: a single exact-string replacement in the source. For every mutant the files
the tests need are copied to a scratch directory, the bug is applied there and the whole pytest suite runs. A
mutant is *killed* when the suite fails.

Order of work:
  1. the unmodified suite must pass;
  2. the control mutant (an unmissable bug) must be killed - otherwise the harness itself is broken and it stops;
  3. all other mutants run.

    python mutation/run_mutants.py --label first      # before writing tests for survivors
    python mutation/run_mutants.py --label final      # after

Both runs are kept in results/mutation.json.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
COPY = ["src", "tests", "scripts", "docs", "data/derived", "data/raw_manifest.json", "results", "README.md",
        "pytest.ini"]
OUT = REPO / "results" / "mutation.json"

CONTROL = ("C00", "src/pavement_ai/china.py", 'return 100.0 / (1.0 + c["a0"] * math.exp(c["a1"] * iri))',
           "return 0.0", "control: RQI always zero")

# (id, file, original snippet, mutated snippet, what the bug means)
MUTANTS = [
    # ---- JTG indices ------------------------------------------------------------------------------------------
    ("M01", "src/pavement_ai/china.py", '"expressway_class1": {"a0": 0.026, "a1": 0.65}',
     '"expressway_class1": {"a0": 0.0185, "a1": 0.65}', "expressway RQI uses the a0 of the lower classes"),
    ("M02", "src/pavement_ai/china.py", 'return 100.0 / (1.0 + c["a0"] * math.exp(c["a1"] * iri))',
     'return 100.0 / (1.0 + c["a0"] * math.exp(c["a1"]) * iri)', "RQI: IRI outside the exponential"),
    ("M03", "src/pavement_ai/china.py", 'return math.log((100.0 / target_rqi - 1.0) / c["a0"]) / c["a1"]',
     'return math.log((100.0 / target_rqi - 1.0) * c["a0"]) / c["a1"]', "inverse RQI multiplies by a0"),
    ("M04", "src/pavement_ai/china.py", "return 90.0 - RDI_A1 * (rut_mm - RDI_RDA)",
     "return 90.0 - RDI_A1 * rut_mm", "RDI second branch not measured from RDa"),
    ("M05", "src/pavement_ai/china.py", "    if rut_mm <= RDI_RDB:", "    if rut_mm < RDI_RDB:",
     "RDI at exactly RDb"),
    ("M06", "src/pavement_ai/china.py", "PCI_A0_ASPHALT, PCI_A1_ASPHALT = 15.00, 0.412",
     "PCI_A0_ASPHALT, PCI_A1_ASPHALT = 10.66, 0.461", "PCI uses the cement-concrete coefficients"),
    ("M07", "src/pavement_ai/china.py", "        if index >= limit:", "        if index > limit:",
     "grade limits exclusive instead of inclusive"),
    ("M08", "src/pavement_ai/china.py",
     '"thin_overlay": {"table": "5.3.2", "pci_min": 85.0, "rqi_min": 85.0, "rdi_min": 80.0}',
     '"thin_overlay": {"table": "5.3.2", "pci_min": 85.0, "rqi_min": 88.0, "rdi_min": 85.0}',
     "thin-overlay window takes the ultra-thin values"),
    # ---- events -------------------------------------------------------------------------------------------------
    ("M09", "src/pavement_ai/events.py", "        if overlay_mm <= THIN_OVERLAY_MAX_MM:",
     "        if overlay_mm < THIN_OVERLAY_MAX_MM:", "a 40 mm overlay no longer counts as thin"),
    ("M10", "src/pavement_ai/events.py", "        if overlay_mm < THICK_OVERLAY_MIN_MM:",
     "        if overlay_mm <= THICK_OVERLAY_MIN_MM:", "a 75 mm overlay counted as medium"),
    ("M11", "src/pavement_ai/events.py", "SEAL_CODES = frozenset({28, 29, 30, 31, 32, 33, 34})",
     "SEAL_CODES = frozenset({28, 29, 30, 31, 32, 34})", "slurry seal (33) dropped from the seal codes"),
    ("M12", "src/pavement_ai/events.py",
     "RESETTING = frozenset({ORIGINAL, SEAL, THIN_OVERLAY, MEDIUM_OVERLAY, THICK_OVERLAY, OVERLAY_UNKNOWN})",
     "RESETTING = frozenset({ORIGINAL, ROUTINE, SEAL, THIN_OVERLAY, MEDIUM_OVERLAY, THICK_OVERLAY, OVERLAY_UNKNOWN})",
     "routine work (crack sealing) starts a new segment"),
    ("M13", "src/pavement_ai/events.py", "    if codes & OVERLAY_CODES:\n", "    if codes & SEAL_CODES:\n        return SEAL\n    if codes & OVERLAY_CODES:\n",
     "a seal recorded with an overlay outranks the overlay"),
    # ---- pairs and features ---------------------------------------------------------------------------------------
    ("M14", "src/pavement_ai/data.py", "    return (d.dt.year + (d.dt.dayofyear - 1) / 365.25).to_numpy(dtype=float)",
     "    return (d.dt.year + d.dt.month / 12.0).to_numpy(dtype=float)", "decimal year from the month number"),
    ("M15", "src/pavement_ai/data.py", "    b = float(((t - tm) * (y - ym)).sum() / sxx)",
     "    b = float(((t - tm) * (y - ym)).sum() / len(t))", "OLS slope divided by n instead of Sxx"),
    ("M16", "src/pavement_ai/data.py", "                a, b = ols_line(t[:n_hist], y[:n_hist])\n",
     "                a, b = ols_line(t, y)\n", "trend baseline fitted on the whole segment (look-ahead leak)"),
    ("M17", "src/pavement_ai/data.py", "                if h > max_h:\n                    break",
     "                if h > max_h + 5.0:\n                    break", "maximum horizon not enforced"),
    ("M18", "src/pavement_ai/data.py", '    for (_sid, _seg), g in ser.groupby(["section_id", "seg"], sort=False):',
     '    for _sid, g in ser.groupby("section_id", sort=False):', "pairs run across a treatment"),
    ("M19", "src/pavement_ai/data.py", 'by=["section_id", "seg"], direction="backward",\n                      tolerance=tolerance)',
     'by=["section_id", "seg"], direction="nearest",\n                      tolerance=tolerance)',
     "other indicators attached from the nearest visit, also future ones"),
    ("M20", "src/pavement_ai/data.py", 'on="year", by="section_id", direction="backward")',
     'on="year", by="section_id", direction="forward")', "traffic taken from years after the origin"),
    ("M21", "src/pavement_ai/data.py", "            elif not (sid in new_build.index and bool(new_build[sid])):\n                start = np.nan",
     "            elif not (sid in new_build.index and bool(new_build[sid])):\n                pass",
     "monitoring start used as construction date"),
    # ---- models ---------------------------------------------------------------------------------------------------
    ("M22", "src/pavement_ai/models.py", 'self.rate_ = float(np.median((pairs["y1"] - pairs["y0"]) / pairs["h"]))',
     'self.rate_ = float(np.mean((pairs["y1"] - pairs["y0"]) / pairs["h"]))', "global rate is the mean rate"),
    ("M23", "src/pavement_ai/models.py", 'return (pairs["y0"] + self.rate_ * pairs["h"]).to_numpy(dtype=float)',
     'return (pairs["y0"] + self.rate_).to_numpy(dtype=float)', "global rate ignores the horizon"),
    ("M24", "src/pavement_ai/models.py", 'return np.searchsorted(self.edges, np.asarray(y, dtype=float), side="right")',
     'return np.searchsorted(self.edges, np.asarray(y, dtype=float), side="left")', "Markov state boundaries shifted"),
    ("M25", "src/pavement_ai/models.py", "steps = np.maximum(1, np.rint(pairs[\"h\"].to_numpy(dtype=float)).astype(int))",
     "steps = np.maximum(1, np.floor(pairs[\"h\"].to_numpy(dtype=float)).astype(int))", "Markov steps rounded down"),
    ("M26", "src/pavement_ai/models.py", "np.add.at(counts, (self.state(one[\"y0\"]), self.state(one[\"y1\"])), 1.0)",
     "np.add.at(counts, (self.state(one[\"y1\"]), self.state(one[\"y0\"])), 1.0)", "Markov transition matrix transposed"),
    ("M27", "src/pavement_ai/models.py", "step = self.model_.predict(X)\n        return np.clip(pairs[\"y0\"].to_numpy(dtype=float) + step, self.lo, self.hi)",
     "step = self.model_.predict(X)\n        return np.clip(step, self.lo, self.hi)", "boosting returns the increment only"),
    ("M28", "src/pavement_ai/models.py", 'X["on_pcc"] = pairs["family"].astype(str).str.endswith("PCC").to_numpy(dtype=float)',
     'X["on_pcc"] = pairs["family"].astype(str).str.startswith("AC").to_numpy(dtype=float)', "overlay-on-concrete flag always on"),
    # ---- validation -----------------------------------------------------------------------------------------------
    ("M29", "src/pavement_ai/validation.py", '        train = train & (pairs["t1"].to_numpy() < cutoff)',
     '        train = train & (pairs["t0"].to_numpy() < cutoff)', "training pairs may end after the time cut"),
    ("M30", "src/pavement_ai/validation.py", '        test = test & (pairs["t0"].to_numpy() >= cutoff)',
     '        test = test & (pairs["t1"].to_numpy() >= cutoff)', "test pairs may start before the time cut"),
    ("M31", "src/pavement_ai/validation.py", "    train = f != fold\n", "    train = np.ones(len(pairs), dtype=bool)\n",
     "test sites also used for training (leak)"),
    ("M32", "src/pavement_ai/validation.py", "    return float(np.sqrt(np.mean(np.square(err))))",
     "    return float(np.mean(np.square(err)))", "RMSE without the square root"),
    ("M33", "src/pavement_ai/validation.py", "    idx = rng.integers(0, g, size=(n_boot, g))",
     "    idx = np.tile(np.arange(g), (n_boot, 1))", "bootstrap does not resample (zero-width intervals)"),
    ("M34", "src/pavement_ai/deterioration.py", 'gain = {"diff": -d["diff"], "lo": -d["hi"], "hi": -d["lo"]}',
     'gain = {"diff": d["diff"], "lo": d["lo"], "hi": d["hi"]}', "sign of boosting-minus-baseline flipped"),
    ("M35", "src/pavement_ai/deterioration.py", 'best = min(BASELINES, key=lambda m: res["methods"][m]["mae"])',
     'best = max(BASELINES, key=lambda m: res["methods"][m]["mae"])', "boosting compared with the worst baseline"),
    ("M36", "src/pavement_ai/deterioration.py", 'res["gbm_beats_best_baseline"] = bool(gain["hi"] < 0.0)',
     'res["gbm_beats_best_baseline"] = bool(gain["diff"] < 0.0)', "'beats' declared without looking at the interval"),
    # ---- treatment effects ------------------------------------------------------------------------------------------
    ("M37", "src/pavement_ai/treatment.py", '"drop": yb[-1] - ya[0],', '"drop": yb[0] - ya[0],',
     "drop measured from the first visit on the old surface"),
    ("M38", "src/pavement_ai/treatment.py", "t_event - tb[-1] > max_pre or ta[0] - t_event > max_post",
     "t_event - tb[-1] > max_pre and ta[0] - t_event > max_post", "before/after gap limits not both enforced"),
    ("M39", "src/pavement_ai/treatment.py", "    if len(t) < min_obs or (t.max() - t.min()) < min_span:",
     "    if len(t) < 2:", "rates from two visits or very short spans"),
    ("M40", "src/pavement_ai/treatment.py", 'a, b = ols_line(e["pre"].to_numpy(), e["post"].to_numpy())',
     'a, b = ols_line(e["post"].to_numpy(), e["pre"].to_numpy())', "after-vs-before fit regressed the wrong way round"),
    # ---- optimisation -----------------------------------------------------------------------------------------------
    ("M41", "src/pavement_ai/optimize.py", "return float(min(pre, max(self.floor, self.post_a + self.post_b * pre)))",
     "return float(max(self.floor, self.post_a + self.post_b * pre))", "a treatment can make a smooth section rougher"),
    ("M42", "src/pavement_ai/optimize.py", "            if tr.rate_after is not None:\n                r = tr.rate_after",
     "            if tr.rate_after is not None:\n                r = sec.rate", "growth rate after treatment ignored"),
    ("M43", "src/pavement_ai/optimize.py", "    return sec.iri0 + sec.rate * (year - 1)", "    return sec.iri0 + sec.rate * year",
     "condition before treatment taken one year late"),
    ("M44", "src/pavement_ai/optimize.py", 'out.append({"i": i, "t": t, "k": k, "cost": tr.cost * sec.length, "benefit": gain})',
     'out.append({"i": i, "t": t, "k": k, "cost": tr.cost, "benefit": gain})', "cost ignores section length"),
    ("M45", "src/pavement_ai/optimize.py", "    rows = np.concatenate([[o[\"i\"] for o in opts], [len(sections) + o[\"t\"] - 1 for o in opts]])",
     "    rows = np.concatenate([[o[\"i\"] for o in opts], [len(sections) for o in opts]])",
     "all years share the first year's budget row"),
    ("M46", "src/pavement_ai/optimize.py", "    lp.sense_ = highspy.ObjSense.kMaximize", "    lp.sense_ = highspy.ObjSense.kMinimize",
     "MIP minimises the benefit"),
    ("M47", "src/pavement_ai/optimize.py", '            cand.append((-(cur if order == "worst" else age), i, cur, age))',
     '            cand.append(((cur if order == "worst" else age), i, cur, age))', "rules rank best-first / youngest-first"),
    ("M48", "src/pavement_ai/optimize.py", "            if cost <= left + 1e-9:\n                plan[i] = (t, k)\n                left -= cost",
     "            if cost <= left + 1e-9:\n                plan[i] = (t, k)", "rule never deducts what it spends"),
    ("M49", "src/pavement_ai/optimize.py", "        return self.eligible is None or tr.name in self.eligible", "        return True",
     "section eligibility ignored"),
    ("M50", "src/pavement_ai/optimize.py", "        return self.min_rqi is None or rqi(pre) >= self.min_rqi", "        return True",
     "RQI window of the preventive treatment ignored"),
    ("M51", "src/pavement_ai/optimize.py", "    mean_by_year = (traj * length[:, None]).sum(axis=0) / length.sum()",
     "    mean_by_year = traj.mean(axis=0)", "network mean not length-weighted"),
    # ---- pipeline glue ----------------------------------------------------------------------------------------------
    ("M52", "src/pavement_ai/pipeline.py", '    if pci >= o["preventive_min_pci"] and rdi >= o["preventive_min_rdi"]:',
     '    if pci >= o["preventive_min_pci"] or rdi >= o["preventive_min_rdi"]:', "thin overlay allowed on PCI or RDI alone"),
    ("M53", "src/pavement_ai/pipeline.py", '    if pci >= o["minor_rehab_min_pci"]:\n', '    if pci >= 0.0:\n',
     "resurfacing allowed on any cracking"),
    ("M54", "src/pavement_ai/pipeline.py", "            return x0 + (x1 - x0) * (target - y0) / (y1 - y0)",
     "            return x0 + (x1 - x0) * (target - y0) / y1", "budget-to-match interpolation wrong"),
    ("M55", "src/pavement_ai/pipeline.py", "        if cur >= wf[\"major_iri\"]:\n            return 2",
     "        if cur >= wf[\"major_iri\"]:\n            return 1", "worst-first never picks the thick overlay by roughness"),
    ("M56", "src/pavement_ai/pipeline.py", 'out.append(Treatment(level, per_mile / config.LANE_MILE_KM,',
     'out.append(Treatment(level, per_mile * config.LANE_MILE_KM,', "cost per lane-mile converted the wrong way"),
    ("M57", "src/pavement_ai/pipeline.py", '    latest = latest[year >= o["network_min_last_visit_year"]].reset_index(drop=True)',
     '    latest = latest.reset_index(drop=True)', "network takes every section, however old its last visit"),
    # ---- report -------------------------------------------------------------------------------------------------------
    ("M58", "src/pavement_ai/report.py", '        return format(value * 100.0, f".{int(spec[3:] or 0)}f")',
     '        return format(value, f".{int(spec[3:] or 0)}f")', "percentages not multiplied by 100"),
    ("M59", "src/pavement_ai/report.py", "                if abs(scaled - round(scaled)) < 1e-9 and format(round(scaled), \"d\") == plain:",
     "                if format(round(scaled), \"d\") == plain:", "number check lets rounded fractions pass as whole numbers"),
    ("M60", "src/pavement_ai/report.py", "        if not _supported(token, numbers, string_tokens):\n            missing.append(token)",
     "        if not _supported(token, numbers, string_tokens):\n            pass", "number check never reports anything"),
    ("M61", "src/pavement_ai/report_tables.py", '    if g["hi"] < 0:\n        return "boosting is better"',
     '    if g["diff"] < 0:\n        return "boosting is better"', "verdict 'better' without the interval"),
    ("M62", "src/pavement_ai/report_tables.py", '    if g["lo"] > 0:\n        return "boosting is worse"',
     '    if g["lo"] > 1e9:\n        return "boosting is worse"', "verdict never says 'worse'"),
]


def copy_repo(dst: Path) -> None:
    for rel in COPY:
        src = REPO / rel
        if src.is_dir():
            shutil.copytree(src, dst / rel, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache", "figures"))
        else:
            (dst / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst / rel)


def run_pytest(cwd: Path) -> tuple[int, str]:
    p = subprocess.run([sys.executable, "-m", "pytest", "-q", "-x", "-rfE", "-p", "no:cacheprovider"], cwd=cwd,
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=1800)
    return p.returncode, p.stdout + p.stderr


def run_mutant(m) -> dict:
    mid, rel, old, new, desc = m
    with tempfile.TemporaryDirectory(prefix=f"mut_{mid}_") as tmp:
        tmp = Path(tmp)
        copy_repo(tmp)
        path = tmp / rel
        src = path.read_text(encoding="utf-8")
        n = src.count(old)
        if n != 1:
            return {"id": mid, "file": rel, "desc": desc, "killed": None, "error": f"snippet found {n} times"}
        path.write_text(src.replace(old, new), encoding="utf-8", newline="\n")
        t0 = time.time()
        code, out = run_pytest(tmp)
        failed = re.findall(r"(?:FAILED|ERROR) (tests/\S+?)(?: - |\s|$)", out)
        return {"id": mid, "file": rel, "desc": desc, "killed": code != 0, "first_failure": (failed or [None])[0],
                "seconds": round(time.time() - t0, 1)}


def collect_count() -> int:
    p = subprocess.run([sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider"], cwd=REPO,
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600)
    m = re.search(r"(\d+) tests? collected", p.stdout)
    if not m:
        sys.exit("could not count the tests:\n" + p.stdout[-2000:] + p.stderr[-2000:])
    return int(m.group(1))


def save(report: dict) -> None:
    """Write results/mutation.json and rebuild README.md / docs/brief.md, which quote it."""
    OUT.write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8", newline="\n")
    subprocess.run([sys.executable, str(REPO / "scripts" / "make_report.py")], cwd=REPO, check=True)


def main(label: str, workers: int, only: list[str]) -> None:
    report = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    if not only:
        # the documents quote the number of tests and both runs; put the current count (and, before the first
        # run, empty placeholders) in place so that the unmodified suite can pass
        report["tests"] = collect_count()
        for key in ("first", "final"):
            report.setdefault(key, {"pending": True, "tests": report["tests"], "total": 0, "killed": 0, "survived": 0})
        save(report)
    with tempfile.TemporaryDirectory(prefix="mut_base_") as tmp:
        copy_repo(Path(tmp))
        code, out = run_pytest(Path(tmp))
        if code != 0:
            print(out[-3000:])
            sys.exit("the unmodified suite fails; fix it before mutation testing")
        m = re.search(r"(\d+) passed", out)
        baseline = int(m.group(1)) if m else None
    control = run_mutant(CONTROL)
    if control["killed"] is not True:
        sys.exit(f"control mutant was not killed ({control}); the harness cannot be trusted")
    print(f"baseline {baseline} tests pass; control mutant killed by {control['first_failure']}", flush=True)
    todo = [m for m in MUTANTS if not only or m[0] in only]
    with ThreadPoolExecutor(max_workers=workers) as ex:
        res = list(ex.map(run_mutant, todo))
    bad = [r for r in res if r["killed"] is None]
    if bad:
        sys.exit(f"mutant snippets not found exactly once: {bad}")
    killed = sum(r["killed"] for r in res)
    for r in res:
        print(f"{r['id']} {'killed  ' if r['killed'] else 'SURVIVED'} {r['desc']}  [{r['first_failure']}]")
    print(f"\n{killed}/{len(res)} killed; baseline {baseline} tests")
    if only:
        return
    report["control"] = {"desc": control["desc"], "killed": True, "first_failure": control["first_failure"]}
    report[label] = {"tests": baseline, "total": len(res), "killed": killed, "survived": len(res) - killed,
                     "survivors": [r["id"] for r in res if not r["killed"]], "mutants": res}
    report["tests"] = baseline
    save(report)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", choices=["first", "final"], required=True)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--only", nargs="*", default=[])
    a = ap.parse_args()
    main(a.label, a.workers, a.only)
