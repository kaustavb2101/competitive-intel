#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_crop_farmer_income.py — GROSS **and NET** farmer income per household / per person, by crop
(objective #1: the portfolio-risk floor for farming households).

Network-free, deterministic. Answers, per field crop AutoX's agri borrowers depend on:
  "What does a farming household actually earn — and after costs, do they make money at all?"

THE DENOMINATOR FIX (why this was rebuilt):
  The old build divided planted area by NABC `farmer_family` — which are crop REGISTRATION RECORDS
  (16.5M for rice), NOT households. That gave an impossible 4.17 rai per rice "farm". OAE's own
  compendium reports 4,532,663 rice HOUSEHOLDS on 61.34M rai → ~13.5 rai/household. This build now
  uses OAE's real per-crop household count as the denominator (source-data/oae_farm_economics.json).

NET INCOME (new — the striking finding):
  OAE publishes ผลตอบแทนสุทธิ (net return, THB/tonne) per crop. In crop-year 2568 it is NEGATIVE for
  rice (-1,433), cassava (-320) and rubber (-2,460): these households LOSE money per tonne at the
  farm gate this year; maize (+930) and oil palm (+3,080) are positive. Net is surfaced honestly as
  a loss where it is a loss — not hidden.

PRICE RECONCILIATION:
  The old build used the NABC daily spot price for ข้าวเปลือกหอมมะลิ 105 (jasmine paddy), ~17.69 THB/kg
  — a premium single variety, not the crop average. OAE's Cai-up all-rice farm-gate paddy price for
  2568 is 8,105 THB/tonne = 8.105 THB/kg. This build sources ALL prices from OAE (Cai-up), so gross
  and net are internally consistent (gross/tonne − cost/tonne = net/tonne, same source & vintage).

NATIONAL vs PER-PROVINCE:
  MEASURED national: households, area, yield, price, cost, net all from OAE Cai-up (single source,
    same vintage) → rai/household, gross & net per household and per person. Fully measured.
  PER-PROVINCE (a geographic overlay, ESTIMATED): OAE's economics are national-only, so per-province
    rows keep the map/risk lens by (a) allocating the national household count across provinces by
    each province's share of the measured distribution (NABC households; oil palm by DOAE area), and
    (b) for RICE, scaling gross/net by the province's MEASURED yield relative to the national yield
    (rice yield is per-province measured; other crops carry the national figure flat). Every province
    row is tagged so no one mistakes the overlay for a measured per-province income.

The one ESTIMATED leg of the per-PERSON figure remains WORKERS_PER_FARM = 1.6 (documented below).

Output: platform/data/crop_farmer_income.json — per crop a national economics block (gross + net,
per household and per person) + per-province rows, plus the farm-household income/DEBT-by-region
table (from OAE). Crops sorted lowest-net-per-person-first (losses surface at the top).

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
from lib.regionmap import canonical, REGION

ECON = os.path.join(ROOT, "source-data", "oae_farm_economics.json")   # primary (denominator + net)
YIELD = os.path.join(ROOT, "source-data", "oae_yield.json")           # per-province RICE yield spread
FAMILIES = os.path.join(ROOT, "source-data", "nabc_agri.json")        # per-province distribution weights
AREA = os.path.join(ROOT, "source-data", "doae_planted_area.json")    # oil-palm distribution weight
PRICES = os.path.join(ROOT, "source-data", "farmgate_prices.json")    # legacy fallback only
OUT = os.path.join(ROOT, "platform", "data", "crop_farmer_income.json")

# Inputs that must exist for the primary (OAE-economics) path. YIELD/FAMILIES/AREA are optional
# enrichers for the per-province overlay; ECON is the one that must be present.
PRIMARY_INPUTS = (ECON,)
LEGACY_INPUTS = (YIELD, PRICES, AREA, FAMILIES)

# The single ESTIMATED leg. NSO agricultural households average ~1.5-2 agricultural workers per
# holding (NSO Agricultural Census 2013 / Labour Force Survey). We adopt the round midpoint 1.6 as
# one transparent constant, exposed as meta.workers_per_farm so per-person figures can be re-derived.
WORKERS_PER_FARM = 1.6
WORKERS_CITE = ("ESTIMATED — 1.6 agricultural workers per farm household, the midpoint of the NSO "
                "agricultural-household range (~1.5-2 workers/holding; NSO Agricultural Census 2013 "
                "/ Labour Force Survey). The ONLY estimated leg of the per-person figure; per-"
                "household figures are fully measured.")
RAI_PER_HA = 6.25   # DOAE area is stored in hectares (rai / 6.25); convert back to rai

CROP_EN = {"rice": "Rice", "maize": "Maize", "cassava": "Cassava",
           "rubber": "Rubber", "oilpalm": "Oil palm"}
CROP_ORDER = ["rice", "maize", "cassava", "rubber", "oilpalm"]
# NABC farmer-household key per crop (per-province distribution weight). Oil palm has no NABC key →
# allocated by DOAE planted-area share instead.
FAMILY_KEY = {"rice": "ข้าว", "maize": "ข้าวโพดเลี้ยงสัตว์", "cassava": "มันสำปะหลัง",
              "rubber": "ยางพารา", "oilpalm": None}
DOAE_KEY = {"oilpalm": "oilpalm"}   # crops allocated by DOAE area share (no NABC household key)

RAI_MIN, RAI_MAX = 5.0, 40.0   # sanity band for rai/household (rice should land ~13.5)


def _load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _canon_map(d):
    out = {}
    for p, rec in d.items():
        c = canonical(p)
        if c in REGION:
            out[c] = rec
    return out


def build():
    econ = _load(ECON)
    ecrops = econ["crops"]

    # optional enrichers for the per-province overlay
    yld = _load(YIELD)["crops"] if os.path.exists(YIELD) else {}
    fam_c = _canon_map(_load(FAMILIES)["farmer_family"]) if os.path.exists(FAMILIES) else {}
    area_c = _canon_map(_load(AREA)["provinces"]) if os.path.exists(AREA) else {}

    crops_out = []
    gaps = ["sugarcane — no OAE household-economics page in the compendium; EXCLUDED."]

    for crop in CROP_ORDER:
        e = ecrops.get(crop)
        if not e:
            gaps.append("%s — absent from oae_farm_economics.json; skipped." % crop)
            continue
        hh = e["households"]
        area_rai = e["area_rai"]
        prod_tons = e["production_tons"]
        price_t = e["farmgate_price_per_ton"]
        net_t = e["net_return_per_ton"]
        if not hh or hh <= 0:
            gaps.append("%s — no household count; skipped." % crop)
            continue

        rai_per_hh = area_rai / hh
        if not (RAI_MIN <= rai_per_hh <= RAI_MAX):
            sys.exit("build_crop_farmer_income.py: %s rai/household = %.2f outside sane band "
                     "[%.0f, %.0f] — check oae_farm_economics.json." % (crop, rai_per_hh, RAI_MIN, RAI_MAX))
        prod_per_hh = prod_tons / hh                      # tonnes/household/yr
        gross_hh = prod_per_hh * price_t                  # THB/household/yr
        net_hh = prod_per_hh * net_t                      # THB/household/yr (negative = loss)
        gross_pp_mo = gross_hh / WORKERS_PER_FARM / 12.0
        net_pp_mo = net_hh / WORKERS_PER_FARM / 12.0

        national = {
            "households": hh,
            "area_rai": area_rai,
            "area_basis": e["area_basis"],
            "production_tons": prod_tons,
            "rai_per_household": round(rai_per_hh, 2),
            "yield_kg_per_rai": e["yield_kg_per_rai"],
            "price_thb_per_kg": round(price_t / 1000.0, 4),
            "net_return_per_ton": net_t,
            "cost_per_ton": e.get("cost_per_ton"),
            "gross_per_household_year": round(gross_hh),
            "net_per_household_year": round(net_hh),
            "gross_per_person_month": round(gross_pp_mo),
            "net_per_person_month": round(net_pp_mo),
            "loss": net_t < 0,
        }

        # ---- per-province overlay (ESTIMATED geographic decomposition) --------------------------
        # weights: NABC household share (rice/maize/cassava/rubber) or DOAE area share (oil palm)
        weights = {}
        alloc_basis = None
        fkey = FAMILY_KEY.get(crop)
        if fkey:
            alloc_basis = "NABC farming-household share"
            for c in REGION:
                v = (fam_c.get(c) or {}).get(fkey)
                if v and v > 0:
                    weights[c] = float(v)
        elif crop in DOAE_KEY:
            alloc_basis = "DOAE planted-area share (no NABC household key for this crop)"
            for c in REGION:
                v = (area_c.get(c) or {}).get(DOAE_KEY[crop])
                if v and v > 0:
                    weights[c] = float(v) * RAI_PER_HA

        rows = []
        wtot = sum(weights.values())
        # rice per-province yield spread (measured); reference = oae_yield national (prod-weighted)
        ycrop = yld.get("rice") if crop == "rice" else None
        prov_yield = (ycrop or {}).get("provinces", {}) if ycrop else {}
        nat_ref_yield = (ycrop or {}).get("national") if ycrop else None

        if wtot > 0:
            for c in sorted(weights):
                share = weights[c] / wtot
                hh_prov = round(hh * share)
                if hh_prov <= 0:
                    continue
                if crop == "rice" and c in prov_yield and nat_ref_yield:
                    yfac = prov_yield[c] / nat_ref_yield
                    yv, ysrc = prov_yield[c], "measured"
                else:
                    yfac = 1.0
                    yv, ysrc = e["yield_kg_per_rai"], "national"
                rows.append({
                    "province": c,
                    "region": REGION.get(c),
                    "households": hh_prov,
                    "share_pct": round(share * 100, 2),
                    "yield_kg_per_rai": round(yv),
                    "yield_source": ysrc,
                    "gross_per_person_month": round(gross_pp_mo * yfac),
                    "net_per_person_month": round(net_pp_mo * yfac),
                    "gross_per_household_year": round(gross_hh * yfac),
                    "net_per_household_year": round(net_hh * yfac),
                    "loss": (net_hh * yfac) < 0,
                })
            rows.sort(key=lambda r: (r["net_per_person_month"], r["province"]))
        else:
            gaps.append("%s — no per-province allocation weight available; national only." % crop)

        crops_out.append({
            "crop": crop,
            "crop_en": CROP_EN[crop],
            "crop_th": e.get("commod_th"),
            "vintage": e.get("vintage"),
            "loss": net_t < 0,
            "price_thb_per_kg": round(price_t / 1000.0, 4),
            "yield_scope": ("rice: per-province MEASURED yield spread over national economics"
                            if crop == "rice" else
                            "national economics applied flat to every province (no per-province "
                            "measured differentiator)"),
            "province_alloc_basis": alloc_basis,
            "n_provinces": len(rows),
            "national": national,
            "provinces": rows,
        })

    # crops ordered lowest national net-per-person-month first → losses surface at the top
    crops_out.sort(key=lambda c: (c["national"]["net_per_person_month"], c["crop"]))

    emeta = econ["meta"]
    meta = {
        "title": "Gross AND net farmer income per household / person by crop "
                 "(portfolio risk, objective #1)",
        "generated_by": "pipeline/build_crop_farmer_income.py",
        "deterministic": True,
        "network_free": True,
        "unit": "THB (baht)",
        "workers_per_farm": WORKERS_PER_FARM,
        "n_crops": len(crops_out),
        "denominator": "OAE real per-crop FARMING-HOUSEHOLD count (source-data/oae_farm_economics.json) "
                       "— replaces the old NABC farmer_family registration-record count that caused "
                       "the implausible 4.17 rai/farm bug.",
        "sort": "crops lowest national net-per-person-month first (losses at the top); "
                "province rows lowest net-per-person first.",
        "formula": {
            "rai_per_household": "area_rai / households   (MEASURED, OAE)",
            "production_per_household": "production_tons / households   (MEASURED, OAE)",
            "gross_per_household_year": "production_per_household * farmgate_price_per_ton   (MEASURED)",
            "net_per_household_year": "production_per_household * net_return_per_ton   (MEASURED; "
                                      "negative = a loss)",
            "per_person_month": "(household figure) / workers_per_farm / 12   (workers_per_farm ESTIMATED)",
            "province_overlay": "national gross/net allocated by household/area share; rice scaled by "
                                "measured province-yield / national-yield (ESTIMATED overlay)",
        },
        "provenance": {
            "measured": [
                "Households, area, yield, farm-gate price, cost and NET RETURN per crop: OAE Cai-up "
                "2568 compendium (source-data/oae_farm_economics.json; text-layer, spot-verified). "
                "Source: %s" % emeta.get("source"),
                "rai_per_household, gross and net per household are pure products of the OAE figures "
                "— measured.",
                "Rice per-province yield spread (used only to scale the province overlay): OAE "
                "catalog (oae_yield.json), per-province measured.",
                "Farm-household income and year-end DEBT by region: OAE Cai-up 2568 (see "
                "household_economics below).",
            ],
            "estimated": [
                WORKERS_CITE,
                "PER-PROVINCE rows are a geographic OVERLAY, not a measured per-province income: OAE "
                "economics are national-only. The national household count is allocated across "
                "provinces by NABC household share (oil palm by DOAE area share); only RICE gross/net "
                "vary by province (scaled by measured province yield). All other crops carry the "
                "national gross/net flat on every province row (yield_source=\"national\").",
            ],
            "reconciled": [
                "RICE PRICE: old build used NABC daily spot for jasmine paddy (ข้าวเปลือกหอมมะลิ 105) "
                "~17.69 THB/kg — a premium single variety. Replaced with OAE Cai-up all-rice farm-"
                "gate paddy 8.105 THB/kg (2568), consistent with the OAE cost & net figures.",
                "All crop prices now sourced from OAE Cai-up (not NABC), so gross − cost = net holds "
                "within one source and vintage.",
            ],
        },
        "vintages": {
            "crop_economics": emeta.get("crop_vintage"),
            "household_economics": emeta.get("household_vintage"),
            "rice_province_yield": (yld.get("rice") or {}).get("vintage") if yld else None,
        },
        "gaps": gaps,
        "caveats": [
            "NET is OAE's ผลตอบแทนสุทธิ (per tonne) × production per household — a real per-household "
            "profit/loss at the farm gate. In 2568 rice, cassava and rubber are LOSS-MAKING.",
            "Per-person divides the per-household figure by a single estimated workers/farm constant "
            "(1.6); adjust meta.workers_per_farm to re-scale.",
            "Per-province gross/net for non-rice crops is the national figure applied flat (no per-"
            "province measured economics exist); the province spread you see is only rice.",
            "Farm-gate price and net return are national annual averages, not per-province.",
            "A household may farm more than one crop; single-crop figures here are per crop-holding, "
            "not a whole-household total. See household_economics for the whole-household income/debt.",
        ],
        "household_economics": econ.get("household_economics"),
    }
    return {"meta": meta, "crops": crops_out}


def legacy_build():
    """Fallback GROSS-only path (OAE economics absent). Uses the OLD NABC farmer_family denominator
    — flagged clearly as legacy/uncorrected. Kept only so the app degrades rather than breaking."""
    y = _load(YIELD)["crops"]
    pr = _load(PRICES)["commodities"]
    area_c = _canon_map(_load(AREA)["provinces"])
    fam_c = _canon_map(_load(FAMILIES)["farmer_family"])

    def price_kg(entry):
        p, u = entry.get("price"), entry.get("unit") or ""
        if p is None:
            return None
        return p / 1000.0 if "ตัน" in u else float(p)

    crops_out = []
    for crop in CROP_ORDER:
        ycrop, pentry, fkey = y.get(crop), pr.get(crop), FAMILY_KEY[crop]
        akey = {"rice": "rice", "maize": "maize", "cassava": "cassava",
                "rubber": "rubber", "oilpalm": "oilpalm"}[crop]
        if ycrop is None or pentry is None or fkey is None:
            continue
        price = price_kg(pentry)
        if price is None:
            continue
        nat_yield = ycrop.get("national")
        prov_yield = ycrop.get("provinces", {})
        rows, tr, tf = [], 0.0, 0.0
        for c in sorted(REGION):
            arec, frec = area_c.get(c), fam_c.get(c)
            if not arec or not frec:
                continue
            ha, fams = arec.get(akey), frec.get(fkey)
            if not ha or not fams or ha <= 0 or fams <= 0:
                continue
            planted_rai = ha * RAI_PER_HA
            yv, ysrc = (prov_yield[c], "measured") if c in prov_yield else (nat_yield, "national")
            if yv is None:
                continue
            rpf = planted_rai / fams
            gfy = rpf * yv * price
            rows.append({"province": c, "region": REGION.get(c),
                         "yield_kg_per_rai": round(yv), "yield_source": ysrc,
                         "gross_per_person_month": round(gfy / WORKERS_PER_FARM / 12.0),
                         "net_per_person_month": None, "loss": None})
            tr += planted_rai
            tf += fams
        if not rows:
            continue
        rows.sort(key=lambda r: (r["gross_per_person_month"], r["province"]))
        rpf = tr / tf if tf else None
        gfy = rpf * nat_yield * price if rpf else None
        crops_out.append({
            "crop": crop, "crop_en": CROP_EN[crop], "crop_th": ycrop.get("commod_th"),
            "loss": None, "price_thb_per_kg": round(price, 4), "n_provinces": len(rows),
            "national": {"gross_per_person_month": round(gfy / WORKERS_PER_FARM / 12.0) if gfy else None,
                         "net_per_person_month": None},
            "provinces": rows,
        })
    crops_out.sort(key=lambda c: (c["national"]["gross_per_person_month"] or 0, c["crop"]))
    meta = {
        "title": "Gross farmer income per person by crop (LEGACY fallback)",
        "generated_by": "pipeline/build_crop_farmer_income.py",
        "deterministic": True, "network_free": True, "unit": "THB (baht)",
        "workers_per_farm": WORKERS_PER_FARM, "n_crops": len(crops_out),
        "denominator": "LEGACY — NABC farmer_family (registration records, NOT households; known to "
                       "under-state rai/household). oae_farm_economics.json was absent, so the "
                       "corrected household denominator and NET income are unavailable this run.",
        "warning": "This is the pre-fix GROSS-only output; run pull_oae_farm_economics.py to restore "
                   "the corrected household denominator + net income.",
    }
    return {"meta": meta, "crops": crops_out}


def dumps(obj):
    return json.dumps(obj, ensure_ascii=False, indent=2) + "\n"


def _which_path():
    """Return ('primary'|'legacy'|None). Primary if OAE economics present; else legacy if the old
    inputs are all present; else None (nothing to build)."""
    if os.path.exists(ECON):
        return "primary"
    if all(os.path.exists(p) for p in LEGACY_INPUTS):
        return "legacy"
    return None


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
                         "exit 3 SKIP if inputs are absent")
    args = ap.parse_args()

    path = _which_path()
    if path is None:
        rel = os.path.relpath(ECON, ROOT)
        if args.check:
            print("build_crop_farmer_income.py --check: SKIP (absent: %s and legacy inputs)" % rel)
            sys.exit(3)
        sys.exit("build_crop_farmer_income.py: missing %s — run pull_oae_farm_economics.py first "
                 "(or the legacy NABC/DOAE/yield/price pulls)." % rel)

    text = dumps(build() if path == "primary" else legacy_build())

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
    print("wrote %s (%d crops, path=%s)" % (OUT, len(data["crops"]), path))
    for c in data["crops"]:
        n = c["national"]
        if path == "primary":
            print("  %-8s rai/hh=%-6s gross/person/mo=%-7s net/person/mo=%-7s %s"
                  % (c["crop"], n["rai_per_household"], n["gross_per_person_month"],
                     n["net_per_person_month"], "LOSS" if c["loss"] else ""))
        else:
            print("  %-8s gross/person/mo=%s (legacy)" % (c["crop"], n["gross_per_person_month"]))


if __name__ == "__main__":
    main()
