#!/usr/bin/env python3
"""
build_collateral_squeeze.py — THE COLLATERAL-COMPETITIVE SQUEEZE (obj #1 × obj #2, the THIRD cross)
===================================================================================================

THE QUESTION THIS ANSWERS
-------------------------
The command centre already carries TWO cross-objective boards, both crossing a portfolio-risk axis
with the SAME competitive axis (peer_province rival:AutoX `ratio`):
  * province_pressure.json ("double pressure") — portfolio axis = HOUSEHOLD debt-to-income +
    unemployment (the general consumer's balance sheet).
  * agri_squeeze.json ("agri squeeze") — portfolio axis = AGRICULTURAL stress (farm-gate price +
    drought — the farm-income channel).

But a title lender's core exposure is neither the household balance sheet nor the harvest — it is
the COLLATERAL it lends against, and how much of that pledged value it would actually recover on
default. AutoX's book is disproportionately MOTORCYCLE title (~50%) plus car/pickup title (~25%);
when used-vehicle resale prices soften, recovery value on the vehicle-title book softens with them,
and the motorcycle slice — which the BoT used-vehicle index cannot even price and which depreciates
fastest — carries extra structural risk. Where that COLLATERAL-recovery softening coincides with
heavy rival dominance is a THIRD, distinct squeeze: a book whose recovery value is trending the
wrong way exactly where margin defence is hardest, and no committed layer names it. This layer is a
pure risk lens on the EXISTING network and makes NO open/close/expand recommendation.

This is a pure, deterministic JOIN of two committed, gated, --check-reproducible files on the 77
provinces, keyed by Thai province name:
  * portfolio-risk (collateral) — collateral_outlook.json (`outlook`: ESTIMATED directional recovery
                                  outlook — softening = the collateral base trending the wrong way).
  * competitive-risk            — peer_province.json (rival:AutoX `ratio` — where rivals own the ground).
It invents no new measurement: it lines the two existing per-province axes up as 0-100 percentiles
so they are comparable, and flags the provinces high on BOTH. The competitive axis is computed with
the SAME mid-rank-ties percentile method build_province_pressure / build_agri_squeeze use on the same
`ratio`, so `contest_pctile` here is directly comparable to (and equal to) the other two boards'.

MEASURED vs ESTIMATED (the data-mandate — stated explicitly, repeated in meta)
------------------------------------------------------------------------------
  collat_risk_pctile = 0-100 percentile rank of NEGATED collateral_outlook.json `outlook` across the
                    77 provinces — high = recovery value SOFTENING most (the risk direction).
                    `outlook` is an ESTIMATED directional composite (~[-1,+1]): its price legs are
                    MEASURED (a World Bank GLOBAL gold-YoY proxy applied NATIONALLY, and the BoT UVPI
                    used-car/pickup resale-price direction — NATIONAL, measured), and its
                    per-province spread comes from the MEASURED motorcycle share of the DLT fleet
                    (moto_title_share). Because the two price legs are national constants, the
                    cross-province ordering of this axis is driven by moto-title exposure — i.e. this
                    ranks provinces most exposed to fast-depreciating, hard-to-price motorcycle-title
                    collateral in a nationally-softening used-vehicle market. The composite is
                    ESTIMATED; its inputs are measured. A RELATIVE rank, not an absolute recovery rate.
  contest_pctile  = 0-100 percentile rank of peer_province.json's rival:AutoX `ratio` across the
                    77 provinces. `ratio`'s inputs are MEASURED (AutoX branch count + the big-4
                    competitor census); the percentile is COMPUTED. The census is a LOWER BOUND
                    (big-4 only; sub-scale + PICO operators not in the ratio) — inherited caveat.
  squeeze_min     = min(collat_risk_pctile, contest_pctile). High ONLY when the WEAKER axis is also
                    high, so it is the honest "high on BOTH" score — never inflated by one axis. COMPUTED.
  squeeze_mean    = mean of the two percentiles — a smoother combined index. COMPUTED.
  quadrant        = median (>=50) split on each axis → HH / HL / LH / LL. COMPUTED, descriptive.
  collat_squeeze  = collat_risk_pctile >= 66.67 AND contest_pctile >= 66.67 (both in the top third).
                    The alert set. COMPUTED.

Both source axes are RELATIVE percentiles over the same 77 provinces, so the combined reads are
rankings ("worse than most provinces on both"), NOT calibrated probabilities. Nothing here is a
verdict; it is a place to look first.

DETERMINISTIC + NETWORK-FREE: reads two committed files, no network, no wall clock, no randomness.
Byte-exact reproducible -> carries --check (the QA gate runs it). Either input may be absent in a
stripped sandbox: build() returns None, --check skip-passes, a plain run exits non-zero with a
clear message (mirrors build_agri_squeeze.py / build_province_pressure.py).

Usage:
  python3 build_collateral_squeeze.py            # write platform/data/collateral_squeeze.json
  python3 build_collateral_squeeze.py --check    # verify byte-for-byte reproduce
"""
import argparse, json, os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "platform", "data")
COLLAT = os.path.join(DATA, "collateral_outlook.json")
PEER = os.path.join(DATA, "peer_province.json")
OUT = os.path.join(DATA, "collateral_squeeze.json")

# A percentile at or above this cut counts as "top third" for the collat_squeeze alert flag. Requiring
# BOTH axes above it is a deliberately strict intersection so the alert set stays small and meaningful.
TOP_THIRD = round(200.0 / 3.0, 2)  # 66.67
MEDIAN = 50.0                       # median split for the descriptive 2x2 quadrant label


def _load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def _percentile_rank(value, sorted_values):
    """0..100 percentile rank of `value` within `sorted_values`: fraction strictly below plus half
    of those equal (mid-rank ties). Deterministic. IDENTICAL method to build_province_pressure /
    build_agri_squeeze, so contest_pctile here equals the double-pressure / agri-squeeze cards'."""
    n = len(sorted_values)
    if n <= 1:
        return 50.0
    below = sum(1 for v in sorted_values if v < value)
    equal = sum(1 for v in sorted_values if v == value)
    return round(100.0 * (below + 0.5 * equal) / n, 2)


def build():
    if not (os.path.exists(COLLAT) and os.path.exists(PEER)):
        return None
    collat = _load(COLLAT)
    peer = _load(PEER)
    # collateral (portfolio) axis, keyed by Thai province name (collateral_outlook rows carry `province`).
    crows = {r["province"]: r for r in collat.get("provinces", []) if r.get("province")}
    prows = peer.get("provinces", [])
    if not crows or not prows:
        return None

    # percentile pools over the SAME 77 provinces so the two axes are comparable. The collateral RISK
    # axis is the NEGATED outlook: softening (a low/negative outlook) → a HIGH risk percentile.
    risk_pool = sorted(-r["outlook"] for r in crows.values() if r.get("outlook") is not None)
    ratios = sorted(p["ratio"] for p in prows if p.get("ratio") is not None)

    records = []
    for p in prows:
        prov = p["province_th"]
        c = crows.get(prov)
        outlook = (c or {}).get("outlook")
        collat_risk_pctile = _percentile_rank(-outlook, risk_pool) if outlook is not None else None
        ratio = p.get("ratio")
        contest_pctile = _percentile_rank(ratio, ratios) if ratio is not None else None

        if collat_risk_pctile is not None and contest_pctile is not None:
            squeeze_min = round(min(collat_risk_pctile, contest_pctile), 2)
            squeeze_mean = round((collat_risk_pctile + contest_pctile) / 2.0, 2)
            q = ("H" if collat_risk_pctile >= MEDIAN else "L") + \
                ("H" if contest_pctile >= MEDIAN else "L")
            sq = collat_risk_pctile >= TOP_THIRD and contest_pctile >= TOP_THIRD
        else:
            squeeze_min = squeeze_mean = q = None
            sq = False

        records.append({
            "province_th": prov,
            "region": p.get("region", ""),
            # portfolio-risk (collateral) axis — ESTIMATED directional outlook (measured price legs +
            # measured moto share), COMPUTED percentile on the softening direction
            "collat_risk_pctile": collat_risk_pctile,
            "outlook": outlook,
            "collateral_score": (c or {}).get("collateral_score"),
            "gold_yoy": (c or {}).get("gold_yoy"),
            "used_veh_yoy": (c or {}).get("used_veh_yoy"),
            "moto_title_share": (c or {}).get("moto_title_share"),
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
            "collat_squeeze": sq,
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
    sq_rows = [r for r in scored if r["collat_squeeze"]]
    quad_counts = {}
    for r in scored:
        quad_counts[r["quadrant"]] = quad_counts.get(r["quadrant"], 0) + 1
    quad_counts = {k: quad_counts[k] for k in sorted(quad_counts)}
    worst = records[0] if records and records[0]["squeeze_min"] is not None else None

    # mean measured motorcycle-title share across the alert set — the structural driver of this axis's
    # cross-province ordering (the two price legs are national constants), so the reader sees what the
    # collateral-risk ranking actually keys on. None when no alert-set row carries a moto share.
    moto_rows = [r for r in sq_rows if isinstance(r.get("moto_title_share"), (int, float))]
    mean_moto = round(sum(r["moto_title_share"] for r in moto_rows) / len(moto_rows), 4) if moto_rows else None

    cnat = collat.get("national") or {}
    meta = {
        "generated_by": "pipeline/build_collateral_squeeze.py",
        "label": "THE COLLATERAL-COMPETITIVE SQUEEZE — where the two objectives coincide on the "
                 "COLLATERAL axis: provinces whose title-loan collateral RECOVERY value is softening "
                 "(collateral_outlook `outlook`: ESTIMATED directional composite of a MEASURED gold "
                 "direction, MEASURED BoT used-vehicle resale-price direction, and MEASURED "
                 "motorcycle-title fleet share) AND where rivals dominate (peer_province rival:AutoX "
                 "ratio), for all 77 provinces. A THIRD, DISTINCT cross from the household-DTI "
                 "(province_pressure) and agri (agri_squeeze) boards — this one sees the collateral "
                 "recovery-value channel neither of those axes captures. A pure deterministic JOIN; "
                 "each axis a 0-100 percentile so the two are comparable. Makes NO open / close / "
                 "expand recommendation — a risk lens on the footprint we run.",
        "objective": "Serves BOTH standing objectives on the collateral channel: portfolio risk #1 "
                     "(collat_risk_pctile — recovery-value softening) x competitive risk #2 "
                     "(contest_pctile — rival:AutoX). The intersection is a book whose collateral is "
                     "trending the wrong way where margin defence is hardest. Complements, does not "
                     "replace, the household-DTI and agri squeeze boards — the third portfolio channel.",
        "provenance": {
            "source_files": [
                "platform/data/collateral_outlook.json (gated, --check-reproducible)",
                "platform/data/peer_province.json (gated, --check-reproducible)",
            ],
            "collat_risk_pctile": "COMPUTED percentile over an ESTIMATED directional input — 0-100 "
                                  "rank of NEGATED collateral_outlook.json `outlook` across the 77 "
                                  "provinces (high = recovery value softening most). `outlook` is an "
                                  "ESTIMATED composite: a MEASURED World Bank GLOBAL gold-YoY proxy "
                                  "(applied nationally), the MEASURED BoT UVPI used-car/pickup "
                                  "resale-price direction (national), and the MEASURED motorcycle "
                                  "share of the DLT registered-vehicle fleet (moto_title_share). "
                                  "Because the two price legs are national constants, the "
                                  "CROSS-PROVINCE ordering of this axis is driven by moto-title "
                                  "exposure. A RELATIVE rank, not an absolute recovery rate.",
            "contest_pctile": "COMPUTED percentile over MEASURED inputs — 0-100 rank of "
                              "peer_province.json's rival:AutoX `ratio` across the 77 provinces (same "
                              "mid-rank-ties method as build_province_pressure / build_agri_squeeze, "
                              "so this equals the double-pressure and agri-squeeze cards' "
                              "contest_pctile). `ratio` = big-4 rival branch count / AutoX branch "
                              "count, both MEASURED; the census is a LOWER BOUND (big-4 only; "
                              "sub-scale + PICO operators not in the ratio).",
            "squeeze_min": "COMPUTED — min(collat_risk_pctile, contest_pctile). High ONLY when the "
                           "weaker axis is also high → the honest 'high on BOTH' score; cannot be "
                           "inflated by one strong axis alone. The board's primary sort key (desc).",
            "squeeze_mean": "COMPUTED — mean of the two percentiles; a smoother combined index.",
            "quadrant": "COMPUTED, descriptive — median (>=%.0f) split on each axis: HH (collateral-"
                        "softening + contested), HL (softening, less contested), LH (contested, less "
                        "softening), LL. First letter = collateral portfolio, second = competitive." % MEDIAN,
            "collat_squeeze": "COMPUTED — true when BOTH percentiles are in the top third (>= %.2f). "
                              "The strict alert set: collateral-recovery softening and rival "
                              "dominance coincide. null-axis provinces are never flagged." % TOP_THIRD,
            "raw_columns": "MEASURED/carried context for each province — outlook, collateral_score, "
                           "gold_yoy, used_veh_yoy, moto_title_share (from collateral_outlook); autox "
                           "/ rivals / ratio / leader / n_outnumbered_districts (from the peer board). "
                           "Carried so the board reads without a re-join.",
        },
        "caveats": [
            "Both axes are RELATIVE percentiles over the same 77 provinces, so every combined read "
            "(squeeze_min, squeeze_mean, quadrant, collat_squeeze) is a RANKING — 'worse than most "
            "provinces on both' — NOT a calibrated probability or an absolute level. A collat_squeeze "
            "province is a place to look first, never a verdict or an action.",
            "The collateral portfolio axis is an ESTIMATED directional outlook, NOT a measured "
            "recovery rate or loss-given-default. Its price legs are measured but NATIONAL (one "
            "global gold proxy and one BoT used-vehicle index for all provinces), so the "
            "CROSS-PROVINCE ordering of this axis is driven by the MEASURED motorcycle-title fleet "
            "share — it ranks provinces most exposed to fast-depreciating, hard-to-price "
            "motorcycle-title collateral in a nationally-softening used-vehicle market. The gold leg "
            "is a GLOBAL price proxy, not a Thai gold-shop quote; the BoT UVPI covers car/pickup, not "
            "motorcycles.",
            "This is a DISTINCT cross from province_pressure.json (household debt-to-income) and "
            "agri_squeeze.json (farm income) — the portfolio axis here is the COLLATERAL recovery "
            "channel. A province can be collateral-squeezed without being on either other board and "
            "vice versa; the three answer different questions and are meant to be read side by side, "
            "not merged.",
            "The equal weighting of the two axes (squeeze_min / squeeze_mean treat collateral and "
            "competitive pressure as equally important) is an editorial choice, not an estimate. The "
            "raw percentiles are carried so a reader can weight them differently.",
            "This layer makes NO open / close / expand recommendation. It is a risk lens on the "
            "EXISTING network (the two standing objectives), consistent with the consolidation "
            "posture — it points at where to look, not what to do.",
            "Provinces where AutoX has no branches (ratio == null) or collateral_outlook has no read "
            "(outlook == null) carry a null axis and are EXCLUDED from the percentile pool and the "
            "alert set — an honest gap, never a guessed 0.",
        ],
        "thresholds": {"top_third_pctile": TOP_THIRD, "median_pctile": MEDIAN},
        "record_format": "{province_th, region, collat_risk_pctile, outlook, collateral_score, "
                         "gold_yoy, used_veh_yoy, moto_title_share, contest_pctile, autox, rivals, "
                         "ratio, leader, n_districts, n_outnumbered_districts, squeeze_min, "
                         "squeeze_mean, quadrant, collat_squeeze}. provinces[] sorted by squeeze_min "
                         "desc (worst collateral-squeeze first); null-axis provinces sort last.",
        "n_provinces": len(records),
        "n_provinces_scored": len(scored),
        "n_collat_squeeze": len(sq_rows),
        "collat_squeeze_provinces": [r["province_th"] for r in sq_rows],
        "quadrant_counts": quad_counts,
        "mean_moto_title_share_in_alert_set": mean_moto,
        "worst_province": ({
            "province_th": worst["province_th"],
            "region": worst["region"],
            "squeeze_min": worst["squeeze_min"],
            "collat_risk_pctile": worst["collat_risk_pctile"],
            "contest_pctile": worst["contest_pctile"],
            "moto_title_share": worst["moto_title_share"],
            "leader": worst["leader"],
        } if worst else None),
        "collateral_source": {
            "layer": "platform/data/collateral_outlook.json",
            "metric": "outlook (directional recovery-value composite: gold + BoT UVPI + moto share)",
            "national_gold_yoy": cnat.get("gold_yoy"),
            "national_used_veh_yoy_blended": cnat.get("used_veh_yoy_blended"),
            "used_veh_price_period": cnat.get("used_veh_price_period"),
            "provenance": (collat.get("meta") or {}).get("provenance"),
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
            print("SKIP: collateral_outlook.json or peer_province.json absent — "
                  "collateral_squeeze not checkable (optional derived layer)")
            return 0
        print("missing input: needs platform/data/collateral_outlook.json AND platform/data/"
              "peer_province.json (run build_collateral_outlook.py + build_peer_province.py).")
        return 1
    text = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    if check:
        if not os.path.exists(OUT) or open(OUT, encoding="utf-8").read() != text:
            print("DRIFT: %s" % os.path.relpath(OUT, ROOT))
            return 1
        m = obj["meta"]
        print("OK: collateral_squeeze.json reproduces (%d provinces, %d collat-squeeze)"
              % (m["n_provinces"], m["n_collat_squeeze"]))
        return 0
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(text)
    m = obj["meta"]
    print("wrote %d provinces -> platform/data/collateral_squeeze.json (%.0f KB)"
          % (m["n_provinces"], len(text.encode("utf-8")) / 1024))
    print("  collat-squeeze (both axes top-third): %d — %s"
          % (m["n_collat_squeeze"], ", ".join(m["collat_squeeze_provinces"]) or "none"))
    print("  quadrant counts: %s" % m["quadrant_counts"])
    w = m.get("worst_province") or {}
    if w:
        print("  worst: %s (squeeze_min %.1f — collat-risk %.1f pctile, contest %.1f pctile, "
              "moto share %s, led by %s)"
              % (w["province_th"], w["squeeze_min"], w["collat_risk_pctile"], w["contest_pctile"],
                 w["moto_title_share"], w["leader"]))
    if m.get("mean_moto_title_share_in_alert_set") is not None:
        print("  mean moto-title share in alert set: %.0f%%"
              % (m["mean_moto_title_share_in_alert_set"] * 100))
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(
        description="collateral-competitive squeeze (collateral recovery softening x competitive pressure)")
    ap.add_argument("--check", action="store_true")
    raise SystemExit(run(check=ap.parse_args().check))
