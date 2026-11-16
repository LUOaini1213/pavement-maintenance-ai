"""Stage 1 of the data build: dump the LTPP tables this study uses from the Access databases to CSV.

Reads data/raw/ltpp_sdr40/*.zip (see scripts/fetch_ltpp.py), unpacks the .mdb files next to them and
writes one CSV per table to data/raw/ltpp_sdr40/csv/ (git-ignored). The databases are parsed as data
with the pure-Python `access-parser` package; nothing from data/raw/ is executed.

    python -I scripts/dump_tables.py            # about ten minutes

Needs requirements-data.txt (access-parser). Stage 2 is scripts/build_extracts.py.
"""
from __future__ import annotations

import csv
import logging
import sys
import time
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
RAW = REPO / "data" / "raw" / "ltpp_sdr40"
MDB = RAW / "mdb"
OUT = RAW / "csv"

# database -> {table: columns to keep (None = all)}
TABLES = {
    "Administration": {
        "EXPERIMENT_SECTION": None,
        "SECTION_LAYER_STRUCTURE": ["STATE_CODE", "SHRP_ID", "CONSTRUCTION_NO", "LAYER_NO", "DESCRIPTION",
                                    "LAYER_TYPE", "REPR_THICKNESS", "MATL_CODE"],
        "SECTION_COORDINATES": ["STATE_CODE", "SHRP_ID", "LATITUDE", "LONGITUDE", "ELEVATION"],
        "CODES": None,
        "REGIONS": None,
    },
    "Inventory": {
        "INV_AGE": None,
    },
    "Maint_Rehab": {
        "MNT_IMP": None,
        "RHB_IMP": None,
        "ANALYSIS_MNT_RHB_SUMMARY": None,
    },
    "Monitoring": {
        "MON_HSS_VISIT_NO": None,
        "MON_HSS_PROFILE_SECTION": ["VISIT_NO", "RUN_NUMBER", "IRI_LEFT_WHEEL_PATH", "IRI_RIGHT_WHEEL_PATH", "MRI",
                                    "RECORD_STATUS"],
        "MON_T_PROF_INDEX_SECTION": ["STATE_CODE", "SHRP_ID", "SURVEY_DATE", "CONSTRUCTION_NO", "NO_PROFILES",
                                     "LLH_DEPTH_1_8_MEAN", "RLH_DEPTH_1_8_MEAN", "MAX_MEAN_DEPTH_1_8",
                                     "RECORD_STATUS"],
        "MON_DIS_AC_REV": ["STATE_CODE", "SHRP_ID", "SURVEY_DATE", "CONSTRUCTION_NO", "GATOR_CRACK_A_L",
                           "GATOR_CRACK_A_M", "GATOR_CRACK_A_H", "BLK_CRACK_A_L", "BLK_CRACK_A_M", "BLK_CRACK_A_H",
                           "LONG_CRACK_WP_L_L", "LONG_CRACK_WP_L_M", "LONG_CRACK_WP_L_H", "LONG_CRACK_NWP_L_L",
                           "LONG_CRACK_NWP_L_M", "LONG_CRACK_NWP_L_H", "TRANS_CRACK_L_L", "TRANS_CRACK_L_M",
                           "TRANS_CRACK_L_H", "PATCH_A_L", "PATCH_A_M", "PATCH_A_H", "SURVEY_WIDTH",
                           "RECORD_STATUS"],
        "MON_DIS_AC_CRACK_INDEX": None,
    },
    "Traffic": {
        "TRF_TREND": ["STATE_CODE", "SHRP_ID", "CONSTRUCTION_NO", "YEAR", "AADTT_ALL_TRUCKS_TREND",
                      "ANNUAL_ESAL_TREND", "ANNUAL_GESAL_TREND", "AADTT_SOURCE", "ESAL_SOURCE"],
    },
    "Climate_Summary_Data": {
        "CLM_SITE_VWS_LINK": None,
        "CLM_VWS_PRECIP_ANNUAL": ["VWS_ID", "YEAR", "TOTAL_ANN_PRECIP", "WET_DAYS_YR", "TOTAL_SNOWFALL_YR"],
        "CLM_VWS_TEMP_ANNUAL": ["VWS_ID", "YEAR", "MEAN_ANN_TEMP_AVG", "DAYS_ABOVE_32_C_YR", "DAYS_BELOW_0_C_YR",
                                "FREEZE_INDEX_YR", "FREEZE_THAW_YR"],
    },
}


def unpack() -> None:
    MDB.mkdir(parents=True, exist_ok=True)
    for z in sorted(p for p in RAW.iterdir() if p.suffix.lower() == ".zip"):
        with zipfile.ZipFile(z) as f:
            for info in f.infolist():
                if info.filename.lower().endswith(".mdb"):
                    dest = MDB / Path(info.filename).name      # flat name only: no path from the archive is used
                    if not dest.exists() or dest.stat().st_size != info.file_size:
                        dest.write_bytes(f.read(info))


def main(only: list[str]) -> None:
    from access_parser import AccessParser
    logging.disable(logging.CRITICAL)
    unpack()
    OUT.mkdir(parents=True, exist_ok=True)
    for dbname, tables in TABLES.items():
        todo = {t: c for t, c in tables.items() if (not only or t in only) and not (OUT / f"{t}.csv").exists()}
        if not todo:
            continue
        db = AccessParser(str(MDB / f"{dbname}.mdb"))
        for table, cols in todo.items():
            t0 = time.time()
            data = db.parse_table(table)
            keep = cols or list(data.keys())
            n = len(next(iter(data.values()))) if data else 0
            tmp = OUT / f"{table}.csv.part"
            with open(tmp, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(keep)
                for i in range(n):
                    w.writerow(["" if data[c][i] is None else data[c][i] for c in keep])
            tmp.replace(OUT / f"{table}.csv")
            print(f"{dbname}.{table}: {n} rows in {time.time() - t0:.0f} s", flush=True)
    print("DONE", flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])
