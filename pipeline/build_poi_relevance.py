#!/usr/bin/env python3
"""
build_poi_relevance.py — RELEVANT-POI DENSITY score per branch
==============================================================
For a TITLE-LOAN lender, not every nearby establishment matters. A 10km
catchment thick with hospitals or government offices is not the same opportunity
as one thick with gold shops, vehicle dealers, wet markets and factories. This
builder collapses the measured per-branch POI catchment into ONE number — a
title-loan-RELEVANT density score — by weighting only the categories that signal
loan DEMAND (informal/wage-earner households who borrow against a title) or
COLLATERAL supply (vehicles, gold).

INPUTS (both index-aligned to platform/data/branches.json):
  - platform/data/branch_occupations.json  (PRIMARY, optional)
      MEASURED Overture establishment buckets within 10km. branches[i].o is a
      14-long count vector aligned to the `buckets` list; branches[i].t the total.
      Buckets: factory, auto, retail, food, hospitality, finance, health,
               education, public, professional, agriculture, personal,
               logistics, construction.
  - platform/data/branches.json k10        (always present)
      MEASURED per-branch 10km OSM POI counts: gold, veh, fmkt, ind, super, cvs,
      sch, rest, bank, atm, hotel, pharm, civic, est.

The two sources are COMPLEMENTARY, not duplicative: Overture's `auto`/`finance`/
`agriculture` buckets and the OSM `gold`/`fmkt` counts each capture signals the
other misses, so the relevant categories are assembled from BOTH where available.

PER BRANCH we emit (index-aligned to branches.json):
  - rel  : the title-loan relevance density score, 0..100 (ESTIMATED weighting
           over MEASURED counts; min-max normalized across all branches)
  - raw  : the raw weighted relevant-POI count (MEASURED counts x ESTIMATED
           weights, BEFORE normalization) — an absolute density, comparable run
           to run only at fixed weights
  - cat  : the raw MEASURED counts for each relevant category (so the app can
           show "what's actually there", not just the blended score)
  - src  : "occ+k10" when branch_occupations was available, else "k10"

PROVENANCE: every COUNT is MEASURED (Overture / OSM, a sample/lower bound, not a
registry). The WEIGHTS are an ESTIMATED relevance model — a judgement about which
categories signal title-loan demand/collateral, stated in `meta.weights` with a
rationale. No count is fabricated; absent categories contribute 0.

GRACEFUL: if branch_occupations.json is absent we fall back to branches.json k10
ONLY (meta.note records it, every src="k10"). If branches.json itself is absent
we emit an honest ABSENT-state file (meta.absent=true, empty branches[]); --check
then skip-passes.

  python3 build_poi_relevance.py            # write platform/data/poi_relevance.json
  python3 build_poi_relevance.py --check    # re-run, byte-compare against committed file
"""
import os, json, argparse, sys

from lib.fingerprint import branches_fingerprint

ROOT = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(ROOT)
DATA = os.path.join(REPO, "platform", "data")
BRANCHES = os.path.join(DATA, "branches.json")
OCC = os.path.join(DATA, "branch_occupations.json")
OUT = os.path.join(DATA, "poi_relevance.json")

# --- the ESTIMATED relevance model -----------------------------------------
# Each relevant category draws from MEASURED counts in branch_occupations.json
# (Overture bucket, by bucket KEY) and/or branches.json k10 (OSM, by k10 key).
# When BOTH a k10 key and an Overture bucket exist for a category, we take the
# MAX of the two (they are different samples of the same real-world thing; max is
# the better lower-bound and avoids double-counting). Weight = relative strength
# of that category as a title-loan DEMAND or COLLATERAL signal.
#
# Rationale (title-loan lens — what drives a borrower to pledge a title):
#   gold      1.5  COLLATERAL + pawn-adjacent culture; gold shops are the single
#                  strongest co-located signal of title/pawn borrowing in Thailand.
#   vehicle   1.4  COLLATERAL supply: car/motorbike dealers & mechanics = where
#                  pledgeable vehicles concentrate (AutoX's core book is vehicles).
#   fresh_mkt 1.1  DEMAND: wet-market vendors are the canonical informal-cash,
#                  thin-file borrower who can't get a bank loan. OSM fmkt ONLY —
#                  the Overture `retail` bucket is EVERY shop type, not fresh
#                  markets, so mapping it here would inflate the count ~100x
#                  (that broad signal is scored separately as retail_general).
#   agri      1.0  DEMAND: farm households — seasonal cash gaps, title-loan heavy
#                  (objective #1's stressed segment).
#   factory   0.9  DEMAND: wage earners with lumpy needs; industrial estates anchor
#                  a working-class borrower base.
#   commerce  0.6  DEMAND/footfall: convenience+supermarket = general retail
#                  vibrancy; weaker, broader proxy for spendable households.
#   retail_general 0.5  DEMAND/footfall: the WHOLE Overture retail bucket (every
#                  shop type). Broad and undiscriminating, so it carries a LOW
#                  weight — it must never masquerade as the fresh-market signal.
#   food_service   0.5  DEMAND/footfall: restaurants / street-food (OSM rest,
#                  Overture food). Informal food operators are real title-loan
#                  demand but the bucket is broad, so it is down-weighted and
#                  scored on its own instead of being folded into commerce.
#   school    0.4  DEMAND: schools proxy HOUSEHOLD FORMATION / family expenses
#                  (fees, uniforms) — a softer borrowing trigger.
# Finance/pawn establishments are deliberately EXCLUDED from the demand score:
# they are competitor SUPPLY, not our demand, and are scored elsewhere
# (competitor_coverage). Hospitality/health/public/professional/logistics/
# construction are NOT title-loan-relevant and contribute 0.
CATEGORIES = [
    # name        weight  k10 keys (summed, MEASURED OSM)   overture bucket keys (summed, MEASURED)
    ("gold",           1.5, ["gold"],         []),            # gold: OSM only (no Overture gold bucket)
    ("vehicle",        1.4, ["veh"],          ["auto"]),
    ("fresh_mkt",      1.1, ["fmkt"],         []),            # OSM fmkt ONLY — honest measured fresh-market count
    ("agri",           1.0, [],               ["agriculture"]),
    ("factory",        0.9, ["ind"],          ["factory"]),
    ("commerce",       0.6, ["cvs", "super"], []),            # cvs+super ONLY (food scored as food_service)
    ("retail_general", 0.5, [],               ["retail"]),    # whole Overture retail bucket — broad, LOW weight
    ("food_service",   0.5, ["rest"],         ["food"]),      # restaurants / street food — broad, LOW weight
    ("school",         0.4, ["sch"],          ["education"]),
]

WEIGHTS = {name: w for (name, w, _k, _o) in CATEGORIES}


def _load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def dumps(obj):
    # deterministic, mirrors the other builders' meta.json convention.
    return json.dumps(obj, ensure_ascii=False, indent=2) + "\n"


def _occ_index(occ):
    """Map an Overture bucket KEY -> its column index in each branch's `o` vector."""
    out = {}
    for i, b in enumerate(occ.get("buckets", [])):
        if isinstance(b, dict) and b.get("key"):
            out[b["key"]] = i
    return out


def build():
    if not os.path.exists(BRANCHES):
        return {
            "meta": {
                "generated_by": "build_poi_relevance.py",
                "absent": True,
                "label": "ESTIMATED relevance weighting over MEASURED POI counts",
                "note": "branches.json absent — honest ABSENT-state; run derive.py first.",
                "n_branches": 0,
                "weights": WEIGHTS,
            },
            "branches": [],
        }

    branches = _load(BRANCHES)
    n = len(branches)

    have_occ = os.path.exists(OCC)
    occ = _load(OCC) if have_occ else None
    occ_recs = occ.get("branches", []) if have_occ else []
    occ_col = _occ_index(occ) if have_occ else {}
    # occupation source is only usable if it is index-aligned to branches.json.
    occ_aligned = have_occ and len(occ_recs) == n

    recs = []
    raws = []
    for i, br in enumerate(branches):
        k10 = br.get("k10") or {}
        ovec = occ_recs[i].get("o") if (occ_aligned and isinstance(occ_recs[i], dict)) else None

        cat = {}
        raw = 0.0
        for name, w, k10keys, occkeys in CATEGORIES:
            k_ct = sum(int(k10.get(k, 0) or 0) for k in k10keys)
            o_ct = 0
            if ovec is not None:
                for ok_ in occkeys:
                    j = occ_col.get(ok_)
                    if j is not None and j < len(ovec):
                        o_ct += int(ovec[j] or 0)
            # MAX of the two measured samples of the same category (see rationale).
            ct = max(k_ct, o_ct)
            cat[name] = ct
            raw += w * ct
        recs.append({"cat": cat, "raw": raw,
                     "src": "occ+k10" if (occ_aligned and ovec is not None) else "k10"})
        raws.append(raw)

    # min-max normalize the weighted raw score to 0..100 (ESTIMATED density index).
    lo = min(raws) if raws else 0.0
    hi = max(raws) if raws else 0.0
    span = (hi - lo) or 1.0
    for r in recs:
        rel = round((r["raw"] - lo) / span * 100.0, 2)
        # order keys for stable, readable output
        r2 = {"rel": rel, "raw": round(r["raw"], 2), "cat": r["cat"], "src": r["src"]}
        r.clear(); r.update(r2)

    note = ("MEASURED counts from branch_occupations.json (Overture) + branches.json k10 (OSM); "
            "per category we take MAX of the two samples.")
    if not occ_aligned:
        if have_occ:
            note = ("branch_occupations.json present but NOT index-aligned to branches.json "
                    "(len mismatch) — fell back to branches.json k10 ONLY.")
        else:
            note = "branch_occupations.json absent — fell back to branches.json k10 ONLY."

    return {
        "meta": {
            "generated_by": "build_poi_relevance.py",
            "label": "ESTIMATED title-loan relevance weighting over MEASURED POI counts (Overture/OSM)",
            "measured": "all category COUNTS are measured (a sample/lower bound, not a registry)",
            "estimated": "the per-category WEIGHTS are a relevance MODEL (judgement), see weights",
            "radius_km": 10.0,
            "n_branches": n,
            "branches_fingerprint": branches_fingerprint(branches),
            "source_occupations": bool(occ_aligned),
            "weights": WEIGHTS,
            "weight_rationale": {
                "gold": "collateral + pawn-adjacent culture; strongest title/pawn co-location signal",
                "vehicle": "collateral supply (vehicle dealers/mechanics) — AutoX's core book",
                "fresh_mkt": "informal cash, thin-file market vendors — canonical title borrower; "
                             "OSM fresh/wet-market count ONLY (the broad Overture retail bucket is "
                             "scored separately as retail_general, not passed off as fresh markets)",
                "agri": "farm households with seasonal cash gaps (objective #1 stressed segment)",
                "factory": "wage earners / industrial-estate working-class borrower base",
                "commerce": "convenience+supermarket footfall — broad household-spend proxy",
                "retail_general": "the WHOLE Overture retail bucket (every shop type) — broad, "
                                  "undiscriminating footfall signal, so deliberately LOW-weighted "
                                  "(0.5) vs the specific fresh-market and commerce signals",
                "food_service": "restaurants / street food (OSM rest, Overture food) — informal "
                                "food operators are real demand but the bucket is broad, so it is "
                                "LOW-weighted (0.5) and kept separate from commerce",
                "school": "household formation / family expenses — softer borrowing trigger",
                "excluded": "finance & pawn = competitor supply (scored in competitor_coverage); "
                            "hospitality/health/public/professional/logistics/construction not relevant",
            },
            "note": note,
            "index_aligned_to": "branches.json (record i == branch i)",
        },
        "branches": recs,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true",
                    help="re-run and byte-compare against the committed JSON; exit 1 on drift "
                         "(skip-passes when the primary input branch_occupations.json is absent)")
    args = ap.parse_args()

    data = build()
    text = dumps(data)

    if args.check:
        # skip-pass when the PRIMARY input is absent: the file (if any) was built
        # against a richer input that is no longer present, so we cannot reproduce it.
        if not os.path.exists(OCC):
            print("CHECK SKIP: branch_occupations.json absent — poi_relevance not byte-checkable")
            sys.exit(0)
        if not os.path.exists(OUT):
            print("CHECK FAIL: %s does not exist" % OUT)
            sys.exit(1)
        with open(OUT, encoding="utf-8") as f:
            existing = f.read()
        if existing == text:
            print("CHECK OK: %s reproduces byte-for-byte (%d branches)" %
                  (OUT, data["meta"]["n_branches"]))
            sys.exit(0)
        print("CHECK FAIL: %s differs from a fresh build" % OUT)
        sys.exit(1)

    with open(OUT, "w", encoding="utf-8") as f:
        f.write(text)
    n = data["meta"]["n_branches"]
    print("wrote %s (%d branches, source_occupations=%s)" %
          (OUT, n, data["meta"].get("source_occupations")))
    ranked = sorted(enumerate(data["branches"]), key=lambda kv: kv[1]["raw"], reverse=True)[:10]
    print("  top-10 by relevant-POI density (raw weighted count):")
    for rank, (i, r) in enumerate(ranked, 1):
        c = r["cat"]
        print("   %2d. branch#%-4d rel=%5.1f raw=%8.1f gold=%d veh=%d fmkt=%d agri=%d fac=%d" %
              (rank, i, r["rel"], r["raw"], c["gold"], c["vehicle"], c["fresh_mkt"],
               c["agri"], c["factory"]))


if __name__ == "__main__":
    main()
