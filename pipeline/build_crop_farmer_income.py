#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_crop_farmer_income.py — GROSS farmer income per person, by crop, per province (objective #1).

Network-free, deterministic. Combines four MEASURED Thai layers into a concrete per-person income
read for the five field crops AutoX's agri borrowers depend on:

  gross income per farm per year  =  rai_per_farm  ×  yield(kg/rai)  ×  farm-gate price(THB/kg)
  gross income per person         =  ÷ WORKERS_PER_FARM  (the one ESTIMATED leg — see below)

WHY GROSS, NOT NET: OAE's cost-of-production per rai is published only as scanned PDFs (confirmed
dead end). Net income needs a cost figure; inventing one would be fabrication. So this is GROSS
farm revenue per person — an income-CEILING read, explicitly labelled. It is a floor-risk signal
(which crop×province produces the least gross revenue per worker), not a take-home wage.

INPUTS (all MEASURED, already on disk):
  source-data/oae_yield.json          yield kg/rai  (pull_oae_yield.py) — rice per-province, others national
  source-data/farmgate_prices.json    farm-gate price (NABC) — rice THB/ton, others THB/kg → reconciled to THB/kg
  source-data/doae_planted_area.json  planted area (DOAE registry) — HECTARES; converted to rai (×6.25)
  source-data/nabc_agri.json          farmer-family (household) counts per crop per province (NABC/OAE)

MEASURED vs ESTIMATED (stated per field, honoured in meta.provenance):
  MEASURED   yield, farm-gate price, planted area, farmer-family counts, and every derived
             rai_per_farm / gross_per_farm_year built only from those.
  ESTIMATED  (1) WORKERS_PER_FARM — a single documented constant (see below), the only assumption;
             (2) for maize/cassava/rubber/oil palm the yield is NATIONAL applied to each province
                 (OAE publishes no machine-readable per-province yield for them) — tagged
                 yield_source="national" on every such row. Rice yield is per-province (measured).

GAPS: sugarcane has no OAE yield dataset (excluded). Oil palm has yield+price+area but NABC
      farmer_family carries no ปาล์มน้ำมัน key, so per-farm income is not computable (excluded,
      noted in meta.gaps).

Output: platform/data/crop_farmer_income.json — per crop: a national row + per-province rows,
sorted lowest-gross-per-person-first (the risk lens). Rich meta.provenance splits MEASURED vs
ESTIMATED and exposes workers_per_farm as a top-level field.

Run:
  python3 build_crop_farmer_income.py           # write platform/data/crop_farmer_income.json
  python3 build_crop_farmer_income.py --check    # re-run, byte-compare; exit 3 SKIP if input absent
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from regionmap import canonical, REGION

YIELD = os.path.join(ROOT, "source-data", "oae_yield.json")
PRICES = os.path.join(ROOT, "source-data", "farmgate_prices.json")
AREA = os.path.join(ROOT, "source-data", "doae_planted_area.json")
FAMILIES = os.path.join(ROOT, "source-data", "nabc_agri.json")
OUT = os.path.join(ROOT, "platform", "data", "crop_farmer_income.json")
INPUTS = (YIELD, PRICES, AREA, FAMILIES)

# The single ESTIMATED leg. NSO agricultural households average ~1.5-2 agricultural workers per
# holding (NSO Agricultural Census 2013 / Labour Force Survey — roughly 5.9M holdings against the
# agricultural labour force). We adopt the round midpoint 1.6 as one transparent constant, exposed
# as meta.workers_per_farm so the per-person figures can be re-derived under any other assumption.
WORKERS_PER_FARM = 1.6
WORKERS_CITE = ("ESTIMATED — 1.6 agricultural workers per farm household, the midpoint of the "
                "NSO agricultural-household range (~1.5-2 workers/holding; NSO Agricultural Census "
                "2013 / Labour Force Survey). This is the ONLY estimated leg of the per-person "
                "figure; per-farm figures are fully measured.")
RAI_PER_HA = 6.25   # DOAE area is stored in hectares (rai / 6.25); convert back to rai

# our 5 crops -> DOAE planted-area key, NABC farmer_family Thai key
DOAE_KEY = {"rice": "rice", "maize": "maize", "cassava": "cassava",
            "rubber": "rubber", "oilpalm": "oilpalm"}
FAMILY_KEY = {"rice": "ข้าว", "maize": "ข้าวโพดเลี้ยงสัตว์", "cassava": "มันสำปะหลัง",
              "rubber": "ยางพารา", "oilpalm": None}   # NABC has no ปาล์มน้ำมัน family count
CROP_EN = {"rice": "Rice", "maize": "Maize", "cassava": "Cassava",
           "rubber": "Rubber", "oilpalm": "Oil palm"}
CROP_ORDER = ["rice", "maize", "cassava", "rubber", "oilpalm"]


def _load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _price_thb_per_kg(entry):
    """Reconcile a farmgate commodities entry to THB/kg (rice is quoted THB/ton)."""
    price, unit = entry.get("price"), entry.get("unit") or ""
    if price is None:
        return None
    if "ตัน" in unit:            # THB/ton -> THB/kg
        return price / 1000.0
    return float(price)           # already THB/kg (บาท/กก.)


def build():
    y = _load(YIELD)["crops"]
    pr = _load(PRICES)["commodities"]
    area = _load(AREA)["provinces"]
    fam = _load(FAMILIES)["farmer_family"]

    # canonicalise the province keys of the area + family layers once
    area_c = {}
    for p, rec in area.items():
        c = canonical(p)
        if c in REGION:
            area_c[c] = rec
    fam_c = {}
    for p, rec in fam.items():
        c = canonical(p)
        if c in REGION:
            fam_c[c] = rec

    crops_out = []
    gaps = ["sugarcane — no OAE yield dataset (per-province is PDF-only); EXCLUDED."]

    for crop in CROP_ORDER:
        ycrop = y.get(crop)
        pentry = pr.get(crop)
        fkey = FAMILY_KEY[crop]
        akey = DOAE_KEY[crop]
        if ycrop is None or pentry is None:
            gaps.append("%s — missing yield or price input; skipped." % crop)
            continue
        if fkey is None:
            gaps.append("%s — planted area, yield and farm-gate price are present, but NABC "
                        "farmer_family carries no '%s' household count, so gross income PER FARM "
                        "cannot be computed; EXCLUDED." % (crop, "ปาล์มน้ำมัน"))
            continue

        price = _price_thb_per_kg(pentry)
        if price is None:
            gaps.append("%s — farm-gate price unusable; skipped." % crop)
            continue
        nat_yield = ycrop.get("national")
        prov_yield = ycrop.get("provinces", {})   # populated only for rice

        rows = []
        tot_rai = tot_fam = 0.0
        for c in sorted(REGION):
            arec = area_c.get(c)
            frec = fam_c.get(c)
            if not arec or not frec:
                continue
            ha = arec.get(akey)
            fams = frec.get(fkey)
            if not ha or not fams or ha <= 0 or fams <= 0:
                continue
            planted_rai = ha * RAI_PER_HA
            if c in prov_yield:
                yv, ysrc = prov_yield[c], "measured"
            else:
                yv, ysrc = nat_yield, "national"
            if yv is None:
                continue
            rai_per_farm = planted_rai / fams
            gross_farm_year = rai_per_farm * yv * price
            gross_person_year = gross_farm_year / WORKERS_PER_FARM
            rows.append({
                "province": c,
                "region": REGION.get(c),
                "planted_rai": round(planted_rai),
                "farmer_family": int(fams),
                "rai_per_farm": round(rai_per_farm, 2),
                "yield_kg_per_rai": round(yv),
                "yield_source": ysrc,
                "gross_per_farm_year": round(gross_farm_year),
                "gross_per_person_year": round(gross_person_year),
                "gross_per_person_month": round(gross_person_year / 12.0),
            })
            tot_rai += planted_rai
            tot_fam += fams

        if not rows:
            gaps.append("%s — no province had both area and family counts; skipped." % crop)
            continue

        # lowest gross-per-person-month first = the floor-risk lens
        rows.sort(key=lambda r: (r["gross_per_person_month"], r["province"]))

        nat_rpf = tot_rai / tot_fam if tot_fam else None
        nat_farm_year = nat_rpf * nat_yield * price if nat_rpf is not None else None
        nat_person_year = nat_farm_year / WORKERS_PER_FARM if nat_farm_year is not None else None
        crops_out.append({
            "crop": crop,
            "crop_en": CROP_EN[crop],
            "crop_th": ycrop.get("commod_th"),
            "yield_scope": ("per-province measured" if prov_yield else
                            "national yield applied to every province (ESTIMATED leg)"),
            "yield_national_kg_per_rai": nat_yield,
            "price_thb_per_kg": round(price, 4),
            "price_series_th": pentry.get("product_th"),
            "price_unit_raw": pentry.get("unit"),
            "n_provinces": len(rows),
            "national": {
                "planted_rai": round(tot_rai),
                "farmer_family": round(tot_fam),
                "rai_per_farm": round(nat_rpf, 2) if nat_rpf is not None else None,
                "gross_per_farm_year": round(nat_farm_year) if nat_farm_year is not None else None,
                "gross_per_person_year": round(nat_person_year) if nat_person_year is not None else None,
                "gross_per_person_month": round(nat_person_year / 12.0) if nat_person_year is not None else None,
            },
            "provinces": rows,
        })

    # crops ordered lowest national gross-per-person-month first (risk lens; None last)
    crops_out.sort(key=lambda c: (c["national"]["gross_per_person_month"] is None,
                                  c["national"]["gross_per_person_month"] or 0, c["crop"]))

    ymeta = _load(YIELD)["meta"]
    pmeta = _load(PRICES)["meta"]
    ameta = _load(AREA)["meta"]
    fmeta = _load(FAMILIES)["meta"]
    meta = {
        "title": "Gross farmer income per person by crop, per province (portfolio risk, objective #1)",
        "generated_by": "pipeline/build_crop_farmer_income.py",
        "deterministic": True,
        "network_free": True,
        "unit": "THB (baht)",
        "workers_per_farm": WORKERS_PER_FARM,
        "n_crops": len(crops_out),
        "sort": "crops and provinces both lowest-gross-per-person-first (floor-risk lens)",
        "formula": {
            "rai_per_farm": "planted_rai / farmer_family   (MEASURED)",
            "gross_per_farm_year": "rai_per_farm * yield_kg_per_rai * price_thb_per_kg   (MEASURED)",
            "gross_per_person_year": "gross_per_farm_year / workers_per_farm   (ESTIMATED leg)",
            "gross_per_person_month": "gross_per_person_year / 12",
        },
        "provenance": {
            "measured": [
                "Yield (kg/rai): OAE — %s. Rice per-province (77); maize/cassava/rubber/oil palm "
                "national." % ymeta.get("source"),
                "Farm-gate price (THB/kg, rice reconciled from THB/ton): %s" % pmeta.get("source"),
                "Planted area (rai, converted from DOAE hectares ×%.2f): %s"
                % (RAI_PER_HA, ameta.get("source")),
                "Farmer-family (household) counts: %s" % fmeta.get("source"),
                "rai_per_farm and gross_per_farm_year are pure products of the above — measured.",
            ],
            "estimated": [
                WORKERS_CITE,
                "For maize/cassava/rubber/oil palm the yield is the NATIONAL figure applied to every "
                "province (OAE publishes no machine-readable per-province yield for them); each such "
                "row is tagged yield_source=\"national\". Rice rows are yield_source=\"measured\".",
            ],
            "not_computed": [
                "NET income — OAE cost-of-production per rai is PDF-only (dead end). This is GROSS "
                "farm revenue per person, an income-ceiling read, NOT take-home pay.",
            ],
        },
        "vintages": {
            "yield_by_crop": ymeta.get("vintage_by_crop"),
            "farmgate_price": pmeta.get("vintage"),
            "planted_area": ameta.get("year_be"),
            "farmer_family": fmeta.get("vintage"),
        },
        "gaps": gaps,
        "caveats": [
            "GROSS revenue per person, not net and not take-home wage — no cost of production is "
            "deducted (OAE cost/rai is PDF-only).",
            "Per-person divides per-farm gross by a single estimated workers/farm constant (1.6); "
            "adjust meta.workers_per_farm to re-scale.",
            "Non-rice yields are national applied to province (yield_source=\"national\"): province "
            "spread reflects area/family differences, not real yield variation.",
            "Farm-gate price is a national daily average, not a per-province price.",
            "A farm household is often counted under more than one crop; single-crop revenue here is "
            "per registered crop-holding, not a whole-household total.",
        ],
    }
    return {"meta": meta, "crops": crops_out}


def dumps(obj):
    return json.dumps(obj, ensure_ascii=False, indent=2) + "\n"


def main():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:
            pass
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true",
                    help="re-run and byte-compare against the committed JSON; exit 1 on drift, "
                         "exit 3 SKIP if an input is absent")
    args = ap.parse_args()

    missing = [p for p in INPUTS if not os.path.exists(p)]
    if missing:
        rel = ", ".join(os.path.relpath(p, ROOT) for p in missing)
        if args.check:
            print("build_crop_farmer_income.py --check: SKIP (absent: %s)" % rel)
            sys.exit(3)
        sys.exit("build_crop_farmer_income.py: missing input(s): %s — run pull_oae_yield.py "
                 "and the NABC/DOAE pulls first." % rel)

    text = dumps(build())

    if args.check:
        if not os.path.exists(OUT):
            print("build_crop_farmer_income.py --check: SKIP (output not generated yet)")
            sys.exit(3)
        if open(OUT, encoding="utf-8").read() != text:
            sys.exit("build_crop_farmer_income.py --check: crop_farmer_income.json drifted — run "
                     "python3 pipeline/build_crop_farmer_income.py")
        print("build_crop_farmer_income.py --check: OK (byte-exact)")
        return

    with open(OUT, "w", encoding="utf-8") as f:
        f.write(text)
    data = json.loads(text)
    print("wrote %s (%d crops)" % (OUT, len(data["crops"])))
    for c in data["crops"]:
        n = c["national"]
        print("  %-8s gross/person/mo=%s THB  (per-farm/yr=%s, %d provinces, %s)"
              % (c["crop"], n["gross_per_person_month"], n["gross_per_farm_year"],
                 c["n_provinces"], c["yield_scope"]))


if __name__ == "__main__":
    main()
