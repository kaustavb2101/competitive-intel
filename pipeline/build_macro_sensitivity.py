#!/usr/bin/env python3
"""
build_macro_sensitivity.py — WHAT MOVES THIS BRANCH (objective #1, portfolio risk).

THE QUESTION THIS ANSWERS
-------------------------
"For THIS branch, which two macro moves matter most right now — and in which direction?"
e.g.  Rubber price +32.4% YoY × 13% of province crop area × agri catchment score 41.

It is deliberately SIMPLER than build_macro_exposure.py (which models occupation-bucket
sensitivity from the Overture Places sample). This layer joins only three ALWAYS-PRESENT
committed inputs, so it covers all 2,015 branches with no optional-anchor skip path:

  platform/data/branches.json      per-branch segment context: agri-PD score `a`,
                                   collateral score `c` (both ESTIMATED 0-100), measured
                                   OSM gold shops ≤10km (k10.gold), measured rain % of
                                   normal (`rain`), province `v`.
  platform/data/crop_stress.json   per-province MEASURED components: OAE crop-mix
                                   planting-area shares, crop_dependence, drought (0..1
                                   from measured rain_3mo_anom), rain_pct_of_normal.
  source-data/commodity_board.json REAL World Bank Pink Sheet price YoY (Rice, Rubber,
                                   Palm oil, Gold) — GLOBAL direction proxy, NOT Thai
                                   farm-gate.

MEASURED vs ESTIMATED (stated in meta + repeated in the UI chip)
----------------------------------------------------------------
  MEASURED   price YoY signals (Pink Sheet, global proxy), province crop-mix shares +
             crop_dependence (OAE planting area), drought / rain % of normal (rainfall),
             gold shops ≤10km (OSM count).
  ESTIMATED  the branch relevance weights: segment scores `a` / `c` are themselves
             estimated 0-100 screens, and the driver formula that combines signal ×
             relevance is editorial credit judgement.
  → every published score/rank is an ESTIMATED PROXY OVER MEASURED INPUTS. It ranks
    which macro lever moves a branch's book; it is NOT a measured elasticity or PD.

THE 5 DRIVERS (fixed order = tie-break + audit order)
-----------------------------------------------------
  rice / rubber / palm   crop price × province crop share × branch agri catchment
  gold                   gold price × branch collateral score × measured gold-shop presence
  drought                rainfall deficit × branch agri catchment × province crop dependence

FORMULA (per branch, per driver — fully transparent)
----------------------------------------------------
  crop c:   sev = clamp(|yoy_c| / 25, 0, 1)           25% YoY = full severity — the same
                                                       denominator build_crop_stress.py uses
            rel = crop_share_c × (a / 100)
            ctx = round(crop_share_c × 100)            % of province planted area (MEASURED)
  gold:     sev = clamp(|yoy_gold| / 25, 0, 1)
            rel = (c / 100) × min(1, gold_shops / 5)   5+ gold shops ≤10km = full presence
            ctx = gold_shops                           measured OSM count
  drought:  sev = province drought (0..1, measured rain proxy)
            rel = (a / 100) × crop_dependence
            ctx = round(rain_pct_of_normal)            % of normal rain (MEASURED proxy)
  score   = round(100 × sev × rel)    SHARE-DILUTED: typical 0-30, compare ORDER not magnitude
  dir     = 't' (tailwind) when price YoY > 0 — the move supports borrower income /
            collateral value; 'h' (headwind) otherwise. drought is headwind-only.
  t2      = the top-2 drivers by score (desc), zero-score drivers dropped.

BUENG KAN FALLBACK (OAE gap — no crop_stress entry): crop shares are unknowable there,
so crop drivers fall to 0 and drought falls back to the branch's OWN measured rain field
with the same clamp((100-rain)/40) formula crop_stress uses, at full agri relevance
(a/100). Caveated in meta.gaps.

DETERMINISTIC + NETWORK-FREE — byte-exact reproducible; carries --check (QA gate).
Output is INDEX-ALIGNED to branches.json (entry i ↔ branch i) and stamps
meta.branches_fingerprint (tamper-evident alignment, see pipeline/fingerprint.py).

Usage:
  python3 build_macro_sensitivity.py            # write platform/data/macro_sensitivity.json
  python3 build_macro_sensitivity.py --check    # verify byte-for-byte reproduce
"""
import argparse
import json
import os
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "platform", "data")
BRANCHES = os.path.join(DATA, "branches.json")
CROP = os.path.join(DATA, "crop_stress.json")
BOARD = os.path.join(ROOT, "source-data", "commodity_board.json")
OUT = os.path.join(DATA, "macro_sensitivity.json")
sys.path.insert(0, HERE)
from regionmap import canonical
from fingerprint import branches_fingerprint

# fixed driver order — tie-break for equal scores and the audit order in meta.
# NOTE: gold is deliberately excluded — AutoX lends against vehicle titles, not gold, so gold
# price / gold-shop presence is NOT a driver of the book.
DRIVER_ORDER = ("rice", "rubber", "palm", "drought")
# Pink Sheet board row per price driver (source-data/commodity_board.json "lab").
BOARD_LAB = {"rice": "Rice", "rubber": "Rubber", "palm": "Palm oil"}
# crop_stress.json crop_mix crop name per crop driver.
CROP_NAME = {"rice": "Rice", "rubber": "Rubber", "palm": "Oil palm"}
# |YoY| of 25% == full severity 1.0 — same denominator as build_crop_stress.py price_term.
PRICE_SEV_DEN = 25.0
# Bueng Kan fallback drought formula denominator — same as build_crop_stress.py drought_term.
RAIN_DEN = 40.0

DRIVER_LABELS = {
    "rice": "Rice price", "rubber": "Rubber price", "palm": "Palm-oil price",
    "drought": "Drought / rainfall",
}
CTX_LABELS = {
    "rice": "% of province planted area (MEASURED, OAE)",
    "rubber": "% of province planted area (MEASURED, OAE)",
    "palm": "% of province planted area (MEASURED, OAE)",
    "drought": "% of normal 3-month rain (MEASURED proxy)",
}


def _load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def _clamp01(x):
    return 0.0 if x < 0 else (1.0 if x > 1 else x)


def build():
    branches = _load(BRANCHES)
    board = _load(BOARD)
    crop = _load(CROP)["provinces"]

    by_lab = {r["lab"]: r for r in board}
    vintages = sorted({r.get("stale") for r in board if r.get("stale")})
    price_vintage = vintages[-1] if vintages else None

    # ── measured price signals per driver ───────────────────────────────────
    signals = {}
    for k, lab in BOARD_LAB.items():
        row = by_lab[lab]
        yoy = float(row["yoy"])
        signals[k] = {
            "label": DRIVER_LABELS[k],
            "yoy_pct": yoy,
            "dir": "t" if yoy > 0 else "h",   # price up = supports income/collateral
            "vintage": row.get("stale"),
            "source": "World Bank Pink Sheet via source-data/commodity_board.json ('%s')" % lab,
            "provenance": "MEASURED — GLOBAL price YoY %, a direction proxy, NOT Thai farm-gate",
            "ctx_label": CTX_LABELS[k],
        }
    signals["drought"] = {
        "label": DRIVER_LABELS["drought"],
        "dir": "h",  # rainfall deficit only ever hurts farm cash flow
        "source": "3-month rainfall vs normal per province (platform/data/crop_stress.json drought "
                  "/ rain_pct_of_normal; HDX/CHIRPS via the enrichment loop)",
        "provenance": "MEASURED PROXY — rainfall % of normal; the 0..1 drought direction is derived, not a yield outcome",
        "ctx_label": CTX_LABELS["drought"],
    }

    # ── province lookups (canonical Thai name → measured crop context) ──────
    prov = {}
    for p in crop:
        shares = {c["crop"]: c["share"] for c in p.get("crop_mix", [])}
        prov[canonical(p["th"])] = {
            "rice": shares.get("Rice", 0.0),
            "rubber": shares.get("Rubber", 0.0),
            "palm": shares.get("Oil palm", 0.0),
            "dep": p.get("crop_dependence") or 0.0,
            "drought": p.get("drought") or 0.0,
            "rain": (p.get("components") or {}).get("rain_pct_of_normal"),
        }

    # ── per-branch top-2 drivers ─────────────────────────────────────────────
    order = {k: i for i, k in enumerate(DRIVER_ORDER)}
    out = []
    n_fallback = 0
    # province rollup tallies: top-driver counts + score sums per province
    ptally = defaultdict(lambda: {"n": 0, "top": defaultdict(int), "hdir": defaultdict(int),
                                  "score": defaultdict(float), "region": None})
    for b in branches:
        a_rel = (b.get("a") or 0) / 100.0          # ESTIMATED agri catchment weight
        pv = prov.get(canonical(b.get("v") or ""))

        cand = []
        for k in ("rice", "rubber", "palm"):
            share = pv[k] if pv else 0.0
            sev = _clamp01(abs(signals[k]["yoy_pct"]) / PRICE_SEV_DEN)
            score = int(round(100 * sev * share * a_rel))
            if score > 0:
                cand.append([k, score, signals[k]["dir"], int(round(share * 100))])
        if pv:
            dsev = pv["drought"]
            drel = a_rel * pv["dep"]
            dctx = int(round(pv["rain"])) if pv["rain"] is not None else None
        else:
            # Bueng Kan fallback: OAE gap — branch's own measured rain field, full agri relevance
            n_fallback += 1
            rain = b.get("rain")
            dsev = _clamp01((100.0 - rain) / RAIN_DEN) if rain is not None else 0.0
            drel = a_rel
            dctx = int(round(rain)) if rain is not None else None
        dscore = int(round(100 * dsev * drel))
        if dscore > 0:
            cand.append(["drought", dscore, "h", dctx])

        cand.sort(key=lambda t: (-t[1], order[t[0]]))
        out.append(cand[:2])

        # province rollup on the TOP driver only (what moves this branch most)
        pt = ptally[b.get("v") or "?"]
        pt["n"] += 1
        pt["region"] = pt["region"] or b.get("r")
        if cand:
            k = cand[0][0]
            pt["top"][k] += 1
            pt["score"][k] += cand[0][1]
            if cand[0][2] == "h":
                pt["hdir"][k] += 1

    # ── province macro watchlist (modal top driver per province) ────────────
    provinces = []
    for th in sorted(ptally.keys()):
        pt = ptally[th]
        if not pt["top"]:
            continue
        k = sorted(pt["top"].keys(), key=lambda x: (-pt["top"][x], order[x]))[0]
        hits = pt["top"][k]
        provinces.append({
            "th": th,
            "region": pt["region"],
            "n": pt["n"],
            "driver": k,
            "dir": "h" if pt["hdir"][k] * 2 >= hits else "t",  # majority direction among hit branches
            "hits": hits,                                       # branches whose TOP driver is k
            "avg_score": round(pt["score"][k] / hits, 1),
        })
    # headwind-dominant provinces first (the watchlist), then by how much book the driver moves
    provinces.sort(key=lambda p: (0 if p["dir"] == "h" else 1, -p["hits"], -p["avg_score"], p["th"]))

    meta = {
        "title": "What moves this branch — top-2 macro drivers per branch (portfolio risk, objective #1)",
        "generated_by": "pipeline/build_macro_sensitivity.py",
        "deterministic": True,
        "network_free": True,
        "label": "ESTIMATED PROXY OVER MEASURED INPUTS — real Pink Sheet price YoY (GLOBAL direction "
                 "proxy, not Thai farm-gate) and measured OAE crop shares / rainfall, combined through "
                 "ESTIMATED branch relevance weights (segment score a is an estimated 0-100 screen). A "
                 "ranking of which macro lever moves each branch's book — NOT a measured elasticity or "
                 "default rate. Gold is excluded: AutoX lends against vehicle titles, not gold.",
        "provenance": {
            "price_signals": "MEASURED — World Bank Pink Sheet YoY via source-data/commodity_board.json "
                             "(vintage %s). GLOBAL prices, a direction proxy, NOT Thai farm-gate." % price_vintage,
            "crop_shares": "MEASURED — OAE planting-area shares per province (platform/data/crop_stress.json crop_mix)",
            "drought": "MEASURED PROXY — 3-month rainfall %% of normal (crop_stress.json components.rain_pct_of_normal)",
            "relevance_weights": "ESTIMATED — branch agri segment score (branches.json a, "
                                 "estimated 0-100 OSM/price screen) scales the driver relevance",
        },
        "formula": "score = round(100 × severity × relevance). Crops: sev=clamp(|yoy|/%d,0,1), "
                   "rel=crop_share×(a/100). Drought: sev=province drought(0..1), rel=(a/100)×crop_dependence. "
                   "dir: 't' tailwind when price YoY>0, else 'h'; drought is headwind-only. t2 = top-2 by "
                   "score desc (fixed driver order tie-break)."
                   % (int(PRICE_SEV_DEN),),
        "score_scale": "RELATIVE 0-100 but diluted by measured shares and estimated segment scores — a "
                       "crop driver rarely exceeds ~50. Compare ORDER, not magnitude.",
        "rec_format": "branches[i] = t2 = up to 2 of [driver_key, score, 'h'|'t', ctx] — ctx meaning per "
                      "driver is meta.drivers[key].ctx_label. INDEX-ALIGNED to branches.json (entry i ↔ branch i).",
        "province_format": "provinces[] = macro watchlist: modal TOP driver per province, headwind-dominant "
                           "first. hits = branches whose #1 driver it is; avg_score share-diluted (est).",
        "gaps": "Bueng Kan has no OAE crop_stress entry: crop drivers read 0 there and drought falls back "
                "to the branch's own measured rain field, clamp((100-rain)/%d), at full agri relevance "
                "(%d branches). No fuel / used-vehicle / manufacturing price series exists in the offline "
                "sources, so those levers are NOT scored — see build_macro_exposure.py for the occupation-"
                "weighted view that models the manufacturing cycle editorially." % (int(RAIN_DEN), n_fallback),
        "driver_keys": list(DRIVER_ORDER),
        "drivers": {k: signals[k] for k in DRIVER_ORDER},
        "price_vintage": price_vintage,
        "n_branches": len(out),
        "n_provinces": len(provinces),
        "branches_fingerprint": branches_fingerprint(branches),
    }
    return {"meta": meta, "branches": out, "provinces": provinces}


def run(check=False):
    obj = build()
    text = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    if check:
        if not os.path.exists(OUT) or open(OUT, encoding="utf-8").read() != text:
            print("DRIFT: %s" % os.path.relpath(OUT, ROOT))
            return 1
        print("OK: macro_sensitivity.json reproduces (%d branches)" % obj["meta"]["n_branches"])
        return 0
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(text)
    m = obj["meta"]
    print("wrote %d branches -> platform/data/macro_sensitivity.json (%.0f KB)"
          % (m["n_branches"], len(text.encode("utf-8")) / 1024))
    for p in obj["provinces"][:5]:
        print("  %-14s top=%s dir=%s hits=%d/%d avg=%.1f"
              % (p["th"], p["driver"], p["dir"], p["hits"], p["n"], p["avg_score"]))
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="top-2 macro drivers per branch (what moves this branch)")
    ap.add_argument("--check", action="store_true")
    raise SystemExit(run(check=ap.parse_args().check))
