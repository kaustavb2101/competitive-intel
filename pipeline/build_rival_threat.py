#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_rival_threat.py — COMPETITIVE RISK (objective #2): the density × quality JOIN.

The rival-density board says WHERE rivals are; the rival-reputation board says HOW GOOD they are.
Neither, alone, answers the question the reputation headline actually poses —
"where a rival is both dense and well-liked, share is hardest to take". This layer computes that
join per rival brand: national footprint next to measured Google service rating, so the strategy
team can read, at a glance, which rival is the strongest COMBINED threat to the network we already
run — and which is large but beatable on service.

  in : platform/data/competitor_coverage.json  branch footprint per brand
                                                  found     MEASURED  (de-duped census count)
                                                  expected  ESTIMATED (cited company-IR headline)
       platform/data/rival_reputation.json      review-weighted Google rating per brand (MEASURED
                                                  sample of located rival branches)
       platform/data/branches.json              AutoX's own footprint (MEASURED — 2,015 branches)
  out: platform/data/rival_threat.json          per-brand threat matrix + plain-language verdict

TWO AXES, EACH HONESTLY LABELLED:
  footprint  — branches vs AutoX. Reported (company IR, ESTIMATED-from-public-reports) is the
               primary count where cited; the measured census count is carried alongside. Where the
               census materially over-/under-counts vs IR, the row says so (do not read a dirty
               census count as a registry).
  service    — review-count-weighted Google rating (MEASURED, a located-branch sample). NOT an AutoX
               figure — our own branches carry no ratings, so no AutoX rating is shown or invented.

Makes NO open / close / expand recommendation — a risk lens on the footprint we already run.

Deterministic + network-free; every float rounded to 2 dp so the output is byte-stable. `--check`
byte-compares. SKIPs (exit 3) if rival_reputation.json is absent (its ratings are a Google pull that
is not present in every checkout) — the density half alone is not this layer's job.

  python3 build_rival_threat.py
  python3 build_rival_threat.py --check
"""
import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "platform", "data")
COVERAGE = os.path.join(DATA, "competitor_coverage.json")
REPUTATION = os.path.join(DATA, "rival_reputation.json")
BRANCHES = os.path.join(DATA, "branches.json")
OUT = os.path.join(DATA, "rival_threat.json")

# Rating tiers (fixed, defensible cuts — not a relative split that flips on a 4-brand sample).
WELL_LOVED = 4.50   # >= : best-loved
SOLID = 4.00        # >= : solid service
# Footprint tiers vs AutoX (branch-count ratio).
FAR_LARGER = 2.00   # >= : far larger than our network
PEER_LO = 0.50      # >= : peer-scale (0.5x .. 2x)


def _rating_tier(r):
    if r is None:
        return None
    if r >= WELL_LOVED:
        return "best-loved"
    if r >= SOLID:
        return "solid"
    return "weak service"


def _footprint_tier(ratio):
    if ratio is None:
        return None
    if ratio >= FAR_LARGER:
        return "far larger"
    if ratio >= PEER_LO:
        return "peer-scale"
    return "sub-scale"


def _verdict(brand, reported, found, ratio, rating, reviews, over_flag):
    """Plain-language read of the two measured/estimated axes for one brand."""
    ft, rt = _footprint_tier(ratio), _rating_tier(rating)
    if ratio is not None and rating is not None:
        combined = (min(ratio, 3.0) / 3.0) * 0.5 + (rating / 5.0) * 0.5
        # concrete, non-abstract sentence
        fx = "%.1f× our footprint" % ratio
        svc = {"best-loved": "best-loved rival (%.2f★)" % rating,
               "solid": "solid service (%.2f★)" % rating,
               "weak service": "weak service (%.2f★)" % rating}[rt]
        if ft == "far larger" and rt in ("solid", "weak service"):
            head = "Volume threat"
        elif ft in ("peer-scale", "sub-scale") and rt == "best-loved":
            head = "Quality threat"
        elif ft == "far larger" and rt == "best-loved":
            head = "Strongest combined threat"
        else:
            head = "Contained"
        v = "%s: %s and %s." % (head, fx, svc)
        if over_flag:
            v += (" Census over-counts it (found %s vs %s reported) — read the reported figure."
                  % ("{:,}".format(found) if found is not None else "—",
                     "{:,}".format(reported) if reported is not None else "—"))
        return head, round(combined, 3), v
    # partial rows — only one axis known
    if ratio is not None:
        return "Footprint only", None, ("Footprint only (%s, %s) — no located-branch rating sampled."
                                        % ("%.1f× our footprint" % ratio, ft))
    if rating is not None:
        return "Rating only", None, ("Rating only (%.2f★, %d reviews, %s) — no branch count cited."
                                     % (rating, reviews or 0, rt))
    return "—", None, "—"


def build():
    cov = json.load(open(COVERAGE, encoding="utf-8"))
    rep = json.load(open(REPUTATION, encoding="utf-8"))
    autox = len(json.load(open(BRANCHES, encoding="utf-8")))

    cov_by = {b.get("brand"): b for b in cov.get("brands", []) if b.get("brand")}
    rep_by = {b.get("brand"): b for b in rep.get("by_brand", []) if b.get("brand")}
    brands = list(cov_by.keys()) + [b for b in rep_by if b not in cov_by]

    rows = []
    for b in brands:
        c = cov_by.get(b, {})
        r = rep_by.get(b, {})
        reported = c.get("expected")            # ESTIMATED (company IR)
        found = c.get("found")                  # MEASURED (census, deduped)
        rating = r.get("rating_wavg")           # MEASURED (Google, sample)
        reviews = r.get("reviews")
        n_rated = r.get("n_rated")
        # Footprint count for the vs-AutoX ratio: prefer the cited IR headline; fall back to census.
        count = reported if reported is not None else found
        ratio = round(count / autox, 2) if (count is not None and autox) else None
        # Flag a materially dirty census count (>=1.5x the cited IR headline) so nobody reads it raw.
        over_flag = bool(reported and found and found >= 1.5 * reported)
        head, combined, verdict = _verdict(b, reported, found, ratio, rating, reviews, over_flag)
        rows.append({
            "brand": b,
            "branches_reported": reported,
            "branches_found": found,
            "footprint_vs_autox": ratio,
            "rating_wavg": rating,
            "reviews": reviews,
            "n_rated": n_rated,
            "footprint_tier": _footprint_tier(ratio),
            "rating_tier": _rating_tier(rating),
            "threat_class": head,
            "census_overcount": over_flag,
            "verdict": verdict,
            "_combined": combined,
        })

    # Order: brands with BOTH axes first (by combined threat desc), then partials, then name.
    rows.sort(key=lambda x: (x["_combined"] is None, -(x["_combined"] or 0), x["brand"]))
    for x in rows:
        del x["_combined"]

    both = [x for x in rows if x["footprint_vs_autox"] is not None and x["rating_wavg"] is not None]
    volume = next((x for x in both if x["threat_class"] in ("Volume threat", "Strongest combined threat")), None)
    quality = next((x for x in both if x["threat_class"] in ("Quality threat", "Strongest combined threat")), None)
    parts = []
    if volume:
        parts.append("%s is the volume threat (%.1f× our footprint, %.2f★)"
                     % (volume["brand"], volume["footprint_vs_autox"], volume["rating_wavg"]))
    if quality and quality is not volume:
        parts.append("%s is the quality threat (%.1f× our footprint but best-loved at %.2f★)"
                     % (quality["brand"], quality["footprint_vs_autox"], quality["rating_wavg"]))
    headline = ""
    if parts:
        headline = ("; ".join(parts)
                    + ". A rival that is both large and well-rated is where AutoX's share is hardest to defend.")

    return {
        "meta": {
            "title": "Rival threat matrix — footprint × service quality per brand (obj #2)",
            "generated_by": "pipeline/build_rival_threat.py",
            "label": "MIXED, classified ESTIMATED — the SERVICE axis (Google rating, review-weighted) "
                     "is MEASURED (a located-branch sample); the FOOTPRINT axis is ESTIMATED-from-public-"
                     "reports (company-IR branch counts, cited), with the measured census count carried "
                     "alongside. NOT an AutoX figure on the service axis — our branches carry no ratings. "
                     "Makes NO open/close/expand recommendation.",
            "source": "join of platform/data/competitor_coverage.json (footprint) + "
                      "platform/data/rival_reputation.json (service) — both committed, deterministic.",
            "autox_branches": autox,
            "footprint_axis": "ESTIMATED-from-public-reports (company IR); census count carried as branches_found.",
            "service_axis": "MEASURED (Google Places rating, review-count-weighted, located-branch sample).",
            "tiers": {"rating": {"best-loved": ">=%.2f" % WELL_LOVED, "solid": ">=%.2f" % SOLID,
                                 "weak service": "<%.2f" % SOLID},
                      "footprint_vs_autox": {"far larger": ">=%.2f" % FAR_LARGER,
                                             "peer-scale": ">=%.2f" % PEER_LO, "sub-scale": "<%.2f" % PEER_LO}},
            "reputation_vintage": (rep.get("meta") or {}).get("vintage"),
        },
        "headline": headline,
        "brands": rows,
    }


def serialize(o):
    return json.dumps(o, ensure_ascii=False, separators=(",", ":"))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    if not os.path.exists(REPUTATION):
        if args.check:
            print("build_rival_threat.py --check: SKIP (rival_reputation.json absent — Google Places pull)")
            sys.exit(3)
        sys.exit("build_rival_threat.py: platform/data/rival_reputation.json missing — run build_rival_reputation.py")
    if not os.path.exists(COVERAGE):
        sys.exit("build_rival_threat.py: platform/data/competitor_coverage.json missing — run build_competitor_coverage.py")
    payload = serialize(build())
    if args.check:
        if not os.path.exists(OUT):
            sys.exit("build_rival_threat.py --check: output missing — run the builder.")
        if open(OUT, encoding="utf-8").read() != payload:
            sys.exit("build_rival_threat.py --check: drifted — re-run the builder.")
        print("build_rival_threat.py --check: OK (byte-exact)")
        return
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(payload)
    obj = json.loads(payload)
    print("wrote %s — %d brands (AutoX=%d)" % (OUT, len(obj["brands"]), obj["meta"]["autox_branches"]))
    for b in obj["brands"]:
        print("  %-12s footprint=%s (rep %s / found %s) rating=%s [%s]"
              % (b["brand"], b["footprint_vs_autox"], b["branches_reported"], b["branches_found"],
                 b["rating_wavg"], b["threat_class"]))
    print("  headline:", obj["headline"])


if __name__ == "__main__":
    main()
