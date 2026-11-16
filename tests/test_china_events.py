"""Hand-checked cases for the JTG index formulas and the LTPP event classification."""
import math

import pytest

from pavement_ai import china, events


# ---- JTG 5210-2018 eq. (7.4.7): RQI = 100 / (1 + a0 exp(a1 IRI)) ------------------------------------------
def test_rqi_expressway_hand_values():
    # IRI 0: 100 / 1.026
    assert china.rqi(0.0) == pytest.approx(97.46589, abs=1e-5)
    # IRI 2: exp(1.3) = 3.669297, x 0.026 = 0.0954017, 100 / 1.0954017
    assert china.rqi(2.0) == pytest.approx(91.2907, abs=1e-4)
    # IRI 4: exp(2.6) = 13.463738, x 0.026 = 0.350057, 100 / 1.350057
    assert china.rqi(4.0) == pytest.approx(74.0709, abs=1e-4)


def test_rqi_other_classes_use_their_own_coefficients():
    # IRI 2: exp(1.16) = 3.189933, x 0.0185 = 0.0590138, 100 / 1.0590138
    assert china.rqi(2.0, "other") == pytest.approx(94.4275, abs=1e-4)
    assert china.RQI_COEFFICIENTS["expressway_class1"] == {"a0": 0.026, "a1": 0.65}
    assert china.RQI_COEFFICIENTS["other"] == {"a0": 0.0185, "a1": 0.58}


def test_iri_for_rqi_is_the_inverse():
    # RQI 90: (100/90 - 1) / 0.026 = 4.273504, ln = 1.452435, / 0.65
    assert china.iri_for_rqi(90.0) == pytest.approx(2.234515, abs=1e-5)
    # RQI 80: 0.25 / 0.026 = 9.615385, ln = 2.263364, / 0.65
    assert china.iri_for_rqi(80.0) == pytest.approx(3.482098, abs=1e-5)
    for target in (95.0, 85.0, 70.0, 60.0):
        assert china.rqi(china.iri_for_rqi(target)) == pytest.approx(target, abs=1e-9)
    assert china.rqi(china.iri_for_rqi(85.0, "other"), "other") == pytest.approx(85.0, abs=1e-9)


# ---- JTG 5210-2018 eq. (7.4.8): RDI ---------------------------------------------------------------------------
@pytest.mark.parametrize("rut, expected", [(0.0, 100.0), (5.0, 95.0), (10.0, 90.0), (15.0, 75.0), (20.0, 60.0),
                                           (40.0, 0.0), (40.5, 0.0), (55.0, 0.0)])
def test_rdi_piecewise(rut, expected):
    assert china.rdi(rut) == pytest.approx(expected, abs=1e-12)


# ---- JTG 5210-2018 Table 4.0.2 --------------------------------------------------------------------------------
@pytest.mark.parametrize("value, name", [(100.0, "excellent"), (90.0, "excellent"), (89.99, "good"), (80.0, "good"),
                                         (79.99, "average"), (70.0, "average"), (69.99, "poor"), (60.0, "poor"),
                                         (59.99, "failed"), (0.0, "failed")])
def test_grade_limits(value, name):
    assert china.grade(value) == name


def test_grade_shares_sum_to_one_and_keep_order():
    shares = china.grade_shares([95, 91, 85, 75, 65, 50, 50, 92])
    assert list(shares) == ["excellent", "good", "average", "poor", "failed"]
    assert shares == {"excellent": 3 / 8, "good": 1 / 8, "average": 1 / 8, "poor": 1 / 8, "failed": 2 / 8}
    assert math.isclose(sum(shares.values()), 1.0)
    assert china.GRADE_ZH["excellent"] == "优" and china.GRADE_ZH["failed"] == "差"


def test_preventive_windows_are_the_published_ones():
    w = china.PREVENTIVE_WINDOWS_EXPRESSWAY
    assert w["thin_overlay"]["rqi_min"] == 85.0 and w["thin_overlay"]["rdi_min"] == 80.0
    assert w["micro_surfacing"]["rqi_min"] == 90.0 and w["fog_seal"]["rqi_min"] == 93.0
    assert w["ultra_thin_overlay"]["rqi_min"] == 88.0


# ---- event classification ---------------------------------------------------------------------------------------
def test_parse_codes():
    assert events.parse_codes("31,51") == frozenset({31, 51})
    assert events.parse_codes(" 1, 2,3 ") == frozenset({1, 2, 3})
    assert events.parse_codes("") == frozenset()
    assert events.parse_codes(None) == frozenset()
    assert events.parse_codes(float("nan")) == frozenset()
    assert events.parse_codes("19.0") == frozenset({19})


@pytest.mark.parametrize("codes, mm, cn, expected", [
    ("", None, 1, "original"),
    ("19", 50.0, 1, "original"),                 # the first construction number is always the original surface
    ("1", None, 2, "routine"),                   # crack sealing
    ("25", None, 3, "routine"),                  # pothole patching
    ("31", None, 2, "seal"),                     # aggregate seal coat
    ("33", None, 2, "seal"),                     # slurry seal
    ("1,34", None, 2, "seal"),                   # crack seal + fog seal
    ("19", 25.0, 2, "thin_overlay"),
    ("19", 40.0, 2, "thin_overlay"),             # 40 mm is still thin
    ("51", 41.0, 2, "medium_overlay"),
    ("51", 74.9, 2, "medium_overlay"),
    ("55", 75.0, 2, "thick_overlay"),            # 75 mm is thick
    ("19", 130.0, 4, "thick_overlay"),
    ("31,51", 61.0, 6, "medium_overlay"),        # an overlay outranks the seal recorded with it
    ("18", None, 2, "thick_overlay"),            # reconstruction
    ("19", None, 2, "overlay_unknown"),
    ("19", float("nan"), 2, "overlay_unknown"),
    ("19", 0.0, 2, "overlay_unknown"),
    ("12", None, 2, "routine"),                  # milling / grinding only
])
def test_classify_event(codes, mm, cn, expected):
    assert events.classify_event(codes, mm, cn) == expected


def test_resetting_set():
    assert "routine" not in events.RESETTING
    assert {"original", "seal", "thin_overlay", "medium_overlay", "thick_overlay",
            "overlay_unknown"} == set(events.RESETTING)
