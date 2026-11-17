"""Every setting and external number of the study in one place, each tagged real / calibrated / assumption.

"real"        read from LTPP or quoted from a cited public document
"calibrated"  estimated in this repository from the LTPP extracts
"assumption"  chosen by the author; the results depend on it and it has no source
"""
from __future__ import annotations

LANE_MILE_KM = 1.609344

VALIDATION = {"folds": 5, "cutoff_year": 2000.0, "n_boot": 1000, "level": 0.95, "min_horizon": 0.5,
              "max_horizon": 5.0, "seed": 0}

# ---- unit costs, thousand USD per lane-mile, as printed in the sources --------------------------------------
COSTS = {
    "preventive": {
        "label": "thin asphalt overlay (40 mm or less)",
        "low_per_lane_mile": 29.409, "high_per_lane_mile": 249.699, "dollar_year": 2009,
        "source": "FHWA-HIF-10-020, Performance Evaluation of Various Rehabilitation and Preservation Treatments "
                  "(January 2010), chapter 3, summary table 'HMA - thin overlay': 'Based on 13 projects, cost/lane "
                  "mile ranges from $29,409 to $249,699' (2009 dollars)",
        "url": "https://www.fhwa.dot.gov/pavement/preservation/pubs/perfeval/chap03.cfm",
        "point": "midpoint of the published range (assumption)",
    },
    "minor_rehab": {
        "label": "resurfacing (overlay above 40 and below 75 mm)",
        "per_lane_mile": 332.0, "dollar_year": 2016,
        "source": "FHWA, Status of the Nation's Highways, Bridges, and Transit: Conditions & Performance, 24th "
                  "edition, Appendix A, Exhibit A-5, rural Interstate, flat terrain, 'Resurface Existing Lane'",
        "url": "https://www.fhwa.dot.gov/policy/24cpr/pdf/AppendixA.pdf",
        "point": "value as published",
    },
    "major_rehab": {
        "label": "thick overlay (75 mm or more) or reconstruction",
        "per_lane_mile": 1160.0, "dollar_year": 2016,
        "source": "same exhibit, 'Typical Reconstruction - Reconstruct Existing Lane'",
        "url": "https://www.fhwa.dot.gov/policy/24cpr/pdf/AppendixA.pdf",
        "point": "value as published; pricing a thick overlay as a reconstruction is an assumption (on the high side)",
    },
}
# LTPP event class whose measured before/after effect stands for each treatment level.
EFFECT_CLASS = {"preventive": "thin_overlay", "minor_rehab": "medium_overlay", "major_rehab": "thick_overlay"}

OPTIMISATION = {
    "horizon_years": 5,
    "mip_rel_gap": 0.002,                     # HiGHS stops once the plan is proven within 0.2 % of the best bound
    "network_min_last_visit_year": 2010,      # assumption: a section enters the network if profiled in 2010 or later
    "section_length_lane_km": 1.0,            # assumption: each 152 m LTPP test section stands for one lane-km
    "budget_shares": [0.005, 0.01, 0.02, 0.03, 0.05, 0.08, 0.12],   # of the cost of resurfacing the whole network
    "base_budget_share": 0.03,
    # JTG/T 5142-01-2021 Table 5.3.2, thin overlay on expressways: PCI and RQI at least 85, RDI at least 80
    "preventive_min_rqi": 85.0, "preventive_min_pci": 85.0, "preventive_min_rdi": 80.0,
    "minor_rehab_min_pci": 70.0,              # assumption: below grade "average" (PCI 70) only a thick overlay will do
    "treatment_floor_iri": 0.5,               # assumption: no treatment leaves a surface smoother than this
    "worst_first": {"trigger_iri": 1.5, "major_iri": 2.5},   # assumption: treat from 1.5 m/km, rebuild from 2.5
    "fixed_cycle_years": 8.0,                 # assumption: thin overlay on every surface that reaches this age
}

INPUT_TABLE = [
    ("IRI, rut depth, cracking, layer thickness, truck traffic, ESAL, climate, work history", "real",
     "LTPP SDR 40 (FHWA InfoPave), release level E records"),
    ("RQI and RDI formulas, coefficients, grade limits", "real", "JTG 5210-2018, clauses 7.4.7, 7.4.8, Table 4.0.2"),
    ("PCI formula and coefficients for asphalt pavement", "real", "JTG 5210-2018, clause 7.4.5"),
    ("Thin overlay allowed only while PCI and RQI are 85 or more and RDI is 80 or more", "real",
     "JTG/T 5142-01-2021, Table 5.3.2 (expressway)"),
    ("LTPP cracking percent (HPMS definition) used as the distress ratio DR in the PCI formula", "assumption",
     "none; DR in JTG 5210-2018 weights each distress type and severity, which is not reproduced"),
    ("Resurfacing allowed only while PCI is 70 or more", "assumption", "none; 70 is the lower limit of grade 'average'"),
    ("Thin overlay = 40 mm or less", "real", "JTG/T 5142-01-2021, commentary to clause 2.1.1"),
    ("Unit costs of resurfacing and reconstruction", "real", "FHWA C&P report, 24th ed., Exhibit A-5 (2016 USD)"),
    ("Unit cost of a thin overlay", "assumption", "midpoint of the range in FHWA-HIF-10-020 (2009 USD), not inflated"),
    ("IRI after a treatment as a line in the IRI before; IRI growth rate after a treatment", "calibrated",
     "before/after pairs of LTPP events, results/treatment_effects.json"),
    ("Do-nothing IRI growth rate", "calibrated", "method that wins the forward validation, results/deterioration.json"),
    ("75 mm limit between medium and thick overlay", "assumption", "none"),
    ("One lane-km per test section; network = sections profiled since 2010", "assumption", "none"),
    ("At most one treatment per section in the five-year plan", "assumption", "keeps the model linear"),
    ("Budget levels; worst-first triggers 1.5 and 2.5 m/km; 8-year cycle; 0.5 m/km floor", "assumption", "none"),
    ("Pricing a thick overlay as a reconstruction", "assumption", "none; on the high side"),
    ("Markov state limits; five-year maximum horizon; year-2000 time cut", "assumption", "none"),
]
