个人利用公开数据做的案头研究，不是实际养护方案，也不构成工程建议。
Personal desk study on public data; not a real maintenance plan or engineering advice.

# 路面养护简报 / Pavement maintenance brief

本简报由 `scripts/make_report.py` 依据 `results/*.json` 自动生成，数字全部来自结果文件并由测试核对。
Generated from `results/*.json` by `scripts/make_report.py`; every number is read from the results and checked by a test.

## 路网现状 / Network condition

- 对象：LTPP（SDR 40）中 491 个沥青路面试验路段的最新实测状态，每段按一车道公里计
  （示意性路网，并非某一运营单位的真实路网）。
  Scope: latest measured state of 491 LTPP asphalt test sections
  (SDR 40), each counted as one lane-km (a stand-in network, not an operator's real one).
- 平均 IRI 1.12 m/km，最大 3.75 m/km；
  19.3 % 的路段 IRI 高于 1.5 m/km。
  Mean IRI 1.12 m/km, maximum 3.75 m/km;
  19.3 % of the sections are above
  1.5 m/km.
- 车辙中位数 4 mm，裂缝率中位数 2.0 %。
  Median rut depth 4 mm, median cracking
  2.0 %.
- 按 JTG 5210-2018 分级（路段占比）/ Grades under JTG 5210-2018 (share of sections):

| index | excellent (优) | good (良) | average (中) | poor (次) | failed (差) |
| --- | --- | --- | --- | --- | --- |
| RQI from IRI | 94.9 % | 4.5 % | 0.6 % | 0.0 % | 0.0 % |
| RDI from rut depth | 94.5 % | 3.7 % | 1.2 % | 0.4 % | 0.2 % |
| PCI from cracking percent (approximation) | 42.4 % | 9.0 % | 6.3 % | 5.5 % | 36.9 % |

  PCI 以 LTPP 裂缝率近似代替标准中的破损率 DR，仅供参考。
  PCI uses the LTPP cracking percent in place of the standard's distress ratio and is indicative only.

## 不养护的趋势 / Outlook without treatment

- 采用的衰变速率：全路网统一每年 0.023 m/km（49,409 组历史观测对的中位数）。原因：按站点分组、时间在后的检验中，梯度提升模型的 IRI 误差为 0.110 m/km，最优朴素基线为 0.106 m/km，前者没有胜出。
  Growth rate used: 0.023 m/km per year for every section (median of 49,409 historical pairs). Reason: under site-grouped, forward-in-time validation the boosting model's IRI error is 0.110 m/km against 0.106 m/km for the best naive baseline; it did not win.
- 若 5 年内不做任何处治，路网平均 IRI 将由 1.12 升至
  1.24 m/km。
  With no treatment for 5 years the network mean IRI goes from
  1.12 to 1.24 m/km.

## 建议方案 / Proposed programme

年度预算 3.04 百万美元（约为全路网中修一遍费用的
3 %），混合整数规划（HiGHS）给出的逐年安排（路段数）：
Annual budget 3.04 million USD (about
3 % of the cost of resurfacing the whole network); programme from the
mixed-integer model (HiGHS), sections per year:

| year 年 | preventive 预防养护 | minor rehab 中修 | major rehab 大修 | spend 支出 (million USD) |
| --- | --- | --- | --- | --- |
| 1 | 23 | 5 | 0 | 3.03 |
| 2 | 13 | 2 | 2 | 2.98 |
| 3 | 11 | 3 | 2 | 3.01 |
| 4 | 5 | 2 | 3 | 3.01 |
| 5 | 8 | 4 | 2 | 2.96 |

- 合计处治 85 段：预防养护（薄层罩面）
  60 段、中修 16 段、大修
  9 段，支出 14.99 百万美元。
  85 sections treated in total: 60
  preventive (thin overlay), 16 minor and
  9 major rehabilitation; spend
  14.99 million USD.
- 期末路网平均 IRI：本方案 1.106 m/km；同等预算下「最差优先」
  1.152 m/km、「固定周期」1.193 m/km；
  不养护 1.240 m/km。
  Network mean IRI at the end: 1.106 m/km with this programme,
  1.152 with worst-first and
  1.193 with a fixed cycle on the same budget,
  1.240 with no treatment.
- 相对不养护节省的「IRI·年」：本方案 237.8，最差优先
  129.9（前者为后者的
  1.83 倍）。
  IRI-years saved against doing nothing: 237.8 with this programme,
  129.9 with worst-first
  (1.83 times as much).
- 薄层罩面仅用于 PCI、RQI 不低于 85 且 RDI 不低于
  80 的路段（JTG/T 5142-01-2021 表
  5.3.2，高速公路）。
  Thin overlays go only to sections with PCI and RQI of at least
  85 and RDI of at least
  80 (JTG/T 5142-01-2021, Table
  5.3.2, expressway).

## 使用前须知 / Before relying on this

- 处治效果来自 LTPP 养护前后实测对比，存在选择偏差；单价为美国公开资料口径；目标只含平整度，未计结构承载力、
  安全与交通组织。详见 README 的「Limitations」。
  Treatment effects are before/after differences from LTPP with selection bias; unit costs are U.S. public
  figures; the objective covers roughness only, not structural capacity, safety or traffic management. See
  "Limitations" in the README.
