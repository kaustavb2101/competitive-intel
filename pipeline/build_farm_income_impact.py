#!/usr/bin/env python3
"""
build_farm_income_impact.py — FARM-INCOME IMPACT (portfolio risk, objective #1): what this year's
crop price move does to farm income, by province / region / branch, on TWO bases (price and margin).

Owner's original ask: "impact of each crop x planted area x NSO farm income of the province."
Three corrections he approved sit on top of that, and are implemented here:

  CORRECTION 1 — weight by REVENUE, not planted area.
    revenue(p,c) = area(p,c) * yield_per_rai(c) * price_per_kg(c)
    A rai of oil palm earns several times a rai of cassava; area alone misstates exposure.

  CORRECTION 2 — shock only the CROP share of farm income, not all of it.
    crop_income_share_pct is read LIVE from platform/data/farm_household.json (MEASURED OAE
    farm-household cash P&L survey): farm_crops income / total household cash income, for the
    latest surveyed crop_year. That single ratio already nets out BOTH gaps in one MEASURED
    number: (a) ~half a farm household's cash is non-farm, and (b) livestock/other income inside
    the farm total isn't crop income either. farm_household.json is explicitly NATIONAL ONLY (its
    own scope_warning forbids joining it to geography) — so this script uses it as exactly one
    national SCALAR multiplier, never keyed by province. If that file is ever absent or malformed,
    the build falls back to FALLBACK_CROP_INCOME_SHARE_PCT below, an ESTIMATED named constant, and
    says so loudly in meta (never silently).

  CORRECTION 3 — report a PRICE shock AND a MARGIN shock, both.
    Costs are ~fixed per rai, so a price move p translates into a bigger MARGIN move:
      margin_shock_pct(c) = price_yoy_pct(c) * R(c) / (R(c) - C(c))
    R = revenue/rai (Correction 1's own figure), C = cost/rai (platform/data/crop_margin.json,
    OAE cost reports). Guarded: R - C <= 0 (crop at/below break-even) -> margin_shock_pct = null
    with a reason, never a divide-by-zero or a nonsense multiplier.

Crop universe = the 5 crops with BOTH a measured production cost (crop_margin.json) AND province
planting area (crop_prov_area.json OAE census for rice/rubber/oilpalm; doae_planted_area.json DOAE
registry for cassava/maize, ha -> rai): cassava, maize, oilpalm, rice, rubber. Coconut / pineapple /
sugarcane have a measured PRICE (farmgate_prices.json / crop_stress.json) but NO measured production
cost anywhere in this repo, so no margin_shock can be computed for them under Correction 3 — they are
dropped from this builder entirely (both bases), not just from the margin side, so price_impact_pct
and margin_impact_pct stay on the same apples-to-apples crop set. See meta.dropped_crops.

BRANCH GRAIN: NSO farm income is published at PROVINCE grain (agri_income_by_province.json, itself
NSO SES 2566 Agriculture-occupation income). source-data/branches_final.json carries no measured
per-branch farm-account / agri-household count, so every branch row is the province figure split
EQUALLY across that province's branches — an ALLOCATION, not a measurement. Every branch row carries
basis="allocation" and meta says so plainly.

  in : source-data/crop_prov_area.json         MEASURED OAE planting area, rai (rice/rubber/oilpalm)
       source-data/doae_planted_area.json      MEASURED DOAE registry area, ha (cassava/maize)
       platform/data/crop_margin.json          MEASURED yield/price/cost/price_yoy per crop
       platform/data/agri_income_by_province.json  MEASURED NSO SES 2566 agri income per province
       platform/data/farm_household.json       MEASURED national farm/crop income-share split
       source-data/branches_final.json         branch -> province (for the branch allocation)
       pipeline/lib/regionmap.py               canonical() / region_of() province-string folding
  out: platform/data/farm_income_impact.json   (--check: byte-exact reproduce)

Run:
  python3 build_farm_income_impact.py            # write platform/data/farm_income_impact.json
  python3 build_farm_income_impact.py --check    # re-run, byte-compare against committed file
"""
import argparse
import json
import os
import sys
from collections import defaultdict

from lib.regionmap import canonical, region_of, REGION

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, "source-data")
PLAT = os.path.join(ROOT, "platform", "data")
OUT = os.path.join(PLAT, "farm_income_impact.json")

REQUIRED_INPUTS = [
    os.path.join(SRC, "crop_prov_area.json"),
    os.path.join(SRC, "doae_planted_area.json"),
    os.path.join(SRC, "branches_final.json"),
    os.path.join(PLAT, "crop_margin.json"),
    os.path.join(PLAT, "agri_income_by_province.json"),
]

HA_TO_RAI = 6.25   # DOAE hectares -> rai (crop_prov_area.json convention; matches build_crop_stress.py)

# crop key -> English label (for the crops[] display)
CROP_EN = {"cassava": "Cassava", "maize": "Maize", "oilpalm": "Oil palm",
           "rice": "Rice", "rubber": "Rubber"}

# crop keys this builder covers — the 5 with BOTH measured area AND measured production cost.
CROPS = ("cassava", "maize", "oilpalm", "rice", "rubber")

# crops with a measured PRICE (crop_stress.json / farmgate_prices.json) but no measured production
# cost anywhere in this repo, so Correction 3's margin_shock cannot be computed for them — dropped
# from this builder entirely (documented, not silent).
DROPPED_CROPS = {
    "coconut": "measured price exists (farmgate_prices.json) but no measured production cost "
               "(crop_margin.json does not cover it) — margin_shock undefined under Correction 3.",
    "pineapple": "measured price exists (farmgate_prices.json) but no measured production cost "
                 "(crop_margin.json does not cover it) — margin_shock undefined under Correction 3.",
    "sugarcane": "measured price exists (farmgate_prices.json, OCSB announced price) but no measured "
                 "production cost anywhere in this repo (crop_margin.json's own omitted_crops list) — "
                 "margin_shock undefined under Correction 3.",
}

# ESTIMATED fallback ONLY used if platform/data/farm_household.json is absent/malformed at build time
# (it is present today — see meta.crop_income_share for the MEASURED value actually used). Named and
# labelled per the owner's instruction: "if no measured split exists, say so loudly ... and expose the
# assumption as a named constant." This mirrors the ESTIMATED crop_sensitivity=0.55 already used (for a
# related but not identical purpose) in pipeline/build_income_impact.py / build_crop_mix.py.
FALLBACK_CROP_INCOME_SHARE_PCT = 39.5


def load(*parts):
    with open(os.path.join(*parts), encoding="utf-8") as f:
        return json.load(f)


def load_crop_constants():
    """Per-crop national constants from platform/data/crop_margin.json: yield, price, cost,
    price_yoy_pct, revenue_per_rai (Correction 1) and margin_shock_pct (Correction 3, guarded).

    Returns (constants: {crop: {...}}, meta_rows: [source rows used, for provenance]).
    """
    doc = load(PLAT, "crop_margin.json")
    rows_by_crop = defaultdict(list)
    for row in doc.get("crops", []):
        c = row.get("crop")
        if c in CROPS:
            rows_by_crop[c].append(row)

    out = {}
    used_rows = []
    for c in CROPS:
        rows = rows_by_crop.get(c) or []
        if not rows:
            continue
        # rice carries 3 rows (one national "all rice" compendium row + two fertilizer-practice
        # sub-analyses); pick the compendium row — cost_method="derived_from_cost_per_ton" — which
        # is the same all-rice basis crop_prov_area.json / oae_farm_economics.json use elsewhere.
        # The other 4 crops have exactly one row each, so this is a no-op for them.
        chosen = next((r for r in rows if r.get("cost_method") == "derived_from_cost_per_ton"), rows[0])
        used_rows.append(chosen)
        yld = chosen.get("yield_kg_per_rai")
        price_kg = chosen.get("price_kg")
        cost_per_rai = chosen.get("cost_per_rai")
        price_yoy_pct = chosen.get("price_yoy_pct")
        if yld is None or price_kg is None or price_yoy_pct is None:
            continue
        revenue_per_rai = round(yld * price_kg, 2)
        if cost_per_rai is not None:
            margin_per_rai = round(revenue_per_rai - cost_per_rai, 2)
        else:
            margin_per_rai = None
        # --- Correction 3 guard: R - C <= 0 -> null, never a divide-by-zero / nonsense multiplier ---
        if margin_per_rai is None:
            margin_shock_pct = None
            margin_reason = "no measured cost_per_rai for this crop row"
        elif margin_per_rai <= 0:
            margin_shock_pct = None
            margin_reason = ("crop at/below break-even (R-C=%.2f THB/rai <= 0); margin multiplier "
                              "undefined" % margin_per_rai)
        else:
            margin_shock_pct = round(price_yoy_pct * revenue_per_rai / margin_per_rai, 2)
            margin_reason = None
        out[c] = {
            "yield_kg_per_rai": yld,
            "price_thb_per_kg": price_kg,
            "price_yoy_pct": price_yoy_pct,
            "cost_per_rai": cost_per_rai,
            "revenue_per_rai": revenue_per_rai,
            "margin_per_rai": margin_per_rai,
            "margin_shock_pct": margin_shock_pct,
            "margin_shock_reason": margin_reason,
            "price_asof": chosen.get("price_asof"),
            "cost_year": chosen.get("cost_year"),
        }
    return out, used_rows


def load_area():
    """{crop: {prov_th: rai}} for the 5 covered crops, province strings folded through canonical().

    rice/rubber/oilpalm: source-data/crop_prov_area.json (OAE planting-area census, already rai).
    cassava/maize: source-data/doae_planted_area.json (DOAE farmer registry, hectares -> rai) —
    crop_prov_area.json carries neither, same gap build_crop_stress.py fills the same way.
    """
    area = defaultdict(dict)

    cpa = load(SRC, "crop_prov_area.json")
    for c in ("rice", "rubber", "oilpalm"):
        for raw_prov, rai in (cpa.get(c) or {}).items():
            prov = canonical(raw_prov)
            if not prov or not rai or rai <= 0:
                continue   # blank/unresolved key = the unallocated non-portfolio bucket; excluded
            area[c][prov] = area[c].get(prov, 0.0) + float(rai)

    doae = load(SRC, "doae_planted_area.json")
    for raw_prov, crops in (doae.get("provinces") or {}).items():
        prov = canonical(raw_prov)
        if not prov or not isinstance(crops, dict):
            continue
        for c in ("cassava", "maize"):
            ha = crops.get(c)
            if isinstance(ha, (int, float)) and ha > 0:
                area[c][prov] = area[c].get(prov, 0.0) + ha * HA_TO_RAI

    return area


def load_crop_income_share():
    """MEASURED crop-share-of-income (Correction 2), read LIVE from farm_household.json.

    Returns (crop_income_share_pct, provenance_dict). Falls back to the named ESTIMATED constant
    (loudly labelled) only if the file is absent or missing the expected fields.
    """
    path = os.path.join(PLAT, "farm_household.json")
    if os.path.exists(path):
        try:
            doc = load(PLAT, "farm_household.json")
            lat = doc["latest"]
            farm_crops = lat["income"]["farm_crops"]
            total = lat["income"]["total"]
            if isinstance(farm_crops, (int, float)) and isinstance(total, (int, float)) and total > 0:
                pct = round(farm_crops / total * 100.0, 2)
                return pct, {
                    "status": "MEASURED",
                    "source": "platform/data/farm_household.json (OAE farm-household cash P&L survey)",
                    "crop_year": lat.get("crop_year"),
                    "farm_crops_thb": farm_crops,
                    "farm_total_thb": lat["income"].get("farm_total"),
                    "total_thb": total,
                    "farm_share_of_income_pct": lat.get("farm_share_of_income_pct"),
                    "nonfarm_share_of_income_pct": lat.get("nonfarm_share_of_income_pct"),
                    "formula": "crop_income_share_pct = farm_crops / total * 100 — nets out BOTH the "
                               "farm/non-farm split AND the crop/livestock/other split inside farm "
                               "income in one MEASURED ratio (farm_share_of_income_pct x crop-share-"
                               "of-farm-income reduces to exactly this).",
                }
        except (KeyError, TypeError, ValueError):
            pass
    return FALLBACK_CROP_INCOME_SHARE_PCT, {
        "status": "ESTIMATED — FALLBACK (loud)",
        "warning": "platform/data/farm_household.json was absent or unreadable at build time, so "
                   "the MEASURED crop-income-share split could not be read. Falling back to the "
                   "named constant FALLBACK_CROP_INCOME_SHARE_PCT=%.1f in "
                   "pipeline/build_farm_income_impact.py — an ESTIMATE, not a measurement. Restore "
                   "farm_household.json to get the measured figure back." % FALLBACK_CROP_INCOME_SHARE_PCT,
    }


def _reconcile_cents(raw_pairs, target_pct):
    """Round each (key, raw_pct) contribution to 2dp such that the rounded values sum EXACTLY
    (in integer cents, avoiding float-equality pitfalls) to round(target_pct, 2). The residual from
    independent per-crop rounding is assigned to the crop with the largest |raw contribution|
    (the province's dominant crop) so every province's crops[].contribution_pp foots to its own
    price_impact_pct, verified by the caller.
    """
    target_cents = int(round(target_pct * 100))
    cents = [(k, int(round(v * 100))) for k, v in raw_pairs]
    diff = target_cents - sum(c for _, c in cents)
    if diff and cents:
        idx = max(range(len(cents)), key=lambda i: abs(raw_pairs[i][1]))
        k, c = cents[idx]
        cents[idx] = (k, c + diff)
    return {k: round(c / 100.0, 2) for k, c in cents}


def build():
    crop_const, cm_rows_used = load_crop_constants()
    area = load_area()
    crop_income_share_pct, share_provenance = load_crop_income_share()

    agri_income = load(PLAT, "agri_income_by_province.json")["provinces"]
    branches = load(SRC, "branches_final.json")

    # --- branch province set (canonicalized) + per-province branch count, for the branch alloc ---
    branch_provs = defaultdict(list)
    for r in branches:
        prov = canonical(r.get("prov"))
        if prov:
            branch_provs[prov].append(r)

    covered_crops = sorted(c for c in CROPS if c in crop_const)

    # --- per-province revenue(p,c) across the covered, priced crops (Correction 1) ---
    prov_revenue = defaultdict(dict)   # prov -> {crop: revenue_thb}
    prov_area_rai = defaultdict(dict)  # prov -> {crop: area_rai}  (for the crops[].area_rai field)
    for c in covered_crops:
        k = crop_const[c]
        for prov, rai in area.get(c, {}).items():
            if rai <= 0:
                continue
            prov_area_rai[prov][c] = rai
            prov_revenue[prov][c] = rai * k["revenue_per_rai"]

    provinces_out = []
    dropped_zero_area = []
    for prov in sorted(prov_revenue.keys()):
        rev = prov_revenue[prov]
        w_sum = sum(rev.values())
        if w_sum <= 0:
            dropped_zero_area.append(prov)
            continue

        # price_impact_pct: revenue-weighted mean price YoY over covered crops present here
        raw_price_pairs = [(c, (rev[c] / w_sum) * crop_const[c]["price_yoy_pct"]) for c in rev]
        price_impact_pct = round(sum(v for _, v in raw_price_pairs), 2)
        contrib = _reconcile_cents(raw_price_pairs, price_impact_pct)

        # margin_impact_pct: revenue-weighted mean margin_shock over crops with a VALID (non-null)
        # margin_shock only — renormalized over that subset (a crop guarded to null simply doesn't
        # contribute), same pattern build_crop_stress.py uses for its own price_coverage.
        margin_rev = {c: rev[c] for c in rev if crop_const[c]["margin_shock_pct"] is not None}
        w_sum_margin = sum(margin_rev.values())
        if w_sum_margin > 0:
            margin_impact_pct = round(
                sum((margin_rev[c] / w_sum_margin) * crop_const[c]["margin_shock_pct"]
                    for c in margin_rev), 2)
            margin_coverage_pct = round(w_sum_margin / w_sum * 100.0, 2)
        else:
            margin_impact_pct = None
            margin_coverage_pct = 0.0

        crops_list = []
        for c in sorted(rev.keys(), key=lambda c: (-rev[c], c)):
            crops_list.append({
                "crop": CROP_EN.get(c, c),
                "area_rai": int(round(prov_area_rai[prov][c])),
                "revenue_share_pct": round(rev[c] / w_sum * 100.0, 2),
                "price_yoy_pct": crop_const[c]["price_yoy_pct"],
                "margin_shock_pct": crop_const[c]["margin_shock_pct"],
                "contribution_pp": contrib[c],
            })

        region = region_of(prov)
        agri = agri_income.get(prov) or {}
        agri_monthly = agri.get("agri_income")
        farm_income_thb = int(round(agri_monthly * 12)) if isinstance(agri_monthly, (int, float)) else None
        if farm_income_thb is not None:
            crop_income_thb = int(round(farm_income_thb * crop_income_share_pct / 100.0))
            d_income_price_thb = int(round(crop_income_thb * price_impact_pct / 100.0))
            d_income_margin_thb = (int(round(crop_income_thb * margin_impact_pct / 100.0))
                                    if margin_impact_pct is not None else None)
        else:
            crop_income_thb = None
            d_income_price_thb = None
            d_income_margin_thb = None

        reconciles = round(sum(contrib.values()), 2) == price_impact_pct
        assert reconciles, "crops[].contribution_pp must sum to price_impact_pct for %s" % prov

        provinces_out.append({
            "th": prov,
            "region": region,
            "price_impact_pct": price_impact_pct,
            "margin_impact_pct": margin_impact_pct,
            "crop_income_thb": crop_income_thb,
            "farm_income_thb": farm_income_thb,
            "crop_income_share_pct": crop_income_share_pct,
            "d_income_price_thb": d_income_price_thb,
            "d_income_margin_thb": d_income_margin_thb,
            "reconciles": reconciles,
            "crops": crops_list,
            "components": {
                "revenue_thb": int(round(w_sum)),
                "margin_coverage_pct": margin_coverage_pct,
                "n_branches": len(branch_provs.get(prov, [])),
            },
        })

    # worst-first: smallest (most negative / least favourable) margin_impact_pct leads the table.
    provinces_out.sort(key=lambda r: (
        r["margin_impact_pct"] if r["margin_impact_pct"] is not None else 0.0,
        r["th"],
    ))

    # --- regions: sum the THB legs, then price/margin_impact_pct = the crop_income-weighted mean ---
    regions_out = []
    by_region = defaultdict(list)
    for r in provinces_out:
        by_region[r["region"]].append(r)
    for region in sorted(by_region.keys()):
        rows = by_region[region]
        crop_income_thb = sum(r["crop_income_thb"] for r in rows if r["crop_income_thb"] is not None)
        d_price = sum(r["d_income_price_thb"] for r in rows if r["d_income_price_thb"] is not None)
        d_margin_rows = [r for r in rows if r["d_income_margin_thb"] is not None]
        d_margin = sum(r["d_income_margin_thb"] for r in d_margin_rows)
        crop_income_margin_basis = sum(r["crop_income_thb"] for r in d_margin_rows
                                        if r["crop_income_thb"] is not None)
        regions_out.append({
            "region": region,
            "price_impact_pct": round(d_price / crop_income_thb * 100.0, 2) if crop_income_thb else 0.0,
            "margin_impact_pct": (round(d_margin / crop_income_margin_basis * 100.0, 2)
                                  if crop_income_margin_basis else None),
            "crop_income_thb": int(round(crop_income_thb)),
            "d_income_price_thb": int(round(d_price)),
            "d_income_margin_thb": int(round(d_margin)),
            "n_provinces": len(rows),
        })
    regions_out.sort(key=lambda r: (
        r["margin_impact_pct"] if r["margin_impact_pct"] is not None else 0.0,
        r["region"],
    ))

    # --- national rollup, same weighting convention ---
    crop_income_thb_nat = sum(r["crop_income_thb"] for r in provinces_out if r["crop_income_thb"] is not None)
    d_price_nat = sum(r["d_income_price_thb"] for r in provinces_out if r["d_income_price_thb"] is not None)
    margin_rows_nat = [r for r in provinces_out if r["d_income_margin_thb"] is not None]
    d_margin_nat = sum(r["d_income_margin_thb"] for r in margin_rows_nat)
    crop_income_margin_basis_nat = sum(r["crop_income_thb"] for r in margin_rows_nat
                                        if r["crop_income_thb"] is not None)
    national = {
        "price_impact_pct": (round(d_price_nat / crop_income_thb_nat * 100.0, 2)
                              if crop_income_thb_nat else 0.0),
        "margin_impact_pct": (round(d_margin_nat / crop_income_margin_basis_nat * 100.0, 2)
                              if crop_income_margin_basis_nat else None),
        "crop_income_thb": int(round(crop_income_thb_nat)),
        "d_income_price_thb": int(round(d_price_nat)),
        "d_income_margin_thb": int(round(d_margin_nat)),
        "n_provinces": len(provinces_out),
        "n_crops": len(covered_crops),
    }

    # --- branches: EQUAL split of the province's THB legs across that province's branches ---
    prov_by_th = {r["th"]: r for r in provinces_out}
    branches_out = []
    for r in branches:
        prov = canonical(r.get("prov"))
        prec = prov_by_th.get(prov)
        n = len(branch_provs.get(prov, [])) if prov else 0
        d_price_b = None
        d_margin_b = None
        if prec and n:
            if prec["d_income_price_thb"] is not None:
                d_price_b = int(round(prec["d_income_price_thb"] / n))
            if prec["d_income_margin_thb"] is not None:
                d_margin_b = int(round(prec["d_income_margin_thb"] / n))
        branches_out.append({
            "branch_id_or_name": r.get("code") or r.get("name"),
            "province_th": prov or r.get("prov"),
            "region": prec["region"] if prec else region_of(prov) if prov else None,
            "d_income_price_thb": d_price_b,
            "d_income_margin_thb": d_margin_b,
            "basis": "allocation",
        })
    branches_out.sort(key=lambda b: (b["province_th"] or "", b["branch_id_or_name"] or ""))

    meta = {
        "title": "Farm-income impact — price and margin shock, by crop revenue weight (portfolio "
                 "risk, objective #1)",
        "generated_by": "pipeline/build_farm_income_impact.py",
        "deterministic": True,
        "network_free": True,
        "owner_formula": "impact of each crop x planted area x NSO farm income of the province "
                         "(owner's original ask), corrected as below (owner-approved).",
        "corrections": {
            "1_revenue_weighting": "revenue(p,c) = area(p,c) * yield_per_rai(c) * price_per_kg(c) — "
                                   "weights each crop by REVENUE, not planted area, so a rai of oil "
                                   "palm counts several times a rai of cassava, as it earns.",
            "2_crop_share_of_income": "the price/margin shock is applied to crop_income_thb = "
                                      "farm_income_thb x crop_income_share_pct, NOT to 100%% of "
                                      "farm_income_thb. See meta.crop_income_share for the MEASURED "
                                      "split actually used.",
            "3_price_and_margin": "reports BOTH price_impact_pct (crop-gate price move) AND "
                                  "margin_impact_pct (margin_shock = price_yoy * R/(R-C), R=revenue/"
                                  "rai, C=cost/rai — moves further than price because costs are ~"
                                  "fixed per rai). Guarded: R-C<=0 -> null with a reason (see "
                                  "crop_constants[].margin_shock_reason), never a divide-by-zero.",
        },
        "crop_income_share": share_provenance,
        "crop_income_share_pct_used": crop_income_share_pct,
        "crop_constants": {
            c: {k: v for k, v in crop_const[c].items() if k != "margin_shock_reason" or v is not None}
            for c in covered_crops
        },
        "dropped_crops": DROPPED_CROPS,
        "dropped_provinces_zero_area": sorted(dropped_zero_area),
        "branch_grain": {
            "basis": "allocation",
            "what": "NSO farm income (agri_income_by_province.json) is published at PROVINCE grain. "
                    "Every branch row is that province's d_income_price_thb / d_income_margin_thb "
                    "split EQUALLY across the province's branches in the AutoX network — an "
                    "ALLOCATION, not a measurement of that branch's own borrowers.",
            "allocation_key": "equal split (1/n_branches_in_province). source-data/branches_final.json "
                              "carries no measured per-branch farm-account or agri-household count to "
                              "weight by instead; if one is added later, prefer it over equal split.",
        },
        "farm_income_basis": {
            "source": "platform/data/agri_income_by_province.json (agri_income) x 12",
            "what": "agri_income is the NSO SES 2566 average MONTHLY Agriculture-occupation income "
                    "for that province, MEASURED. Annualized (x12) here for a representative province "
                    "farm-income level — this is a per-agriculture-worker income floor, not a "
                    "province-aggregate farm-household total (no measured province agri-workforce or "
                    "farm-household headcount exists in this repo to build a true aggregate).",
        },
        "reconciliation": "Per-province crops[].contribution_pp is rounded (integer-cent correction "
                          "against the dominant crop) so it sums EXACTLY to that province's own "
                          "price_impact_pct — asserted in code (build() raises if it does not) and "
                          "re-exposed per province as the boolean `reconciles`.",
        "rollup_caveat": "regions[]/national are SUMS of each province's own representative "
                        "crop_income_thb / d_income_*_thb (with price_impact_pct/margin_impact_pct "
                        "recomputed as the crop-income-weighted mean of the underlying province "
                        "values) — NOT a population- or farm-household-count-weighted true national "
                        "aggregate. Read direction and relative magnitude across provinces/regions, "
                        "not the rollup as a literal portfolio total.",
        "crop_margin_source_rows": cm_rows_used,
        "provenance": {
            "crop_prov_area.json": "MEASURED OAE planting area (rai) — rice/rubber/oilpalm.",
            "doae_planted_area.json": "MEASURED DOAE farmer-registry planted area (hectares -> rai) "
                                      "— cassava/maize (OAE crop_prov_area.json does not carry them).",
            "crop_margin.json": "MEASURED yield/price/cost per crop (OAE cost reports + NABC/OCSB "
                                "farm-gate prices) — this build's R, C and price_yoy_pct per crop.",
            "agri_income_by_province.json": "MEASURED NSO SES 2566 Agriculture-occupation monthly "
                                            "income per province — this build's farm_income_thb base.",
            "farm_household.json": "MEASURED OAE farm-household cash P&L survey, NATIONAL ONLY — "
                                   "this build's crop_income_share_pct (a single national scalar, "
                                   "never joined to geography, per that file's own scope_warning).",
            "branches_final.json": "the 2,015-branch master — province + branch count for the "
                                   "branch-grain allocation.",
        },
        "caveats": [
            "R (revenue/rai), C (cost/rai) and price_yoy_pct are NATIONAL per-crop constants — only "
            "planted AREA varies by province here; no per-province farm-gate price or cost exists.",
            "crop_income_share_pct is a NATIONAL constant (farm_household.json is a national survey, "
                "not a per-province one) applied identically to every province's own farm_income_thb.",
            "margin_impact_pct excludes any crop whose margin_shock is guarded null (R-C<=0) and "
                "renormalizes over the remaining covered revenue — see components.margin_coverage_pct.",
            "this supersedes the ESTIMATED crop_sensitivity=0.55 constant used for a related purpose "
                "in pipeline/build_income_impact.py / build_crop_mix.py: this builder uses the "
                "MEASURED farm_household.json split instead wherever it is available.",
        ],
    }

    return {
        "meta": meta,
        "national": national,
        "regions": regions_out,
        "provinces": provinces_out,
        "branches": branches_out,
    }


def dumps(obj):
    # compact, per the determinism contract; LF-only handled by the newline="" file opens below
    # (the exact idiom pipeline/build_crop_stress.py uses — NOT Python's default universal-newline
    # translation, which is what turned committed LF into local CRLF on Windows for other builders).
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":")) + "\n"


def _missing_inputs():
    return [p for p in REQUIRED_INPUTS if not os.path.exists(p)]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true",
                    help="re-run and byte-compare against the committed JSON; exit 1 on drift")
    args = ap.parse_args()

    missing = _missing_inputs()
    if missing:
        print("SKIP: required input(s) missing: %s" % ", ".join(os.path.relpath(p, ROOT) for p in missing))
        sys.exit(3)

    data = build()
    text = dumps(data)

    if args.check:
        if not os.path.exists(OUT):
            print("SKIP: %s does not exist yet (--check has nothing to compare against)" % OUT)
            sys.exit(3)
        # newline="" on both the read and the write so this compares the ACTUAL bytes on disk — see
        # build_crop_stress.py's --check for the full CRLF-vs-LF story this idiom fixes.
        with open(OUT, encoding="utf-8", newline="") as f:
            existing = f.read()
        if existing == text:
            print("CHECK OK: %s reproduces byte-for-byte (%d provinces)" %
                  (OUT, len(data["provinces"])))
            sys.exit(0)
        print("CHECK FAIL: %s differs from a fresh build" % OUT)
        sys.exit(1)

    with open(OUT, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    n = data["national"]
    print("wrote %s (%d provinces, %d crops, %d branches)" %
          (OUT, len(data["provinces"]), n["n_crops"], len(data["branches"])))
    print("  national: price_impact=%.2f%% margin_impact=%s crop_income=THB%s" % (
        n["price_impact_pct"],
        ("%.2f%%" % n["margin_impact_pct"]) if n["margin_impact_pct"] is not None else "n/a",
        format(n["crop_income_thb"], ",")))
    worst = sorted(data["provinces"], key=lambda r: (
        r["margin_impact_pct"] if r["margin_impact_pct"] is not None else 0.0))[:5]
    for r in worst:
        print("  %-14s margin_impact=%s price_impact=%.2f%% reconciles=%s" % (
            r["th"],
            ("%.2f%%" % r["margin_impact_pct"]) if r["margin_impact_pct"] is not None else "n/a",
            r["price_impact_pct"], r["reconciles"]))


if __name__ == "__main__":
    main()
