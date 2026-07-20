#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_rival_threat_region.py — COMPETITIVE RISK (objective #2): the density × quality join,
localised to the 5 regions where AutoX's branches actually sit.

`build_rival_threat.py` answers the join per rival BRAND, nationally. But AutoX defends a footprint,
not a brand — and the reputation board's own headline ("where a rival is both dense and well-liked,
share is hardest to take") is a statement about PLACES. This layer computes that join per REGION:
how outgunned AutoX is on the ground (measured census footprint) next to how well-liked the rival
field is there (measured Google rating), so the strategy team can read which regions are hardest to
defend — dense AND well-liked — vs. which are outgunned-but-beatable-on-service.

  in : platform/data/peer_province.json      MEASURED per-province big-4 census footprint next to
                                               AutoX's own branch count, carrying each province's
                                               `region`; aggregated here to the 5 regions.
       platform/data/rival_reputation.json   MEASURED review-weighted Google rating per region
                                               (`by_region`), a located-branch sample.
  out: platform/data/rival_threat_region.json  per-region density × quality read + verdict.

TWO AXES, BOTH MEASURED (this cut is more measured than the brand matrix, which leans on IR headlines):
  density  — rivals:AutoX branch ratio within the region (MEASURED census, both sides), plus the
             share of AutoX's own districts where it is outnumbered. "Heavily outgunned" = the
             region's ratio exceeds the NATIONAL rivals:AutoX ratio (a fixed, computed reference,
             not a 5-item relative split that flips on noise).
  service  — review-count-weighted Google rating for the located rival branches in the region
             (MEASURED sample). Sample size (n_rated / reviews) is carried per region and the
             verdict flags a THIN sample so a small-sample rating is never read as a full census.

Makes NO open / close / expand recommendation — a risk lens on the footprint we already run.

Deterministic + network-free; every float rounded so the output is byte-stable. `--check`
byte-compares. SKIPs (exit 3) if rival_reputation.json is absent (its ratings are a Google pull not
present in every checkout) — the density half alone is not this layer's job.

  python3 build_rival_threat_region.py
  python3 build_rival_threat_region.py --check
"""
import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "platform", "data")
PEER = os.path.join(DATA, "peer_province.json")
REPUTATION = os.path.join(DATA, "rival_reputation.json")
OUT = os.path.join(DATA, "rival_threat_region.json")

# Fixed, defensible service cuts (same as the brand matrix — not a relative split on 5 regions).
WELL_LOVED = 4.50   # >= : best-loved
SOLID = 4.00        # >= : solid service
# A rating sample thinner than this many located rivals is flagged so it isn't read as a census.
THIN_SAMPLE = 60


def _rating_tier(r):
    if r is None:
        return None
    if r >= WELL_LOVED:
        return "best-loved"
    if r >= SOLID:
        return "solid"
    return "weak service"


def _verdict(ratio, pct_out, rating, n_rated):
    """Plain-language read of density × quality for one region.

    Every region is heavily outgunned (rivals outnumber AutoX several-fold everywhere), so density is
    a magnitude context, not the discriminator — the defensibility lever that actually differs across
    regions is rival SERVICE quality (the fixed best-loved/solid cut). So the class is service-led and
    the raw density (ratio + share of AutoX districts outnumbered) is carried as context.
    """
    rt = _rating_tier(rating)
    if ratio is None or rating is None:
        return "—", "—"
    dens = "outgunned %.1f× on branches" % ratio
    if pct_out is not None:
        dens += " (rivals lead in %g%% of our districts)" % pct_out
    svc = {"best-loved": "and the rival field is best-loved (%.2f★)" % rating,
           "solid": "but rivals are only solid, not loved (%.2f★)" % rating,
           "weak service": "and rivals are weak on service (%.2f★)" % rating}[rt]
    head = {"best-loved": "Hardest to defend",
            "solid": "Beatable on service",
            "weak service": "Most defensible"}[rt]
    v = "%s: %s, %s." % (head, dens, svc)
    if n_rated is not None and n_rated < THIN_SAMPLE:
        v += " Thin rating sample (%d located rivals) — read the star figure as indicative." % n_rated
    return head, v


def build():
    peer = json.load(open(PEER, encoding="utf-8"))
    rep = json.load(open(REPUTATION, encoding="utf-8"))
    rep_by = {r.get("region"): r for r in rep.get("by_region", []) if r.get("region")}

    # Aggregate the measured per-province footprint to regions. Ordered by first appearance so the
    # output is deterministic without sorting on a float that could tie.
    agg = {}
    order = []
    for p in peer.get("provinces", []):
        reg = p.get("region")
        if not reg:
            continue
        if reg not in agg:
            agg[reg] = {"autox": 0, "rivals": 0, "n_districts": 0, "n_outnumbered": 0, "n_prov": 0}
            order.append(reg)
        a = agg[reg]
        a["autox"] += p.get("autox") or 0
        a["rivals"] += p.get("rivals") or 0
        a["n_districts"] += p.get("n_districts") or 0
        a["n_outnumbered"] += p.get("n_outnumbered_districts") or 0
        a["n_prov"] += 1

    tot_autox = sum(a["autox"] for a in agg.values())
    tot_rivals = sum(a["rivals"] for a in agg.values())
    nat_ratio = round(tot_rivals / tot_autox, 2) if tot_autox else None

    rows = []
    for reg in order:
        a = agg[reg]
        r = rep_by.get(reg, {})
        ratio = round(a["rivals"] / a["autox"], 2) if a["autox"] else None
        pct_out = round(100.0 * a["n_outnumbered"] / a["n_districts"], 1) if a["n_districts"] else None
        rating = r.get("rating_wavg")
        n_rated = r.get("n_rated")
        reviews = r.get("reviews")
        head, verdict = _verdict(ratio, pct_out, rating, n_rated)
        rows.append({
            "region": reg,
            "provinces": a["n_prov"],
            "autox": a["autox"],
            "rivals": a["rivals"],
            "rivals_vs_autox": ratio,
            "pct_districts_outnumbered": pct_out,
            "rating_wavg": rating,
            "n_rated": n_rated,
            "reviews": reviews,
            "rating_tier": _rating_tier(rating),
            "heavily_outgunned": (ratio is not None and nat_ratio is not None and ratio > nat_ratio),
            "thin_rating_sample": (n_rated is not None and n_rated < THIN_SAMPLE),
            "threat_class": head,
            "verdict": verdict,
        })

    # Present order: hardest to defend first, then by density desc, then region name (stable).
    class_rank = {"Hardest to defend": 0, "Beatable on service": 1, "Most defensible": 2, "—": 4}
    rows.sort(key=lambda x: (class_rank.get(x["threat_class"], 9),
                             -(x["rivals_vs_autox"] or 0), x["region"]))

    hardest = [x for x in rows if x["threat_class"] == "Hardest to defend"]
    if hardest:
        names = ", ".join(x["region"] for x in hardest)
        headline = ("%s %s hardest to defend — outgunned on the ground AND the rival field is best-loved "
                    "there. Where a rival is both dense and well-liked, AutoX's share is hardest to take."
                    % (names, "are" if len(hardest) > 1 else "is"))
    else:
        headline = ("No region has a best-loved rival field — rivals outnumber AutoX everywhere but are "
                    "only solid on service, so share is contestable on service quality across the network.")

    return {
        "meta": {
            "title": "Rival threat by region — density × service quality where AutoX's branches sit (obj #2)",
            "generated_by": "pipeline/build_rival_threat_region.py",
            "label": "MEASURED (both axes) — DENSITY is the measured rivals:AutoX census ratio within "
                     "the region (both sides counted) plus the share of AutoX districts where rivals "
                     "lead; SERVICE is the measured review-weighted Google rating for located rival "
                     "branches (a sample — n_rated / reviews carried per region; thin samples flagged). "
                     "NOT an AutoX figure on the service axis — our branches carry no ratings. Every "
                     "region is heavily outgunned (rivals outnumber AutoX several-fold everywhere), so "
                     "the defensibility CLASS is led by the fixed rival-service cut (best-loved >=%.2f = "
                     "hardest to defend; solid = beatable on service); density is magnitude context. "
                     "`heavily_outgunned` (region ratio > national %s) is carried as an honest sub-signal "
                     "but does not drive the class. Makes NO open/close/expand recommendation."
                     % (WELL_LOVED, nat_ratio),
            "source": "join of platform/data/peer_province.json (measured census footprint, per region) + "
                      "platform/data/rival_reputation.json by_region (measured Google service rating).",
            "national_rivals_vs_autox": nat_ratio,
            "autox_branches_ranked": tot_autox,
            "rivals_counted": tot_rivals,
            "tiers": {"rating": {"best-loved": ">=%.2f" % WELL_LOVED, "solid": ">=%.2f" % SOLID,
                                 "weak service": "<%.2f" % SOLID},
                      "thin_rating_sample": "n_rated < %d located rivals" % THIN_SAMPLE},
        },
        "headline": headline,
        "regions": rows,
    }


def serialize(o):
    return json.dumps(o, ensure_ascii=False, separators=(",", ":"))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    if not os.path.exists(REPUTATION):
        if args.check:
            print("build_rival_threat_region.py --check: SKIP (rival_reputation.json absent — Google Places pull)")
            sys.exit(3)
        sys.exit("build_rival_threat_region.py: platform/data/rival_reputation.json missing — run build_rival_reputation.py")
    if not os.path.exists(PEER):
        sys.exit("build_rival_threat_region.py: platform/data/peer_province.json missing — run build_peer_province.py")
    payload = serialize(build())
    if args.check:
        if not os.path.exists(OUT):
            sys.exit("build_rival_threat_region.py --check: output missing — run the builder.")
        if open(OUT, encoding="utf-8").read() != payload:
            sys.exit("build_rival_threat_region.py --check: drifted — re-run the builder.")
        print("build_rival_threat_region.py --check: OK (byte-exact)")
        return
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(payload)
    obj = json.loads(payload)
    print("wrote %s — %d regions (national rivals:AutoX=%s)"
          % (OUT, len(obj["regions"]), obj["meta"]["national_rivals_vs_autox"]))
    for r in obj["regions"]:
        print("  %-12s %5.2fx  out%%=%s  rating=%s  [%s]"
              % (r["region"], r["rivals_vs_autox"], r["pct_districts_outnumbered"],
                 r["rating_wavg"], r["threat_class"]))
    print("  headline:", obj["headline"])


if __name__ == "__main__":
    main()
