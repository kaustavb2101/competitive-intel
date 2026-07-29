#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_vehicle_collateral.py — the VEHICLE-TITLE COLLATERAL read (objective #1, portfolio risk).

AutoX lends against vehicle titles; the diesel pickup is the core title collateral, and the
EV / diesel transition is the resale-value risk sitting under that collateral. This build answers
the two MEASURED questions that are actually reachable from a cloud IP:

  1. PER-PROVINCE DIESEL SHARE (MEASURED) — diesel's share of the car (รย.1) + pickup (รย.3)
     registered stock, per province, plus the pickup diesel count. This is the collateral
     resale-exposure signal: where diesel dominates the title-able fleet, the EV transition most
     threatens future recovery values. Source: DLT dataset_1_1_04 (cumulative registered stock by
     ประเภทรถ × จังหวัด × ประเภทเชื้อเพลิง) at gdcatalog.dlt.go.th — reachable from any IP.
     Diesel classification mirrors build_ev_penetration.py exactly (pure diesel = fuel contains
     'ดีเซล' and NOT '-ไฟฟ้า', so diesel-hybrid ดีเซล-ไฟฟ้า and PHEV are excluded; bi-fuel diesel
     such as LPG+ดีเซล / CNG+ดีเซล IS counted — it is still a diesel powertrain).

  2. NATIONAL COLLATERAL BRAND MIX (MEASURED, NATIONAL ONLY) — which brands make up the title-
     relevant fleet, from the already-committed DLT first-registration brand data
     (platform/data/brand_trends.json ← DLT stat_1_1_01, by ยี่ห้อ). Pickups (รย.3) are
     Toyota+Isuzu-led; cars (รย.1) Honda/Toyota; BYD/EV is rising. This is NATIONAL ONLY and is
     labelled as such: a MEASURED brand×province cross is NOT in reachable Thai open data — brand is
     national-only in DLT stat_1_1_01, province is crossed only with type/fuel in dataset_1_1_04, and
     the true brand×province cross lives on the geoblocked data.go.th aggregator. We deliberately do
     NOT synthesise an estimated national-shares×province cross.

Deterministic over the committed inputs; --check byte-exact; exit 3 (SKIP) when an input is absent
(the DLT raw mirror is gitignored / re-pullable, like build_ev_penetration.py).

  python3 build_vehicle_collateral.py
  python3 build_vehicle_collateral.py --check
"""
import argparse, csv, glob, io, json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from lib.regionmap import canonical, REGION

SRC_GLOB = os.path.join(ROOT, "source-data", "dlt", "raw", "dataset_1_1_04", "*.csv")
BRANDS = os.path.join(ROOT, "platform", "data", "brand_trends.json")
OUT = os.path.join(ROOT, "platform", "data", "vehicle_collateral.json")

# vehicle-type (ประเภทรถ) prefixes in dataset_1_1_04 — the title-relevant private types
CAR_PREFIX = "รย. 1 "     # รถยนต์นั่งส่วนบุคคลไม่เกิน 7 คน (private car)
PICKUP_PREFIX = "รย. 3 "  # รถยนต์บรรทุกส่วนบุคคล (personal pickup — the core title collateral)

DIESEL_MARK = "ดีเซล"
HYBRID_MARK = "-ไฟฟ้า"     # ดีเซล-ไฟฟ้า / เบนซิน-ไฟฟ้า (and the …เสียบปลั๊ก PHEV variants)

THAI_MONTHS = {"มกราคม": "01", "กุมภาพันธ์": "02", "มีนาคม": "03", "เมษายน": "04", "พฤษภาคม": "05",
               "มิถุนายน": "06", "กรกฎาคม": "07", "สิงหาคม": "08", "กันยายน": "09", "ตุลาคม": "10",
               "พฤศจิกายน": "11", "ธันวาคม": "12"}


def _is_diesel(fuel):
    return DIESEL_MARK in fuel and HYBRID_MARK not in fuel


def _vintage(fn):
    base = os.path.basename(fn)
    m = re.search(r"(\d{1,2})_(%s)_(25\d\d)" % "|".join(THAI_MONTHS), base)
    if m:
        return "%d-%s-%02d" % (int(m.group(3)) - 543, THAI_MONTHS[m.group(2)], int(m.group(1)))
    m = re.search(r"(25\d\d)(\d\d)(\d\d)", base)   # e.g. ..._25690228
    if m:
        return "%d-%s-%s" % (int(m.group(1)) - 543, m.group(2), m.group(3))
    return base


def _national_brand_mix():
    """National collateral brand mix from the committed brand_trends.json (DLT first regis by brand).
    Returns the latest available year's pickup + car top-brand lists. National only."""
    if not os.path.exists(BRANDS):
        return None
    bt = json.load(open(BRANDS, encoding="utf-8"))
    years = bt.get("years") or {}
    if not years:
        return None
    latest = max(years, key=lambda y: int(re.sub(r"\D", "", y) or 0))
    y = years[latest]
    try:
        ce = int(re.sub(r"\D", "", latest)) - 543
    except ValueError:
        ce = None
    return {
        "vintage_be": latest,
        "vintage_ce": ce,
        "measure": "first vehicle registrations (new to the fleet) by brand — DLT stat_1_1_01",
        "pickup_top_brands": y.get("top_pickup_brands") or [],
        "car_top_brands": y.get("top_brands") or [],
        "ev_only_share_pct": y.get("ev_only_share_pct"),
        "total_first_regis_cars": y.get("total_first_regis_cars"),
        "note": "NATIONAL ONLY — brand is not available crossed with province in reachable Thai open "
                "data (brand is national-only in DLT stat_1_1_01; the true brand×province cross lives "
                "on the geoblocked data.go.th). New first-registrations are tomorrow's used-vehicle "
                "collateral: pickups are Toyota+Isuzu-led, cars Honda/Toyota, with BYD/EV rising.",
    }


def build():
    fn = sorted(glob.glob(SRC_GLOB))[-1]
    rows = list(csv.reader(io.StringIO(open(fn, encoding="utf-8-sig", errors="replace").read())))[1:]
    prov = {}
    for r in rows:
        if len(r) < 5:
            continue
        vtype, p, fuel, n = r[1].strip(), r[2].strip(), r[3].strip(), r[4]
        try:
            n = int(n)
        except ValueError:
            continue
        if not p:
            continue
        is_car = vtype.startswith(CAR_PREFIX)
        is_pick = vtype.startswith(PICKUP_PREFIX)
        if not (is_car or is_pick):
            continue
        e = prov.setdefault(p, {"cp_total": 0, "cp_diesel": 0, "pickup_total": 0, "pickup_diesel": 0})
        diesel = _is_diesel(fuel)
        e["cp_total"] += n
        if diesel:
            e["cp_diesel"] += n
        if is_pick:
            e["pickup_total"] += n
            if diesel:
                e["pickup_diesel"] += n

    out = []
    for p, e in prov.items():
        c = canonical(p)
        if c not in REGION:
            continue
        t = e["cp_total"] or 1
        out.append({
            "th": c,
            "region": REGION.get(c),
            "car_pickup_total": e["cp_total"],
            "diesel": e["cp_diesel"],
            "diesel_share_pct": round(100.0 * e["cp_diesel"] / t, 1),
            "pickup_total": e["pickup_total"],
            "pickup_diesel": e["pickup_diesel"],
        })
    # most diesel-exposed collateral first (highest EV-transition resale risk at the top)
    out.sort(key=lambda r: (-r["diesel_share_pct"], r["th"]))

    nat_cp = sum(r["car_pickup_total"] for r in out)
    nat_d = sum(r["diesel"] for r in out)
    nat_pt = sum(r["pickup_total"] for r in out)
    nat_pd = sum(r["pickup_diesel"] for r in out)
    national = {
        "car_pickup_total": nat_cp,
        "diesel": nat_d,
        "diesel_share_pct": round(100.0 * nat_d / nat_cp, 1) if nat_cp else None,
        "pickup_total": nat_pt,
        "pickup_diesel": nat_pd,
    }

    brand_mix = _national_brand_mix()

    return {
        "meta": {
            "title": "Vehicle-title collateral — per-province diesel share + national brand mix (DLT, measured)",
            "generated_by": "pipeline/build_vehicle_collateral.py",
            "deterministic": True,
            "network_free": True,
            "label": "MEASURED — per-province DIESEL SHARE of the car (รย.1) + pickup (รย.3) registered "
                     "stock (DLT dataset_1_1_04, cumulative by type×province×fuel). National collateral "
                     "BRAND mix from DLT first-registrations (brand_trends.json ← stat_1_1_01). BRAND IS "
                     "NATIONAL ONLY — a measured brand×province cross is not in reachable Thai open data.",
            "source": {
                "diesel_share": "gdcatalog.dlt.go.th dataset_1_1_04 -> source-data/dlt/raw/dataset_1_1_04/ "
                                "(pull via pull_dlt_all.py / pull_dlt_fuel.py; raw is gitignored, re-pullable)",
                "brand_mix": "platform/data/brand_trends.json (DLT stat_1_1_01 first registrations by brand)",
            },
            "vintage": _vintage(fn),
            "why": "AutoX lends against vehicle titles; diesel pickups are the core title collateral and "
                   "the EV/diesel transition is the resale-value risk. Provinces where diesel dominates "
                   "the title-able (car+pickup) fleet are where collateral recovery values are most "
                   "exposed as the fleet electrifies.",
            "diesel_classification": "pure diesel = fuel type contains 'ดีเซล' and NOT '-ไฟฟ้า' — excludes "
                                     "diesel-hybrid (ดีเซล-ไฟฟ้า) and plug-in (…เสียบปลั๊ก); includes bi-"
                                     "fuel diesel (LPG+ดีเซล, CNG+ดีเซล). Mirrors build_ev_penetration.py.",
            "types_included": {"car": "รย.1 รถยนต์นั่งส่วนบุคคลไม่เกิน 7 คน",
                               "pickup": "รย.3 รถยนต์บรรทุกส่วนบุคคล (core title collateral)"},
            "national": national,
            "n_provinces": len(out),
            "provenance": {
                "measured": [
                    "Per-province diesel share of car+pickup registered stock: DLT dataset_1_1_04 "
                    "(cumulative registrations by ประเภทรถ × จังหวัด × ประเภทเชื้อเพลิง), vintage in meta. "
                    "Pure counts, no modelling.",
                    "National collateral brand mix (pickup + car top brands, EV-only share): DLT "
                    "first-registrations by brand (stat_1_1_01), via brand_trends.json.",
                ],
                "national_only": [
                    "BRAND MIX is NATIONAL ONLY. Brand is not crossed with province in any reachable Thai "
                    "open-data resource: DLT stat_1_1_01 carries brand at the national level; dataset_1_1_04 "
                    "crosses province only with type and fuel; the true brand×province cross lives on the "
                    "geoblocked data.go.th aggregator. We do NOT estimate a national-shares×province cross.",
                ],
            },
            "caveats": [
                "Diesel share is over CUMULATIVE registered stock (the fleet on the road), not new "
                "registrations — it moves slowly, which is the right base for a resale-value watch.",
                "Brand mix is NEW first-registrations (a leading indicator of tomorrow's used collateral), "
                "national only — do not read it per province.",
                "No used-vehicle price index is involved; this is the collateral COMPOSITION, not a "
                "measured recovery value.",
            ],
        },
        "provinces": out,
        "national_brand_mix": brand_mix,
    }


def _inputs_present():
    return bool(glob.glob(SRC_GLOB))


def main():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:
            pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true",
                    help="re-run and byte-compare against the committed JSON; exit 1 on drift, "
                         "exit 3 SKIP if the DLT mirror input is absent")
    args = ap.parse_args()

    if not _inputs_present():
        if args.check:
            print("build_vehicle_collateral.py --check: SKIP (DLT mirror dataset_1_1_04 absent — "
                  "run pull_dlt_fuel.py / pull_dlt_all.py)")
            sys.exit(3)
        sys.exit("build_vehicle_collateral.py: DLT mirror dataset_1_1_04 absent — run "
                 "pull_dlt_fuel.py (or pull_dlt_all.py) first.")

    payload = json.dumps(build(), ensure_ascii=False, separators=(",", ":"))

    if args.check:
        if not os.path.exists(OUT):
            print("build_vehicle_collateral.py --check: SKIP (vehicle_collateral.json not generated yet)")
            sys.exit(3)
        if open(OUT, encoding="utf-8").read() != payload:
            sys.exit("build_vehicle_collateral.py --check: vehicle_collateral.json drifted — run "
                     "python3 pipeline/build_vehicle_collateral.py")
        print("build_vehicle_collateral.py --check: OK (byte-exact)")
        return

    with open(OUT, "w", encoding="utf-8") as f:
        f.write(payload)
    d = json.loads(payload)
    n = d["meta"]["national"]
    print("wrote %s — vintage %s, national car+pickup diesel share %.1f%% (%d provinces)"
          % (OUT, d["meta"]["vintage"], n["diesel_share_pct"], d["meta"]["n_provinces"]))
    print("  top diesel-share provinces:")
    for r in d["provinces"][:5]:
        print("    %-16s %5.1f%%  (pickup diesel %d)" % (r["th"], r["diesel_share_pct"], r["pickup_diesel"]))
    bm = d.get("national_brand_mix")
    if bm:
        pk = ", ".join("%s %d" % (b["b"], b["n"]) for b in bm["pickup_top_brands"][:3])
        print("  national pickup brand mix (%s): %s" % (bm["vintage_be"], pk))


if __name__ == "__main__":
    main()
