#!/usr/bin/env python3
"""
build_crop_stress.py — PORTFOLIO RISK (objective #1): per-province crop-household stress.

Network-free, deterministic. Joins three LOCAL source-data files:
  - crop_prov_area.json    planting area (rai) per crop -> {province_th: area}
  - commodity_board.json   price board rows (crop label + YoY %); GLOBAL price direction proxy
  - branches_final.json    per-branch rain_3mo_anom (drought proxy) + prov/region

PLUS one OPTIONAL measured upgrade (docs/DATA_ACQUISITION_PLAN.md P3):
  - oae_farmgate_prices.json  MEASURED Thai farm-gate YoY per crop, landed by
    pipeline/pull_oae_prices.py. When present AND current-vintage, its per-crop
    YoY REPLACES the World Bank GLOBAL proxy for matching crops and the labels
    flip to MEASURED-OAE for those crops (meta.price_sources says which). When
    ABSENT (or stale — the BE-2562 crop_prices.json lesson), the output is
    BYTE-IDENTICAL to the proxy-only build, so `--check` stays green either way.

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
    "maize": "Maize",   # board carries Maize (GLOBAL proxy); NABC live overrides where present
}
# crop key in crop_prov_area.json -> commodity key in oae_farmgate_prices.json
# (only crops with planting area can be area-weighted; the OAE landing file may
# also carry sugarcane/cassava/maize, unusable here until area data lands)
CROP_TO_OAE = {
    "rice": "rice",
    "rubber": "rubber",
    "oilpalm": "oilpalm",
}
OAE_FILE = "oae_farmgate_prices.json"
# crop key in crop_prov_area.json -> crop key in nabc_prices.json crop_yoy (LIVE Thai daily prices,
# agriapi.nabc.go.th — cloud-refreshable, PREFERRED over the OAE snapshot and the GLOBAL proxy).
CROP_TO_NABC = {
    "rice": "rice",
    "rubber": "rubber",
    "oilpalm": "oilpalm",
    "cassava": "cassava",   # MEASURED live NABC daily; area folded in from DOAE (see DOAE_FILE)
    "maize": "maize",       # MEASURED live NABC daily; area folded in from DOAE (see DOAE_FILE)
}
NABC_FILE = "nabc_prices.json"
# crop key in crop_prov_area.json -> crop key in farmgate_prices.json crop_yoy. This is the roadmap's
# di-farmgate deliverable: the dedicated MEASURED Thai FARM-GATE price layer (raw farm-commodity daily
# national averages), built by pipeline/build_farmgate_prices.py from the reachable NABC feed. It is
# the TOP-preference measured source — preferred over the NABC snapshot, the OAE snapshot, and the
# World Bank GLOBAL proxy (which remains the graceful fallback when this layer is absent).
CROP_TO_FARMGATE = {
    "rice": "rice",
    "rubber": "rubber",
    "oilpalm": "oilpalm",
    # Added 2026-08-01 alongside their area. These three are the board's three steepest FALLING
    # measured Thai prices, so before this the area-weighted price_stress could only ever be
    # dragged UP: every crop it could see was rising. cassava/maize keep coming through
    # CROP_TO_NABC below, which resolves to the same measured feed.
    "coconut": "coconut",
    "pineapple": "pineapple",
    "sugarcane": "sugarcane",
}
FARMGATE_FILE = "farmgate_prices.json"
# staleness guard: the OAE vintage may lag the commodity board's own vintage by
# at most this many months, else the file is treated as absent (the crop_prices
# BE-2562 lesson: a measured-but-7-years-stale series is WORSE than the proxy).
OAE_MAX_LAG_MONTHS = 12
# cassava + maize planting area is ABSENT from crop_prov_area.json (OAE carries rice/rubber/oilpalm
# only) but present, MEASURED, in the DOAE farmer registry (doae_planted_area.json, in HECTARES). Fold
# it in so the two dominant upland borrower crops enter both the area-weighted price signal and the
# crop_mix display, priced by the same live NABC daily feed already trusted for rice/rubber/oilpalm.
# Absent file => cassava/maize simply do not load and the output degrades to the prior 3-crop build.
DOAE_FILE = "doae_planted_area.json"
# Coconut and pineapple joined 2026-08-01, when ingest_doae.py started reading all 19 registry crops
# instead of 5. Their area was in the same webservice response all along.
DOAE_AREA_CROPS = ("cassava", "maize", "coconut", "pineapple")
HA_TO_RAI = 6.25                          # DOAE hectares -> rai (crop_prov_area.json is in rai)

# Sugarcane is in NEITHER crop_prov_area.json NOR the DOAE registry — cane growers register with
# OCSB, which is the register of record for the crop. Folded in from its own measured layer so the
# largest crop belt in the country (11.4m rai across 47 provinces) stops being invisible to
# price_stress. Absent file => sugarcane simply does not load, same graceful degrade as DOAE.
OCSB_FILE = "ocsb_cane.json"
OCSB_AREA_CROPS = ("sugarcane",)
# human-readable crop labels (en) for the UI
CROP_EN = {"rice": "Rice", "rubber": "Rubber", "oilpalm": "Oil palm",
           "cassava": "Cassava", "maize": "Maize", "coconut": "Coconut",
           "pineapple": "Pineapple", "sugarcane": "Sugarcane"}

# normalization constants (see FORMULA in module docstring)
PRICE_SCALE = 25.0      # % YoY drop that maps price_term to 1.0
DROUGHT_FLOOR = 40.0    # rainfall shortfall (pp below normal) that maps drought_term to 1.0
NORMAL_RAIN = 100.0     # rain_3mo_anom value meaning "normal" precipitation
W_PRICE = 0.6
W_DROUGHT = 0.4

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


def _months(y, m):
    return int(y) * 12 + int(m)


def _board_vintage_months(board):
    """Newest 'stale' vintage on the board ('2025M12' -> months since year 0)."""
    best = None
    for row in board:
        m = None
        s = str(row.get("stale") or "")
        parts = s.split("M")
        if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
            m = _months(parts[0], parts[1])
        if m is not None and (best is None or m > best):
            best = m
    return best


def load_oae(board):
    """Load the OPTIONAL measured OAE farm-gate file (pull_oae_prices.py).

    Returns the parsed doc, or None when the file is absent, malformed, or
    STALE (more than OAE_MAX_LAG_MONTHS behind the commodity board's own
    vintage — deterministic: compared against an input, never the wall clock).
    None => build proceeds exactly as before, byte-identical output.
    """
    path = os.path.join(SRC, OAE_FILE)
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
        vc = doc["meta"]["vintage_ce"]
        oae_m = _months(vc["year"], vc["month"] or 12)
    except (KeyError, TypeError, ValueError) as e:
        print("WARNING: %s present but unreadable (%s) — falling back to the "
              "GLOBAL proxy for all crops" % (OAE_FILE, e), file=sys.stderr)
        return None
    board_m = _board_vintage_months(board)
    if board_m is not None and oae_m < board_m - OAE_MAX_LAG_MONTHS:
        print("WARNING: %s vintage %s lags the commodity board by >%d months — "
              "treating as absent (stale-file guard; the BE-2562 lesson)"
              % (OAE_FILE, doc["meta"].get("vintage"), OAE_MAX_LAG_MONTHS),
              file=sys.stderr)
        return None
    return doc


def load_doae_area():
    """OPTIONAL MEASURED cassava/maize planting area from the DOAE farmer registry.

    Returns {crop: {prov_th: rai}} for DOAE_AREA_CROPS (hectares -> rai, rounded to
    whole rai to match the crop_prov_area.json integer-rai convention), or {} when the
    file is absent/malformed. Absent => cassava/maize don't load and the build degrades
    to the prior rice/rubber/oilpalm shape (byte-identical to the pre-DOAE output).
    """
    path = os.path.join(SRC, DOAE_FILE)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            provs = json.load(f)["provinces"]
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as e:
        print("WARNING: %s present but unreadable (%s) — cassava/maize area not folded in"
              % (DOAE_FILE, e), file=sys.stderr)
        return {}
    out = {c: {} for c in DOAE_AREA_CROPS}
    for prov, crops in provs.items():
        if not isinstance(crops, dict):
            continue
        for c in DOAE_AREA_CROPS:
            ha = crops.get(c)
            if isinstance(ha, (int, float)) and ha > 0:
                out[c][prov] = int(round(ha * HA_TO_RAI))
    return {c: m for c, m in out.items() if m}


def load_ocsb_area():
    """MEASURED sugarcane area per province from OCSB (already rai — no ha conversion).

    Same contract as load_doae_area(): {crop: {prov_th: rai}}, or {} when the file is absent or
    malformed, so the build degrades to the prior shape instead of failing.
    """
    path = os.path.join(SRC, OCSB_FILE)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            provs = json.load(f)["provinces"]
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as e:
        print("WARNING: %s present but unreadable (%s) — sugarcane area not folded in"
              % (OCSB_FILE, e), file=sys.stderr)
        return {}
    out = {}
    for prov, rec in provs.items():
        rai = (rec or {}).get("area_rai")
        if isinstance(rai, (int, float)) and rai > 0:
            out.setdefault("sugarcane", {})[prov] = int(round(rai))
    return out


def build():
    crop_area = load("crop_prov_area.json")   # {crop: {prov_th: rai}} — OAE rice/rubber/oilpalm
    # fold in MEASURED cassava/maize area (DOAE farmer registry, hectares -> rai). Only crops NOT
    # already present are added, so the OAE rice/rubber/oilpalm area is never overwritten.
    doae_area = load_doae_area()
    doae_area_crops = []
    for c, m in doae_area.items():
        if c not in crop_area:
            crop_area[c] = m
            doae_area_crops.append(c)
    # ...then sugarcane from OCSB, on the same never-overwrite rule.
    ocsb_area_crops = []
    for c, m in load_ocsb_area().items():
        if c not in crop_area:
            crop_area[c] = m
            ocsb_area_crops.append(c)
    board = load("commodity_board.json")       # list of rows
    branches = load("branches_final.json")     # list of branch dicts

    # --- board lookup: crop key -> yoy % (only crops we have planting area for) ---
    board_by_label = {row["lab"]: row for row in board}
    crop_yoy = {}
    crop_src = {}   # crop key -> "board" (GLOBAL proxy) | "oae" (MEASURED Thai)
    for ckey, blabel in CROP_TO_BOARD.items():
        if blabel in board_by_label:
            crop_yoy[ckey] = float(board_by_label[blabel]["yoy"])
            crop_src[ckey] = "board"

    # --- PREFER measured Thai farm-gate YoY (OAE) where the file is present ---
    # Absent/stale file => oae is None and NOTHING below changes: the output
    # stays byte-identical to the proxy-only build (--check green either way).
    oae = load_oae(board)
    oae_used = []
    if oae is not None:
        oae_comm = oae.get("commodities") or {}
        for ckey in sorted(CROP_TO_OAE):
            entry = oae_comm.get(CROP_TO_OAE[ckey])
            if entry and entry.get("yoy") is not None:
                crop_yoy[ckey] = float(entry["yoy"])
                crop_src[ckey] = "oae"
                oae_used.append(ckey)
        if not oae_used:
            oae = None  # file matched no priceable crop — behave as absent

    # --- PREFER LIVE NABC daily Thai prices (agriapi.nabc.go.th) over OAE snapshot + GLOBAL proxy ---
    # Same live feed build_branch_agri.py prefers, so both agri surfaces read consistent measured Thai
    # prices. Absent file => no change (output stays byte-identical; --check green either way).
    nabc_used = []
    nabc = load(NABC_FILE) if os.path.exists(os.path.join(SRC, NABC_FILE)) else None
    if nabc is not None:
        nabc_yoy = nabc.get("crop_yoy") or {}
        for ckey in sorted(CROP_TO_NABC):
            val = nabc_yoy.get(CROP_TO_NABC[ckey])
            if isinstance(val, (int, float)):
                crop_yoy[ckey] = float(val)
                crop_src[ckey] = "nabc"
                nabc_used.append(ckey)

    # --- PREFER the dedicated MEASURED Thai FARM-GATE layer (di-farmgate) over everything above ---
    # source-data/farmgate_prices.json (pipeline/build_farmgate_prices.py). This is the roadmap's
    # measured farm-gate deliverable: it consolidates the reachable NABC raw-farm-commodity daily
    # national-average prices into one explicitly-named farm-gate layer, and REPLACES the World Bank
    # GLOBAL proxy for matching crops. Absent file => no change (output byte-identical; --check green).
    farmgate_used = []
    farmgate = load(FARMGATE_FILE) if os.path.exists(os.path.join(SRC, FARMGATE_FILE)) else None
    if farmgate is not None:
        fg_yoy = farmgate.get("crop_yoy") or {}
        for ckey in sorted(CROP_TO_FARMGATE):
            val = fg_yoy.get(CROP_TO_FARMGATE[ckey])
            if isinstance(val, (int, float)):
                crop_yoy[ckey] = float(val)
                crop_src[ckey] = "farmgate"
                farmgate_used.append(ckey)

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

        # crop_mix: ALL crops we have planting area for, by descending area share. Listing the full
        # mix (not a top-N slice) keeps the shares summing to 1.0 now that up to 5 crops are mapped
        # (rice/rubber/oil palm/cassava/maize); the app reads crop_mix[0]/[1] (dominant + runner-up).
        mix_sorted = sorted(mix_raw.items(), key=lambda kv: (-kv[1], kv[0]))
        crop_mix = []
        for ckey, rai in mix_sorted:
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
        # which now lists the full mix, so this is the true rice+rubber share of province area.
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
            "crop_mix": "MEASURED — dominant crops by planting-area share (rai): rice/rubber/oil "
                        "palm from OAE (crop_prov_area.json), cassava/maize from the DOAE 2568 "
                        "farmer registry (doae_planted_area.json, hectares -> rai).",
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
            "crop_prov_area.json": "OAE planting area (rai) per crop per province — MEASURED "
                                   "(rice / rubber / oil palm).",
            "commodity_board.json": "World Bank Pink Sheet GLOBAL commodity prices, YoY %% — "
                                    "PROXY for direction of Thai farm-gate, not farm-gate itself.",
            "branches_final.json": "rain_3mo_anom per branch — MEASURED rainfall anomaly proxy.",
        },
        "caveats": [
            "Global prices move with, but are not equal to, Thai farm-gate prices; treat "
            "price_stress as a direction signal only.",
            "rice / rubber / oil palm / cassava / maize are area-mapped and priced; sugar and "
            "other crops in a province are shown in crop_mix but NOT in price_stress.",
            "planting area is MIXED-SOURCE: rice/rubber/oil palm from OAE (crop_prov_area.json), "
            "cassava/maize from the DOAE 2568 farmer registry (doae_planted_area.json). Both are "
            "MEASURED but differ slightly in vintage/definition, so cross-crop area weights carry "
            "a small source-consistency caveat.",
            "drought uses each province's own branch network; provinces with few branches have a "
            "thinner rainfall sample (see components.n_rain_branches).",
            "agri_stress is an index for triage, not a forecast of defaults.",
        ],
    }
    if doae_area_crops:
        meta["provenance"]["doae_planted_area.json"] = (
            "MEASURED DOAE farmer-registry planted area (BE 2568, hectares -> rai) — folded in for "
            "%s, the dominant upland borrower crops absent from the OAE crop_prov_area.json "
            "(rice/rubber/oil palm only). Priced by the live NABC daily feed." %
            ", ".join(CROP_EN.get(c, c) for c in doae_area_crops))
    if ocsb_area_crops:
        meta["provenance"][OCSB_FILE] = (
            "MEASURED OCSB cane area (production year 2565/66, rai) — folded in for %s. Cane is in "
            "neither the OAE planted-area census nor the DOAE farmer registry, because growers "
            "register with OCSB; this is the register of record. Priced by the ANNOUNCED national "
            "cane price (administered per season, ~10 CCS), not a market quote." %
            ", ".join(CROP_EN.get(c, c) for c in ocsb_area_crops))

    # --- MEASURED relabel: when a measured price source (NABC live or OAE farm-gate) was used ---
    # Every mutation of meta lives inside this guard so the all-proxy output stays byte-identical to
    # the historical proxy-only build. Preference: NABC live Thai daily > OAE farm-gate > GLOBAL proxy.
    if oae is not None or nabc_used or farmgate_used:
        om = oae.get("meta", {}) if oae is not None else {}
        oae_vintage = om.get("vintage")
        fgm = farmgate.get("meta", {}) if farmgate is not None else {}
        fg_vintage = fgm.get("vintage")

        _MEASURED_SRC = ("farmgate", "nabc", "oae")  # every non-proxy (MEASURED Thai) source

        def _src_label(c):
            s = crop_src.get(c)
            if s == "farmgate":
                return ("MEASURED-farmgate — Thai daily national-average price for the raw farm "
                        "commodity (farm-gate layer, NABC agriapi.nabc.go.th; vintage %s)" % fg_vintage)
            if s == "nabc":
                return "MEASURED-NABC — Thai live daily market YoY % (agriapi.nabc.go.th)"
            if s == "oae":
                return "MEASURED-OAE — Thai farm-gate YoY %% (vintage %s)" % oae_vintage
            return "PROXY — World Bank Pink Sheet GLOBAL YoY %% (direction only)"

        meta["fields"]["price_stress"] = (
            "MIXED — planting-area-weighted price YoY % across the province's covered crops. "
            "Per-crop source in meta.price_sources: the MEASURED Thai FARM-GATE layer "
            "(farmgate_prices.json) preferred, then LIVE NABC Thai daily prices, then MEASURED-OAE "
            "Thai farm-gate, else the World Bank GLOBAL proxy (direction only).")
        meta["price_sources"] = {CROP_EN.get(c, c): _src_label(c) for c in covered_crops}
        if farmgate_used:
            meta["provenance"]["farmgate_prices.json"] = (
                "MEASURED Thai farm-gate price layer (di-farmgate), built by "
                "pipeline/build_farmgate_prices.py from the NABC daily national-average feed "
                "(agriapi.nabc.go.th, reachable from a Thai IP / cloud). Replaces the World Bank "
                "GLOBAL proxy for: %s. vintage %s." % (
                    ", ".join(CROP_EN.get(c, c) for c in farmgate_used), fg_vintage))
        if nabc_used:
            meta["provenance"]["nabc_prices.json"] = (
                "NABC live daily market prices (agriapi.nabc.go.th), pulled by "
                "pipeline/pull_nabc_prices.py — MEASURED, cloud-refreshable. Crops: %s." %
                ", ".join(CROP_EN.get(c, c) for c in nabc_used))
        if oae is not None:
            meta["provenance"]["oae_farmgate_prices.json"] = (
                "OAE farm-gate prices (ราคาที่เกษตรกรขายได้), pulled by "
                "pipeline/pull_oae_prices.py — MEASURED. vintage %s, dataset %s." % (
                    oae_vintage, om.get("dataset_id")))
        measured_en = [CROP_EN.get(c, c) for c in covered_crops if crop_src.get(c) in _MEASURED_SRC]
        meta["caveats"][0] = (
            "Price sources are MIXED per crop (see meta.price_sources): %s use MEASURED Thai YoY "
            "(farm-gate layer / NABC live / OAE farm-gate); any other priced crop still uses the "
            "GLOBAL World Bank proxy (direction signal only)." % ", ".join(measured_en))
        if crop_src.get("rice") in _MEASURED_SRC and crop_src.get("rubber") in _MEASURED_SRC:
            meta["double_stress"]["caveat"] = (
                "price_term for rice/rubber now uses MEASURED Thai YoY (farm-gate layer / NABC live / "
                "OAE farm-gate), not the GLOBAL proxy. Still treat the flag as a triage flag, not a "
                "forecast.")

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
        # newline="" on the READ as well as the write, so this compares what is ACTUALLY in the
        # file. Without it, Python's universal-newline translation turns CRLF back into \n on the
        # way in and --check passes on Windows over bytes that are not the bytes on disk.
        #
        # git normalises to LF on commit, so the committed blob was never wrong — the damage is
        # local and quieter than that: build_provenance.py records os.path.getsize(), so running it
        # on a Windows working copy censuses the INFLATED CRLF sizes and writes a provenance file
        # that then fails --check on CI. That is the whole reason provenance has to be regenerated
        # through the WSL LF mirror. Writing LF here removes one more reason to need it.
        with open(OUT, encoding="utf-8", newline="") as f:
            existing = f.read()
        if existing == text:
            print("CHECK OK: %s reproduces byte-for-byte (%d provinces)" %
                  (OUT, data["meta"]["n_provinces"]))
            sys.exit(0)
        print("CHECK FAIL: %s differs from a fresh build" % OUT)
        sys.exit(1)

    # newline="" keeps the file LF on every platform — see the --check comment above.
    with open(OUT, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    print("wrote %s (%d provinces, worst-first)" % (OUT, data["meta"]["n_provinces"]))
    top = data["provinces"][:5]
    for r in top:
        print("  %-14s agri_stress=%.4f price=%s rain=%s dep=%.3f" % (
            r["th"], r["agri_stress"], r["price_stress"],
            r["components"]["rain_pct_of_normal"], r["crop_dependence"]))


if __name__ == "__main__":
    main()
