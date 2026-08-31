#!/usr/bin/env python3
"""
build_province_pressure.py — COMBINED PROVINCE PRESSURE (the two objectives, one board)
=======================================================================================

THE QUESTION THIS ANSWERS
-------------------------
The platform already scores the two standing objectives SEPARATELY, province by province:

  * portfolio risk  — province_stress_index.json (composite_stress: an NSO debt-to-income +
                      unemployment percentile blend — where BORROWERS are structurally stressed).
  * competitive risk — peer_province.json (rival:AutoX ratio + how many districts we are
                      outnumbered in — where RIVALS already own the ground around our branches).

What no committed layer answers is the question a strategy director asks FIRST: **where do the
two coincide?** A province that is both borrower-stressed AND rival-dominated is under pressure
from both directions at once — the portfolio is fragile exactly where margin defence is hardest.
That intersection is the single sharpest cross-objective signal for the existing network, and it
is precisely the "two questions on one screen" the command centre is meant to lead with.

This layer is a pure, deterministic JOIN of those two committed, gated, --check-reproducible
files on the 77 provinces. It invents no new measurement: it lines the two existing per-province
axes up side by side, expresses each as a 0-100 percentile so they are comparable, and flags the
provinces that sit high on BOTH. It makes NO open / close / expand recommendation — it is a risk
lens on the footprint we already run.

MEASURED vs ESTIMATED (the data-mandate — stated explicitly, repeated in meta)
------------------------------------------------------------------------------
  stress_pctile   = composite_stress carried verbatim from province_stress_index.json.
                    ESTIMATED — a 0-100 percentile blend of two MEASURED NSO inputs (SES
                    debt-to-income + LFS unemployment). A RELATIVE rank, not an absolute level.
  contest_pctile  = 0-100 percentile rank of peer_province.json's rival:AutoX `ratio` across the
                    77 provinces. The ratio's inputs are MEASURED (AutoX branch count + the big-4
                    competitor census); the percentile itself is COMPUTED here. The census is a
                    LOWER BOUND (Google caps ~60/query; Heng is a sample) — inherited caveat.
  both_min        = min(stress_pctile, contest_pctile). A province scores high here ONLY when its
                    WEAKER axis is still high, so it is the honest "high on BOTH" score — it can
                    never be inflated by one strong axis alone. COMPUTED.
  both_mean       = mean of the two percentiles — a smoother combined index. COMPUTED.
  quadrant        = median (>=50) split on each axis → HH / HL / LH / LL. COMPUTED, descriptive.
  double_pressure = stress_pctile >= 66.67 AND contest_pctile >= 66.67 (both in the top third).
                    The alert set. COMPUTED.

Both source axes are RELATIVE percentiles over the same 77 provinces, so the combined reads are
rankings ("worse than most provinces on both"), NOT calibrated probabilities. Nothing here is a
verdict; it is a place to look first.

DETERMINISTIC + NETWORK-FREE: reads two committed files, no network, no wall clock, no
randomness. Byte-exact reproducible -> carries --check (the QA gate runs it). Either input may be
absent in a stripped sandbox: build() returns None, --check skip-passes, a plain run exits
non-zero with a clear message (mirrors build_peer_province.py).

Usage:
  python3 build_province_pressure.py            # write platform/data/province_pressure.json
  python3 build_province_pressure.py --check    # verify byte-for-byte reproduce
"""
import argparse, json, os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "platform", "data")
STRESS = os.path.join(DATA, "province_stress_index.json")
PEER = os.path.join(DATA, "peer_province.json")
# MEASURED real-book axis (optional additive join). tape_real.json is gated + --check-reproducible;
# its province aggregates are the real loan tape (382,735 accounts, no-PII, floored at MIN_CELL).
TAPE = os.path.join(DATA, "tape_real.json")
OUT = os.path.join(DATA, "province_pressure.json")

# Disclosure floor for the real tape (see .claude/skills/tape-pii-floor). tape_real.json is already
# floored at ingest; we re-assert it here so a province book row is NEVER carried on < 30 accounts.
MIN_CELL = 30

# A percentile at or above this cut counts as "top third" for the double_pressure alert flag.
# 100/3 = 33.3% of provinces sit above it on a single axis; requiring BOTH axes above it is a
# deliberately strict intersection so the alert set stays small and meaningful.
TOP_THIRD = round(200.0 / 3.0, 2)  # 66.67
# Median split for the descriptive 2x2 quadrant label (>= => "high").
MEDIAN = 50.0


def _load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def _percentile_rank(value, sorted_values):
    """0..100 percentile rank of `value` within `sorted_values`: fraction strictly below plus
    half of those equal (mid-rank ties). Deterministic. Identical method to build_province_stress
    / build_household_risk, so contest_pctile is directly comparable to the carried stress_pctile."""
    n = len(sorted_values)
    if n <= 1:
        return 50.0
    below = sum(1 for v in sorted_values if v < value)
    equal = sum(1 for v in sorted_values if v == value)
    return round(100.0 * (below + 0.5 * equal) / n, 2)


def build():
    if not (os.path.exists(STRESS) and os.path.exists(PEER)):
        return None
    stress = _load(STRESS)
    peer = _load(PEER)
    # portfolio-risk axis, keyed by Thai province name
    srows = {r["province"]: r for r in stress.get("provinces", [])}
    prows = peer.get("provinces", [])
    if not srows or not prows:
        return None

    # MEASURED real-book context (optional): tape_real.json province aggregates, keyed by Thai
    # province name. os_sum = outstanding ฿ (LIVE + 180+ legacy combined book value); npl_live_os_pct
    # = the LIVE book's NPL, outstanding-weighted (the actionable read — reported apart from legacy).
    # Absent in a stripped sandbox → book fields stay null (an honest gap, never guessed); the gate
    # runs in CI where tape_real.json is committed, so --check reproduces byte-exact there.
    tape_pv, tape_meta, n_book_suppressed = {}, {}, 0
    if os.path.exists(TAPE):
        tape = _load(TAPE)
        tape_meta = tape.get("meta") or {}
        for prov, v in (tape.get("provinces") or {}).items():
            if not isinstance(v, dict):
                continue
            if (v.get("n") or 0) < MIN_CELL:
                n_book_suppressed += 1          # never carry a book row below the disclosure floor
                continue
            tape_pv[prov] = v

    # competitive-risk axis: rival:AutoX ratio per province (null where autox == 0 → no footprint
    # to be outnumbered in; excluded from the percentile pool and never flagged double_pressure).
    ratios = sorted(p["ratio"] for p in prows if p.get("ratio") is not None)

    # MEASURED-book scale pool: outstanding ฿ across the provinces the peer board also covers, so
    # book_pctile answers "how much of AutoX's real book actually sits here" on the same 77-province
    # scale as the two pressure axes. COMPUTED over a MEASURED input.
    book_os_pool = sorted(
        float(tape_pv[p["province_th"]]["os_sum"])
        for p in prows
        if p["province_th"] in tape_pv and tape_pv[p["province_th"]].get("os_sum") is not None
    )

    records = []
    for p in prows:
        prov = p["province_th"]
        s = srows.get(prov)
        if s is None:
            # province present in the peer board but not the stress index — carry it with a null
            # portfolio axis rather than dropping it (honest gap, never a guessed 0).
            stress_pctile = None
        else:
            stress_pctile = s.get("composite_stress")
        ratio = p.get("ratio")
        contest_pctile = _percentile_rank(ratio, ratios) if ratio is not None else None

        # MEASURED real-book context for this province (null when tape absent or below MIN_CELL).
        tv = tape_pv.get(prov)
        book_os = round(float(tv["os_sum"])) if tv and tv.get("os_sum") is not None else None
        book_npl_os_pct = tv.get("npl_live_os_pct") if tv else None
        book_n = tv.get("n") if tv else None
        book_pctile = (_percentile_rank(float(book_os), book_os_pool)
                       if book_os is not None and book_os_pool else None)

        if stress_pctile is not None and contest_pctile is not None:
            both_min = round(min(stress_pctile, contest_pctile), 2)
            both_mean = round((stress_pctile + contest_pctile) / 2.0, 2)
            q = ("H" if stress_pctile >= MEDIAN else "L") + \
                ("H" if contest_pctile >= MEDIAN else "L")
            dbl = stress_pctile >= TOP_THIRD and contest_pctile >= TOP_THIRD
        else:
            both_min = both_mean = q = None
            dbl = False

        records.append({
            "province_th": prov,
            "region": p.get("region", ""),
            # portfolio-risk axis (ESTIMATED percentile over MEASURED NSO inputs)
            "stress_pctile": stress_pctile,
            "debt_to_income": (s or {}).get("debt_to_income"),
            "unemployment_rate": (s or {}).get("unemployment_rate"),
            # competitive-risk axis (MEASURED census inputs, COMPUTED percentile)
            "contest_pctile": contest_pctile,
            "autox": p.get("autox"),
            "rivals": p.get("rivals"),
            "ratio": ratio,
            "leader": p.get("leader"),
            "autox_rank": p.get("autox_rank"),
            "n_ranked": p.get("n_ranked"),
            "n_districts": p.get("n_districts"),
            "n_outnumbered_districts": p.get("n_outnumbered_districts"),
            # MEASURED sub-scale-competitor CONTEXT (FPO registry, carried verbatim from
            # peer_province.json .pico): the licensed พิโกไฟแนนซ์ (PICO-finance) operator count for
            # the province — a DISTINCT small-ticket rival class the big-4 contest_pctile does NOT
            # count. Carried as context only (like the book columns), NEVER folded into the score,
            # so a double-pressure province that ALSO sits atop a dense sub-scale field is visible.
            # int / MEASURED-0 / null (registry absent or province unmatched) — inherited verbatim.
            "pico": p.get("pico"),
            # MEASURED real-book context (tape_real.json; live-book NPL reported apart from 180+ legacy)
            "book_os": book_os,
            "book_npl_os_pct": book_npl_os_pct,
            "book_n": book_n,
            "book_pctile": book_pctile,
            # combined
            "both_min": both_min,
            "both_mean": both_mean,
            "quadrant": q,
            "double_pressure": dbl,
        })

    # worst-first by both_min desc (a province leads only when its WEAKER axis is still high —
    # unambiguous double pressure), then both_mean desc, then province_th asc for a stable tie-break.
    # Records missing either axis (both_min is None) sort last.
    records.sort(key=lambda r: (
        r["both_min"] is None,
        -(r["both_min"] if r["both_min"] is not None else 0),
        -(r["both_mean"] if r["both_mean"] is not None else 0),
        r["province_th"],
    ))

    scored = [r for r in records if r["both_min"] is not None]
    dbl_rows = [r for r in scored if r["double_pressure"]]
    quad_counts = {}
    for r in scored:
        quad_counts[r["quadrant"]] = quad_counts.get(r["quadrant"], 0) + 1
    quad_counts = {k: quad_counts[k] for k in sorted(quad_counts)}
    worst = records[0] if records and records[0]["both_min"] is not None else None

    # MEASURED book carried by the double-pressure alert set — the concrete "how much real ฿ sits in
    # the worst-pressured provinces, at what live NPL" read. Outstanding-weighted so the NPL is honest.
    dbl_book_rows = [r for r in dbl_rows if r.get("book_os") is not None]
    dbl_book_os = sum(r["book_os"] for r in dbl_book_rows) or 0
    dbl_book_npl_num = sum((r["book_os"] * (r.get("book_npl_os_pct") or 0.0))
                           for r in dbl_book_rows if r.get("book_npl_os_pct") is not None)
    dbl_book_os_with_npl = sum(r["book_os"] for r in dbl_book_rows
                               if r.get("book_npl_os_pct") is not None)
    dbl_book_npl_pct = (round(dbl_book_npl_num / dbl_book_os_with_npl, 2)
                        if dbl_book_os_with_npl else None)

    # MEASURED sub-scale-competitor field carried by the double-pressure alert set — how many
    # licensed PICO-finance operators cluster in the worst-pressured provinces. This is the
    # DISTINCT rival class the big-4 contest_pctile does NOT count (the caveat's documented
    # under-read), surfaced here as CONTEXT so a fragile+contested province that ALSO faces a
    # dense sub-scale field is visible. Carried, never folded into the score.
    dbl_pico_rows = [r for r in dbl_rows if isinstance(r.get("pico"), int)]
    dbl_pico_total = sum(r["pico"] for r in dbl_pico_rows)
    n_dbl_pico_present = sum(1 for r in dbl_pico_rows if r["pico"] > 0)
    # PICO context available at all (any province carries an int count) — gates the surfacing.
    pico_present_any = any(isinstance(r.get("pico"), int) for r in records)
    peer_pico_src = (peer.get("meta") or {}).get("pico_source") or {}

    meta = {
        "generated_by": "pipeline/build_province_pressure.py",
        "label": "COMBINED PROVINCE PRESSURE — where the two objectives coincide: provinces that "
                 "are BOTH borrower-stressed (portfolio risk) AND rival-dominated (competitive "
                 "risk), for all 77 provinces. A pure deterministic JOIN of province_stress_index"
                 ".json (composite_stress) and peer_province.json (rival:AutoX ratio); each axis "
                 "expressed as a 0-100 percentile so the two are comparable. Each province also "
                 "carries its MEASURED real-book context (tape_real.json: outstanding ฿ + LIVE-book "
                 "NPL) so the ranking can be read in real money, not just ranks. Makes NO open / "
                 "close / expand recommendation — a risk lens on the footprint we already run.",
        "objective": "Serves BOTH standing objectives at once (the command-centre's 'two questions "
                     "on one screen'): portfolio risk #1 (stress_pctile) x competitive risk #2 "
                     "(contest_pctile). The intersection is where a fragile portfolio meets the "
                     "hardest margin defence.",
        "provenance": {
            "source_files": [
                "platform/data/province_stress_index.json (gated, --check-reproducible)",
                "platform/data/peer_province.json (gated, --check-reproducible)",
                "platform/data/tape_real.json (gated, --check-reproducible; MEASURED book context)",
            ],
            "stress_pctile": "ESTIMATED — composite_stress carried verbatim from "
                             "province_stress_index.json: a 0-100 percentile blend (0.5*DTI + "
                             "0.5*unemployment percentile) of two MEASURED NSO inputs (SES "
                             "debt-to-income + LFS unemployment). A RELATIVE rank across the 77 "
                             "provinces, not an absolute default level.",
            "contest_pctile": "COMPUTED percentile over MEASURED inputs — 0-100 percentile rank of "
                              "peer_province.json's rival:AutoX `ratio` across the 77 provinces "
                              "(same mid-rank-ties method as the stress percentile, so the two are "
                              "directly comparable). `ratio` = big-4 rival branch count / AutoX "
                              "branch count, both MEASURED; the census is a LOWER BOUND (Google "
                              "caps ~60/query/province; Heng is a sample) — inherited caveat.",
            "pico": "MEASURED CONTEXT (not an axis) — the province's licensed พิโกไฟแนนซ์ "
                    "(PICO-finance) operator count, carried verbatim from peer_province.json .pico "
                    "(FPO open-data registry). A DISTINCT small-ticket rival class the big-4 "
                    "contest_pctile does NOT count. Carried so a double-pressure province that ALSO "
                    "sits atop a dense sub-scale field is visible; deliberately NEVER folded into "
                    "contest_pctile/both_min/double_pressure (mixing a province-count registry into "
                    "the haversine big-4 ratio would be dishonest). int / MEASURED-0 / null.",
            "both_min": "COMPUTED — min(stress_pctile, contest_pctile). High ONLY when the weaker "
                        "axis is also high → the honest 'high on BOTH' score; cannot be inflated by "
                        "one strong axis alone. The board's primary sort key (desc).",
            "both_mean": "COMPUTED — mean of the two percentiles; a smoother combined index.",
            "quadrant": "COMPUTED, descriptive — median (>=%.0f) split on each axis: HH (stressed "
                        "+ contested), HL (stressed, less contested), LH (contested, less "
                        "stressed), LL. First letter = portfolio, second = competitive." % MEDIAN,
            "double_pressure": "COMPUTED — true when BOTH percentiles are in the top third "
                               "(>= %.2f). The strict alert set: borrower stress and rival "
                               "dominance coincide. null-axis provinces are never flagged."
                               % TOP_THIRD,
            "raw_columns": "MEASURED/carried context for each province — debt_to_income + "
                           "unemployment_rate (NSO, from the stress index), autox / rivals / ratio "
                           "/ leader / autox_rank / n_outnumbered_districts (from the peer board). "
                           "Carried so the board is readable without re-joining the two sources.",
            "book_os": "MEASURED — the province's outstanding book value in ฿ (os_sum) from the real "
                       "loan tape (tape_real.json). The COMBINED book (live + 180+ legacy). Carried so "
                       "the pressure ranking can be read against where AutoX actually holds ฿ at risk "
                       "— a percentile rank is not a scale, and ฿ exposure is the scale that matters. "
                       "null where tape_real.json is absent or the province is below MIN_CELL=%d "
                       "accounts (never carried below the disclosure floor)." % MIN_CELL,
            "book_npl_os_pct": "MEASURED — the LIVE book's NPL, outstanding-weighted (npl_live_os_pct "
                               "from tape_real.json). The actionable credit-quality read, reported "
                               "APART from the 180+ legacy book (a blended figure is not actionable). "
                               "This is a real, absolute level — NOT a percentile.",
            "book_n": "MEASURED — the province's real account count in the tape (>= MIN_CELL=%d)." % MIN_CELL,
            "book_pctile": "COMPUTED over a MEASURED input — 0-100 percentile rank of book_os across "
                           "the provinces the peer board covers (same mid-rank-ties method as the two "
                           "pressure axes, so ฿-scale is directly comparable to stress/contest). "
                           "Lets the reader ask 'is this a big-book province too?' on one scale.",
        },
        "caveats": [
            "Both axes are RELATIVE percentiles over the same 77 provinces, so every combined read "
            "(both_min, both_mean, quadrant, double_pressure) is a RANKING — 'worse than most "
            "provinces on both' — NOT a calibrated probability or an absolute level. A double_"
            "pressure province is a place to look first, never a verdict or an action.",
            "The portfolio axis (stress_pctile) is ESTIMATED (a percentile blend), while the "
            "competitive axis's INPUTS are MEASURED (branch census) though its percentile is "
            "COMPUTED. The combined score is therefore MIXED — it inherits the ESTIMATED label. "
            "The competitor census is a LOWER BOUND (big-4 only; sub-scale local operators and the "
            "distinct PICO class are NOT in the ratio), so contest_pctile under-reads true local "
            "competitive density, more so in provinces where small operators cluster. The MEASURED "
            "per-province licensed-PICO count is now carried as a CONTEXT column (`pico`, NOT folded "
            "into the score) so this under-read is visible per province — a double-pressure province "
            "that also sits atop a dense sub-scale field can be read directly off the board.",
            "The equal weighting of the two axes (both_min / both_mean treat portfolio and "
            "competitive pressure as equally important) is an editorial choice, not an estimate. "
            "The raw percentiles are carried so a reader can weight them differently.",
            "This layer makes NO open / close / expand recommendation. It is a risk lens on the "
            "EXISTING network (the two standing objectives), consistent with the consolidation "
            "posture — it points at where to look, not what to do.",
            "Provinces where AutoX has no branches assigned in the census (ratio == null) carry a "
            "null competitive axis and are EXCLUDED from the percentile pool and the alert set — "
            "an honest gap, never a guessed 0. (Today every one of the 77 provinces has an AutoX "
            "footprint, so the pool is complete.)",
            "The MEASURED book columns (book_os / book_npl_os_pct / book_pctile) are CONTEXT, not a "
            "third pressure axis: they do NOT change double_pressure, both_min, both_mean or the sort "
            "order. They answer a separate question — 'of the double-pressure provinces, which hold "
            "the most real ฿ and the worst live NPL?' — so an abstract percentile ranking can be read "
            "in real money. book_npl_os_pct is the LIVE book only; the 180+ legacy book is held apart "
            "(see tape_real.json) and is never blended in here. book_os is the combined outstanding.",
        ],
        "thresholds": {"top_third_pctile": TOP_THIRD, "median_pctile": MEDIAN},
        "record_format": "{province_th, region, stress_pctile, debt_to_income, unemployment_rate, "
                         "contest_pctile, autox, rivals, ratio, leader, autox_rank, n_ranked, "
                         "n_districts, n_outnumbered_districts, pico, book_os, book_npl_os_pct, "
                         "book_n, book_pctile, both_min, both_mean, quadrant, double_pressure}. "
                         "provinces[] sorted by both_min desc (worst double pressure first); "
                         "null-axis provinces sort last. The pico and book_* columns are MEASURED "
                         "context (peer_province.json / tape_real.json), not a sort or alert axis.",
        "n_provinces": len(records),
        "n_provinces_scored": len(scored),
        "n_double_pressure": len(dbl_rows),
        "double_pressure_provinces": [r["province_th"] for r in dbl_rows],
        "quadrant_counts": quad_counts,
        "worst_province": ({
            "province_th": worst["province_th"],
            "region": worst["region"],
            "both_min": worst["both_min"],
            "stress_pctile": worst["stress_pctile"],
            "contest_pctile": worst["contest_pctile"],
            "ratio": worst["ratio"],
            "leader": worst["leader"],
        } if worst else None),
        "stress_source": {
            "layer": "platform/data/province_stress_index.json",
            "metric": "composite_stress",
            "source": (stress.get("meta") or {}).get("source"),
        },
        "peer_source": {
            "layer": "platform/data/peer_province.json",
            "metric": "ratio (rivals/autox)",
            "total_autox": (peer.get("meta") or {}).get("total_autox"),
            "total_rivals": (peer.get("meta") or {}).get("total_rivals"),
        },
        "book_source": {
            "layer": "platform/data/tape_real.json",
            "metric": "os_sum (outstanding ฿, combined book) + npl_live_os_pct (LIVE-book NPL, os-weighted)",
            "provenance": "MEASURED — real loan tape, no-PII province aggregates (>= MIN_CELL).",
            "mob_anchor": tape_meta.get("mob_anchor"),
            "min_cell": MIN_CELL,
            "n_provinces_with_book": len(book_os_pool),
            "n_book_suppressed": n_book_suppressed,
        } if tape_pv else None,
        # concrete money read on the alert set: total outstanding + os-weighted LIVE NPL across the
        # double-pressure provinces (MEASURED). null when tape absent. Lets the thesis say ฿, not ranks.
        "double_pressure_book": ({
            "n_provinces": len(dbl_book_rows),
            "book_os_total": dbl_book_os,
            "book_npl_os_pct": dbl_book_npl_pct,
        } if dbl_book_rows else None),
        # MEASURED sub-scale-competitor context on the alert set: how many licensed PICO-finance
        # operators cluster in the double-pressure provinces (the distinct class the big-4
        # contest_pctile misses). Context only — never a third pressure axis. null when the FPO
        # registry is absent from the sandbox.
        "double_pressure_pico": ({
            "n_provinces": len(dbl_pico_rows),
            "pico_total": dbl_pico_total,
            "n_provinces_pico_present": n_dbl_pico_present,
        } if dbl_pico_rows else None),
        "pico_source": ({
            "layer": "platform/data/peer_province.json (.pico, from pico_census.json / FPO registry)",
            "metric": "licensed PICO-finance operator count per province (MEASURED, distinct class)",
            "vintage": peer_pico_src.get("vintage"),
            "n_operators": peer_pico_src.get("n_operators"),
        } if pico_present_any else None),
    }
    return {"meta": meta, "provinces": records}


def run(check=False):
    obj = build()
    if obj is None:
        if check:
            print("SKIP: province_stress_index.json or peer_province.json absent — "
                  "province_pressure not checkable (optional derived layer)")
            return 0
        print("missing input: needs platform/data/province_stress_index.json AND "
              "platform/data/peer_province.json (run build_province_stress.py + build_peer_province.py).")
        return 1
    text = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    if check:
        if not os.path.exists(OUT) or open(OUT, encoding="utf-8").read() != text:
            print("DRIFT: %s" % os.path.relpath(OUT, ROOT))
            return 1
        m = obj["meta"]
        print("OK: province_pressure.json reproduces (%d provinces, %d double-pressure)"
              % (m["n_provinces"], m["n_double_pressure"]))
        return 0
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(text)
    m = obj["meta"]
    print("wrote %d provinces -> platform/data/province_pressure.json (%.0f KB)"
          % (m["n_provinces"], len(text.encode("utf-8")) / 1024))
    print("  double-pressure (both axes top-third): %d — %s"
          % (m["n_double_pressure"], ", ".join(m["double_pressure_provinces"]) or "none"))
    print("  quadrant counts: %s" % m["quadrant_counts"])
    w = m.get("worst_province") or {}
    if w:
        print("  worst: %s (both_min %.1f — stress %.1f pctile, contest %.1f pctile, led by %s)"
              % (w["province_th"], w["both_min"], w["stress_pctile"], w["contest_pctile"], w["leader"]))
    db = m.get("double_pressure_book")
    if db:
        print("  MEASURED book in the alert set: ฿%.2fbn outstanding across %d provinces, "
              "LIVE NPL %.2f%% (os-weighted)"
              % (db["book_os_total"] / 1e9, db["n_provinces"],
                 db["book_npl_os_pct"] if db["book_npl_os_pct"] is not None else float("nan")))
    bs = m.get("book_source")
    if bs and bs.get("n_book_suppressed"):
        print("  book rows suppressed below MIN_CELL=%d: %d" % (MIN_CELL, bs["n_book_suppressed"]))
    dpi = m.get("double_pressure_pico")
    if dpi:
        print("  MEASURED sub-scale (PICO) in the alert set: %d operators across %d of %d "
              "double-pressure provinces (distinct class, context only)"
              % (dpi["pico_total"], dpi["n_provinces_pico_present"], dpi["n_provinces"]))
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(
        description="combined province pressure (portfolio stress x competitive pressure)")
    ap.add_argument("--check", action="store_true")
    raise SystemExit(run(check=ap.parse_args().check))
