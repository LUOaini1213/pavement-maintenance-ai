"""Download the LTPP Standard Data Release (SDR) volumes this study uses.

Source: FHWA Long-Term Pavement Performance (LTPP) InfoPave, Standard Data Release page
https://infopave.fhwa.dot.gov/Data/StandardDataRelease . Each volume link on that page calls
/DownloadTracker/SDR/Volume/<id>; the tracker page carries the real file location (a CloudFront URL)
in a JSON object. No login is needed.

The zips land in data/raw/ltpp_sdr40/ (git-ignored). Nothing in data/raw/ is ever executed: the zips
hold Microsoft Access databases that scripts/build_extracts.py reads as data.

    python scripts/fetch_ltpp.py            # download what is missing, then write data/raw_manifest.json
    python scripts/fetch_ltpp.py --verify   # only re-hash the local files against the manifest

Only the Python standard library is used.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
RAW = REPO / "data" / "raw" / "ltpp_sdr40"
MANIFEST = REPO / "data" / "raw_manifest.json"
TRACKER = "https://infopave.fhwa.dot.gov/DownloadTracker/SDR/Volume/{vid}?viewDownload=inline"
SDR_PAGE = "https://infopave.fhwa.dot.gov/Data/StandardDataRelease"
UA = "Mozilla/5.0 (personal desk study; data fetch script)"

# SDR 40 (September 2026) volumes, by the IDs on the Standard Data Release page (topic view).
VOLUMES = {
    3323: "Administration",
    3305: "Inventory",
    3306: "Maint Rehab",
    3384: "Pavement Structure and Construction - Consolidated",
    3317: "Specific Pavement Studies",
    3333: "Traffic",
    3346: "Climate Summary Data",
    3376: "Monitoring",
}


def _get(url: str, timeout: int = 120) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def resolve(vid: int) -> dict:
    """Return the tracker's JSON record (FileName, FilePath, FileSize in MB) for one volume."""
    page = _get(TRACKER.format(vid=vid)).decode("utf-8", "replace")
    m = re.search(r"var dwnloadData = (\{.*?\});", page)
    if not m:
        raise RuntimeError(f"volume {vid}: tracker page has no download record")
    rec = json.loads(m.group(1))
    if not rec.get("FileFound"):
        raise RuntimeError(f"volume {vid}: tracker says the file does not exist")
    return rec


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    old = json.loads(MANIFEST.read_text(encoding="utf-8")) if MANIFEST.exists() else {"files": []}
    known = {f["volume_id"]: f for f in old.get("files", [])}
    files = []
    for vid, label in VOLUMES.items():
        rec = resolve(vid)
        url = rec["FilePath"]
        parts = urllib.parse.urlsplit(url)
        safe_url = urllib.parse.urlunsplit(parts._replace(path=urllib.parse.quote(parts.path)))
        dest = RAW / rec["FileName"]
        if dest.exists() and vid in known and known[vid]["sha256"] == sha256(dest):
            files.append(known[vid])
            print(f"have  {dest.name}")
            continue
        t0 = time.time()
        data = _get(safe_url, timeout=900)
        dest.write_bytes(data)
        entry = {
            "volume_id": vid,
            "volume": label,
            "file_name": rec["FileName"],
            "tracker_url": TRACKER.format(vid=vid),
            "file_url": url,
            "retrieved_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
        }
        files.append(entry)
        print(f"got   {dest.name}  {len(data) / 1e6:.1f} MB in {time.time() - t0:.0f} s")
    manifest = {
        "dataset": "FHWA LTPP InfoPave Standard Data Release 40 (September 2026)",
        "landing_page": SDR_PAGE,
        "citation": "Long Term Pavement Performance InfoPave, Standard Data Release, SDR 40, "
                    "https://infopave.fhwa.dot.gov/Data/StandardDataRelease",
        "licence": "U.S. Government Works (data.gov record 'Long-Term Pavement Performance (LTPP)', "
                   "license https://www.usa.gov/government-works); see docs/sources.md",
        "files": files,
    }
    MANIFEST.write_text(json.dumps(manifest, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {MANIFEST.relative_to(REPO)}")


def verify() -> int:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    bad = 0
    for f in manifest["files"]:
        p = RAW / f["file_name"]
        ok = p.exists() and sha256(p) == f["sha256"]
        bad += not ok
        print(("ok    " if ok else "BAD   ") + f["file_name"])
    return bad


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--verify", action="store_true")
    a = ap.parse_args()
    if a.verify:
        sys.exit(1 if verify() else 0)
    fetch()
