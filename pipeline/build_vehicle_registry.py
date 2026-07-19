#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_vehicle_registry.py — national registered-vehicle collateral base by type + trend (MEASURED).

Distils the MOT cumulative registered-vehicle registry (one row per vehicle-type × year) into a clean,
collateral-grouped national layer: how large the registered-vehicle collateral base is, split into the
classes an AutoX/เงินไชโย title book actually lends against, and how each class has grown. It is the
external anchor for the book's collateral mix — motorcycle title ≈ half the book, car/pickup ≈ a quarter —
now grounded in the government registry instead of an assumption.

INPUT  source-data/datagoth/mot_vehicles.csv — MOT open-data cumulative registered vehicles
       (datagov.mot.go.th "whole.csv"; columns ประเภทกฎหมาย / ประเภทรถ (vehicle type) / ปี (year, BE) /
       จำนวน (count) / หน่วย). One row per type × year, national (NOT province-granular — the province
       DLT resource is geo-blocked from cloud IPs; see pull_datagoth.py ACCESS NOTES). Pulled by
       pull_datagoth.py (--only mot_vehicles). The raw CSV is gitignored + re-pullable; this builder's
       committed OUTPUT is the repo's source of truth.

OUTPUT platform/data/vehicle_registry.json — { meta, latest, prior, yoy, series }.
       Every count is MEASURED (a straight read of the government registry); no synthesis, no scoring.
       Vehicle types are grouped by their รย. code into the four collateral classes AutoX lends against
       (motorcycle / car / pickup+van / agri) plus an "other" bucket (taxis, buses, trucks, trailers).

PROVENANCE is stable + byte-exact: output is a pure function of the CSV CONTENT (not the pull timestamp).
The source URL is pinned below; the vintage is read from the registry's own max ปี field.

DETERMINISTIC + NETWORK-FREE. Carries --check; SKIP-passes (exit 3) when the gitignored mot_vehicles.csv
is absent — same convention as build_pico_census / build_dbd_formation / build_branch_cropland.

  python3 build_vehicle_registry.py
  python3 build_vehicle_registry.py --check
"""
import argparse, csv, json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CSV_IN = os.path.join(ROOT, "source-data", "datagoth", "mot_vehicles.csv")
OUT = os.path.join(ROOT, "platform", "data", "vehicle_registry.json")

# Pinned to the pulled MOT resource (datagov.mot.go.th dataset 69db5cd5 …/whole.csv). A constant — NOT
# read from the volatile pull manifest — so the output is byte-stable across re-pulls of the same file.
SOURCE_URL = "https://datagov.mot.go.th/dataset/69db5cd5-1a57-4306-9d7c-cc17e36e8711"

COL_TYPE = "ประเภทรถ"
COL_YEAR = "ปี"
COL_N = "จำนวน"

SERIES_YEARS = 10  # trailing years kept in the per-class series

# รย. code -> collateral class. Codes not listed fall to "other" (taxis, buses, trucks, trailers,
# tricycles, road rollers, trailers — not the small-ticket title collateral AutoX lends against).
CODE_CLASS = {
    "12": "motorcycle", "17": "motorcycle",   # private + public motorcycle — title-loan core
    "1": "car", "2": "car",                    # sedan ≤7 + microbus/passenger van
    "3": "pickup",                             # personal van & pick-up
    "13": "agri", "15": "agri",                # tractor + farm vehicle — agri collateral
}
CLASSES = ["motorcycle", "car", "pickup", "agri"]  # the four AutoX-relevant classes, display order

_CODE = re.compile(r"^รย\.?\s*(\d+)")


def _class_of(vtype):
    m = _CODE.match((vtype or "").strip())
    if not m:
        return "other"
    return CODE_CLASS.get(m.group(1), "other")


def _int(s):
    try:
        return int(float((s or "0").strip().replace(",", "") or 0))
    except ValueError:
        return 0


def build():
    # year (BE int) -> {class -> summed count}, plus an all-types total per year
    by_year = {}
    for row in csv.DictReader(open(CSV_IN, encoding="utf-8-sig")):
        try:
            ybe = int((row.get(COL_YEAR) or "").strip())
        except ValueError:
            continue
        n = _int(row.get(COL_N))
        cls = _class_of(row.get(COL_TYPE))
        rec = by_year.setdefault(ybe, {c: 0 for c in CLASSES + ["other", "all"]})
        rec[cls] += n
        rec["all"] += n

    years = sorted(by_year)
    if not years:
        raise SystemExit("mot_vehicles.csv parsed to zero years — unexpected schema")
    y_latest, y_prior = years[-1], years[-2]

    def snap(ybe):
        r = by_year[ybe]
        title_base = sum(r[c] for c in CLASSES)  # the AutoX-lendable collateral base
        return {
            "year_be": ybe, "year_ce": ybe - 543,
            "groups": {c: r[c] for c in CLASSES},
            "title_base": title_base,      # motorcycle+car+pickup+agri
            "all_vehicles": r["all"],      # every registered type
        }

    latest, prior = snap(y_latest), snap(y_prior)
    yoy = {}
    for c in CLASSES + ["title_base", "all_vehicles"]:
        a = prior["groups"].get(c) if c in CLASSES else prior[c]
        b = latest["groups"].get(c) if c in CLASSES else latest[c]
        yoy[c] = round((b - a) / a * 100, 2) if a else None

    tail = years[-SERIES_YEARS:]
    series = {c: [[y - 543, by_year[y][c]] for y in tail] for c in CLASSES}
    moto_share = round(latest["groups"]["motorcycle"] / latest["title_base"] * 100, 1) \
        if latest["title_base"] else None

    meta = {
        "generated_by": "pipeline/build_vehicle_registry.py",
        "label": ("MEASURED national registered-vehicle collateral base, grouped into the four classes an "
                  "AutoX title book lends against (motorcycle / car / pickup+van / agri) plus an 'other' "
                  "bucket, with the latest vintage, year-on-year growth, and a %d-year trend." % SERIES_YEARS),
        "source": ("MEASURED — MOT (Ministry of Transport) open-data cumulative registered-vehicle registry, "
                   "datagov.mot.go.th. Counts are a direct read of the registry's own จำนวน (count) per "
                   "vehicle type × year; no modelling, no annualisation. Grouped into collateral classes by "
                   "the รย. type code."),
        "provenance": "measured (government vehicle registry, tallied by the registry's own type/year fields)",
        "source_url": SOURCE_URL,
        "granularity": "national (by vehicle type × year)",
        "vintage": "%d (BE %d)" % (y_latest - 543, y_latest),
        "vintage_ce": y_latest - 543,
        "vintage_be": y_latest,
        "prior_year_ce": y_prior - 543,
        "moto_share_of_title_base_pct": moto_share,
        "objective": ("Objective #1 (portfolio risk): the collateral base AutoX's book is secured against. "
                      "Motorcycle title is roughly half the book and car/pickup a quarter — this grounds "
                      "that mix in the government registry and shows where new collateral supply is growing."),
        "gaps": [
            "NATIONAL only — not province-granular. The MOT 'whole.csv' resource is a national type×year "
            "roll-up; the province-level DLT vehicle registry (gdcatalog.dlt.go.th) is geo-blocked from "
            "cloud IPs, so per-province registered-vehicle counts are not refreshed here. The province "
            "dimension is carried separately by source-data/vehicles_by_province.json.",
            "CUMULATIVE registered stock, not new registrations — it counts vehicles ever registered and "
            "not formally struck off, so it overstates the actively-on-road / financeable fleet. Read the "
            "year-on-year delta as net stock growth, not new-vehicle sales.",
            "'agri' here is รย.13 tractor + รย.15 farm vehicle only (the road-registered farm fleet); it is "
            "not the full agricultural machinery base.",
        ],
    }
    return {"meta": meta, "latest": latest, "prior": prior, "yoy": yoy, "series": series}


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
            print("build_vehicle_registry.py --check: SKIP (source-data/datagoth/mot_vehicles.csv absent — "
                  "re-pullable pull_datagoth input, not committed)")
            sys.exit(3)
        sys.exit("mot_vehicles.csv missing — run: python3 pull_datagoth.py --only mot_vehicles")

    payload = serialize(build())
    if args.check:
        if not os.path.exists(OUT):
            print("build_vehicle_registry.py --check: SKIP (vehicle_registry.json not generated yet)")
            sys.exit(3)
        if open(OUT, encoding="utf-8").read() != payload:
            sys.exit("build_vehicle_registry.py --check: vehicle_registry.json drifted — run "
                     "python3 pipeline/build_vehicle_registry.py")
        print("build_vehicle_registry.py --check: OK (byte-exact)")
        return
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(payload)
    obj = json.loads(payload)
    m, lt = obj["meta"], obj["latest"]
    g = lt["groups"]
    print("wrote %s (vintage %s; moto %s, car %s, pickup %s, agri %s; title base %s, moto share %.1f%%)"
          % (OUT, m["vintage"], f"{g['motorcycle']:,}", f"{g['car']:,}", f"{g['pickup']:,}",
             f"{g['agri']:,}", f"{lt['title_base']:,}", m["moto_share_of_title_base_pct"]))
    print("  YoY: " + ", ".join("%s %+.2f%%" % (k, v) for k, v in obj["yoy"].items() if v is not None))


if __name__ == "__main__":
    main()
