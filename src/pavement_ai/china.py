"""Chinese-standard view: riding quality index (RQI), rut depth index (RDI) and condition grades.

Formulas, coefficients and grade limits are those of JTG 5210-2018 "Highway Performance Assessment Standard"
(Ministry of Transport of the PRC), read from the Ministry's official English edition; the preventive-maintenance
condition windows are from JTG/T 5142-01-2021. Clause numbers, URLs and retrieval dates are in docs/sources.md
and in SOURCES below.
"""
from __future__ import annotations

import math

# JTG 5210-2018, clause 7.4.7, equation (7.4.7): RQI = 100 / (1 + a0 * exp(a1 * IRI)), IRI in m/km.
RQI_COEFFICIENTS = {
    "expressway_class1": {"a0": 0.026, "a1": 0.65},     # "Motorways and Class-1 highways"
    "other": {"a0": 0.0185, "a1": 0.58},                # "other classified highways"
}
# JTG 5210-2018, clause 7.4.8, equation (7.4.8), rut depth RD in mm.
RDI_A0, RDI_A1, RDI_RDA, RDI_RDB = 1.0, 3.0, 10.0, 40.0
# JTG 5210-2018, clause 7.4.5, equation (7.4.5-1): PCI = 100 - a0 * DR^a1, DR = distress ratio in %.
PCI_A0_ASPHALT, PCI_A1_ASPHALT = 15.00, 0.412
# JTG 5210-2018, Table 4.0.2: lower limits of the grades for RQI and RDI of asphalt pavements.
GRADE_LIMITS = [(90.0, "excellent"), (80.0, "good"), (70.0, "average"), (60.0, "poor")]
GRADE_ZH = {"excellent": "优", "good": "良", "average": "中", "poor": "次", "failed": "差"}
# JTG/T 5142-01-2021: condition a pavement should still have for a preventive treatment, expressways.
PREVENTIVE_WINDOWS_EXPRESSWAY = {
    "fog_seal": {"table": "5.2.2", "pci_min": 93.0, "rqi_min": 93.0, "rdi_min": 93.0},
    "micro_surfacing": {"table": "5.2.5", "pci_min": 90.0, "rqi_min": 90.0, "rdi_min": 90.0},
    "thin_overlay": {"table": "5.3.2", "pci_min": 85.0, "rqi_min": 85.0, "rdi_min": 80.0},
    "ultra_thin_overlay": {"table": "5.3.2", "pci_min": 88.0, "rqi_min": 88.0, "rdi_min": 85.0},
}

SOURCES = {
    "jtg_5210_2018": {
        "title": "JTG 5210-2018 (EN) Highway Performance Assessment Standard, official English edition",
        "issuer": "Ministry of Transport of the People's Republic of China",
        "issued": "2018-12-25", "effective": "2019-05-01",
        "url": "https://xxgk.mot.gov.cn/jigou/glj/202204/P020220425579066545831.pdf",
        "sha256": "e36a3baad330112843318aa5ef2028b31e8601676ecd933085e1a5398f4656fd",
        "retrieved": "2026-11-17",
        "used": "clause 7.4.5 eq. (7.4.5-1) on PDF page 40; clause 7.4.7 eq. (7.4.7) on PDF pages 42-43; "
                "clause 7.4.8 eq. (7.4.8) on PDF page 43; Table 4.0.2 on PDF page 22",
    },
    "jtg_t_5142_01_2021": {
        "title": "JTG/T 5142-01-2021 公路沥青路面预防养护技术规范",
        "issuer": "Ministry of Transport of the People's Republic of China",
        "issued": "2021-08-17", "effective": "2021-12-01",
        "url": "https://xxgk.mot.gov.cn/jigou/glj/202108/P020210827331277450621.pdf",
        "sha256": "023b669df996a869663d5ae38f24a71582bda7cbc43466f3e8afa6aeccdf68bc",
        "retrieved": "2026-11-17",
        "used": "Tables 5.2.2, 5.2.5 and 5.3.2 on PDF pages 21-22; commentary to clause 2.1.1 on PDF page 10",
    },
}


def rqi(iri: float, road_class: str = "expressway_class1") -> float:
    c = RQI_COEFFICIENTS[road_class]
    return 100.0 / (1.0 + c["a0"] * math.exp(c["a1"] * iri))


def iri_for_rqi(target_rqi: float, road_class: str = "expressway_class1") -> float:
    """Inverse of rqi(): the IRI (m/km) at which RQI equals `target_rqi`."""
    c = RQI_COEFFICIENTS[road_class]
    return math.log((100.0 / target_rqi - 1.0) / c["a0"]) / c["a1"]


def rdi(rut_mm: float) -> float:
    if rut_mm <= RDI_RDA:
        return 100.0 - RDI_A0 * rut_mm
    if rut_mm <= RDI_RDB:
        return 90.0 - RDI_A1 * (rut_mm - RDI_RDA)
    return 0.0


def pci(distress_ratio_pct: float) -> float:
    """Pavement surface condition index of an asphalt pavement from the distress ratio DR (%)."""
    return 100.0 - PCI_A0_ASPHALT * max(0.0, distress_ratio_pct) ** PCI_A1_ASPHALT


def dr_for_pci(target_pci: float) -> float:
    """Inverse of pci(): the distress ratio (%) at which PCI equals `target_pci`."""
    return ((100.0 - target_pci) / PCI_A0_ASPHALT) ** (1.0 / PCI_A1_ASPHALT)


def grade(index: float) -> str:
    for limit, name in GRADE_LIMITS:
        if index >= limit:
            return name
    return "failed"


def grade_shares(values) -> dict:
    """Share of values in each grade, keys in the order excellent ... failed."""
    names = [n for _, n in GRADE_LIMITS] + ["failed"]
    counts = {n: 0 for n in names}
    for v in values:
        counts[grade(float(v))] += 1
    total = max(1, sum(counts.values()))
    return {n: counts[n] / total for n in names}
