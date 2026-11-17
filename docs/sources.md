# Sources, data terms and what could not be verified

Every external fact used in this repository is listed here with its issuer, date, URL and the day it was
retrieved. Numbers that have no source are listed as assumptions in the README table and in
`src/pavement_ai/config.py`.

## 1. Data

| Item | Detail |
|---|---|
| Dataset | Long-Term Pavement Performance (LTPP) programme, Standard Data Release 40 |
| Issuer | U.S. Department of Transportation, Federal Highway Administration (FHWA), via LTPP InfoPave |
| Landing page | https://infopave.fhwa.dot.gov/Data/StandardDataRelease (lists "SDR 40 (September 2026)"; the citation file inside the archives reads "SDR 40 – August, 2026") |
| Retrieved | 2026-11-15, without login, through the per-volume download links of that page |
| Files | 8 zip archives (Administration, Inventory, Maint Rehab, Consolidated, Specific Pavement Studies, Traffic, Climate Summary Data, Monitoring); URL, size, retrieval time and SHA-256 of each are in `data/raw_manifest.json` |
| Citation asked for by the issuer | "Long Term Pavement Performance InfoPave, Standard Data Release, SDR 40, https://infopave.fhwa.dot.gov/Data/StandardDataRelease" |

### Terms of use that were checked

1. The InfoPave pages carry no licence text of their own. Their footer links to FHWA's "Disclaimer and
   Limitation of Liability", https://www.fhwa.dot.gov/disclaim.cfm (page last modified 2013-09-24, retrieved
   2026-11-16). Under "Ownership" it says: "Information presented on this web site is considered public
   information and may be distributed or copied." The same page disclaims any warranty on accuracy or
   completeness and says that naming a product does not constitute endorsement.
2. The data.gov catalogue record "Long-Term Pavement Performance (LTPP)",
   https://catalog.data.gov/dataset/long-term-pavement-performance-ltpp (publisher Federal Highway
   Administration, dataset last updated 2026-09-03, retrieved 2026-11-15), gives the licence as
   https://www.usa.gov/government-works and the access level as "public".
3. https://www.usa.gov/government-copyright (last updated 2026-04-30, retrieved 2026-11-16) adds two
   conditions for U.S. government works: "You cannot use government materials in a way that implies endorsement
   by a government agency, official, or employee", and agency logos and trademarks need permission.

### What this repository does with the data

* The raw archives and the Access databases are **not** in the repository (`data/raw/` is git-ignored).
  `scripts/fetch_ltpp.py` downloads them again and `--verify` checks them against the recorded SHA-256.
* `data/derived/*.csv` (about 3 MB, hashes in `data/derived/manifest.json`) are small extracts of LTPP records
  for asphalt-surfaced test sections: profile visits, rut depth, cracking, construction events, layer
  thickness, truck traffic and climate normals. They are redistributed on the basis of item 1 above, with the
  citation requested by the issuer. They are LTPP data with unit conversions and averages; they are not
  endorsed by FHWA.
* The MIT licence in `LICENSE` covers the code and text written for this repository, not the LTPP data.

## 2. Chinese standards (Part C and the treatment windows)

| Fact used | Source | Where in the source | Retrieved |
|---|---|---|---|
| RQI = 100 / (1 + a0·e^(a1·IRI)); a0 = 0.026 and a1 = 0.65 for motorways and class-1 highways, a0 = 0.0185 and a1 = 0.58 for other highways | JTG 5210-2018 (EN), *Highway Performance Assessment Standard*, official English edition; issued 2018-12-25, effective 2019-05-01; Ministry of Transport of the PRC; https://xxgk.mot.gov.cn/jigou/glj/202204/P020220425579066545831.pdf (SHA-256 e36a3baa…f4656fd) | clause 7.4.7, equation (7.4.7), PDF pages 42–43: "a0 — use 0.026 for Motorways and Class-1 highways, or 0.0185 for other classified highways", "a1 — use 0.65 for Motorways and Class-1 highways, or 0.58 for other classified highways" | 2026-11-17 |
| RDI = 100 − a0·RD for RD ≤ RDa; 90 − a1·(RD − RDa) for RDa < RD ≤ RDb; 0 above; RDa = 10.0, RDb = 40.0, a0 = 1.0, a1 = 3.0 | same | clause 7.4.8, equation (7.4.8), PDF page 43 | 2026-11-17 |
| PCI = 100 − a0·DR^a1; a0 = 15.00 and a1 = 0.412 for asphalt pavement | same | clause 7.4.5, equation (7.4.5-1), PDF page 40 | 2026-11-17 |
| Grades for RQI, RDI, PCI: excellent ≥ 90, good ≥ 80, average ≥ 70, poor ≥ 60, failed < 60 (note 1: for the PCI of motorways "excellent" starts at 92) | same | Table 4.0.2, PDF page 22 | 2026-11-17 |
| Weights of the sub-indices in PQI (asphalt, motorway and class-1: PCI 0.35, RQI 0.30, RDI 0.15, PBI 0.10, SRI or PWI 0.10) — read but not used | same | Table 7.4.3, PDF page 40 | 2026-11-17 |
| Thin overlay on an expressway is suited to pavements with PCI and RQI ≥ 85 and RDI ≥ 80 (ultra-thin overlay 88 / 85; micro-surfacing PCI, RQI ≥ 90 and RDI ≥ 90; fog seal ≥ 93) | JTG/T 5142-01—2021 《公路沥青路面预防养护技术规范》; issued 2021-08-17, effective 2021-12-01; Ministry of Transport of the PRC; https://xxgk.mot.gov.cn/jigou/glj/202108/P020210827331277450621.pdf (SHA-256 023b669d…cdf68bc) | 表 5.3.2 「薄层罩面和超薄罩面适用的各等级公路路况水平」, 表 5.2.5, 表 5.2.2; PDF pages 21–22 | 2026-11-17 |
| A preventive treatment is thin, "一般不超过 40mm" | same | commentary (条文说明) to clause 2.1.1, PDF page 10 | 2026-11-17 |
| Benefit of a treatment measured as area under the condition curve, and benefit-cost ratio | same | Appendix A, A.2.1–A.3.1, PDF page 62 (the idea behind the "IRI-years saved" objective; the appendix formulas themselves are not implemented) | 2026-11-17 |

The English edition of JTG 5210-2018 states that it is consistent with the Chinese edition and that the Chinese
edition prevails in case of dispute.

## 3. Unit costs (Part B)

| Fact used | Source | Where | Retrieved |
|---|---|---|---|
| Resurface existing lane, rural Interstate, flat: 332 thousand 2016 USD per lane-mile; typical reconstruction of an existing lane: 1,160 thousand | FHWA, *Status of the Nation's Highways, Bridges, and Transit: Conditions & Performance Report*, 24th edition, Appendix A; https://www.fhwa.dot.gov/policy/24cpr/pdf/AppendixA.pdf (SHA-256 a54e6ded…6ab350de) | Exhibit A-5 "Typical Rural Pavement Costs per Lane Mile Assumed in HERS by Type of Improvement", page A-7 | 2026-11-17 |
| Thin asphalt overlay: "Based on 13 projects, cost/lane mile ranges from $29,409 to $249,699" (2009 dollars) | FHWA-HIF-10-020, *Performance Evaluation of Various Rehabilitation and Preservation Treatments*, January 2010, FHWA Office of Asset Management; https://www.fhwa.dot.gov/pavement/preservation/pubs/perfeval/chap03.cfm | chapter 3, summary table "HMA – thin overlay" | 2026-11-17 |
| Same report, for context only (not used): chip seal $6,732–$145,976, micro-surfacing $19,436–$32,698, mill and resurfacing $63,612–$679,684 per lane-mile | same | chapter 3 summary tables | 2026-11-17 |

## 4. Could not verify — treated as assumptions or left out

* The Chinese-language PDF of JTG 5210-2018 on the Ministry's site
  (https://xxgk.mot.gov.cn/jigou/glj/202006/P020230330565298344924.pdf) is a scan without a text layer. Its
  clauses were not compared by eye with the English edition; all values above come from the English edition.
* The page numbers printed on the pages of the English PDF were not legible in the extracted text; the page
  numbers given above are positions in the PDF file.
* No official full text of JTG 5142-2019 (the asphalt pavement maintenance specification) was found, so the
  repository uses **no** rehabilitation trigger from it. The limits "resurfacing only while PCI ≥ 70", the
  worst-first triggers (1.5 and 2.5 m/km) and the 8-year cycle are assumptions.
* The distress ratio DR of JTG 5210-2018 weights every distress type and severity (Tables 7.4.5-1/-2). LTPP's
  cracking percent (HPMS definition) is used in its place; this is an approximation, not the standard's DR.
* The thin-overlay cost is the midpoint of a wide published range in 2009 dollars; the other two costs are in
  2016 dollars. No price index was applied.
* HERS "typical reconstruction" is used as the price of a thick overlay; no public source was found that
  prices overlays by thickness class on the same basis as Exhibit A-5.
* LTPP's own climate-zone thresholds were not checked, so no climate zone is derived; the annual climate
  variables are used directly.
* InfoPave has no dedicated terms-of-use page that could be found; the statements in section 1 are the ones
  the site links to or that the data.gov record declares.
