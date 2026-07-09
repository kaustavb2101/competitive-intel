#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_brand_trends.py — MEASURED national new-vehicle market: registration trend + top brands + EV push.

Source: source-data/dlt/*.csv — DLT's own gdcatalog (stat_1_1_01_first_regis_vehicles_car +
dataset_stat_1_003), pulled 2026-07-09 while the intermittent host answered. First registrations
BY BRAND AND MODEL per year (พ.ศ. 2565–2568 = CE 2022–2025) + new-registration totals by vehicle
type. This is the collateral-side demand signal Kaustav asked for: which brands (= future used
collateral) are entering the fleet, how fast the pickup/passenger mix is shifting, and how hard
the EV wave is hitting (EV-heavy marques erode ICE resale — the diesel-pickup watch).

Deterministic + network-free over the committed CSVs; --check byte-exact; exits 3 (SKIP) when the
pull is absent. Brand counts are MEASURED; the "EV-focused brands" share is an ESTIMATED
classification (fixed marque list) over measured counts — labelled as such.

  python3 build_brand_trends.py
  python3 build_brand_trends.py --check
"""
import argparse, csv, glob, json, os, re, sys
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.join(ROOT, "source-data", "dlt")
OUT = os.path.join(ROOT, "platform", "data", "brand_trends.json")

# vehicle-type buckets (รย. classes) — pickup = รย.3 personal truck, the AutoX core collateral
PICKUP_TYPE = "รถยนต์บรรทุกส่วนบุคคล"
PASSENGER_TYPE = "รถยนต์นั่งส่วนบุคคลไม่เกิน 7 คน"
# ESTIMATED classification: marques that sell (essentially) only EVs in Thailand. Toyota/Honda/MG
# sell both, so they are NOT listed — this measures the pure-EV push, a conservative floor.
EV_ONLY_BRANDS = {"BYD", "AION", "NETA", "ORA", "DEEPAL", "ZEEKR", "XPENG", "AVATR", "WULING",
                  "TESLA", "VOLT", "RIDDARA", "SERES", "AITO", "IM MOTORS", "JUNEYAO", "LEAPMOTOR",
                  "GEELY EX", "SMART", "HYPTEC", "MHERO", "FOMM", "POCCO", "DENZA", "XIAOMI", "ONVO"}


def _read(fn):
    with open(fn, encoding="utf-8-sig", newline="") as f:
        return [r for r in csv.reader(f) if r and r[0].strip()]


def build():
    brand_files = sorted(glob.glob(os.path.join(SRC_DIR, "first_regis_brand_25*.csv")))
    regis_files = sorted(glob.glob(os.path.join(SRC_DIR, "new_regis_25*.csv")))
    years = {}
    for fn in brand_files:
        yr = re.search(r"(25\d\d)", os.path.basename(fn)).group(1)
        rows = _read(fn)[1:]
        tot = defaultdict(int); pick = defaultdict(int); ev = 0; allc = 0
        for r in rows:
            if len(r) < 5:
                continue
            typ, brand, n = r[1].strip(), r[2].strip().upper(), r[4]
            try:
                n = int(n)
            except ValueError:
                continue
            tot[brand] += n; allc += n
            if typ == PICKUP_TYPE:
                pick[brand] += n
            if brand in EV_ONLY_BRANDS:
                ev += n
        top = sorted(tot.items(), key=lambda x: -x[1])[:12]
        ptop = sorted(pick.items(), key=lambda x: -x[1])[:6]
        years[yr] = {
            "total_first_regis_cars": allc,
            "top_brands": [{"b": b, "n": n} for b, n in top],
            "top_pickup_brands": [{"b": b, "n": n} for b, n in ptop],
            "ev_only_brand_regis": ev,
            "ev_only_share_pct": round(100.0 * ev / allc, 1) if allc else 0.0,
        }
    # current-year MONTHLY files (schema adds a เดือน column: year, month, type, brand, model, count)
    # → a YTD block extending the annual trend into the running year. Feb-2569's upstream file is a
    # truncated 6-row stub, so only complete-looking months (>500 rows) are accepted.
    ytd = None
    monthly = sorted(glob.glob(os.path.join(SRC_DIR, "first_regis_brand_monthly_25*.csv")))
    if monthly:
        tot = defaultdict(int); ev = 0; allc = 0; months = []
        yr = None
        for fn in monthly:
            rows = _read(fn)[1:]
            if len(rows) < 500:
                continue
            m = re.search(r"monthly_(25\d\d)_(\d\d)", os.path.basename(fn))
            if m:
                yr = m.group(1); months.append(m.group(2))
            for r in rows:
                if len(r) < 6:
                    continue
                brand, n = r[3].strip().upper(), r[5]
                try:
                    n = int(n)
                except ValueError:
                    continue
                tot[brand] += n; allc += n
                if brand in EV_ONLY_BRANDS:
                    ev += n
        if allc:
            ytd = {
                "year_be": yr, "months": sorted(months),
                "total_first_regis_cars": allc,
                "top_brands": [{"b": b, "n": n} for b, n in sorted(tot.items(), key=lambda x: -x[1])[:8]],
                "ev_only_share_pct": round(100.0 * ev / allc, 1),
            }

    # new-registration totals by class (trend across years)
    trend = {}
    for fn in regis_files:
        yr = re.search(r"(25\d\d)", os.path.basename(fn)).group(1)
        rows = _read(fn)[1:]
        rec = {"passenger": 0, "pickup": 0, "total": 0}
        for r in rows:
            if len(r) < 4:
                continue
            typ, n = r[2], r[3]
            try:
                n = int(n)
            except ValueError:
                continue
            rec["total"] += n
            if PASSENGER_TYPE in typ:
                rec["passenger"] += n
            elif PICKUP_TYPE in typ:
                rec["pickup"] += n
        trend[yr] = rec
    ys = sorted(years)
    return {
        "meta": {
            "title": "New-vehicle market — first registrations by brand + trend (DLT, measured)",
            "generated_by": "pipeline/build_brand_trends.py",
            "label": "MEASURED — DLT first registrations by brand/model per year (gdcatalog.dlt.go.th, "
                     "stat_1_1_01 + dataset_stat_1_003, pulled 2026-07-09). EV-only share is an ESTIMATED "
                     "classification (fixed pure-EV marque list, conservative floor — dual-powertrain "
                     "brands like Toyota/MG excluded) over the measured counts.",
            "years_be": ys,
            "note_be_to_ce": "พ.ศ. − 543 = ค.ศ. (2568 = 2025)",
            "why": "Which brands enter the fleet today is tomorrow's used-vehicle collateral; the pure-EV "
                   "share is the leading indicator for the diesel-pickup resale watch (collateral outlook).",
        },
        "years": years,
        "ytd": ytd,
        "new_regis_trend": trend,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    if not glob.glob(os.path.join(SRC_DIR, "first_regis_brand_25*.csv")):
        print("build_brand_trends.py: source-data/dlt/ pull absent — run the DLT pull (SKIP).")
        sys.exit(3)
    payload = json.dumps(build(), ensure_ascii=False, separators=(",", ":"))
    if args.check:
        if not os.path.exists(OUT):
            sys.exit("build_brand_trends.py --check: output missing — run the builder.")
        if open(OUT, encoding="utf-8").read() != payload:
            sys.exit("build_brand_trends.py --check: drifted — re-run the builder.")
        print("build_brand_trends.py --check: OK (byte-exact)")
        return
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(payload)
    d = json.loads(payload)
    latest = sorted(d["years"])[-1]
    y = d["years"][latest]
    print("wrote %s" % OUT)
    print("  %s: %s first regis · top: %s · EV-only share %.1f%%" % (
        latest, format(y["total_first_regis_cars"], ","),
        ", ".join(x["b"] for x in y["top_brands"][:5]), y["ev_only_share_pct"]))


if __name__ == "__main__":
    main()
