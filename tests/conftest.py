"""Small hand-made data sets shaped like data/derived/, so every expected value can be worked out on paper."""
import numpy as np
import pandas as pd
import pytest


def _sections(rows):
    base = {"gps_sps": "G", "experiment": "1", "lat": 30.0, "lon": -90.0, "precip_mm": 1000.0, "temp_c": 15.0,
            "freeze_index": 50.0, "freeze_thaw": 40.0, "days_above_32c": 60.0, "opened": np.nan}
    return pd.DataFrame([{**base, **r} for r in rows])


def _periods(rows):
    base = {"work_codes": "", "overlay_mm": np.nan, "family": "ACUB", "ac_mm": 150.0, "unbound_base_mm": 300.0,
            "bound_base_mm": np.nan, "pcc_mm": np.nan}
    return pd.DataFrame([{**base, **r} for r in rows])


@pytest.fixture
def toy():
    """Two sections.

    01-0001 (opened 1985-07-02): IRI 1.0 / 1.2 / 1.4 on 1 Jan 1991-93, crack sealing in 1992 (routine, no reset),
    a 100 mm overlay on 1993-07-02, then IRI 0.80 / 0.85 / 0.90 on 1 Jan 1994-96.
    01-0002: one visit in 1988 (2.0), a slurry seal on 1993-07-02, visits 1994-96 (1.9 / 2.0 / 2.1). The gap before
    the seal is more than three years, so it gives no before/after event.
    """
    sections = _sections([
        {"section_id": "01-0001", "site_id": "01-00", "opened": "1985-07-02"},
        {"section_id": "01-0002", "site_id": "01-00"},
    ])
    periods = _periods([
        {"section_id": "01-0001", "cn": 1, "start": "1987-01-01", "event": "original"},
        {"section_id": "01-0001", "cn": 2, "start": "1992-06-01", "event": "routine", "work_codes": "1"},
        {"section_id": "01-0001", "cn": 3, "start": "1993-07-02", "event": "thick_overlay", "work_codes": "19",
         "overlay_mm": 100.0, "ac_mm": 250.0},
        {"section_id": "01-0002", "cn": 1, "start": "1987-01-01", "event": "original"},
        {"section_id": "01-0002", "cn": 2, "start": "1993-07-02", "event": "seal", "work_codes": "33"},
    ])
    iri = pd.DataFrame([
        ("01-0001", "1991-01-01", 1, 1.0), ("01-0001", "1992-01-01", 1, 1.2), ("01-0001", "1993-01-01", 2, 1.4),
        ("01-0001", "1994-01-01", 3, 0.80), ("01-0001", "1995-01-01", 3, 0.85), ("01-0001", "1996-01-01", 3, 0.90),
        ("01-0002", "1988-01-01", 1, 2.0),
        ("01-0002", "1994-01-01", 2, 1.9), ("01-0002", "1995-01-01", 2, 2.0), ("01-0002", "1996-01-01", 2, 2.1),
    ], columns=["section_id", "date", "cn", "iri"])
    iri["n_runs"] = 5
    rut = pd.DataFrame([
        ("01-0001", "1990-06-01", 1, 4.0), ("01-0001", "1992-06-01", 2, 6.0), ("01-0001", "1995-06-01", 3, 2.0),
    ], columns=["section_id", "date", "cn", "rut_mm"])
    crack = pd.DataFrame([
        ("01-0001", "1991-06-01", 1, 3.0), ("01-0001", "1994-06-01", 3, 0.0),
    ], columns=["section_id", "date", "cn", "crack_pct"])
    for c in ["mepdg_crack_pct", "fatigue_m2", "trans_m", "long_m"]:
        crack[c] = 0.0
    traffic = pd.DataFrame([
        ("01-0001", 1990, 500.0, 100.0), ("01-0001", 1991, 520.0, 200.0), ("01-0001", 1992, 540.0, np.nan),
        ("01-0001", 1993, 560.0, 300.0), ("01-0001", 1995, 600.0, 400.0),
    ], columns=["section_id", "year", "aadtt", "kesal"])
    return {"sections": sections, "periods": periods, "iri": iri, "rut": rut, "crack": crack, "traffic": traffic}
