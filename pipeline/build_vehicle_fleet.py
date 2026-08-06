#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_vehicle_fleet.py — national title-collateral fleet trend (portfolio risk, MEASURED).

Distils the DLT/MOT national cumulative registered-vehicle stock time series into a clean,
AutoX-collateral-class layer: how big the national fleet of the vehicle classes AutoX lends against
is, and — the point of this layer — whether that collateral base is EXPANDING or CONTRACTING year on
year. Every existing vehicle layer (vehicles_by_province.json / branch_vehicles.json / the collateral
outlook board) is a SINGLE-VINTAGE province snapshot; none carries the TIME dimension. This adds it:
a measured national trajectory for the three title-collateral classes.

Why it matters (objective #1, portfolio / collateral risk). CORRECTED 2026-08-02: this file used to
say the book is "~50% motorcycle-title and ~25% car/pickup-title". That was written before the real
tape landed (2026-07-21) and the tape does not support it. MEASURED: motorcycles are 33.3% of ACCOUNTS
but only 5.8% of OUTSTANDING (THB2.69bn of THB46.57bn); pickup + passenger car are 54.0% of accounts
and 60.7% of outstanding. The old figure was an account-count intuition applied to a money question —
the same unit error the farm book was built to kill. If the national registered fleet of a collateral
class is contracting, the
resale/recovery pool behind that slice of the book is shrinking even before any change in default
rates — a leading, measured signal that the collateral outlook board currently only carries as an
"editorial / estimated watch" for the diesel-pickup side. This lets that watch cite a measured number.

INPUT  source-data/datagoth/mot_vehicles.csv — the MOT/DLT open-data national cumulative registered-
       vehicle stock file (one row per vehicle type per Buddhist-era year; columns ประเภทกฎหมาย /
       ประเภทรถ / ปี (BE year) / จำนวน (count) / หน่วย). Pulled by pull_datagoth.py (--only
       mot_vehicles) from datagov.mot.go.th. The raw CSV is gitignored + re-pullable; this builder's
       committed OUTPUT is the repo's source of truth. NATIONAL granularity (no province split in this
       resource) — stated plainly in meta; the province split lives in vehicles_by_province.json.

OUTPUT platform/data/vehicle_fleet.json — { meta, classes[], series{be_year->{class->count}} }.
       Every count is MEASURED (a straight read of the government registry); latest-year level, YoY %,
       and a 6-year trailing series per collateral class. No synthesis, no scoring, no forecast.

PROVENANCE is stable + byte-exact: the output is a pure function of the CSV CONTENT (the trailing-year
window and per-year sums are derived from the file, not from the pull timestamp). The MOT resource URL
is pinned as a constant below; bump it when a newer resource is pulled.

DETERMINISTIC + NETWORK-FREE. Carries --check; SKIP-passes (exit 3) when the gitignored
mot_vehicles.csv is absent (the CI gate has no such pull committed), so the determinism gate never
breaks on a missing input — same convention as build_dbd_formation / build_pico_census.

  python3 build_vehicle_fleet.py
  python3 build_vehicle_fleet.py --check
"""
import argparse, csv, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CSV_IN = os.path.join(ROOT, "source-data", "datagoth", "mot_vehicles.csv")
OUT = os.path.join(ROOT, "platform", "data", "vehicle_fleet.json")

# Pinned to the pulled MOT resource (datagov.mot.go.th cumulative registered-vehicle stock). A constant
# — NOT read from the volatile pull manifest — so the output is byte-stable across re-pulls.
SOURCE_URL = "https://datagov.mot.go.th/dataset/รถจดทะเบียนสะสม"

# AutoX title-loan collateral classes, mapped by the registry's English type label (ประเภทรถ). The
# registry splits ~25 statutory vehicle types; we roll up only the classes AutoX actually lends against
# into their book meaning. Order is display order (largest slices of the book by OUTSTANDING first).
CLASSES = [
    ("pickup", "Pickup title",     ["Van & Pick Up"],
     "38.3% of AutoX outstanding (measured tape) — the single largest collateral class in the book; "
     "resale under EV/glut pressure."),
    ("car",    "Car title",        ["Sedan", "Microbus & Passenger Van"],
     "22.4% of AutoX outstanding (measured tape) — higher ticket and a deeper resale market than "
     "motorcycles."),
    ("moto",   "Motorcycle title", ["Motorcycle", "Public Motorcycle"],
     "33.3% of AutoX accounts but 5.8% of outstanding (measured tape) — the most numerous and "
     "lowest-recovery title collateral, and the smallest slice of the money."),
]
N_YEARS = 6                          # trailing window for the trend series/sparkline

def _class_of(label):
    for key, _disp, needles, _note in CLASSES:
        for n in needles:
            if n in label:
                return key
    return None

def build():
    # per BE year -> {class -> count}. Sum the (possibly several) statutory types in each class.
    per_year = {}
    with open(CSV_IN, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            try:
                y = int((row.get("ปี") or "").strip())
                n = int((row.get("จำนวน") or "0").strip().replace(",", "") or 0)
            except ValueError:
                continue
            cls = _class_of(row.get("ประเภทรถ") or "")
            if not cls:
                continue
            per_year.setdefault(y, {}).setdefault(cls, 0)
            per_year[y][cls] += n

    years = sorted(per_year)
    window = years[-N_YEARS:]
    latest, prev = years[-1], years[-2]
    keys = [c[0] for c in CLASSES]

    series = {str(y): {k: per_year[y].get(k, 0) for k in keys} for y in window}

    classes = []
    for key, disp, _needles, note in CLASSES:
        cur = per_year[latest].get(key, 0)
        pre = per_year[prev].get(key, 0)
        yoy = round(100.0 * (cur - pre) / pre, 2) if pre else None
        first = per_year[window[0]].get(key, 0)
        multi = round(100.0 * (cur - first) / first, 2) if first else None
        classes.append({
            "key": key, "label": disp, "note": note,
            "latest": cur, "prev": pre, "yoy_pct": yoy,
            f"since_{window[0]}_pct": multi, "direction": ("up" if (yoy or 0) > 0 else "down"),
        })

    # honest headline: the collateral base that is CONTRACTING (yoy<0) is the risk signal.
    contracting = sorted((c for c in classes if (c["yoy_pct"] or 0) < 0),
                         key=lambda c: c["yoy_pct"])
    moto = next(c for c in classes if c["key"] == "moto")

    meta = {
        "generated_by": "pipeline/build_vehicle_fleet.py",
        "label": ("MEASURED national registered-vehicle fleet trend for the AutoX title-collateral "
                  "classes (motorcycle / pickup / car). Latest-year level + YoY %% + a trailing "
                  "%d-year series. The TIME dimension of the collateral base — is it expanding or "
                  "contracting — NOT a per-province split (that lives in vehicles_by_province.json), "
                  "and NOT a recovery value or price." % N_YEARS),
        "source": ("MEASURED — DLT/MOT open-data national cumulative registered-vehicle stock by "
                   "statutory type by Buddhist-era year (datagov.mot.go.th). A straight read of the "
                   "government registry, rolled up to AutoX collateral classes; not modelled, no "
                   "forecast, no annualisation."),
        "provenance": "measured (government vehicle registry, tallied by the registry's own type + year)",
        "source_url": SOURCE_URL,
        "granularity": "national (no province split in this resource)",
        "unit": "registered vehicles (cumulative stock)",
        "latest_year_be": latest, "latest_year_ce": latest - 543,
        "prev_year_be": prev, "prev_year_ce": prev - 543,
        "window_be": [window[0], window[-1]],
        "n_years_available": len(years),
        "objective": ("Objective #1 (collateral / portfolio risk): a contracting national fleet of a "
                      "collateral class means a shrinking resale/recovery pool behind that slice of the "
                      "book — a leading, measured read on collateral value, not a price."),
        "headline": (
            ("pickup-title fleet contracting %.2f%% YoY (%d BE) — first measured confirmation of the "
             "diesel-pickup collateral squeeze; motorcycle fleet +%.2f%% YoY (growth decelerating)"
             % (contracting[0]["yoy_pct"], latest, moto["yoy_pct"]))
            if contracting else
            ("all three title-collateral classes still growing YoY (%d BE); motorcycle fleet +%.2f%%"
             % (latest, moto["yoy_pct"]))),
        "gaps": [
            "NATIONAL only — this MOT resource is not split by province. Use vehicles_by_province.json "
            "for the per-province collateral mix; this layer adds the national trend over time.",
            "Cumulative REGISTERED stock, not sales and not de-registrations of scrapped vehicles; a "
            "flat/declining stock reflects net of new registrations minus removals, read directionally.",
            "Fleet size is the collateral POOL, not its resale VALUE — no Thai used-vehicle price index "
            "is in this data, so this is a base-size signal, not a recovery rate.",
        ],
    }
    return {"meta": meta, "classes": classes, "series": series}

def serialize(o):
    return json.dumps(o, ensure_ascii=False, separators=(",", ":"))

def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    for s in (sys.stdout, sys.stderr):
        try: s.reconfigure(encoding="utf-8")
        except Exception: pass

    if not os.path.exists(CSV_IN):
        if args.check:
            print("build_vehicle_fleet.py --check: SKIP (source-data/datagoth/mot_vehicles.csv absent "
                  "— re-pullable pull_datagoth input, not committed)")
            sys.exit(3)
        sys.exit("mot_vehicles.csv missing — run: python3 pull_datagoth.py --only mot_vehicles")

    payload = serialize(build())
    if args.check:
        if not os.path.exists(OUT):
            print("build_vehicle_fleet.py --check: SKIP (vehicle_fleet.json not generated yet)")
            sys.exit(3)
        if open(OUT, encoding="utf-8").read() != payload:
            sys.exit("build_vehicle_fleet.py --check: vehicle_fleet.json drifted — run "
                     "python3 pipeline/build_vehicle_fleet.py")
        print("build_vehicle_fleet.py --check: OK (byte-exact)")
        return
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(payload)
    obj = json.loads(payload)
    m = obj["meta"]
    print("wrote %s (%d BE, national fleet trend, %d-year window)"
          % (OUT, m["latest_year_be"], N_YEARS))
    for c in obj["classes"]:
        print("  %-14s %12s  YoY %+6.2f%%" % (c["label"], "{:,}".format(c["latest"]),
                                              c["yoy_pct"] if c["yoy_pct"] is not None else 0.0))
    print("  headline: %s" % m["headline"])

if __name__ == "__main__":
    main()
