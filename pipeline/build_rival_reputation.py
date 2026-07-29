#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_rival_reputation.py — COMPETITIVE RISK (objective #2): a measured SERVICE-QUALITY layer on
top of rival density. Rolls the per-branch Google ratings (pull_place_ratings.py) up to a
by-brand and by-region reputation board.

  in : source-data/competitor_ratings.json   MEASURED Google rating + review count per located
                                              rival branch (place_id · brand · prov · rating · n)
  out: platform/data/rival_reputation.json    by-brand + by-region rating boards + headline

Reputation is a quality read the density map can't give: two districts equally saturated by a rival
differ if that rival is loved (hard to displace) or disliked (a service opening). Review-count-
weighted mean is the headline (a 5-star place with 3 reviews should not outweigh a 4.2 with 800);
the simple mean is shown alongside. MEASURED sample — the located subset of rivals, not the full
census, and NOT an AutoX number (our branches carry no ratings). Labelled as such.

Deterministic + network-free; ratings are rounded to 2 dp so the output is byte-stable across
Python builds. `--check` byte-compares; SKIPs (exit 3) if competitor_ratings.json is absent.

  python3 build_rival_reputation.py
  python3 build_rival_reputation.py --check
"""
import argparse
import json
import os
import sys
from collections import defaultdict

from lib.regionmap import region_of

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "source-data")
IN = os.path.join(SRC, "competitor_ratings.json")
OUT = os.path.join(ROOT, "platform", "data", "rival_reputation.json")

REGION_ORDER = ["Central&BKK", "Isan", "East", "North", "South"]


def _agg(rows):
    """(n_rated, reviews, simple mean, review-weighted mean) for a list of {rating,n}."""
    n = len(rows)
    reviews = sum(int(r.get("n") or 0) for r in rows)
    smean = round(sum(r["rating"] for r in rows) / n, 2) if n else None
    wnum = sum(r["rating"] * int(r.get("n") or 0) for r in rows)
    wmean = round(wnum / reviews, 2) if reviews else smean
    return n, reviews, smean, wmean


def build():
    doc = json.load(open(IN, encoding="utf-8"))
    rows = doc.get("ratings", [])

    by_brand_rows = defaultdict(list)
    by_region_rows = defaultdict(list)
    for r in rows:
        if r.get("rating") is None:
            continue
        by_brand_rows[r.get("brand") or "—"].append(r)
        by_region_rows[region_of(r.get("prov") or "")].append(r)

    brands = []
    for b, rs in by_brand_rows.items():
        n, reviews, smean, wmean = _agg(rs)
        brands.append({"brand": b, "n_rated": n, "reviews": reviews,
                       "rating_wavg": wmean, "rating_mean": smean})
    brands.sort(key=lambda x: (-(x["rating_wavg"] or 0), -x["reviews"]))

    regions = []
    for rg in REGION_ORDER:
        rs = by_region_rows.get(rg)
        if not rs:
            continue
        n, reviews, smean, wmean = _agg(rs)
        regions.append({"region": rg, "n_rated": n, "reviews": reviews,
                        "rating_wavg": wmean, "rating_mean": smean})

    n_all, reviews_all, smean_all, wmean_all = _agg([r for r in rows if r.get("rating") is not None])
    best = brands[0] if brands else None
    worst = brands[-1] if brands else None
    headline = ""
    if best and worst and best["brand"] != worst["brand"]:
        headline = ("Rival service reputation: %s leads at %.2f★ (%d reviews), %s trails at %.2f★ — "
                    "where a rival is both dense and well-liked, share is hardest to take."
                    % (best["brand"], best["rating_wavg"], best["reviews"],
                       worst["brand"], worst["rating_wavg"]))

    return {
        "meta": {
            "title": "Rival service reputation — measured Google ratings by brand & region (obj #2)",
            "generated_by": "pipeline/build_rival_reputation.py",
            "label": "MEASURED — Google Places rating + review count for the located rival branches "
                     "(sample, not the full census), review-count-weighted. NOT an AutoX figure — our "
                     "branches carry no ratings. A quality lens on the rival field, not a default rate.",
            "source": "source-data/competitor_ratings.json (pull_place_ratings.py · Google Places New)",
            "n_rated": n_all, "reviews": reviews_all,
            "rating_wavg": wmean_all, "rating_mean": smean_all,
            "vintage": doc.get("meta", {}).get("vintage"),
        },
        "headline": headline,
        "by_brand": brands,
        "by_region": regions,
    }


def serialize(o):
    return json.dumps(o, ensure_ascii=False, separators=(",", ":"))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    if not os.path.exists(IN):
        if args.check:
            print("build_rival_reputation.py --check: SKIP (competitor_ratings.json absent — network pull)")
            sys.exit(3)
        sys.exit("build_rival_reputation.py: source-data/competitor_ratings.json missing — run pull_place_ratings.py")
    payload = serialize(build())
    if args.check:
        if not os.path.exists(OUT):
            sys.exit("build_rival_reputation.py --check: output missing — run the builder.")
        if open(OUT, encoding="utf-8").read() != payload:
            sys.exit("build_rival_reputation.py --check: drifted — re-run the builder.")
        print("build_rival_reputation.py --check: OK (byte-exact)")
        return
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(payload)
    obj = json.loads(payload)
    print("wrote %s — %d brands, %d regions, %d rated rival branches"
          % (OUT, len(obj["by_brand"]), len(obj["by_region"]), obj["meta"]["n_rated"]))
    for b in obj["by_brand"]:
        print("  %-14s %s★ wavg · %s★ mean · n=%d · %d reviews"
              % (b["brand"], b["rating_wavg"], b["rating_mean"], b["n_rated"], b["reviews"]))


if __name__ == "__main__":
    main()
