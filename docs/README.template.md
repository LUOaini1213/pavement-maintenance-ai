Personal desk study on public data; not a real maintenance plan or engineering advice.

# pavement-maintenance-ai

Pavement deterioration forecasting and budget-constrained maintenance planning on the public FHWA LTPP
database, with the Chinese highway condition indices ({{china:standards.assessment}}) as a second view.
This file is generated from `results/*.json` by `scripts/make_report.py`; every number in it is read from
those files and a test checks that.

**What it found, in short**

{{table:verdict_sentences}}
- Splitting the same IRI pairs at random instead of by site makes boosting look
  {{deterioration:iri.leaky_random_pairs.all.gbm_mae_change_pct|+.1f}} % against the best baseline; with sites
  kept apart and the test period after the training period the figure is
  {{deterioration:iri.grouped_forward.all.gbm_mae_change_pct|+.1f}} %. The first number is a leak, not skill.
- Recorded treatments: a thin overlay lowered IRI by
  {{treatment_effects:iri.classes.thin_overlay.drop_mean|.2f}} m/km on average, a thick one by
  {{treatment_effects:iri.classes.thick_overlay.drop_mean|.2f}} m/km, a seal coat by
  {{treatment_effects:iri.classes.seal.drop_mean|.2f}} m/km (no measurable change in roughness).
- Network plan over {{optimisation:horizon_years|d}} years on {{optimisation:network.sections|d}} sections at an
  annual budget of {{inputs:optimisation.base_budget_share|pct0}} % of the cost of resurfacing everything: the MIP
  saves {{optimisation:base.mip.iri_years_saved|.1f}} IRI-years against doing nothing, the worst-first rule
  {{optimisation:base.worst_first.iri_years_saved|.1f}} with the same money
  ({{optimisation:base.mip_vs_worst_first.benefit_ratio|.2f}} times as much).

## 中文摘要

个人利用公开数据做的案头研究，不是实际养护方案，也不构成工程建议。

- 数据：美国联邦公路局 LTPP 长期路面性能数据库（{{data:release}}），沥青面层路段
  {{data:sections|,d}} 个；IRI 检测 {{data:indicators.iri.visits|,d}} 次、车辙 {{data:indicators.rut.visits|,d}}
  次、裂缝调查 {{data:indicators.crack.visits|,d}} 次（{{data:indicators.iri.first_year|d}}–{{data:indicators.iri.last_year|d}} 年）。
  原始数据不入库，只保留获取脚本与 SHA-256；仓库内为小体量派生表。
- 性能预测（按站点分组留出，并且训练期在前、测试期在后）：对比末次值、本路段线性/指数外推、
  路网中位速率、马尔可夫链与梯度提升。结论如实记录：
{{table:verdict_sentences_zh}}
- 养护效果（养护前后实测对比，存在选择偏差）：薄层罩面平均降低 IRI
  {{treatment_effects:iri.classes.thin_overlay.drop_mean|.2f}} m/km，厚罩面
  {{treatment_effects:iri.classes.thick_overlay.drop_mean|.2f}} m/km，封层类
  {{treatment_effects:iri.classes.seal.drop_mean|.2f}} m/km（对平整度基本无改善）。
- 养护决策：{{optimisation:network.sections|d}} 个路段、{{optimisation:horizon_years|d}} 年、年度预算约束下的混合整数规划
  （HiGHS 求解，{{optimisation:base.mip.binary_variables|,d}} 个 0-1 变量）。同等预算下节省的「IRI·年」为
  {{optimisation:base.mip.iri_years_saved|.1f}}，「最差优先」规则为
  {{optimisation:base.worst_first.iri_years_saved|.1f}}，前者是后者的
  {{optimisation:base.mip_vs_worst_first.benefit_ratio|.2f}} 倍。
- 中国标准视角：按 {{china:standards.assessment}} 式 {{china:clauses.rqi}} 把 IRI 换算为 RQI、按式
  {{china:clauses.rdi}} 把车辙换算为 RDI，并按表 {{china:clauses.grades}} 分级；薄层罩面适用条件取自
  {{china:standards.preventive}} 表 {{china:preventive_windows_expressway.thin_overlay.table}}。系数与条款均核对自交通运输部官网文本，
  出处见 `docs/sources.md`。
- 工程化：{{mutation:tests|d}} 个离线测试；变异测试首轮 {{mutation:first.killed|d}}/{{mutation:first.total|d}}，
  补测试后 {{mutation:final.killed|d}}/{{mutation:final.total|d}}。

## Data

{{data:dataset}}, downloaded on {{data:retrieved}} from {{data:landing_page}} without login
({{data:raw_files|d}} archives, hashes in `data/raw_manifest.json`). The raw files are not in the repository;
`scripts/fetch_ltpp.py` fetches them and `scripts/dump_tables.py` plus `scripts/build_extracts.py` rebuild the
small extracts in `data/derived/` that everything else runs on.

Kept: {{data:sections|,d}} asphalt-surfaced test sections at {{data:sites|,d}} sites.

| indicator | visits | sections | years | median |
|---|---|---|---|---|
| IRI (mean of both wheel paths, m/km) | {{data:indicators.iri.visits|,d}} | {{data:indicators.iri.sections|,d}} | {{data:indicators.iri.first_year|d}}–{{data:indicators.iri.last_year|d}} | {{data:indicators.iri.median|.2f}} |
| rut depth (mm) | {{data:indicators.rut.visits|,d}} | {{data:indicators.rut.sections|,d}} | {{data:indicators.rut.first_year|d}}–{{data:indicators.rut.last_year|d}} | {{data:indicators.rut.median|.1f}} |
| cracking (% of area, HPMS definition) | {{data:indicators.crack.visits|,d}} | {{data:indicators.crack.sections|,d}} | {{data:indicators.crack.first_year|d}}–{{data:indicators.crack.last_year|d}} | {{data:indicators.crack.median|.1f}} |

Recorded construction events on these sections: {{data:events.seal|,d}} seal coats or surface treatments,
{{data:events.thin_overlay|,d}} thin, {{data:events.medium_overlay|,d}} medium and
{{data:events.thick_overlay|,d}} thick overlays, and {{data:events.routine|,d}} routine jobs (crack sealing,
patching) that do not renew the surface.

**Terms of use.** InfoPave links to FHWA's disclaimer, which states that information on the site "is considered
public information and may be distributed or copied"; the data.gov record of LTPP gives the licence as U.S.
Government Works. Details, quotations and retrieval dates are in `docs/sources.md`. Requested citation:
{{data:citation}}. FHWA does not endorse this work.

## A. Deterioration forecasting

A *pair* is an origin visit and a later visit on the same surface (no renewal in between),
{{deterioration:settings.min_horizon|.1f}} to {{deterioration:settings.max_horizon|.0f}} years apart. Each method
predicts the later value from what was known at the origin.

- Baselines: last value; the section's own linear and exponential trend; last value plus the network's median
  annual rate; a Markov chain on condition states with a one-year step.
- Machine learning: gradient boosting on the increment, with age, time since the last renewal and its type,
  layer thicknesses, truck traffic and ESAL up to the origin year, climate normals, the own trend so far and the
  latest values of the other two indicators.
- Validation: {{deterioration:settings.folds|d}} folds of whole sites (a site is a state plus project, so
  co-located sections never sit on both sides). In the stricter scheme the training pairs must also end before
  {{deterioration:settings.cutoff_year|.0f}} and the test pairs start in or after it. Intervals are
  {{deterioration:settings.level|pct0}} % percentile intervals from {{deterioration:settings.n_boot|,d}} bootstrap
  resamples of whole sites.

Site-grouped and forward in time (the headline):

{{table:forecast_forward}}

Site-grouped only:

{{table:forecast_grouped}}

Boosting against the best baseline, by horizon:

{{table:verdicts}}

What a leaky split would have shown for IRI:

{{table:leaky}}

![MAE by method](results/figures/forecast_mae.png)

### Treatment effects from the work history

Last measurement on the old surface (at most {{treatment_effects:settings.max_years_before|.0f}} years before
the event) against the first one on the new surface (at most {{treatment_effects:settings.max_years_after|.0f}}
years after). Rates are least-squares slopes over at least
{{treatment_effects:settings.min_visits_for_rate|d}} visits.

IRI (m/km):

{{table:treatment_iri}}

Rut depth (mm):

{{table:treatment_rut}}

Cracking (%):

{{table:treatment_crack}}

These are before/after differences, not causal effects. Agencies choose which sections to treat and when; the
"before" value is taken near a peak, so part of the drop is regression to the mean; and thicker overlays went
onto rougher pavements (see the "median before" column), so the classes are not comparable groups.

## B. Network-level plan under an annual budget

The network is made of the {{optimisation:network.sections|d}} sections whose last profile visit is in
{{inputs:optimisation.network_min_last_visit_year|d}} or later and that have a rut and a cracking survey on the
current surface ({{optimisation:network.excluded_without_rut_or_cracking|d}} of
{{optimisation:network.candidates|d}} candidates lack one). Each stands for one lane-km. Mean IRI at the start is
{{optimisation:network.mean_iri|.2f}} m/km.

Do-nothing growth: {{optimisation:network.rate_median|.3f}} m/km per year for every section, because
{{optimisation:rate_model_reason}}.

{{table:treatments_used}}

The MIP has one binary variable per allowed (section, year, treatment), at most one treatment per section in
the horizon and one budget row per year; the objective is the IRI-years saved against doing nothing. It is
solved with HiGHS ({{optimisation:base.mip.binary_variables|,d}} binaries,
{{optimisation:base.mip.constraints|,d}} rows, status {{optimisation:base.mip.status}}).
The worst-first rule ranks sections by current IRI and resurfaces those at or above
{{inputs:optimisation.worst_first.trigger_iri|.1f}} m/km (thick overlay at or above
{{inputs:optimisation.worst_first.major_iri|.1f}} m/km or where resurfacing is not allowed) until the year's money
is gone. The fixed-cycle rule gives a thin overlay to every surface that is
{{inputs:optimisation.fixed_cycle_years|.0f}} years old, oldest first.

Annual budget {{optimisation:base.annual_budget_million|.2f}} million USD
({{inputs:optimisation.base_budget_share|pct0}} % of the {{optimisation:resurfacing_whole_network_million|.1f}}
million it would cost to resurface the whole network):

{{table:plan}}

Budget sensitivity:

{{table:sweep}}

![Budget trade-off](results/figures/budget_tradeoff.png)

Other checks: with the thin overlay priced at the low and at the high end of the published range the MIP saves
{{optimisation:preventive_cost_sensitivity.0.benefit_ratio|.2f}} and
{{optimisation:preventive_cost_sensitivity.1.benefit_ratio|.2f}} times as many IRI-years as worst-first. With
section-specific growth rates from the boosting model instead of the single network rate, the ratio is
{{optimisation:rate_model_sensitivity.benefit_ratio_vs_worst_first|.2f}} and
{{optimisation:rate_model_sensitivity.plan_overlap|pct1}} % of the sections treated under either rate model are
treated under both.

## C. Chinese standard view

{{china:sources.jtg_5210_2018.title}} ({{china:sources.jtg_5210_2018.issuer}}; {{china:sources.jtg_5210_2018.url}},
retrieved {{china:sources.jtg_5210_2018.retrieved}}):

- Clause {{china:clauses.rqi}}: RQI = {{china:hundred|.0f}} / ({{china:one|.0f}} + a0 · exp(a1 · IRI)), with a0 =
  {{china:rqi_coefficients.expressway_class1.a0|.3f}} and a1 = {{china:rqi_coefficients.expressway_class1.a1|.2f}}
  for motorways and class-one highways (a0 = {{china:rqi_coefficients.other.a0|.4f}}, a1 =
  {{china:rqi_coefficients.other.a1|.2f}} for the other classes).
- Clause {{china:clauses.rdi}}: RDI falls by {{china:rdi_parameters.a0|.1f}} per mm of rut up to
  {{china:rdi_parameters.rda_mm|.0f}} mm, then by {{china:rdi_parameters.a1|.1f}} per mm, and is zero above
  {{china:rdi_parameters.rdb_mm|.0f}} mm.
- Clause {{china:clauses.pci}}: PCI = {{china:hundred|.0f}} − {{china:pci_parameters_asphalt.a0|.2f}} ·
  DR^{{china:pci_parameters_asphalt.a1|.3f}} for asphalt, DR being the distress ratio in %.
- Table {{china:clauses.grades}}: excellent from {{china:grade_limits.excellent|.0f}}, good from
  {{china:grade_limits.good|.0f}}, average from {{china:grade_limits.average|.0f}}, poor from
  {{china:grade_limits.poor|.0f}}, failed below.

On an expressway the grade limits therefore sit at IRI {{china:iri_at_rqi_expressway.90|.2f}},
{{china:iri_at_rqi_expressway.80|.2f}}, {{china:iri_at_rqi_expressway.70|.2f}} and
{{china:iri_at_rqi_expressway.60|.2f}} m/km. {{china:all_visits.rqi_grade_shares.excellent|pct1}} % of all
{{china:all_visits.n_iri|,d}} LTPP profile visits used here would be graded excellent on riding quality: by this
scale RQI hardly moves over the range in which most of these sections live, so the planning model works on IRI
itself and reports the grades alongside.

Grades of the planning network at the start (share of sections):

{{table:grades}}

{{china:standards.preventive}}, Table {{china:preventive_windows_expressway.thin_overlay.table}}, suits a thin
overlay on an expressway to pavements with PCI and RQI of at least
{{china:preventive_windows_expressway.thin_overlay.rqi_min|.0f}} and RDI of at least
{{china:preventive_windows_expressway.thin_overlay.rdi_min|.0f}}; that window is the eligibility rule for the
preventive treatment in part B (RQI {{china:preventive_windows_expressway.thin_overlay.rqi_min|.0f}} is IRI
{{china:iri_at_rqi_expressway.85|.2f}} m/km, RDI {{china:preventive_windows_expressway.thin_overlay.rdi_min|.0f}} is a
rut of {{china:rut_mm_at_rdi_80|.1f}} mm, PCI {{china:preventive_windows_expressway.thin_overlay.pci_min|.0f}} is a
distress ratio of {{china:distress_ratio_at_pci.85|.1f}} %).
{{optimisation:network.share_eligible_preventive|pct1}} % of the network's sections pass it.

## D. Maintenance brief

`docs/brief.md` is a short Chinese-and-English brief generated from the same results by the same script; its
numbers are checked by the same test.

## Inputs: real, calibrated or assumption

{{table:inputs}}

## Limitations

- LTPP test sections are short research sections scattered over North America, not one operator's network, and
  not Chinese expressways (different structures, axle loads, climate and maintenance practice). The "network"
  in part B is a stand-in built from real section states.
- The forecasting comparison says what these methods do on LTPP visits a few years apart. It does not say that
  machine learning cannot help on denser, more uniform network surveys.
- The plan optimises roughness only. Cracking and rutting enter as eligibility at the start of the plan and are
  not projected forward; structural capacity, safety, user cost and traffic disruption are absent. With
  roughness as the only goal and a short horizon, thicker treatments buy little that thin ones do not, which
  the measured after-treatment IRI already shows; a real programme has other reasons for them.
- One treatment per section in the horizon, a linear do-nothing path and deterministic effects.
- Treatment effects are before/after differences with selection bias (see above).
- Unit costs are U.S. figures from two FHWA documents in different dollar years; the thin-overlay cost is the
  midpoint of a wide range. The PCI used for eligibility is an approximation (LTPP cracking percent in place
  of the standard's weighted distress ratio).
- Items that could not be verified are listed in `docs/sources.md`.

## Reproduce

Python {{inputs:python}}, pinned in `requirements.txt`.

```
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt     # Linux/macOS: .venv/bin/python
.venv/Scripts/python -m pytest                              # offline
.venv/Scripts/python scripts/run_all.py                     # recompute results/*.json and figures
.venv/Scripts/python scripts/make_report.py                 # rebuild README.md and docs/brief.md
```

Rebuilding the extracts from the source needs `requirements-data.txt` and network access:
`scripts/fetch_ltpp.py`, then `scripts/dump_tables.py`, then `scripts/build_extracts.py`.

## Tests

{{mutation:tests|d}} offline tests (`pytest`), most of them hand-calculated cases; the workflow in
`.github/workflows/ci.yml` runs them with the pinned requirements and regenerates this file to compare.
Mutation testing (`mutation/run_mutants.py`): a control mutant that must be caught runs first; then
{{mutation:first.total|d}} deliberate bugs were injected one at a time. First run: {{mutation:first.killed|d}}
caught, {{mutation:first.survived|d}} survived. After adding tests for the survivors:
{{mutation:final.killed|d}} of {{mutation:final.total|d}} caught. Both runs are in `results/mutation.json`.

## Licence

Code and text: MIT (see `LICENSE`). The LTPP data and the cited standards and reports belong to their issuers
and are used under the terms recorded in `docs/sources.md`.
