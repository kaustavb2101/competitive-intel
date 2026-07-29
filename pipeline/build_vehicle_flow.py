#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_vehicle_flow.py — PORTFOLIO RISK (objective #1): province-level vehicle-collateral
CHURN (registration/deregistration/ownership-transfer flow), distilled from DLT's
"การดำเนินการทางทะเบียน" (registration-actions) monthly releases.

Why this is new (not a duplicate of vehicles_by_province.json): the existing DLT layer
(vehicles_by_province.json, dataset_1_1_04) is a STOCK snapshot — how many vehicles are
registered, as of one date. This script reads a different DLT dataset — dataset_stat_1_008,
the monthly registration-ACTIONS log — to build a FLOW signal: how fast that stock is
turning over. A high permanent-deregistration ("scrappage") rate on motorcycles/pickups is
a direct portfolio-risk read: collateral is ageing out of the fleet faster, pressuring
recovery values on a title book concentrated in that vehicle class. A high ownership-
TRANSFER rate is a used-vehicle-market-liquidity signal (repossessed collateral resells
faster where transfers are common).

Source: source-data/dlt/raw/dataset_stat_1_008/*.csv — DLT gdcatalog (bypasses the
data.go.th geoblock), mirrored whole by pipeline/pull_dlt_all.py (2026-07-10, "DATA HUNT
wave 10"). Car-law releases only (รถยนต์ — car/pickup/motorcycle/etc. registration
classes); the land-transport-law sibling (dataset_stat_1_009, trucks/buses) is a separate,
not-yet-distilled dataset — logged as a follow-up, not attempted here (scope discipline).

Method: sums the TRAILING 12 MONTHS of available releases (the most recent complete
year) per province, for three collateral-relevant vehicle classes (car ≤7-seat personal
รย.1, personal pickup รย.3, motorcycle รย.12) plus an all-types total, then derives:
  dereg_rate    = permanently-deregistered ("รถแจ้งไม่ใช้ตลอดไป") / total-processed
                  ("รถที่ดำเนินการ") over the window — collateral-ageing / scrappage proxy.
  transfer_rate = ownership-transfers ("รถโอน") / total-processed over the window —
                  used-vehicle-market liquidity proxy.
A single month would be noisy (seasonal/administrative batching); 12 months smooths that
while still reading as "current" (ends at the latest available release).

100% MEASURED, no modelling beyond the sum + a plain ratio (documented in meta.formula).
Deterministic + network-free over the already-committed CSV mirror; --check byte-exact.
Exits 3 (SKIP, not drift) when the source directory is absent or has <12 usable months —
mirrors build_branch_fuel.py's honest ABSENT-state convention.

    python3 build_vehicle_flow.py
    python3 build_vehicle_flow.py --check
"""
import argparse, csv, glob, json, os, sys
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PIPE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PIPE)
from lib.regionmap import canonical, REGION

RAW_DIR = os.path.join(ROOT, "source-data", "dlt", "raw", "dataset_stat_1_008")
OUT = os.path.join(ROOT, "source-data", "vehicle_flow_by_province.json")
WINDOW = 12  # trailing months

THAI_MONTHS = {"มกราคม": 1, "กุมภาพันธ์": 2, "มีนาคม": 3, "เมษายน": 4, "พฤษภาคม": 5,
               "มิถุนายน": 6, "กรกฎาคม": 7, "สิงหาคม": 8, "กันยายน": 9, "ตุลาคม": 10,
               "พฤศจิกายน": 11, "ธันวาคม": 12}

# vehicle-class bucket -> substring match against the CSV's "ประเภทรถ" column
BUCKETS = {"car": "รย. 1 ", "pickup": "รย. 3 ", "moto": "รย. 12 "}

FIELDS = {"processed": "รถที่ดำเนินการ", "dereg_permanent": "รถแจ้งไม่ใช้ตลอดไป", "transferred": "รถโอน"}


def _to_int(x):
    try:
        return int(float(str(x or 0).replace(",", "").strip() or 0))
    except Exception:
        return 0


def _list_months():
    """Every dataset_stat_1_008 file, parsed to (be_year, month_num, path), sorted ascending."""
    out = []
    for path in glob.glob(os.path.join(RAW_DIR, "*.csv")):
        name = os.path.splitext(os.path.basename(path))[0]
        tail = name.split("__")[-1]  # "<ThaiMonth>_<BEyear>"
        try:
            mth, yr = tail.rsplit("_", 1)
            out.append((int(yr), THAI_MONTHS[mth], path))
        except (ValueError, KeyError):
            continue  # not a month file we recognize — skip, don't guess
    out.sort()
    return out


def build():
    months = _list_months()
    if len(months) < WINDOW:
        return None  # not enough real data to form a trailing-12mo window — ABSENT, no fabrication
    window = months[-WINDOW:]  # most recent WINDOW months

    prov = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    for _, _, path in window:
        with open(path, encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                p = canonical((row.get("จังหวัด") or "").strip())
                if p not in REGION:
                    continue
                vtype = row.get("ประเภทรถ") or ""
                bucket = next((b for b, pat in BUCKETS.items() if pat in vtype), None)
                for key, col in FIELDS.items():
                    n = _to_int(row.get(col))
                    prov[p]["all"][key] += n
                    if bucket:
                        prov[p][bucket][key] += n

    def _rates(d):
        proc = d.get("processed", 0)
        out = dict(d)
        out["dereg_rate"] = round(d.get("dereg_permanent", 0) / proc, 4) if proc else None
        out["transfer_rate"] = round(d.get("transferred", 0) / proc, 4) if proc else None
        return out

    provinces = {p: {bucket: _rates(dict(vals)) for bucket, vals in buckets.items()}
                 for p, buckets in sorted(prov.items())}

    lo = f"{window[0][1]:02d}-{window[0][0] - 543}"
    hi = f"{window[-1][1]:02d}-{window[-1][0] - 543}"
    return {
        "meta": {
            "title": "Vehicle registration-transaction flow by province, trailing 12 months (MEASURED)",
            "generated_by": "pipeline/build_vehicle_flow.py",
            "label": "MEASURED — DLT gdcatalog dataset_stat_1_008 (การดำเนินการทางทะเบียน, car-law "
                     "registration actions), summed over the trailing 12 available monthly releases "
                     f"({lo} → {hi}). dereg_rate/transfer_rate are plain ratios over that window's "
                     "own totals — no modelling. Land-transport-law vehicles (trucks/buses, "
                     "dataset_stat_1_009) are NOT included in this pass; a future cycle can add them.",
            "source": "gdcatalog.dlt.go.th dataset_stat_1_008 -> source-data/dlt/raw/dataset_stat_1_008/ "
                      "(pipeline/pull_dlt_all.py, pulled 2026-07-10)",
            "formula": "dereg_rate = permanently-deregistered (รถแจ้งไม่ใช้ตลอดไป) / total-processed "
                      "(รถที่ดำเนินการ) over the window — collateral-ageing/scrappage proxy. "
                      "transfer_rate = ownership-transfers (รถโอน) / total-processed — used-vehicle-market liquidity proxy.",
            "buckets": "all (every รย. vehicle class) / car (รย.1, personal ≤7-seat) / "
                       "pickup (รย.3, personal truck) / moto (รย.12, motorcycle) — the three "
                       "collateral-relevant classes for a title-loan book",
            "window_months": [f"{y}-{m:02d}" for y, m, _ in window],
            "n_provinces": len(provinces),
        },
        "provinces": provinces,
    }


def run(check=False):
    data = build()
    if data is None:
        print("SKIP: source-data/dlt/raw/dataset_stat_1_008/ absent or <12 months present "
              "— not data drift, run pull_dlt_all.py for a fresh mirror")
        return 3
    text = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    if check:
        if not os.path.exists(OUT) or open(OUT, encoding="utf-8").read() != text:
            print("DRIFT: source-data/vehicle_flow_by_province.json")
            return 1
        print(f"OK: vehicle_flow_by_province.json reproduces byte-exact ({data['meta']['n_provinces']} provinces)")
        return 0
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"wrote source-data/vehicle_flow_by_province.json ({data['meta']['n_provinces']} provinces)")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true")
    raise SystemExit(run(check=ap.parse_args().check))
