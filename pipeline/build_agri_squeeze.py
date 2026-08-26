#!/usr/bin/env python3
"""
build_agri_squeeze.py — THE AGRI-COMPETITIVE SQUEEZE (obj #1 × obj #2, a DISTINCT cross)
========================================================================================

THE QUESTION THIS ANSWERS
-------------------------
The command centre already carries ONE cross-objective board — `province_pressure.json`
("double pressure"): provinces that are both borrower-stressed on the HOUSEHOLD axis (NSO
debt-to-income + unemployment) AND rival-dominated. That axis is the general consumer's balance
sheet.

But AutoX's book is disproportionately AGRICULTURAL — farm-gate income, drought, and crop-margin
are a portfolio-risk channel the household-DTI blend does not see. A province can look calm on
household stress yet carry farm borrowers whose repayment capacity is collapsing on a crop-price
or drought shock. Where that AGRICULTURAL stress coincides with heavy rival dominance is a
SECOND, distinct squeeze — a fragile FARM book exactly where margin defence is hardest — and no
committed layer names it. `build_opportunity_score.py` fuses agri_stress but is DORMANT and
expansion-shaped (it makes a place-to-open call); this layer is a pure risk lens on the EXISTING
network and makes NO open/close/expand recommendation.

This is a pure, deterministic JOIN of two committed, gated, --check-reproducible files on the 77
provinces, keyed by Thai province name:
  * portfolio-risk (agri)  — crop_stress.json (agri_stress: MEASURED Thai farm-gate price stress +
                             OAE drought/rainfall + crop dependence — where FARM borrowers are stressed).
  * competitive-risk       — peer_province.json (rival:AutoX `ratio` — where rivals own the ground).
It invents no new measurement: it lines the two existing per-province axes up as 0-100 percentiles
so they are comparable, and flags the provinces high on BOTH. The competitive axis is computed with
the SAME mid-rank-ties percentile method `build_province_pressure.py` uses on the same `ratio`, so
`contest_pctile` here is directly comparable to (and equal to) the double-pressure card's.

MEASURED vs ESTIMATED (the data-mandate — stated explicitly, repeated in meta)
------------------------------------------------------------------------------
  agri_pctile     = 0-100 percentile rank of crop_stress.json's `agri_stress` across the 77
                    provinces. agri_stress is MIXED-leaning-MEASURED: its price term is MEASURED
                    Thai farm-gate (NABC live / OAE) where a crop is priced, with a World Bank
                    GLOBAL proxy ONLY as a fallback for unpriced crops; drought/rainfall are
                    MEASURED (OAE). `price_coverage` (fraction of the province's crop value priced
                    from measured farm-gate) is carried per province so the reader sees the mix.
                    The percentile itself is a RELATIVE rank, not an absolute default level.
  contest_pctile  = 0-100 percentile rank of peer_province.json's rival:AutoX `ratio` across the
                    77 provinces. `ratio`'s inputs are MEASURED (AutoX branch count + the big-4
                    competitor census); the percentile is COMPUTED. The census is a LOWER BOUND
                    (big-4 only; sub-scale + PICO operators not in the ratio) — inherited caveat.
  squeeze_min     = min(agri_pctile, contest_pctile). High ONLY when the WEAKER axis is also high,
                    so it is the honest "high on BOTH" score — never inflated by one axis. COMPUTED.
  squeeze_mean    = mean of the two percentiles — a smoother combined index. COMPUTED.
  quadrant        = median (>=50) split on each axis → HH / HL / LH / LL. COMPUTED, descriptive.
  agri_squeeze    = agri_pctile >= 66.67 AND contest_pctile >= 66.67 (both in the top third).
                    The alert set. COMPUTED.

Both source axes are RELATIVE percentiles over the same 77 provinces, so the combined reads are
rankings ("worse than most provinces on both"), NOT calibrated probabilities. Nothing here is a
verdict; it is a place to look first.

DETERMINISTIC + NETWORK-FREE: reads two committed files, no network, no wall clock, no randomness.
Byte-exact reproducible -> carries --check (the QA gate runs it). Either input may be absent in a
stripped sandbox: build() returns None, --check skip-passes, a plain run exits non-zero with a
clear message (mirrors build_province_pressure.py).

Usage:
  python3 build_agri_squeeze.py            # write platform/data/agri_squeeze.json
  python3 build_agri_squeeze.py --check    # verify byte-for-byte reproduce
"""
import argparse, json, os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "platform", "data")
CROP = os.path.join(DATA, "crop_stress.json")
PEER = os.path.join(DATA, "peer_province.json")
OUT = os.path.join(DATA, "agri_squeeze.json")

# A percentile at or above this cut counts as "top third" for the agri_squeeze alert flag. Requiring
# BOTH axes above it is a deliberately strict intersection so the alert set stays small and meaningful.
TOP_THIRD = round(200.0 / 3.0, 2)  # 66.67
MEDIAN = 50.0                       # median split for the descriptive 2x2 quadrant label


def _load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def _percentile_rank(value, sorted_values):
    """0..100 percentile rank of `value` within `sorted_values`: fraction strictly below plus half
    of those equal (mid-rank ties). Deterministic. IDENTICAL method to build_province_pressure /
    build_province_stress, so contest_pctile here equals the double-pressure card's contest_pctile."""
    n = len(sorted_values)
    if n <= 1:
        return 50.0
    below = sum(1 for v in sorted_values if v < value)
    equal = sum(1 for v in sorted_values if v == value)
    return round(100.0 * (below + 0.5 * equal) / n, 2)


def build():
    if not (os.path.exists(CROP) and os.path.exists(PEER)):
        return None
    crop = _load(CROP)
    peer = _load(PEER)
    # agri (portfolio) axis, keyed by Thai province name (crop_stress rows carry `th`).
    crows = {r["th"]: r for r in crop.get("provinces", []) if r.get("th")}
    prows = peer.get("provinces", [])
    if not crows or not prows:
        return None

    # percentile pools over the SAME 77 provinces so the two axes are comparable.
    agri_pool = sorted(r["agri_stress"] for r in crows.values() if r.get("agri_stress") is not None)
    ratios = sorted(p["ratio"] for p in prows if p.get("ratio") is not None)

    records = []
    for p in prows:
        prov = p["province_th"]
        c = crows.get(prov)
        agri_stress = (c or {}).get("agri_stress")
        agri_pctile = _percentile_rank(agri_stress, agri_pool) if agri_stress is not None else None
        ratio = p.get("ratio")
        contest_pctile = _percentile_rank(ratio, ratios) if ratio is not None else None

        comp = (c or {}).get("components") or {}
        crop_mix = (c or {}).get("crop_mix") or []
        top_crop = crop_mix[0]["crop"] if crop_mix and isinstance(crop_mix[0], dict) else None

        if agri_pctile is not None and contest_pctile is not None:
            squeeze_min = round(min(agri_pctile, contest_pctile), 2)
            squeeze_mean = round((agri_pctile + contest_pctile) / 2.0, 2)
            q = ("H" if agri_pctile >= MEDIAN else "L") + \
                ("H" if contest_pctile >= MEDIAN else "L")
            sq = agri_pctile >= TOP_THIRD and contest_pctile >= TOP_THIRD
        else:
            squeeze_min = squeeze_mean = q = None
            sq = False

        records.append({
            "province_th": prov,
            "region": p.get("region", ""),
            # portfolio-risk (agri) axis — MIXED-leaning-MEASURED (farm-gate price + drought), COMPUTED percentile
            "agri_pctile": agri_pctile,
            "agri_stress": agri_stress,
            "drought": (c or {}).get("drought"),
            "price_stress": (c or {}).get("price_stress"),
            "crop_dependence": (c or {}).get("crop_dependence"),
            "top_crop": top_crop,
            "price_coverage": comp.get("price_coverage"),
            "n_agri_branches": comp.get("n_branches"),
            # competitive-risk axis — MEASURED census inputs, COMPUTED percentile
            "contest_pctile": contest_pctile,
            "autox": p.get("autox"),
            "rivals": p.get("rivals"),
            "ratio": ratio,
            "leader": p.get("leader"),
            "n_districts": p.get("n_districts"),
            "n_outnumbered_districts": p.get("n_outnumbered_districts"),
            # combined
            "squeeze_min": squeeze_min,
            "squeeze_mean": squeeze_mean,
            "quadrant": q,
            "agri_squeeze": sq,
        })

    # worst-first by squeeze_min desc (a province leads only when its WEAKER axis is still high —
    # unambiguous double squeeze), then squeeze_mean desc, then province_th asc for a stable tie-break.
    records.sort(key=lambda r: (
        r["squeeze_min"] is None,
        -(r["squeeze_min"] if r["squeeze_min"] is not None else 0),
        -(r["squeeze_mean"] if r["squeeze_mean"] is not None else 0),
        r["province_th"],
    ))

    scored = [r for r in records if r["squeeze_min"] is not None]
    sq_rows = [r for r in scored if r["agri_squeeze"]]
    quad_counts = {}
    for r in scored:
        quad_counts[r["quadrant"]] = quad_counts.get(r["quadrant"], 0) + 1
    quad_counts = {k: quad_counts[k] for k in sorted(quad_counts)}
    worst = records[0] if records and records[0]["squeeze_min"] is not None else None

    # how much of the agri-squeeze alert set is priced from MEASURED farm-gate vs the global fallback —
    # so the honesty of the portfolio axis is legible on the alert set itself (not just per province).
    cov_rows = [r for r in sq_rows if isinstance(r.get("price_coverage"), (int, float))]
    min_cov = round(min((r["price_coverage"] for r in cov_rows), default=0.0), 2) if cov_rows else None

    meta = {
        "generated_by": "pipeline/build_agri_squeeze.py",
        "label": "THE AGRI-COMPETITIVE SQUEEZE — where the two objectives coincide on the AGRICULTURAL "
                 "axis: provinces whose FARM borrowers are stressed (crop_stress agri_stress: MEASURED "
                 "farm-gate price + OAE drought) AND where rivals dominate (peer_province rival:AutoX "
                 "ratio), for all 77 provinces. A DISTINCT cross from province_pressure.json's "
                 "household-DTI axis — this one sees the farm-income channel the DTI blend does not. "
                 "A pure deterministic JOIN; each axis a 0-100 percentile so the two are comparable. "
                 "Makes NO open / close / expand recommendation — a risk lens on the footprint we run.",
        "objective": "Serves BOTH standing objectives on the agri channel: portfolio risk #1 "
                     "(agri_pctile — farm-gate + drought) x competitive risk #2 (contest_pctile — "
                     "rival:AutoX). The intersection is a fragile FARM book where margin defence is "
                     "hardest. Complements, does not replace, the household-DTI double-pressure board.",
        "provenance": {
            "source_files": [
                "platform/data/crop_stress.json (gated, --check-reproducible)",
                "platform/data/peer_province.json (gated, --check-reproducible)",
            ],
            "agri_pctile": "COMPUTED percentile over a MIXED-leaning-MEASURED input — 0-100 rank of "
                           "crop_stress.json's agri_stress across the 77 provinces. agri_stress "
                           "combines a MEASURED Thai farm-gate price term (NABC live / OAE where a "
                           "crop is priced; World Bank GLOBAL proxy ONLY as a fallback for unpriced "
                           "crops), MEASURED OAE drought/rainfall, and crop dependence. "
                           "price_coverage (carried per province) is the fraction priced from "
                           "measured farm-gate. A RELATIVE rank, not an absolute default level.",
            "contest_pctile": "COMPUTED percentile over MEASURED inputs — 0-100 rank of "
                              "peer_province.json's rival:AutoX `ratio` across the 77 provinces (same "
                              "mid-rank-ties method as build_province_pressure, so this equals the "
                              "double-pressure card's contest_pctile). `ratio` = big-4 rival branch "
                              "count / AutoX branch count, both MEASURED; the census is a LOWER BOUND "
                              "(big-4 only; sub-scale + PICO operators not in the ratio).",
            "squeeze_min": "COMPUTED — min(agri_pctile, contest_pctile). High ONLY when the weaker "
                           "axis is also high → the honest 'high on BOTH' score; cannot be inflated "
                           "by one strong axis alone. The board's primary sort key (desc).",
            "squeeze_mean": "COMPUTED — mean of the two percentiles; a smoother combined index.",
            "quadrant": "COMPUTED, descriptive — median (>=%.0f) split on each axis: HH (agri-stressed "
                        "+ contested), HL (agri-stressed, less contested), LH (contested, less "
                        "agri-stressed), LL. First letter = agri portfolio, second = competitive." % MEDIAN,
            "agri_squeeze": "COMPUTED — true when BOTH percentiles are in the top third (>= %.2f). "
                            "The strict alert set: farm-borrower stress and rival dominance coincide. "
                            "null-axis provinces are never flagged." % TOP_THIRD,
            "raw_columns": "MEASURED/carried context for each province — agri_stress, drought, "
                           "price_stress, crop_dependence, top_crop, price_coverage, n_agri_branches "
                           "(from crop_stress); autox / rivals / ratio / leader / n_outnumbered_"
                           "districts (from the peer board). Carried so the board reads without a re-join.",
        },
        "caveats": [
            "Both axes are RELATIVE percentiles over the same 77 provinces, so every combined read "
            "(squeeze_min, squeeze_mean, quadrant, agri_squeeze) is a RANKING — 'worse than most "
            "provinces on both' — NOT a calibrated probability or an absolute level. An agri_squeeze "
            "province is a place to look first, never a verdict or an action.",
            "The agri portfolio axis is MIXED-leaning-MEASURED: MEASURED Thai farm-gate price + OAE "
            "drought where priced, with a World Bank GLOBAL price proxy ONLY as a fallback for "
            "unpriced crops. price_coverage is carried per province so the reader sees the mix; the "
            "competitive axis is COMPUTED over MEASURED census counts. The competitor census is a "
            "LOWER BOUND (big-4 only; sub-scale + PICO operators not in the ratio), so contest_pctile "
            "under-reads true local competitive density where small operators cluster.",
            "This is a DISTINCT cross from province_pressure.json — the portfolio axis here is "
            "AGRICULTURAL (farm income), not the household debt-to-income blend. A province can be "
            "agri-squeezed without being household double-pressure and vice versa; they answer "
            "different questions and are meant to be read side by side, not merged.",
            "The equal weighting of the two axes (squeeze_min / squeeze_mean treat agri and "
            "competitive pressure as equally important) is an editorial choice, not an estimate. The "
            "raw percentiles are carried so a reader can weight them differently.",
            "This layer makes NO open / close / expand recommendation. It is a risk lens on the "
            "EXISTING network (the two standing objectives), consistent with the consolidation "
            "posture — it points at where to look, not what to do.",
            "Provinces where AutoX has no branches (ratio == null) or crop_stress has no agri read "
            "(agri_stress == null) carry a null axis and are EXCLUDED from the percentile pool and "
            "the alert set — an honest gap, never a guessed 0.",
        ],
        "thresholds": {"top_third_pctile": TOP_THIRD, "median_pctile": MEDIAN},
        "record_format": "{province_th, region, agri_pctile, agri_stress, drought, price_stress, "
                         "crop_dependence, top_crop, price_coverage, n_agri_branches, contest_pctile, "
                         "autox, rivals, ratio, leader, n_districts, n_outnumbered_districts, "
                         "squeeze_min, squeeze_mean, quadrant, agri_squeeze}. provinces[] sorted by "
                         "squeeze_min desc (worst agri-squeeze first); null-axis provinces sort last.",
        "n_provinces": len(records),
        "n_provinces_scored": len(scored),
        "n_agri_squeeze": len(sq_rows),
        "agri_squeeze_provinces": [r["province_th"] for r in sq_rows],
        "quadrant_counts": quad_counts,
        "min_price_coverage_in_alert_set": min_cov,
        "worst_province": ({
            "province_th": worst["province_th"],
            "region": worst["region"],
            "squeeze_min": worst["squeeze_min"],
            "agri_pctile": worst["agri_pctile"],
            "contest_pctile": worst["contest_pctile"],
            "top_crop": worst["top_crop"],
            "leader": worst["leader"],
        } if worst else None),
        "agri_source": {
            "layer": "platform/data/crop_stress.json",
            "metric": "agri_stress (farm-gate price + OAE drought + crop dependence)",
            "provenance": (crop.get("meta") or {}).get("provenance"),
        },
        "peer_source": {
            "layer": "platform/data/peer_province.json",
            "metric": "ratio (rivals/autox)",
            "total_autox": (peer.get("meta") or {}).get("total_autox"),
            "total_rivals": (peer.get("meta") or {}).get("total_rivals"),
        },
    }
    return {"meta": meta, "provinces": records}


def run(check=False):
    obj = build()
    if obj is None:
        if check:
            print("SKIP: crop_stress.json or peer_province.json absent — "
                  "agri_squeeze not checkable (optional derived layer)")
            return 0
        print("missing input: needs platform/data/crop_stress.json AND platform/data/peer_province"
              ".json (run build_crop_stress.py + build_peer_province.py).")
        return 1
    text = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    if check:
        if not os.path.exists(OUT) or open(OUT, encoding="utf-8").read() != text:
            print("DRIFT: %s" % os.path.relpath(OUT, ROOT))
            return 1
        m = obj["meta"]
        print("OK: agri_squeeze.json reproduces (%d provinces, %d agri-squeeze)"
              % (m["n_provinces"], m["n_agri_squeeze"]))
        return 0
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(text)
    m = obj["meta"]
    print("wrote %d provinces -> platform/data/agri_squeeze.json (%.0f KB)"
          % (m["n_provinces"], len(text.encode("utf-8")) / 1024))
    print("  agri-squeeze (both axes top-third): %d — %s"
          % (m["n_agri_squeeze"], ", ".join(m["agri_squeeze_provinces"]) or "none"))
    print("  quadrant counts: %s" % m["quadrant_counts"])
    w = m.get("worst_province") or {}
    if w:
        print("  worst: %s (squeeze_min %.1f — agri %.1f pctile, contest %.1f pctile, grows %s, led by %s)"
              % (w["province_th"], w["squeeze_min"], w["agri_pctile"], w["contest_pctile"],
                 w["top_crop"], w["leader"]))
    if m.get("min_price_coverage_in_alert_set") is not None:
        print("  min farm-gate price coverage in alert set: %.0f%%"
              % (m["min_price_coverage_in_alert_set"] * 100))
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(
        description="agri-competitive squeeze (agri portfolio stress x competitive pressure)")
    ap.add_argument("--check", action="store_true")
    raise SystemExit(run(check=ap.parse_args().check))
