#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pull_dlt_fuel.py — pull JUST the DLT fuel-type table (dataset_1_1_04) from gdcatalog.dlt.go.th.

dataset_1_1_04 is cumulative registered-vehicle stock by ประเภทรถ (vehicle type) × จังหวัด
(province) × ประเภทเชื้อเพลิง (fuel type). It is the MEASURED base for both build_ev_penetration.py
(per-province EV/diesel) and build_vehicle_collateral.py (per-province diesel share of the
car+pickup title-able fleet). gdcatalog.dlt.go.th is the geoblock-bypass host (data.go.th itself is
geoblocked) and is reachable from any IP incl. cloud/CI — no Thai laptop needed.

This is the light, single-dataset alternative to pull_dlt_all.py (which mirrors the whole catalog).
It resolves the current CSV resource via the CKAN API (resource URLs rotate) and writes it into
source-data/dlt/raw/dataset_1_1_04/. That directory is GITIGNORED — raw, re-pullable input, never
committed; only the derived platform/data JSON is committed.

  python3 pull_dlt_fuel.py            # download the current dataset_1_1_04 CSV(s)
  python3 pull_dlt_fuel.py --list     # just show the resources, no download
"""
import argparse, json, os, re, sys, time, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTDIR = os.path.join(ROOT, "source-data", "dlt", "raw", "dataset_1_1_04")
BASE = "https://gdcatalog.dlt.go.th/api/3/action/"
DATASET = "dataset_1_1_04"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}


def _get(url, tries=4, timeout=90):
    last = None
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
                return r.read()
        except Exception as e:
            last = e
            time.sleep(4 * (i + 1))
    raise RuntimeError("GET failed after %d tries: %s" % (tries, last))


def _safe(name):
    s = re.sub(r"[^\wก-๙.\- ]+", "_", (name or "resource")).strip().replace(" ", "_")
    return s[:120]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--list", action="store_true", help="enumerate resources only, no download")
    args = ap.parse_args()

    pkg = json.loads(_get(BASE + "package_show?id=" + DATASET))["result"]
    print("%s — %s" % (DATASET, pkg.get("title", "")))
    res_list = [r for r in pkg.get("resources", []) if (r.get("format") or "").upper() == "CSV"]
    if not res_list:
        sys.exit("pull_dlt_fuel.py: no CSV resource on %s (schema changed?)" % DATASET)
    for r in res_list:
        print("  CSV  %s  %s" % (r.get("name", ""), r.get("url", "")))
    if args.list:
        return

    os.makedirs(OUTDIR, exist_ok=True)
    got = 0
    for r in res_list:
        url = r["url"]
        # Name the file EXACTLY as pull_dlt_all.py does — from the resource NAME (which carries the
        # Thai-month vintage, e.g. "...28 กุมภาพันธ์ 2569"). This keeps the two pullers interchangeable
        # so build_ev_penetration.py's _vintage() parser (which reads the Thai-month filename) and
        # build_vehicle_collateral.py both reproduce their committed JSON byte-exact from either puller.
        fn = _safe(r.get("name", r.get("id", "res"))) + ".csv"
        path = os.path.join(OUTDIR, fn)
        raw = _get(url, tries=3)
        if len(raw) < 200:
            print("  [stub] %s (%d bytes) — upstream not serving; skipped" % (fn, len(raw)))
            continue
        open(path, "wb").write(raw)
        rows = raw.count(b"\n")
        print("  wrote %s (%d bytes, ~%d rows)" % (path, len(raw), rows))
        got += 1
    print("done: %d CSV file(s) into %s" % (got, OUTDIR))
    print("next: python3 build_vehicle_collateral.py   (and build_ev_penetration.py)")


if __name__ == "__main__":
    main()
