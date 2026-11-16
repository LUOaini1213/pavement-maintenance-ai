"""Stage 2 of the data build: turn the dumped LTPP tables into the small extracts committed in data/derived/.

Input : data/raw/ltpp_sdr40/csv/*.csv (written by scripts/dump_tables.py; git-ignored)
Output: data/derived/{sections,periods,iri,rut,crack,traffic}.csv and data/derived/manifest.json (SHA-256)

Only asphalt-surfaced (LTPP pavement family AC*) test sections are kept. Every row is a measurement or an
inventory fact from LTPP; the only things added here are unit conversions (inch -> mm), run averages and the
event classification in pavement_ai/events.py.

    python -I scripts/build_extracts.py
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
from pavement_ai.events import classify_event, OVERLAY_CODES  # noqa: E402

CSV = REPO / "data" / "raw" / "ltpp_sdr40" / "csv"
OUT = REPO / "data" / "derived"
INCH = 25.4


def read(name: str) -> pd.DataFrame:
    df = pd.read_csv(CSV / f"{name}.csv", dtype=str, keep_default_na=False)
    if "RECORD_STATUS" in df.columns:
        df = df[df["RECORD_STATUS"] == "E"]          # LTPP release level E = passed all quality checks
    if "STATE_CODE" in df.columns:
        df["STATE_CODE"] = pd.to_numeric(df["STATE_CODE"]).astype(int)
    if "CONSTRUCTION_NO" in df.columns:
        df["CONSTRUCTION_NO"] = pd.to_numeric(df["CONSTRUCTION_NO"]).astype(int)
    if "SHRP_ID" in df.columns:
        df["section_id"] = df["STATE_CODE"].map("{:02d}".format) + "-" + df["SHRP_ID"]
    return df


def num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s.replace("", np.nan), errors="coerce")


def date(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s.replace("", np.nan), errors="coerce").dt.strftime("%Y-%m-%d")


def write(df: pd.DataFrame, name: str) -> None:
    df.to_csv(OUT / name, index=False, lineterminator="\n", float_format="%.4g")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    exp = read("EXPERIMENT_SECTION")
    exp["start"] = date(exp["CN_ASSIGN_DATE"])
    exp = exp.sort_values(["section_id", "CONSTRUCTION_NO"])

    # ---- layer structure per construction number (inches -> mm) -------------------------------------
    lay = read("SECTION_LAYER_STRUCTURE")
    lay["thick_mm"] = num(lay["REPR_THICKNESS"]) * INCH
    lay["desc"] = num(lay["DESCRIPTION"])
    is_ac = (lay["LAYER_TYPE"] == "AC") & (lay["desc"] != 2)          # description 2 = seal coat
    struct = pd.DataFrame({
        "ac_mm": lay[is_ac].groupby(["section_id", "CONSTRUCTION_NO"])["thick_mm"].sum(),
        "overlay_layers_mm": lay[is_ac & (lay["desc"] == 1)].groupby(["section_id", "CONSTRUCTION_NO"])["thick_mm"].sum(),
        "unbound_base_mm": lay[lay["LAYER_TYPE"].isin(["GB", "GS"])].groupby(["section_id", "CONSTRUCTION_NO"])["thick_mm"].sum(),
        "bound_base_mm": lay[lay["LAYER_TYPE"].isin(["TB", "TS"])].groupby(["section_id", "CONSTRUCTION_NO"])["thick_mm"].sum(),
        "pcc_mm": lay[lay["LAYER_TYPE"] == "PC"].groupby(["section_id", "CONSTRUCTION_NO"])["thick_mm"].sum(),
    }).reset_index()

    # ---- overlay thickness recorded with the rehabilitation event -----------------------------------
    rhb = read("RHB_IMP")
    rhb["code"] = num(rhb["IMP_TYPE"])
    rhb["t_mm"] = num(rhb["IMP_THICKNESS"]) * INCH
    ov = rhb[rhb["code"].isin(OVERLAY_CODES)].groupby(["section_id", "CONSTRUCTION_NO"])["t_mm"].sum(min_count=1)
    ov = ov.rename("rhb_overlay_mm").reset_index()

    per = exp[["section_id", "STATE_CODE", "SHRP_ID", "CONSTRUCTION_NO", "start", "CN_CHANGE_REASON",
               "PAVEMENT_FAMILY", "GPS_SPS", "EXPERIMENT_NO"]].merge(struct, how="left").merge(ov, how="left")
    per = per.sort_values(["section_id", "CONSTRUCTION_NO"]).reset_index(drop=True)
    prev_ov = per.groupby("section_id")["overlay_layers_mm"].shift(1).fillna(0.0)
    layer_gain = (per["overlay_layers_mm"].fillna(0.0) - prev_ov).clip(lower=0.0)
    per["overlay_mm"] = per["rhb_overlay_mm"].where(per["rhb_overlay_mm"] > 0, layer_gain.where(layer_gain > 0))
    per["event"] = [classify_event(c, t, n) for c, t, n in
                    zip(per["CN_CHANGE_REASON"], per["overlay_mm"], per["CONSTRUCTION_NO"])]
    ac_sections = sorted(per.loc[per["PAVEMENT_FAMILY"].str.startswith("AC"), "section_id"].unique())
    per = per[per["section_id"].isin(ac_sections)]
    per_out = per.rename(columns={"CONSTRUCTION_NO": "cn", "CN_CHANGE_REASON": "work_codes",
                                  "PAVEMENT_FAMILY": "family"})[
        ["section_id", "cn", "start", "work_codes", "event", "overlay_mm", "family", "ac_mm", "unbound_base_mm",
         "bound_base_mm", "pcc_mm"]]
    for c in ["overlay_mm", "ac_mm", "unbound_base_mm", "bound_base_mm", "pcc_mm"]:
        per_out[c] = per_out[c].round(0)
    write(per_out, "periods.csv")

    # ---- IRI: mean of the runs of one profiler visit ------------------------------------------------
    vis = read("MON_HSS_VISIT_NO")[["VISIT_NO", "section_id", "CONSTRUCTION_NO", "VISIT_DATE"]]
    pro = read("MON_HSS_PROFILE_SECTION")
    pro["mri"] = num(pro["MRI"])
    pro = pro[(pro["mri"] > 0.2) & (pro["mri"] < 12.0)]
    g = pro.groupby("VISIT_NO")["mri"].agg(iri="mean", n_runs="size").reset_index()
    iri = vis.merge(g, on="VISIT_NO")
    iri["date"] = date(iri["VISIT_DATE"])
    iri = iri[iri["section_id"].isin(ac_sections)].dropna(subset=["date"])
    iri = iri.groupby(["section_id", "date"]).agg(cn=("CONSTRUCTION_NO", "max"), iri=("iri", "mean"),
                                                  n_runs=("n_runs", "sum")).reset_index()
    iri["iri"] = iri["iri"].round(3)
    write(iri, "iri.csv")

    # ---- rut depth (1.8 m straight-edge, mm) ----------------------------------------------------------
    rut = read("MON_T_PROF_INDEX_SECTION")
    rut["date"] = date(rut["SURVEY_DATE"])
    rut["rut_mm"] = num(rut["MAX_MEAN_DEPTH_1_8"])
    rut = rut[rut["section_id"].isin(ac_sections)].dropna(subset=["date", "rut_mm"])
    rut = rut.groupby(["section_id", "date"]).agg(cn=("CONSTRUCTION_NO", "max"), rut_mm=("rut_mm", "mean")).reset_index()
    write(rut, "rut.csv")

    # ---- cracking -------------------------------------------------------------------------------------
    ci = read("MON_DIS_AC_CRACK_INDEX")
    ci["date"] = date(ci["SURVEY_DATE"])
    ci["crack_pct"] = num(ci["HPMS16_CRACKING_PERCENT_AC"])
    ci["mepdg_crack_pct"] = num(ci["MEPDG_CRACKING_PERCENT_AC"])
    dis = read("MON_DIS_AC_REV")
    dis["date"] = date(dis["SURVEY_DATE"])
    dis["fatigue_m2"] = sum(num(dis[c]).fillna(0) for c in ["GATOR_CRACK_A_L", "GATOR_CRACK_A_M", "GATOR_CRACK_A_H"])
    dis["trans_m"] = sum(num(dis[c]).fillna(0) for c in ["TRANS_CRACK_L_L", "TRANS_CRACK_L_M", "TRANS_CRACK_L_H"])
    dis["long_m"] = sum(num(dis[c]).fillna(0) for c in ["LONG_CRACK_WP_L_L", "LONG_CRACK_WP_L_M", "LONG_CRACK_WP_L_H",
                                                         "LONG_CRACK_NWP_L_L", "LONG_CRACK_NWP_L_M", "LONG_CRACK_NWP_L_H"])
    crack = dis[["section_id", "date", "CONSTRUCTION_NO", "fatigue_m2", "trans_m", "long_m"]].merge(
        ci[["section_id", "date", "crack_pct", "mepdg_crack_pct"]], on=["section_id", "date"], how="inner")
    crack = crack[crack["section_id"].isin(ac_sections)].dropna(subset=["date", "crack_pct"])
    crack = crack.groupby(["section_id", "date"]).agg(cn=("CONSTRUCTION_NO", "max"), crack_pct=("crack_pct", "mean"),
                                                      mepdg_crack_pct=("mepdg_crack_pct", "mean"),
                                                      fatigue_m2=("fatigue_m2", "mean"), trans_m=("trans_m", "mean"),
                                                      long_m=("long_m", "mean")).reset_index()
    write(crack, "crack.csv")

    # ---- traffic: LTPP-lane trucks and ESAL per year ------------------------------------------------------
    trf = read("TRF_TREND")
    trf["year"] = num(trf["YEAR"])
    trf["aadtt"] = num(trf["AADTT_ALL_TRUCKS_TREND"])
    trf["kesal"] = num(trf["ANNUAL_ESAL_TREND"]) / 1000.0
    trf = trf[trf["section_id"].isin(ac_sections)].dropna(subset=["year"])
    trf = trf.groupby(["section_id", "year"]).agg(aadtt=("aadtt", "mean"), kesal=("kesal", "mean")).reset_index()
    trf["year"] = trf["year"].astype(int)
    write(trf.round({"aadtt": 0, "kesal": 1}), "traffic.csv")

    # ---- climate normals from the virtual weather station of each site ------------------------------------
    link = read("CLM_SITE_VWS_LINK")[["section_id", "STATE_CODE", "SHRP_ID", "VWS_ID"]]
    pr = pd.read_csv(CSV / "CLM_VWS_PRECIP_ANNUAL.csv", dtype=str, keep_default_na=False)
    tp = pd.read_csv(CSV / "CLM_VWS_TEMP_ANNUAL.csv", dtype=str, keep_default_na=False)
    prn = pd.DataFrame({"VWS_ID": pr["VWS_ID"], "precip_mm": num(pr["TOTAL_ANN_PRECIP"])}).groupby("VWS_ID").mean()
    tpn = pd.DataFrame({"VWS_ID": tp["VWS_ID"], "temp_c": num(tp["MEAN_ANN_TEMP_AVG"]),
                        "freeze_index": num(tp["FREEZE_INDEX_YR"]), "freeze_thaw": num(tp["FREEZE_THAW_YR"]),
                        "days_above_32c": num(tp["DAYS_ABOVE_32_C_YR"])}).groupby("VWS_ID").mean()
    clim = link.merge(prn, left_on="VWS_ID", right_index=True, how="left").merge(tpn, left_on="VWS_ID",
                                                                              right_index=True, how="left")
    by_section = clim.drop_duplicates("section_id").set_index("section_id")
    clim["site_id"] = clim["STATE_CODE"].map("{:02d}".format) + "-" + clim["SHRP_ID"].str[:2]
    by_site = clim.groupby("site_id")[["precip_mm", "temp_c", "freeze_index", "freeze_thaw", "days_above_32c"]].mean()

    # ---- pavement age reference -------------------------------------------------------------------------
    age = read("INV_AGE") if (CSV / "INV_AGE.csv").exists() else pd.DataFrame(columns=["section_id"])
    open_col = next((c for c in age.columns if "TRAFFIC_OPEN" in c), None)
    opened = date(age[open_col]).groupby(age["section_id"]).min() if open_col else pd.Series(dtype=str)

    coords = read("SECTION_COORDINATES").drop_duplicates("section_id").set_index("section_id")
    first = per.groupby("section_id").first()
    rows = []
    for sid in ac_sections:
        site = sid[:5]
        c = by_section.loc[sid] if sid in by_section.index else (by_site.loc[site] if site in by_site.index else None)
        rows.append({
            "section_id": sid, "site_id": site, "gps_sps": first.at[sid, "GPS_SPS"],
            "experiment": first.at[sid, "EXPERIMENT_NO"],
            "lat": round(float(coords.at[sid, "LATITUDE"]), 2) if sid in coords.index and coords.at[sid, "LATITUDE"] else np.nan,
            "lon": round(float(coords.at[sid, "LONGITUDE"]), 2) if sid in coords.index and coords.at[sid, "LONGITUDE"] else np.nan,
            "precip_mm": np.nan if c is None else round(float(c["precip_mm"]), 0),
            "temp_c": np.nan if c is None else round(float(c["temp_c"]), 1),
            "freeze_index": np.nan if c is None else round(float(c["freeze_index"]), 0),
            "freeze_thaw": np.nan if c is None else round(float(c["freeze_thaw"]), 0),
            "days_above_32c": np.nan if c is None else round(float(c["days_above_32c"]), 0),
            "opened": opened.get(sid, ""),
        })
    write(pd.DataFrame(rows), "sections.csv")

    files = {}
    for p in sorted(OUT.glob("*.csv")):
        b = p.read_bytes()
        files[p.name] = {"sha256": hashlib.sha256(b).hexdigest(), "bytes": len(b), "rows": b.count(b"\n") - 1}
    (OUT / "manifest.json").write_text(json.dumps({"source": "LTPP SDR 40, see data/raw_manifest.json",
                                                  "files": files}, indent=1) + "\n", encoding="utf-8", newline="\n")
    for k, v in files.items():
        print(f"{k}: {v['rows']} rows, {v['bytes'] / 1e6:.2f} MB")


if __name__ == "__main__":
    main()
