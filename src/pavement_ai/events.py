"""Classify LTPP construction events (the work codes that open a new CONSTRUCTION_NO) into treatment classes.

The work codes are LTPP's MAINT_WORK codes (table CODES of the Administration volume). The grouping into
classes is this study's own; the 40 mm limit for a thin overlay follows the commentary to clause 2.1.1 of
JTG/T 5142-01-2021 ("generally not more than 40 mm"), the 75 mm limit between a medium and a thick overlay is an
assumption (see docs/sources.md).
"""
from __future__ import annotations

import math

# Asphalt overlays, with or without milling, hot / cold / warm mix, virgin or recycled.
OVERLAY_CODES = frozenset({19, 43, 44, 51, 55, 56, 58, 59, 60, 61})
# Surface treatments and seal coats (single / double / triple surface treatment, aggregate, sand, slurry, fog).
SEAL_CODES = frozenset({28, 29, 30, 31, 32, 33, 34})
RECONSTRUCTION_CODES = frozenset({18})

THIN_OVERLAY_MAX_MM = 40.0      # JTG/T 5142-01-2021, commentary to 2.1.1
THICK_OVERLAY_MIN_MM = 75.0     # assumption

ORIGINAL = "original"
ROUTINE = "routine"             # crack sealing, patching, shoulders, drainage ...: does not reset the surface
SEAL = "seal"
THIN_OVERLAY = "thin_overlay"
MEDIUM_OVERLAY = "medium_overlay"
THICK_OVERLAY = "thick_overlay"
OVERLAY_UNKNOWN = "overlay_unknown"

# Events after which the measured surface is a new one: a deterioration series must not run across them.
RESETTING = frozenset({ORIGINAL, SEAL, THIN_OVERLAY, MEDIUM_OVERLAY, THICK_OVERLAY, OVERLAY_UNKNOWN})


def parse_codes(work_codes) -> frozenset:
    """'31,51' -> {31, 51}; empty / missing -> empty set."""
    if work_codes is None:
        return frozenset()
    if isinstance(work_codes, float) and math.isnan(work_codes):
        return frozenset()
    out = set()
    for part in str(work_codes).replace(";", ",").split(","):
        part = part.strip()
        if part:
            out.add(int(float(part)))
    return frozenset(out)


def classify_event(work_codes, overlay_mm, construction_no: int) -> str:
    """Treatment class of the event that opens construction number `construction_no`."""
    if int(construction_no) == 1:
        return ORIGINAL
    codes = parse_codes(work_codes)
    if codes & RECONSTRUCTION_CODES:
        return THICK_OVERLAY
    if codes & OVERLAY_CODES:
        if overlay_mm is None or (isinstance(overlay_mm, float) and math.isnan(overlay_mm)) or overlay_mm <= 0:
            return OVERLAY_UNKNOWN
        if overlay_mm <= THIN_OVERLAY_MAX_MM:
            return THIN_OVERLAY
        if overlay_mm < THICK_OVERLAY_MIN_MM:
            return MEDIUM_OVERLAY
        return THICK_OVERLAY
    if codes & SEAL_CODES:
        return SEAL
    return ROUTINE
