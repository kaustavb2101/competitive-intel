#!/usr/bin/env python3
"""
build_crop_stress.py — PORTFOLIO RISK (objective #1): per-province crop-household stress.

Network-free, deterministic. Joins three LOCAL source-data files:
  - crop_prov_area.json    planting area (rai) per crop -> {province_th: area}
  - commodity_board.json   price board rows (crop label + YoY %); GLOBAL price direction proxy
  - branches_final.json    per-branch rain_3mo_anom (drought proxy) + prov/region

It computes, PER PROVINCE:
  crop_mix       dominant crops by planting-area share (top 3), with share + raw rai.
  price_stress   planting-area-weighted price YoY across the province's crops
                 (more negative = worse). PROXY: World Bank GLOBAL prices, a DIRECTION
                 signal only, NOT Thai farm-gate.  [estimated/proxy]
  drought        province mean of branch rain_3mo_anom (% of normal precip, measured proxy),
                 expressed as a 0..1 "drought direction" (1 = driest). [measured proxy]
  crop_dependence how crop-dependent the province is = total crop rai / max province crop rai,
                 0..1. [measured]
  agri_stress    transparent composite (see FORMULA below). [ESTIMATED]
  components     the raw numbers behind the index so the UI shows reality, not just a score.

FORMULA (documented, plain):
  price_term   = clamp(-price_stress_yoy / 25, 0, 1)
                 price YoY in %; -25% (or worse) -> 1.0, 0% or positive -> 0.0.
                 (25 chosen because the worst board crop, Sugar, is -25.9%.)
  drought_term = clamp((100 - rain_pct_of_normal) / 40, 0, 1)
                 100 = normal rainfall; 60% of normal (or drier) -> 1.0; at/above normal -> 0.0.
                 (40 chosen because observed branch anomalies bottom out near 56% of normal.)
  hazard       = 0.6*price_term + 0.4*drought_term
                 price weighted higher: it hits cash-crop borrowers' incomes directly.
  agri_stress  = round(hazard * crop_dependence, 4)
                 a province is only a PORTFOLIO risk if borrowers there actually farm at scale,
                 so the hazard is scaled by crop_dependence (more crop area = more exposure).

Run:
  python3 build_crop_stress.py            # write platform/data/crop_stress.json
  python3 build_crop_stress.py --check    # re-run, byte-compare against committed file
"""
import json
import os
import sys
import argparse
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, "source-data")
OUT = os.path.join(ROOT, "platform", "data", "crop_stress.json")

# crop key in crop_prov_area.json -> commodity_board label
CROP_TO_BOARD = {
    "rice": "Rice",
    "rubber": "Rubber",
    "oilpalm": "Palm oil",
}
# human-readable crop labels (en) for the UI
CROP_EN = {"rice": "Rice", "rubber": "Rubber", "oilpalm": "Oil palm"}

# normalization constants (see FORMULA in module docstring)
PRICE_SCALE = 25.0      # % YoY drop that maps price_term to 1.0
DROUGHT_FLOOR = 40.0    # rainfall shortfall (pp below normal) that maps drought_term to 1.0
NORMAL_RAIN = 100.0     # rain_3mo_anom value meaning "normal" precipitation
W_PRICE = 0.6
W_DROUGHT = 0.4
TOP_CROPS = 3

# --- double-stress flag (RESEARCH_DIGEST 2026-06-30, obj #1) -----------------
# Research: rice AND rubber farm-gate prices softening into 2026 (global oversupply,
# India white-rice exports resumed) WHILE El Niño drought probability is high from
# mid-2026 (>80%). Flag provinces hit by BOTH at once. Uses ONLY signals already in
# this computation (crop_mix shares, price_term, drought) — no new external numbers.
DS_SHARE_FLOOR = 0.5     # rice+rubber must be >= half of mapped crop area to count
DS_DROUGHT_FLOOR = 0.6   # drought signal (0..1) considered "elevated" at/above this
RICE_RUBBER = ("Rice", "Rubber")


def load(name):
    with open(os.path.join(SRC, name), encoding="utf-8") as f:
        return json.load(f)


def clamp(x, lo, hi):
    return max(lo, min(hi, x))


def build():
    crop_area = load("crop_prov_area.json")   # {crop: {prov_th: rai}}
    board = load("commodity_board.json")       # list of rows
    branches = load("branches_final.json")     # list of branch dicts

    # --- board lookup: crop key -> yoy % (only crops we have planting area for) ---
    board_by_label = {row["lab"]: row for row in board}
    crop_yoy = {}
    for ckey, blabel in CROP_TO_BOARD.items():
        if blabel in board_by_label:
            crop_yoy[ckey] = float(board_by_label[blabel]["yoy"])

    covered_crops = sorted(crop_yoy.keys())
    # crops with planting-area data but no usable board price (coverage gap)
    area_crops = set(crop_area.keys())
    uncovered_area_crops = sorted(area_crops - set(crop_yoy.keys()))
    # board crops in the Crops segment we could NOT area-weight (no planting area)
    board_crop_labels = {r["lab"] for r in board if r.get("seg") == "Crops"}
    uncovered_board_crops = sorted(board_crop_labels - set(CROP_TO_BOARD.values()))

    # --- valid provinces = those in the AutoX branch network (the actual portfolio) ---
    # crop_prov_area.json carries an empty-string '' key (an unallocated rai bucket, not a
    # real province). We only keep provinces that appear in branches_final.json so the join
    # stays clean and the crop_dependence denominator is a real province, not the bucket.
    branch_provs = {r.get("prov") for r in branches if r.get("prov")}

    # --- province -> {crop: rai} (only covered crops contribute to stress weights) ---
    prov_area = defaultdict(dict)   # full mix (all crops, for crop_mix display)
    skipped_area_rai = 0.0
    for ckey, provmap in crop_area.items():
        for prov, rai in provmap.items():
            if not rai or rai <= 0:
                continue
            if prov not in branch_provs:
                skipped_area_rai += float(rai)  # unallocated / non-portfolio bucket
                continue
            prov_area[prov][ckey] = float(rai)

    # --- province drought from branch rain_3mo_anom (measured proxy) ---
    prov_rain = defaultdict(list)   # prov -> [rain values]
    prov_region = {}                # prov -> region (from branches)
    prov_nbranch = defaultdict(int)
    for r in branches:
        prov = r.get("prov")
        if not prov:
            continue
        prov_nbranch[prov] += 1
        prov_region.setdefault(prov, r.get("region"))
        rv = r.get("rain_3mo_anom")
        if rv is not None:
            prov_rain[prov].append(float(rv))

    # crop_dependence denominator = max total crop rai across provinces
    prov_total_rai = {p: sum(m.values()) for p, m in prov_area.items()}
    max_total_rai = max(prov_total_rai.values()) if prov_total_rai else 1.0

    # build per-province records for every province that has crop area
    records = []
    for prov in sorted(prov_area.keys()):
        mix_raw = prov_area[prov]
        total_rai = sum(mix_raw.values())

        # crop_mix: top N crops by area share (display: ALL crops we have area for)
        mix_sorted = sorted(mix_raw.items(), key=lambda kv: (-kv[1], kv[0]))
        crop_mix = []
        for ckey, rai in mix_sorted[:TOP_CROPS]:
            crop_mix.append({
                "crop": CROP_EN.get(ckey, ckey),
                "share": round(rai / total_rai, 4) if total_rai else 0.0,
                "area": int(round(rai)),
            })

        # price_stress: area-weighted YoY across COVERED crops only
        w_sum = 0.0
        w_yoy = 0.0
        for ckey, rai in mix_raw.items():
            if ckey in crop_yoy:
                w_sum += rai
                w_yoy += rai * crop_yoy[ckey]
        if w_sum > 0:
            price_stress = round(w_yoy / w_sum, 2)
            price_coverage = round(w_sum / total_rai, 4) if total_rai else 0.0
        else:
            price_stress = None
            price_coverage = 0.0

        # drought: province mean rain_3mo_anom (% of normal); fewer = drier
        rains = prov_rain.get(prov, [])
        if rains:
            rain_mean = round(sum(rains) / len(rains), 2)
        else:
            rain_mean = None

        # crop_dependence 0..1
        crop_dependence = round(total_rai / max_total_rai, 4) if max_total_rai else 0.0

        # --- composite terms ---
        if price_stress is not None:
            price_term = clamp(-price_stress / PRICE_SCALE, 0.0, 1.0)
        else:
            price_term = 0.0
        if rain_mean is not None:
            drought = round(clamp((NORMAL_RAIN - rain_mean) / DROUGHT_FLOOR, 0.0, 1.0), 4)
            drought_term = drought
        else:
            drought = None
            drought_term = 0.0

        hazard = W_PRICE * price_term + W_DROUGHT * drought_term
        agri_stress = round(hazard * crop_dependence, 4)

        # --- double-stress: softening rice/rubber prices AND elevated drought ---
        # rice_rubber_share = combined planting-area share of rice + rubber (the two
        # crops the 2026 research calls out as price-softening). Drawn from crop_mix,
        # which is already capped at TOP_CROPS, so this is the share among shown crops.
        rice_rubber_share = round(
            sum(c["share"] for c in crop_mix if c["crop"] in RICE_RUBBER), 4
        )
        drought_val = drought if drought is not None else 0.0
        # price_term > 0 means area-weighted price YoY is negative = softening prices.
        ds_price = price_term > 0.0
        ds_share = rice_rubber_share >= DS_SHARE_FLOOR
        ds_drought = drought_val >= DS_DROUGHT_FLOOR
        double_stress = bool(ds_price and ds_share and ds_drought)
        # double_stress_score: 0..1 severity of the overlap (only meaningful when the
        # boolean is true). Geometric-style mean of the two stress legs, gated on the
        # rice/rubber exposure so the score reflects "how much of the book is in the
        # crops that are double-stressed". Built only from existing terms.
        if double_stress:
            double_stress_score = round(price_term * drought_val * rice_rubber_share, 4)
        else:
            double_stress_score = 0.0

        records.append({
            "th": prov,
            "en": None,  # english province name not available in source-data (honest null)
            "region": prov_region.get(prov),
            "crop_mix": crop_mix,
            "price_stress": price_stress,
            "drought": drought,
            "crop_dependence": crop_dependence,
            "agri_stress": agri_stress,
            "double_stress": double_stress,
            "double_stress_score": double_stress_score,
            "components": {
                "total_crop_rai": int(round(total_rai)),
                "price_term": round(price_term, 4),
                "drought_term": round(drought_term, 4),
                "hazard": round(hazard, 4),
                "rain_pct_of_normal": rain_mean,
                "price_coverage": price_coverage,
                "n_branches": prov_nbranch.get(prov, 0),
                "n_rain_branches": len(rains),
                "rice_rubber_share": rice_rubber_share,
                "ds_price_softening": ds_price,
                "ds_share_qualifies": ds_share,
                "ds_drought_elevated": ds_drought,
            },
        })

    # sort worst-first by agri_stress (desc), tie-break by price_stress (more negative worse),
    # then province name for determinism
    records.sort(key=lambda r: (
        -r["agri_stress"],
        (r["price_stress"] if r["price_stress"] is not None else 0.0),
        r["th"],
    ))

    n_double = sum(1 for r in records if r["double_stress"])

    meta = {
        "title": "Per-province crop-household stress (portfolio risk, objective #1)",
        "generated_by": "pipeline/build_crop_stress.py",
        "deterministic": True,
        "network_free": True,
        "n_provinces": len(records),
        "n_double_stress": n_double,
        "sort": "worst-first by agri_stress (desc)",
        "fields": {
            "crop_mix": "MEASURED — dominant crops by planting-area share (rai), OAE.",
            "price_stress": "PROXY/ESTIMATED — planting-area-weighted price YoY %% across the "
                            "province's covered crops. Source = commodity_board (World Bank Pink "
                            "Sheet GLOBAL prices). This is a DIRECTION proxy, NOT Thai farm-gate.",
            "drought": "MEASURED PROXY — derived from branch rain_3mo_anom (3-month rainfall as %% "
                       "of normal). 0..1 where 1 = driest. See components.rain_pct_of_normal for "
                       "the underlying measured value.",
            "crop_dependence": "MEASURED — province total crop rai / max province crop rai (0..1).",
            "agri_stress": "ESTIMATED — composite, see meta.formula. Combines price + drought "
                           "hazard, scaled by crop_dependence. Index, not a measured outcome.",
            "double_stress": "ESTIMATED FLAG — true when a province is rice/rubber-heavy AND its "
                             "rice/rubber prices are softening AND its drought signal is elevated. "
                             "See meta.double_stress for the exact rule. A triage flag, not a "
                             "forecast.",
            "double_stress_score": "ESTIMATED — 0..1 severity of the overlap when the flag is true "
                                   "(0 when false). See meta.double_stress.",
        },
        "formula": {
            "price_term": "clamp(-price_stress / %g, 0, 1)" % PRICE_SCALE,
            "drought_term": "clamp((%g - rain_pct_of_normal) / %g, 0, 1)" % (NORMAL_RAIN, DROUGHT_FLOOR),
            "hazard": "%g*price_term + %g*drought_term" % (W_PRICE, W_DROUGHT),
            "agri_stress": "round(hazard * crop_dependence, 4)",
            "rationale": "Price weighted higher (0.6) — it hits cash-crop borrower income directly. "
                         "Hazard scaled by crop_dependence so a province is flagged a portfolio risk "
                         "only when borrowers there actually farm at scale.",
        },
        "double_stress": {
            "what": "ESTIMATED flag for provinces hit by the 2026 rice/rubber double-stress: "
                    "softening farm prices AND elevated drought, in places that grow rice/rubber.",
            "rule": "double_stress = (rice_rubber_share >= %g) AND (price_term > 0, i.e. rice/rubber "
                    "prices softening) AND (drought >= %g)." % (DS_SHARE_FLOOR, DS_DROUGHT_FLOOR),
            "score": "double_stress_score = price_term * drought * rice_rubber_share when the flag "
                     "is true, else 0. A 0..1 severity of the overlap, built only from existing terms.",
            "thresholds": {
                "rice_rubber_share_floor": DS_SHARE_FLOOR,
                "drought_floor": DS_DROUGHT_FLOOR,
            },
            "inputs": "Uses ONLY signals already computed here: crop_mix shares (rice+rubber), the "
                      "existing price_term (from the GLOBAL price proxy), and the existing drought "
                      "signal (measured rain_3mo_anom proxy). No new external numbers introduced.",
            "n_flagged": n_double,
            "source": "RESEARCH_DIGEST.md 2026-06-30 Entry 1 §C — OAE 2026 outlook (rice & rubber "
                      "softer) + El Niño drought >80% from mid-2026. INTERPRETATION (obj #1).",
            "caveat": "price_term is a GLOBAL-price direction proxy, and in the current vintage all "
                      "priced provinces show some rice/rubber softening, so drought is the effective "
                      "discriminator. Treat as a triage flag, not a default forecast.",
        },
        "coverage": {
            "crops_priced": [CROP_EN[c] for c in covered_crops],
            "board_crops_no_planting_area": uncovered_board_crops,
            "planting_area_crops_no_price": [CROP_EN.get(c, c) for c in uncovered_area_crops],
            "note": "price_stress only covers crops with BOTH planting area and a board price. "
                    "components.price_coverage = share of province crop rai that was priceable.",
            "unallocated_rai_excluded": int(round(skipped_area_rai)),
            "unallocated_note": "rai in crop_prov_area.json under a blank/non-portfolio province "
                                "key (not in the AutoX branch network) — excluded from all stats.",
        },
        "provenance": {
            "crop_prov_area.json": "OAE planting area (rai) per crop per province — MEASURED.",
            "commodity_board.json": "World Bank Pink Sheet GLOBAL commodity prices, YoY %% — "
                                    "PROXY for direction of Thai farm-gate, not farm-gate itself.",
            "branches_final.json": "rain_3mo_anom per branch — MEASURED rainfall anomaly proxy.",
        },
        "caveats": [
            "Global prices move with, but are not equal to, Thai farm-gate prices; treat "
            "price_stress as a direction signal only.",
            "Only rice / rubber / oil palm are both area-mapped and priced; sugar, maize and "
            "other crops in a province are shown in crop_mix but NOT in price_stress.",
            "drought uses each province's own branch network; provinces with few branches have a "
            "thinner rainfall sample (see components.n_rain_branches).",
            "agri_stress is an index for triage, not a forecast of defaults.",
        ],
    }

    return {"meta": meta, "provinces": records}


def dumps(obj):
    # deterministic: keep insertion key order (sort_keys=False), readable separators
    # matching meta.json convention (ensure_ascii=False, default ', '/': ' spacing).
    return json.dumps(obj, ensure_ascii=False, indent=2) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true",
                    help="re-run and byte-compare against the committed JSON; exit 1 on drift")
    args = ap.parse_args()

    data = build()
    text = dumps(data)

    if args.check:
        if not os.path.exists(OUT):
            print("CHECK FAIL: %s does not exist" % OUT)
            sys.exit(1)
        with open(OUT, encoding="utf-8") as f:
            existing = f.read()
        if existing == text:
            print("CHECK OK: %s reproduces byte-for-byte (%d provinces)" %
                  (OUT, data["meta"]["n_provinces"]))
            sys.exit(0)
        print("CHECK FAIL: %s differs from a fresh build" % OUT)
        sys.exit(1)

    with open(OUT, "w", encoding="utf-8") as f:
        f.write(text)
    print("wrote %s (%d provinces, worst-first)" % (OUT, data["meta"]["n_provinces"]))
    top = data["provinces"][:5]
    for r in top:
        print("  %-14s agri_stress=%.4f price=%s rain=%s dep=%.3f" % (
            r["th"], r["agri_stress"], r["price_stress"],
            r["components"]["rain_pct_of_normal"], r["crop_dependence"]))


if __name__ == "__main__":
    main()
