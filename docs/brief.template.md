个人利用公开数据做的案头研究，不是实际养护方案，也不构成工程建议。
Personal desk study on public data; not a real maintenance plan or engineering advice.

# 路面养护简报 / Pavement maintenance brief

本简报由 `scripts/make_report.py` 依据 `results/*.json` 自动生成，数字全部来自结果文件并由测试核对。
Generated from `results/*.json` by `scripts/make_report.py`; every number is read from the results and checked by a test.

## 路网现状 / Network condition

- 对象：LTPP（{{data:release}}）中 {{optimisation:network.sections|d}} 个沥青路面试验路段的最新实测状态，每段按一车道公里计
  （示意性路网，并非某一运营单位的真实路网）。
  Scope: latest measured state of {{optimisation:network.sections|d}} LTPP asphalt test sections
  ({{data:release}}), each counted as one lane-km (a stand-in network, not an operator's real one).
- 平均 IRI {{optimisation:network.mean_iri|.2f}} m/km，最大 {{optimisation:network.max_iri|.2f}} m/km；
  {{optimisation:network.share_iri_above_1p5|pct1}} % 的路段 IRI 高于 {{inputs:optimisation.worst_first.trigger_iri|.1f}} m/km。
  Mean IRI {{optimisation:network.mean_iri|.2f}} m/km, maximum {{optimisation:network.max_iri|.2f}} m/km;
  {{optimisation:network.share_iri_above_1p5|pct1}} % of the sections are above
  {{inputs:optimisation.worst_first.trigger_iri|.1f}} m/km.
- 车辙中位数 {{optimisation:network.median_rut_mm|.0f}} mm，裂缝率中位数 {{optimisation:network.median_cracking_pct|.1f}} %。
  Median rut depth {{optimisation:network.median_rut_mm|.0f}} mm, median cracking
  {{optimisation:network.median_cracking_pct|.1f}} %.
- 按 {{china:standards.assessment}} 分级（路段占比）/ Grades under {{china:standards.assessment}} (share of sections):

{{table:grades}}

  PCI 以 LTPP 裂缝率近似代替标准中的破损率 DR，仅供参考。
  PCI uses the LTPP cracking percent in place of the standard's distress ratio and is indicative only.

## 不养护的趋势 / Outlook without treatment

{{table:rate_note}}
- 若 {{optimisation:horizon_years|d}} 年内不做任何处治，路网平均 IRI 将由 {{optimisation:network.mean_iri|.2f}} 升至
  {{optimisation:base.do_nothing.mean_iri_final|.2f}} m/km。
  With no treatment for {{optimisation:horizon_years|d}} years the network mean IRI goes from
  {{optimisation:network.mean_iri|.2f}} to {{optimisation:base.do_nothing.mean_iri_final|.2f}} m/km.

## 建议方案 / Proposed programme

年度预算 {{optimisation:base.annual_budget_million|.2f}} 百万美元（约为全路网中修一遍费用的
{{inputs:optimisation.base_budget_share|pct0}} %），混合整数规划（HiGHS）给出的逐年安排（路段数）：
Annual budget {{optimisation:base.annual_budget_million|.2f}} million USD (about
{{inputs:optimisation.base_budget_share|pct0}} % of the cost of resurfacing the whole network); programme from the
mixed-integer model (HiGHS), sections per year:

{{table:yearly_plan}}

- 合计处治 {{optimisation:base.mip.treated_sections|d}} 段：预防养护（薄层罩面）
  {{optimisation:base.mip.treatments.preventive|d}} 段、中修 {{optimisation:base.mip.treatments.minor_rehab|d}} 段、大修
  {{optimisation:base.mip.treatments.major_rehab|d}} 段，支出 {{optimisation:base.mip.total_spend_million|.2f}} 百万美元。
  {{optimisation:base.mip.treated_sections|d}} sections treated in total: {{optimisation:base.mip.treatments.preventive|d}}
  preventive (thin overlay), {{optimisation:base.mip.treatments.minor_rehab|d}} minor and
  {{optimisation:base.mip.treatments.major_rehab|d}} major rehabilitation; spend
  {{optimisation:base.mip.total_spend_million|.2f}} million USD.
- 期末路网平均 IRI：本方案 {{optimisation:base.mip.mean_iri_final|.3f}} m/km；同等预算下「最差优先」
  {{optimisation:base.worst_first.mean_iri_final|.3f}} m/km、「固定周期」{{optimisation:base.fixed_cycle.mean_iri_final|.3f}} m/km；
  不养护 {{optimisation:base.do_nothing.mean_iri_final|.3f}} m/km。
  Network mean IRI at the end: {{optimisation:base.mip.mean_iri_final|.3f}} m/km with this programme,
  {{optimisation:base.worst_first.mean_iri_final|.3f}} with worst-first and
  {{optimisation:base.fixed_cycle.mean_iri_final|.3f}} with a fixed cycle on the same budget,
  {{optimisation:base.do_nothing.mean_iri_final|.3f}} with no treatment.
- 相对不养护节省的「IRI·年」：本方案 {{optimisation:base.mip.iri_years_saved|.1f}}，最差优先
  {{optimisation:base.worst_first.iri_years_saved|.1f}}（前者为后者的
  {{optimisation:base.mip_vs_worst_first.benefit_ratio|.2f}} 倍）。
  IRI-years saved against doing nothing: {{optimisation:base.mip.iri_years_saved|.1f}} with this programme,
  {{optimisation:base.worst_first.iri_years_saved|.1f}} with worst-first
  ({{optimisation:base.mip_vs_worst_first.benefit_ratio|.2f}} times as much).
- 薄层罩面仅用于 PCI、RQI 不低于 {{china:preventive_windows_expressway.thin_overlay.rqi_min|.0f}} 且 RDI 不低于
  {{china:preventive_windows_expressway.thin_overlay.rdi_min|.0f}} 的路段（{{china:standards.preventive}} 表
  {{china:preventive_windows_expressway.thin_overlay.table}}，高速公路）。
  Thin overlays go only to sections with PCI and RQI of at least
  {{china:preventive_windows_expressway.thin_overlay.rqi_min|.0f}} and RDI of at least
  {{china:preventive_windows_expressway.thin_overlay.rdi_min|.0f}} ({{china:standards.preventive}}, Table
  {{china:preventive_windows_expressway.thin_overlay.table}}, expressway).

## 使用前须知 / Before relying on this

- 处治效果来自 LTPP 养护前后实测对比，存在选择偏差；单价为美国公开资料口径；目标只含平整度，未计结构承载力、
  安全与交通组织。详见 README 的「Limitations」。
  Treatment effects are before/after differences from LTPP with selection bias; unit costs are U.S. public
  figures; the objective covers roughness only, not structural capacity, safety or traffic management. See
  "Limitations" in the README.
