#!/usr/bin/env python3
"""
build_macro_exposure.py — MACRO FACTORS × CUSTOMER CLUSTER per branch (objective #1).

THE QUESTION THIS ANSWERS
-------------------------
"Which macro moves hit THIS branch's customer base — and which single factor dominates?"

A title loan is repaid out of the borrower's cash flow. Different customer clusters live
off different macro factors: rice farmers off the rice price and the rain, rubber tappers
off the rubber price, gold/pawn trade off the gold price, factory workers off the
manufacturing cycle, and *every* leveraged household off its debt-service burden. This
layer joins the MEASURED occupation mix of each branch's catchment (branch_occupations.json,
Overture Places) against the CURRENT measured macro signals (Pink Sheet price YoY, rainfall
drought proxy, NSO household DTI) through a documented occupation-bucket × macro-factor
SENSITIVITY MATRIX, and publishes each branch's top-3 macro exposures + the dominant factor.

MEASURED vs ESTIMATED (the data-mandate — stated explicitly, repeated in meta)
------------------------------------------------------------------------------
  MEASURED   occupation SHARES per branch (Overture Places, a sample/lower bound).
  MEASURED   crop price signals — Thai FARM-GATE YoY as PRIMARY (source-data/farmgate_prices.json,
             NABC) for rice/rubber/palm/cassava/maize/coconut/sugarcane/pineapple; the World Bank
             GLOBAL Pink Sheet (source-data/commodity_board.json) is fallback-only for a crop
             farm-gate does not price, and the base for gold + livestock (no farm-gate equivalent).
  MEASURED   province crop mix + drought proxy (crop_stress.json: OAE planting area,
             rain_3mo_anom % of normal).
  MEASURED   province household debt-to-income (NSO SES 2566 via household_risk_by_province.json);
             its 0-100 severity is that file's ESTIMATED percentile rank (stress_index).
  ESTIMATED  the SENSITIVITY WEIGHTS (bucket × factor, 0..1): editorial credit judgement,
             one-line rationale per nonzero cell, whole matrix embedded in meta for audit.
  ESTIMATED  the manufacturing-cycle signal level: editorial (Thai MPI/PMI softness), aligned
             with build_occupation_risk.py FACTORY_STRESS = 0.5. No measured industrial-cycle
             series exists in the offline sources — an honest gap, flagged in meta.
  The final per-branch scores are therefore ESTIMATED composites of measured inputs.

FORMULA (per branch, per factor — fully transparent)
----------------------------------------------------
  share[b]        = o[b] / t                          MEASURED occupation share, 0..1
  sens_eff(b,f)   = W[b][f] * scale(f, province)      ESTIMATED weight × MEASURED crop-mix /
                                                      crop-dependence scale where marked
  severity[f]     = 0..100 from the factor's CURRENT measured signal (see meta.factors)
  score[f]        = round( Σ_b share[b] · sens_eff(b,f) · severity[f] )   0..100
  direction[f]    = tailwind when the measured signal improves borrower income/collateral
                    (price YoY > 0), headwind otherwise. drought / leverage / manufacturing
                    are headwind-only levers.
Published per branch: top-3 factors [key, score, "h"|"t"], dominant factor key, plus a
compact top-level vector [factor_index, score] for map lenses. INDEX-ALIGNED to
platform/data/branches.json (entry i ↔ branch i).

PROVINCE-AWARENESS
------------------
Crop-price sensitivity is NOT flat: it scales by the branch province's MEASURED crop-mix
share (crop_stress.json — e.g. rice sensitivity is ~0 in a rubber province). Drought
passthrough to local trade scales by measured crop_dependence. Leverage severity is the
branch province's NSO DTI percentile. Bueng Kan has no crop_stress entry (OAE gap): crop
shares fall to 0 there and drought falls back to the branch's own measured rain field
(same clamp((100-rain)/40) formula crop_stress uses) — caveated in meta.

DETERMINISTIC + NETWORK-FREE + GRACEFUL ABSENT PATH
---------------------------------------------------
No network, no wall clock (vintages come from the data files themselves). Byte-exact
reproducible → carries --check (the QA gate runs it). branch_occupations.json is the
MEASURED anchor and may be absent in a fresh sandbox: build() then returns None, --check
skip-passes, a plain run exits non-zero with a clear message (mirrors build_occupation_risk.py).

Usage:
  python3 build_macro_exposure.py            # write platform/data/macro_exposure.json
  python3 build_macro_exposure.py --check    # verify byte-for-byte reproduce
"""
import argparse, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "platform", "data")
OCC = os.path.join(DATA, "branch_occupations.json")
BRANCHES = os.path.join(DATA, "branches.json")
CROP = os.path.join(DATA, "crop_stress.json")
HH = os.path.join(DATA, "household_risk_by_province.json")
BOARD = os.path.join(ROOT, "source-data", "commodity_board.json")
# MEASURED Thai FARM-GATE price layer — PRIMARY over the GLOBAL Pink Sheet for the crops it prices.
FARMGATE = os.path.join(ROOT, "source-data", "farmgate_prices.json")
META = os.path.join(DATA, "meta.json")
OUT = os.path.join(DATA, "macro_exposure.json")
sys.path.insert(0, HERE)
from lib.regionmap import canonical

# ── the macro-factor set (only what the offline data actually supports) ─
# Order is FIXED — it is the tie-break for the dominant factor and the index space of the
# compact vector. Keys are short on purpose (payload); labels live in meta. The crop factors are
# grouped at the front: the three Pink-Sheet-backed majors (rice/rubber/palm) then the five
# farm-gate-only crops that widen the read to the MEASURED headwind crops (coconut/sugarcane/
# pineapple — negative Thai farm-gate YoY — plus cassava/maize), each scaled by its own province
# planting-area share so it only ever bites where that crop is actually farmed.
FACTOR_ORDER = ("rice", "rubber", "palm", "cassava", "maize", "coconut", "sugarcane", "pineapple",
                "gold", "livestock", "drought", "leverage", "mfg")
# The crop factors, in the same fixed front-of-order. A crop scores only when it carries a price
# signal (farm-gate quote, else a Pink Sheet row for the three majors) AND the branch province has a
# measured planting-area share for it — otherwise the cell contributes nothing (graceful absence).
CROP_FACTORS = ("rice", "rubber", "palm", "cassava", "maize", "coconut", "sugarcane", "pineapple")
# crop factor -> crop_yoy key in farmgate_prices.json (Thai farm-gate MEASURED, PRIMARY base).
FARMGATE_KEY = {
    "rice": "rice", "rubber": "rubber", "palm": "oilpalm", "cassava": "cassava",
    "maize": "maize", "coconut": "coconut", "sugarcane": "sugarcane", "pineapple": "pineapple",
}
# crop factor -> crop_stress.json crop_mix crop name (the MEASURED province planting-area share).
CROP_NAME = {
    "rice": "Rice", "rubber": "Rubber", "palm": "Oil palm", "cassava": "Cassava",
    "maize": "Maize", "coconut": "Coconut", "sugarcane": "Sugarcane", "pineapple": "Pineapple",
}

# Pink Sheet YoY denominator: |yoy| of 25% == full severity 100. Same denominator
# build_crop_stress.py uses for its price_term (clamp(-price/25)) — kept consistent.
PRICE_SEV_DEN = 25.0

# ESTIMATED EDITORIAL national manufacturing-cycle stress level (0..1). Aligned with
# build_occupation_risk.py FACTORY_STRESS — Thai manufacturing PMI/MPI softness through
# 2025-26. Revise both together when a real industrial index is wired in.
MFG_STRESS = 0.5

# ── ESTIMATED sensitivity matrix: occupation bucket × factor weight in [0,1] ─
# Every nonzero cell carries a one-line rationale ("why") — the whole matrix is embedded
# in meta so the editorial judgement is auditable. "scale" marks cells whose effective
# weight is multiplied by a MEASURED province quantity:
#   rice_share / rubber_share / palm_share  — crop_stress.json crop_mix planting-area share
#   crop_dependence                          — crop_stress.json crop_dependence (0..1)
_PT = "farm-price passthrough: in crop provinces local trade cash flow follows farm income (scaled by the province's measured crop share)"
_AGRI_WHY = "farmers' income IS the crop price, weighted by the province's measured planting-area share for this crop"


# Expand a single per-bucket crop weight into one scaled cell per MEASURED crop factor, each scaled
# by THAT crop's own province planting share (`<crop>_share`). This applies the identical
# farm-price-passthrough credit judgement uniformly to every crop the farm-gate feed prices — it is
# the same editorial weight generalized, NOT a new per-crop judgement, so no crop is privileged and
# a headwind crop (coconut/sugarcane/pineapple) bites exactly where it is actually farmed.
def _crop_cells(w, why):
    return {c: {"w": w, "scale": "%s_share" % c, "why": why} for c in CROP_FACTORS}


MATRIX = {
    "factory": {
        "mfg":      {"w": 0.90, "why": "production jobs and overtime move directly with the manufacturing cycle"},
        "leverage": {"w": 0.25, "why": "wage borrowers with high household debt cut loan service first when hours are cut"},
    },
    "auto": {
        "mfg":      {"w": 0.35, "why": "vehicle trade and repair volume tracks the industrial/auto production cycle"},
        "leverage": {"w": 0.30, "why": "big-ticket vehicle purchases are the first spend leveraged households defer"},
    },
    "retail": {
        **_crop_cells(0.45, _PT),
        "drought":  {"w": 0.30, "scale": "crop_dependence", "why": "drought cuts farm cash that market vendors live off, where the province actually farms at scale"},
        "leverage": {"w": 0.35, "why": "informal vendor income falls when leveraged households squeeze daily spending"},
    },
    "food": {
        **_crop_cells(0.30, _PT),
        "drought":  {"w": 0.20, "scale": "crop_dependence", "why": "eating out is an early cut when farm cash dries up in crop-dependent provinces"},
        "leverage": {"w": 0.30, "why": "food service is discretionary spend — squeezed households eat out less"},
    },
    "hospitality": {
        "leverage": {"w": 0.25, "why": "domestic travel/leisure is discretionary; no measured tourism-arrivals signal is available offline (gap noted in meta)"},
    },
    "finance": {
        "gold":     {"w": 0.90, "why": "gold-shop/pawn trade turnover and gold-collateral values move directly with the gold price"},
        "leverage": {"w": 0.25, "why": "small-finance/pawn borrowers are the most debt-stressed customer cluster"},
    },
    "health": {
        "leverage": {"w": 0.10, "why": "healthcare is defensive and largely salaried — least income-cyclical, small debt-service link only"},
    },
    "education": {
        "leverage": {"w": 0.10, "why": "education is defensive and largely salaried — small debt-service link only"},
    },
    "public": {
        "leverage": {"w": 0.05, "why": "government pay is the most stable income in the book — minimal macro sensitivity"},
    },
    "professional": {
        "mfg":      {"w": 0.20, "why": "office/professional services partly bill the industrial sector"},
        "leverage": {"w": 0.15, "why": "salaried professionals carry debt but income is comparatively stable"},
    },
    "agriculture": {
        **_crop_cells(1.00, _AGRI_WHY),
        "livestock": {"w": 0.30, "why": "livestock (chicken/beef) income lever; kept low because the crop-vs-livestock split is NOT measured per province"},
        "drought":  {"w": 0.90, "why": "rainfall failure hits farm yield and farm cash flow directly"},
        "leverage": {"w": 0.25, "why": "farm households carry high seasonal input debt on top of consumer debt"},
    },
    "personal": {
        **_crop_cells(0.25, _PT),
        "leverage": {"w": 0.30, "why": "personal services (salons, repair, laundry) are the first spend cut by squeezed households"},
    },
    "logistics": {
        "mfg":      {"w": 0.50, "why": "freight and transport volume tracks the manufacturing cycle; NOTE no fuel-price series exists in the offline sources, so drivers' fuel sensitivity is NOT scored (honest gap)"},
        "leverage": {"w": 0.20, "why": "owner-drivers finance their vehicles — debt service competes with the title loan"},
    },
    "construction": {
        "mfg":      {"w": 0.30, "why": "industrial/estate construction demand follows the manufacturing capex cycle"},
        "leverage": {"w": 0.30, "why": "informal daily-wage construction income is cut first in a downturn while household debt persists"},
    },
}

# Pink Sheet board rows (source-data/commodity_board.json "lab") each factor reads.
_BOARD_LAB = {"rice": "Rice", "rubber": "Rubber", "palm": "Palm oil", "gold": "Gold"}
_LIVESTOCK_LABS = ("Chicken", "Beef")

FACTOR_LABELS = {
    "rice": "Rice price", "rubber": "Rubber price", "palm": "Palm-oil price",
    "cassava": "Cassava price", "maize": "Maize price", "coconut": "Coconut price",
    "sugarcane": "Sugarcane price", "pineapple": "Pineapple price",
    "gold": "Gold price", "livestock": "Livestock prices (chicken/beef)",
    "drought": "Drought / rainfall", "leverage": "Household leverage (DTI)",
    "mfg": "Manufacturing cycle",
}


def _load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def _clamp01(x):
    return 0.0 if x < 0 else (1.0 if x > 1 else x)


def _median(vals):
    s = sorted(vals)
    n = len(s)
    if n == 0:
        return None
    m = n // 2
    return s[m] if n % 2 else (s[m - 1] + s[m]) / 2.0


def build():
    if not os.path.exists(OCC):
        return None  # MEASURED anchor absent — caller decides (skip-pass on --check)
    occ = _load(OCC)
    bkeys = [b["key"] for b in occ["buckets"]]
    blabels = {b["key"]: b["label"] for b in occ["buckets"]}
    occ_recs = occ["branches"]
    branches = _load(BRANCHES)
    board = _load(BOARD)
    crop = _load(CROP)["provinces"]
    hh = _load(HH)["provinces"]
    app_meta = _load(META)

    # ── measured signals ─────────────────────────────────────────────────────
    by_lab = {r["lab"]: r for r in board}
    vintages = sorted({r.get("stale") for r in board if r.get("stale")})
    price_vintage = vintages[-1] if vintages else None

    # ── PREFER the dedicated MEASURED Thai FARM-GATE layer over the GLOBAL Pink Sheet proxy ──
    # farmgate_prices.json.crop_yoy carries daily national-average Thai farm-gate YoY for the raw
    # farm-commodity forms of these crops (paddy / raw rubber sheet / fresh palm bunch / cassava root
    # / cane / whole coconut / cannery pineapple / maize). CLAUDE.md's stated policy — and
    # build_crop_stress.py's price_stress + the sibling build_macro_sensitivity.py — treat farm-gate
    # as the PRIMARY price base and the World Bank GLOBAL Pink Sheet as fallback-only, for crops the
    # farm-gate feed does not price. This builder now follows the same policy so all three sibling
    # agri-risk reads share ONE price base. Absent file => the three majors fall back to the Pink
    # Sheet and the five farm-gate-only crops simply do not score (graceful absence).
    farmgate = _load(FARMGATE) if os.path.exists(FARMGATE) else None
    fg_yoy = ((farmgate or {}).get("crop_yoy") or {})
    fg_vintage = ((farmgate or {}).get("meta") or {}).get("vintage")

    # ── measured crop price signals (Thai farm-gate first, GLOBAL Pink Sheet fallback for majors) ──
    # A crop is a scored factor only when it carries a real signal here; a crop with neither a
    # farm-gate quote nor a Pink Sheet row is dropped and never referenced by the scoring loop.
    signals = {}
    for f in CROP_FACTORS:
        fg = fg_yoy.get(FARMGATE_KEY[f])
        if isinstance(fg, (int, float)):
            yoy = float(fg)
            signals[f] = {
                "yoy_pct": yoy,
                "vintage": fg_vintage,
                "basis": "farmgate",
                "source": "Thai farm-gate daily national average via source-data/farmgate_prices.json "
                          "crop_yoy['%s'] (NABC agriapi.nabc.go.th)" % FARMGATE_KEY[f],
                "provenance": "MEASURED — Thai FARM-GATE price YoY %, the price the farmer receives",
            }
        elif f in _BOARD_LAB:
            lab = _BOARD_LAB[f]
            row = by_lab[lab]
            yoy = float(row["yoy"])
            signals[f] = {
                "yoy_pct": yoy,
                "vintage": row.get("stale"),
                "basis": "global",
                "source": "World Bank Pink Sheet via source-data/commodity_board.json ('%s') — "
                          "fallback: this crop is absent from farmgate_prices.json" % lab,
                "provenance": "MEASURED — GLOBAL price YoY %, a direction proxy, NOT Thai farm-gate "
                              "(fallback base — no Thai farm-gate quote for this crop)",
                "note": row.get("note"),
            }
        # else: no farm-gate quote and no Pink Sheet row -> this crop is not a scored factor.
    # gold — no Thai farm-gate equivalent; stays on the World Bank Pink Sheet (collateral/pawn price).
    gold_row = by_lab[_BOARD_LAB["gold"]]
    signals["gold"] = {
        "yoy_pct": float(gold_row["yoy"]),
        "vintage": gold_row.get("stale"),
        "basis": "global",
        "source": "World Bank Pink Sheet via source-data/commodity_board.json ('Gold')",
        "provenance": "MEASURED — GLOBAL price YoY %, a direction proxy (no Thai farm-gate equivalent)",
        "note": gold_row.get("note"),
    }
    lv_rows = [by_lab[l] for l in _LIVESTOCK_LABS]
    lv_yoy = round(sum(float(r["yoy"]) for r in lv_rows) / len(lv_rows), 1)
    signals["livestock"] = {
        "yoy_pct": lv_yoy,
        "components": {r["lab"]: r["yoy"] for r in lv_rows},
        "vintage": price_vintage,
        "source": "World Bank Pink Sheet via source-data/commodity_board.json (mean of Chicken + Beef YoY)",
        "provenance": "MEASURED — GLOBAL price YoY %, a direction proxy, NOT Thai farm-gate",
    }

    # province lookups (Thai canonical name → measured quantities)
    prov = {}
    for p in crop:
        shares = {c["crop"]: c["share"] for c in p.get("crop_mix", [])}
        rec = {"%s_share" % f: shares.get(CROP_NAME[f], 0.0) for f in CROP_FACTORS}
        rec["crop_dependence"] = p.get("crop_dependence") or 0.0
        rec["drought"] = p.get("drought") or 0.0
        prov[canonical(p["th"])] = rec
    dti_sev = {}
    dti_val = {}
    for p in hh:
        k = canonical(p["province"])
        if p.get("stress_index") is not None:
            dti_sev[k] = float(p["stress_index"])
        if p.get("debt_to_income") is not None:
            dti_val[k] = float(p["debt_to_income"])

    signals["drought"] = {
        "per_province": True,
        "median_0to1": round(_median([v["drought"] for v in prov.values()]), 3),
        "vintage": app_meta.get("updated"),
        "source": "platform/data/crop_stress.json drought (branch rain_3mo_anom, % of normal); "
                  "fallback for uncovered provinces = branch's own rain field, clamp((100-rain)/40)",
        "provenance": "MEASURED PROXY — 3-month rainfall vs normal, per province",
    }
    signals["leverage"] = {
        "per_province": True,
        "median_dti": round(_median(list(dti_val.values())), 3),
        "max_dti": round(max(dti_val.values()), 3),
        "vintage": "NSO SES 2566 (2023 CE)",
        "source": "platform/data/household_risk_by_province.json (NSO SES household debt / annual income)",
        "provenance": "MEASURED DTI; severity = that file's ESTIMATED 0-100 percentile rank (stress_index)",
    }
    signals["mfg"] = {
        "level_0to1": MFG_STRESS,
        "vintage": None,
        "source": "editorial national level — aligned with pipeline/build_occupation_risk.py FACTORY_STRESS",
        "provenance": "ESTIMATED EDITORIAL — Thai manufacturing PMI/MPI softness; NO measured "
                      "industrial-cycle series exists in the offline sources (honest gap)",
    }

    # national severity + direction per factor (price factors; province factors resolve per branch).
    # Only crop factors that actually carry a price signal (farm-gate or Pink Sheet fallback) score —
    # a crop absent from `signals` is skipped here and guarded out of the per-branch loop below.
    active_crops = [f for f in CROP_FACTORS if f in signals]
    nat_sev = {}
    direction = {}
    for f in active_crops + ["gold", "livestock"]:
        yoy = signals[f]["yoy_pct"]
        nat_sev[f] = round(_clamp01(abs(yoy) / PRICE_SEV_DEN) * 100, 1)
        direction[f] = "tailwind" if yoy > 0 else "headwind"
    nat_sev["mfg"] = round(MFG_STRESS * 100, 1)
    direction["drought"] = direction["leverage"] = direction["mfg"] = "headwind"
    dir_code = {"headwind": "h", "tailwind": "t"}

    # ── per-branch scores ────────────────────────────────────────────────────
    out_branches = []
    vector = []
    dom_tally = {}
    n_fallback_rain = 0
    for i, br in enumerate(branches):
        rec = occ_recs[i]
        t = rec.get("t") or 0
        o = rec.get("o") or []
        pv = canonical(br.get("v") or "")
        pp = prov.get(pv)
        if pp is None:
            # province not in crop_stress (Bueng Kan / OAE gap): crop shares 0,
            # drought from the branch's own measured rain field (same formula).
            rain = br.get("rain")
            dr = _clamp01((100.0 - rain) / 40.0) if isinstance(rain, (int, float)) else 0.0
            pp = {"%s_share" % f: 0.0 for f in CROP_FACTORS}
            pp["crop_dependence"] = 0.0
            pp["drought"] = dr
            n_fallback_rain += 1
        sev = dict(nat_sev)
        sev["drought"] = round(pp["drought"] * 100, 1)
        sev["leverage"] = dti_sev.get(pv, 0.0)

        scores = {}
        if t > 0:
            for bi, bk in enumerate(bkeys):
                share = o[bi] / t
                if share <= 0:
                    continue
                for f, cell in MATRIX.get(bk, {}).items():
                    if f not in sev:
                        continue  # crop factor with no price signal this vintage — never scored
                    w = cell["w"]
                    sc = cell.get("scale")
                    if sc:
                        w *= pp[sc]
                    if w <= 0:
                        continue
                    scores[f] = scores.get(f, 0.0) + share * w * sev[f]

        ranked = sorted(scores.items(), key=lambda kv: (-kv[1], FACTOR_ORDER.index(kv[0])))
        t3 = [[f, min(100, round(s)), dir_code[direction[f]]]
              for f, s in ranked[:3] if round(s) >= 1]
        if t3:
            d = t3[0][0]
            dom_tally[d] = dom_tally.get(d, 0) + 1
            vector.append([FACTOR_ORDER.index(d), t3[0][1]])
        else:
            d = None
            vector.append([-1, 0])
        out_branches.append({"t3": t3, "d": d})

    factors = []
    for f in FACTOR_ORDER:
        if f not in signals:
            continue  # crop factor with no price signal this vintage — omitted (never scored)
        factors.append({
            "key": f,
            "label": FACTOR_LABELS[f],
            "signal": signals[f],
            "severity": nat_sev.get(f, "per-province"),
            "direction": direction[f],
        })

    meta = {
        "title": "Macro-factor exposure per customer cluster per branch (portfolio risk, objective #1)",
        "generated_by": "pipeline/build_macro_exposure.py",
        "deterministic": True,
        "network_free": True,
        "label": "ESTIMATED COMPOSITE — MEASURED occupation shares × ESTIMATED sensitivity weights × "
                 "MEASURED macro signals (prices/DTI/drought; manufacturing level is ESTIMATED editorial). "
                 "A triage ranking of which macro moves hit each branch's customer base — NOT a measured "
                 "default rate.",
        "provenance": {
            "occupation_shares": "MEASURED — Overture Maps Places establishment mix ≤10km "
                                 "(platform/data/branch_occupations.json; a sample/lower bound, not a registry)",
            "price_signals": "MEASURED — Thai FARM-GATE crop price YoY as PRIMARY (source-data/"
                             "farmgate_prices.json crop_yoy, NABC, vintage %s) for rice/rubber/palm plus the "
                             "widened set cassava/maize/coconut/sugarcane/pineapple; World Bank GLOBAL Pink "
                             "Sheet (source-data/commodity_board.json, vintage %s) is fallback-only for a crop "
                             "farm-gate does not price, and the base for gold and livestock. Each factor's "
                             "signal.basis is 'farmgate' | 'global'." % (fg_vintage, price_vintage),
            "drought_signal": "MEASURED PROXY — 3-month rainfall vs normal per province (crop_stress.json)",
            "leverage_signal": "MEASURED — NSO SES 2566 household debt-to-income per province; severity is "
                               "its ESTIMATED percentile rank (household_risk_by_province.json stress_index)",
            "mfg_signal": "ESTIMATED EDITORIAL — national level %.2f, aligned with build_occupation_risk.py "
                          "FACTORY_STRESS; no measured industrial-cycle series offline" % MFG_STRESS,
            "sensitivity_weights": "ESTIMATED EDITORIAL — bucket × factor weights in [0,1], one-line "
                                   "rationale per nonzero cell (meta.matrix); credit judgement, not data",
            "crop_mix_scaling": "MEASURED — province planting-area shares + crop_dependence from "
                                "crop_stress.json (OAE) scale the crop/drought cells marked 'scale'",
        },
        "vintages": {
            "farmgate_prices": fg_vintage,
            "pink_sheet_prices": price_vintage,
            "drought": app_meta.get("updated"),
            "household_dti": "NSO SES 2566 (2023 CE)",
        },
        "index_note": "branches[] and vector[] are INDEX-ALIGNED to platform/data/branches.json "
                      "(entry i ↔ branch i). Never sort/filter without carrying the index.",
        "formula": "score[f] = round( Σ_buckets occ_share × weight × province_scale × severity[f] ), 0..100; "
                   "severity: price = min(|yoy|/%.0f,1)×100 national; drought = province drought×100; "
                   "leverage = province DTI percentile; mfg = %.0f national (editorial)."
                   % (PRICE_SEV_DEN, MFG_STRESS * 100),
        "direction_rule": "tailwind when the measured price YoY > 0 (borrower income/collateral improves), "
                          "headwind otherwise; drought/leverage/mfg are headwind-only. Encoded 'h'/'t' in t3.",
        "score_scale": "0-100 is a validity BOUND, not the working range: occupation shares sum to 1 "
                       "across 14 buckets, so one factor only captures the slice of the catchment it "
                       "touches — scores typically land 0-25. Compare branches RELATIVELY; do not read "
                       "the score as a percentage of anything.",
        "factor_keys": list(FACTOR_ORDER),
        "factors": factors,
        "buckets": [{"key": k, "label": blabels[k]} for k in bkeys],
        "matrix": MATRIX,
        "branch_fields": {
            "t3": "top-3 macro exposures [factor_key, score 0-100, direction 'h'|'t'], score desc; "
                  "factors scoring <1 are dropped",
            "d": "dominant factor key (t3[0][0]); null when no factor scores ≥1",
        },
        "vector_note": "vector[i] = [dominant factor index into meta.factor_keys, its score]; [-1,0] when none — "
                       "a compact per-branch read for map lenses",
        "gaps": [
            "no fuel/energy price series offline — drivers'/logistics' fuel sensitivity NOT scored",
            "no tourism-arrivals signal — hospitality carries only the leverage lever",
            "livestock vs crop farmer split not measured per province — livestock weight kept low (0.30) and national",
            "Bueng Kan absent from crop_stress (OAE gap): crop shares 0 there; drought falls back to the "
            "branch's own measured rain field (%d branches)" % n_fallback_rain,
        ],
        "n_branches": len(out_branches),
        "dominant_tally": {f: dom_tally[f] for f in FACTOR_ORDER if f in dom_tally},
    }
    return {"meta": meta, "branches": out_branches, "vector": vector}


def run(check=False):
    obj = build()
    if obj is None:
        if check:
            print("SKIP: branch_occupations.json absent — macro_exposure not checkable (optional layer)")
            return 0
        print("branch_occupations.json is absent — run build_occupations.py first "
              "(needs the Overture Places pull).")
        return 1
    text = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    if check:
        if not os.path.exists(OUT) or open(OUT, encoding="utf-8").read() != text:
            print("DRIFT: %s" % os.path.relpath(OUT, ROOT))
            return 1
        print("OK: macro_exposure.json reproduces (%d branches)" % obj["meta"]["n_branches"])
        return 0
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(text)
    m = obj["meta"]
    print("wrote %d branches -> platform/data/macro_exposure.json (%.0f KB)"
          % (m["n_branches"], len(text.encode("utf-8")) / 1024))
    print("  dominant-factor tally: %s" % m["dominant_tally"])
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="macro-factor exposure per customer cluster per branch")
    ap.add_argument("--check", action="store_true")
    raise SystemExit(run(check=ap.parse_args().check))
