#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_truck_flow.py — PORTFOLIO RISK (objective #1): COMMERCIAL-fleet churn per province,
distilled from DLT's transport-law registration-actions log (dataset_stat_1_009).

The car-law sibling (build_vehicle_flow.py over dataset_stat_1_008) covers cars/pickups/
motorcycles — the title-loan collateral classes. THIS script reads the Land-Transport-Act
log: trucks (รถบรรทุก, for-hire + private) and buses. Trucks are the logistics-SME borrower
pulse: an owner-operator hauler is a classic heavy-title borrower, and a province where the
truck fleet's churn is contracting (fewer new registrations, more permanent deregistrations)
is a province where that borrower segment's cash flow is thinning.

Source: source-data/dlt/raw/dataset_stat_1_009/*.csv — mirrored whole by pull_dlt_all.py
(50 monthly releases on disk at first build, 2565-07..2569-xx). Same schema as stat_1_008:
per province × vehicle category × month, action counts. Previously an UNTOUCHED mirror
dataset (E0 wave, revamp analysis — "the pipeline-input with no consumer").

Method (mirrors build_vehicle_flow.py): sum the TRAILING 12 MONTHS per province for the
truck buckets, then:
  new_regis     = รถจดใหม่ป้ายแดง + รถจดใหม่ใช้แล้ว   (fleet entering)
  transfers     = รถโอน                                (ownership churn / used-market liquidity)
  dereg         = รถแจ้งเลิกใช้ ม.79 + ม.89            (fleet leaving)
  net_flow      = new_regis - dereg                    (fleet direction; negative = contracting)
Plus the same window one year earlier for a YoY comparison of new_regis.

100% MEASURED sums + plain ratios. Deterministic + network-free; --check byte-exact;
exits 3 (SKIP) when the mirror is absent or holds <24 usable months (need window + prior year).

    python3 build_truck_flow.py
    python3 build_truck_flow.py --check
"""
import argparse, csv, glob, io, json, os, sys
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PIPE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PIPE)
from regionmap import canonical, REGION

RAW_DIR = os.path.join(ROOT, "source-data", "dlt", "raw", "dataset_stat_1_009")
OUT = os.path.join(ROOT, "platform", "data", "truck_flow.json")
WINDOW = 12

THAI_MONTHS = {"มกราคม": 1, "กุมภาพันธ์": 2, "มีนาคม": 3, "เมษายน": 4, "พฤษภาคม": 5,
               "มิถุนายน": 6, "กรกฎาคม": 7, "สิงหาคม": 8, "กันยายน": 9, "ตุลาคม": 10,
               "พฤศจิกายน": 11, "ธันวาคม": 12}

TRUCK_MARK = "รถบรรทุก"   # both ส่วนบุคคล (private) and ไม่ประจำทาง (for-hire)

# header columns (identical schema to stat_1_008): B.E. year, month, province, category, then counts
COL_PROC, COL_NEW_RED, COL_NEW_USED, COL_TRANSFER = 4, 6, 7, 12
COL_DEREG_79, COL_DEREG_89 = 13, 14


def _num(v):
    try:
        return int(str(v).replace(",", "").strip() or 0)
    except ValueError:
        return 0


def load_months():
    """{(ce_year, month): {prov: {new, xfer, dereg, proc}}} over every truck row on disk."""
    months = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    for fn in sorted(glob.glob(os.path.join(RAW_DIR, "*.csv"))):
        rows = list(csv.reader(io.StringIO(open(fn, encoding="utf-8-sig", errors="replace").read())))
        for r in rows[1:]:
            if len(r) < 15 or TRUCK_MARK not in r[3]:
                continue
            mth = THAI_MONTHS.get(r[1].strip())
            try:
                yr = int(r[0]) - 543
            except ValueError:
                continue
            if not mth:
                continue
            prov = canonical(r[2].strip())
            if not prov:
                continue
            e = months[(yr, mth)][prov]
            e["new"] += _num(r[COL_NEW_RED]) + _num(r[COL_NEW_USED])
            e["xfer"] += _num(r[COL_TRANSFER])
            e["dereg"] += _num(r[COL_DEREG_79]) + _num(r[COL_DEREG_89])
            e["proc"] += _num(r[COL_PROC])
    return months


def _window_sum(months, keys):
    agg = defaultdict(lambda: defaultdict(int))
    for k in keys:
        for prov, e in months.get(k, {}).items():
            for f, v in e.items():
                agg[prov][f] += v
    return agg


def build():
    months = load_months()
    keys = sorted(months.keys())
    if len(keys) < 2 * WINDOW:
        return None
    cur_keys = keys[-WINDOW:]
    prev_keys = keys[-2 * WINDOW:-WINDOW]
    cur = _window_sum(months, cur_keys)
    prev = _window_sum(months, prev_keys)

    out = []
    for prov in sorted(cur.keys()):
        c, p = cur[prov], prev.get(prov, {})
        yoy = (round(100.0 * (c["new"] - p["new"]) / p["new"], 1) if p.get("new") else None)
        out.append({"th": prov, "region": REGION.get(prov),
                    "new_regis_12m": c["new"], "transfers_12m": c["xfer"],
                    "dereg_12m": c["dereg"], "net_flow_12m": c["new"] - c["dereg"],
                    "new_regis_yoy_pct": yoy})
    out.sort(key=lambda r: (r["new_regis_yoy_pct"] if r["new_regis_yoy_pct"] is not None else 0.0, r["th"]))

    nat_cur = {f: sum(c[f] for c in cur.values()) for f in ("new", "xfer", "dereg")}
    nat_prev_new = sum(p.get("new", 0) for p in prev.values())
    nat_yoy = round(100.0 * (nat_cur["new"] - nat_prev_new) / nat_prev_new, 1) if nat_prev_new else None
    fmt = lambda k: "%d-%02d" % k
    return {
        "meta": {
            "title": "Commercial truck-fleet flow per province — the logistics-SME borrower pulse (measured)",
            "generated_by": "pipeline/build_truck_flow.py",
            "label": "MEASURED — DLT transport-law registration actions (dataset_stat_1_009), trucks "
                     "(รถบรรทุก private + for-hire). Trailing-12-month sums + plain ratios; no modelling.",
            "source": "source-data/dlt/raw/dataset_stat_1_009 (pull_dlt_all.py mirror)",
            "window": {"current": [fmt(cur_keys[0]), fmt(cur_keys[-1])],
                       "prior": [fmt(prev_keys[0]), fmt(prev_keys[-1])]},
            "fields": {
                "new_regis_12m": "MEASURED — new truck registrations (red-plate + used) in the window",
                "transfers_12m": "MEASURED — ownership transfers (used-market liquidity)",
                "dereg_12m": "MEASURED — permanent deregistrations (ม.79 + ม.89)",
                "net_flow_12m": "MEASURED — new_regis - dereg; negative = the truck fleet is contracting",
                "new_regis_yoy_pct": "MEASURED — new_regis vs the same 12-month window one year earlier",
            },
            "why": "an owner-operator hauler is a classic heavy-title borrower; contracting truck flow "
                   "= that segment's cash flow thinning in the province.",
            "national": {"new_regis_12m": nat_cur["new"], "transfers_12m": nat_cur["xfer"],
                         "dereg_12m": nat_cur["dereg"], "new_regis_yoy_pct": nat_yoy},
            "n_provinces": len(out),
            "sort": "worst-first by new_regis_yoy_pct (asc)",
        },
        "provinces": out,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    if not glob.glob(os.path.join(RAW_DIR, "*.csv")):
        print("build_truck_flow.py: DLT mirror dataset_stat_1_009 absent — run pull_dlt_all.py (SKIP).")
        sys.exit(3)
    data = build()
    if data is None:
        print("build_truck_flow.py: <24 usable months in the mirror — need window + prior year (SKIP).")
        sys.exit(3)
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    if args.check:
        if not os.path.exists(OUT):
            print("build_truck_flow.py --check: SKIP (truck_flow.json not generated yet)")
            sys.exit(3)
        if open(OUT, encoding="utf-8").read() != payload:
            sys.exit("build_truck_flow.py --check: drifted — re-run the builder.")
        print("build_truck_flow.py --check: OK (byte-exact)")
        return
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(payload)
    n = data["meta"]["national"]
    print("wrote %s — window %s..%s, national new %d (%+.1f%% YoY), dereg %d" % (
        OUT, data["meta"]["window"]["current"][0], data["meta"]["window"]["current"][1],
        n["new_regis_12m"], n["new_regis_yoy_pct"] or 0, n["dereg_12m"]))
    for r in data["provinces"][:5]:
        print("   %-16s new %6d (%s%% YoY) net %+d" % (
            r["th"], r["new_regis_12m"], r["new_regis_yoy_pct"], r["net_flow_12m"]))


if __name__ == "__main__":
    main()
