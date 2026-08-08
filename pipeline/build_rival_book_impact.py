#!/usr/bin/env python3
"""
build_rival_book_impact.py — does competition actually cost us anything?
=======================================================================
The Competition view says how many rivals sit around each branch. It has never said what that
does to our book. Every number on that tab is about THEM; none of it is joined to us. So the tab
can tell you we are outnumbered 16,503 to 2,015 and still not answer the question a strategy
director is actually asked: *is the competition hurting us, yes or no.*

This joins the two MEASURED sides that were never joined:

    rival_density.json   per-district rival branch counts   (MEASURED, 928 amphoe, PIP-joined)
    tape_geo_occ.json    per-branch book performance        (MEASURED, real no-PII tape)

1,935 of 2,015 branches carry both, covering ~97% of the accounts.

WHAT THIS IS AND IS NOT
-----------------------
It is a MEASURED cross-section. It is NOT causal, and the honest reason is worth stating rather
than hiding in a footnote: **rivals are not placed at random.** They cluster where demand is —
population, vehicles, market towns — and so do our biggest branches. A raw finding that contested
branches carry more delinquency could just as easily be reporting urbanisation as competition.

So this file publishes TWO reads and labels which is which:

  RAW          branches bucketed by how many rivals share their district, nationally. Easy to
               read, maximally confounded.
  WITHIN-PROV  each branch compared only against other branches IN THE SAME PROVINCE, split at
               that province's own median rival count. This removes the province-level confounds
               (region, urbanisation, income, crop mix) that drive most of the raw gap. It is a
               real control, not a disclaimer — and it is the number to quote.

If the within-province gap is ~0, that IS the finding: competition is not visibly costing us on
credit quality, and the pressure shows up somewhere else (price, volume) that this tape cannot
see. Publishing a null result honestly beats manufacturing an effect.

WEIGHTING
---------
Every aggregate is ACCOUNT-weighted, not branch-weighted. A 40-account branch and a 4,000-account
branch are not one vote each; branch-weighting would let the long tail of tiny branches dominate a
statement about the book.

  in : platform/data/rival_density.json   MEASURED rival + AutoX counts per amphoe
       platform/data/tape_geo_occ.json    MEASURED per-branch book (real tape)
       platform/data/branches.json        branch -> province + district (the join key)
  out: platform/data/rival_book_impact.json

Usage:
  python3 build_rival_book_impact.py
  python3 build_rival_book_impact.py --check
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from branchkey import norm_branch  # noqa: E402

DATA = os.path.join(ROOT, "platform", "data")
IN_RIVAL = os.path.join(DATA, "rival_density.json")
IN_TAPE = os.path.join(DATA, "tape_geo_occ.json")
IN_BRANCHES = os.path.join(DATA, "branches.json")
OUT = os.path.join(DATA, "rival_book_impact.json")

# The tape's own disclosure floor. A branch cell below it is not published anywhere else and is
# not going to start being published here.
MIN_CELL = 30
RC_ABSENT = 3

# Rival-count buckets. Upper bound is inclusive; the last is open-ended. Chosen to put a
# meaningful share of the book in each rather than to produce a pleasing gradient.
BUCKETS = [(0, 0, "no rival in the district"),
           (1, 2, "1-2 rivals"),
           (3, 5, "3-5 rivals"),
           (6, 10, "6-10 rivals"),
           (11, None, "11+ rivals")]


def _load(p):
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


def dumps(obj):
    return json.dumps(obj, ensure_ascii=False, indent=1, sort_keys=True) + "\n"


def _agg(rows):
    """Account-weighted aggregate over a list of joined branch records."""
    n = sum(r["n"] for r in rows)
    if not n:
        return None
    os_sum = sum(r["os_sum"] for r in rows)
    return {
        "n_branches": len(rows),
        "n_accounts": n,
        "os_thb": round(os_sum, 2),
        "avg_balance_thb": int(round(os_sum / n)),
        # Account-weighted means: each branch contributes in proportion to its book.
        "dpd90p_pct": round(sum(r["dpd90p_pct"] * r["n"] for r in rows) / n, 2),
        "early_pct": round(sum(r["early_pct"] * r["n"] for r in rows) / n, 2),
        "rivals_avg": round(sum(r["rivals"] * r["n"] for r in rows) / n, 2),
    }


def build():
    rival, tape, branches = _load(IN_RIVAL), _load(IN_TAPE), _load(IN_BRANCHES)
    if rival is None or tape is None or branches is None:
        return None

    rows = branches["branches"] if isinstance(branches, dict) else branches
    recs = rival.get("records") or []
    # (province, district) -> rival record. Two districts share a (province, name) pair
    # nationally; last-wins is deterministic because records[] order is fixed by the builder.
    by_district = {(r["province_th"], r["name"]): r for r in recs}

    book = {}
    for b in tape.get("branches") or []:
        if (b.get("n") or 0) >= MIN_CELL and b.get("dpd90p_pct") is not None:
            book[norm_branch(b.get("branch") or "")] = b

    joined = []
    for r in rows:
        d = by_district.get((r.get("v"), r.get("d")))
        t = book.get(norm_branch(r.get("n") or ""))
        if not d or not t:
            continue
        joined.append({
            "name": r.get("n"), "prov": r.get("v"), "region": r.get("r"),
            "district": r.get("d"),
            "rivals": d.get("rivals") or 0,
            "autox_in_district": d.get("autox") or 0,
            "by_brand": d.get("by_brand") or {},
            "n": t["n"], "os_sum": t.get("os_sum") or 0.0,
            "dpd90p_pct": t.get("dpd90p_pct") or 0.0,
            "early_pct": t.get("early_pct") or 0.0,
            "pop": r.get("pop") or 0, "dwork": r.get("dwork") or 0,
        })
    if not joined:
        return None

    # ---- RAW read: national buckets by rival count -------------------------------------------
    raw = []
    for lo, hi, label in BUCKETS:
        sel = [j for j in joined if j["rivals"] >= lo and (hi is None or j["rivals"] <= hi)]
        a = _agg(sel)
        if not a:
            continue
        a.update({"bucket": label, "lo": lo, "hi": hi})
        # Carry the confound in the open, on the same row as the result it threatens: median
        # catchment population is the thing that most plausibly drives BOTH rival count and
        # book quality, so the reader should see it move alongside them.
        pops = sorted(j["pop"] for j in sel)
        a["median_catchment_pop"] = pops[len(pops) // 2]
        raw.append(a)

    # ---- WITHIN-PROVINCE read: the actual control ---------------------------------------------
    # Split each province's branches at that province's own median rival count, then pool the
    # two halves nationally. A branch is only ever compared with branches facing the same
    # regional economy, so the gap that survives is not a region effect.
    hi_side, lo_side = [], []
    provs = {}
    for j in joined:
        provs.setdefault(j["prov"], []).append(j)
    n_prov_used = 0
    for prov in sorted(provs):
        sel = provs[prov]
        if len(sel) < 4:
            continue                      # too few branches to split meaningfully
        rs = sorted(j["rivals"] for j in sel)
        med = rs[len(rs) // 2]
        above = [j for j in sel if j["rivals"] > med]
        below = [j for j in sel if j["rivals"] < med]
        if not above or not below:
            continue                      # province is uniform — no contrast to draw
        n_prov_used += 1
        hi_side.extend(above)
        lo_side.extend(below)

    within = None
    if hi_side and lo_side:
        a_hi, a_lo = _agg(hi_side), _agg(lo_side)
        within = {
            "more_contested": a_hi,
            "less_contested": a_lo,
            "gap_dpd90p_pp": round(a_hi["dpd90p_pct"] - a_lo["dpd90p_pct"], 2),
            "gap_early_pp": round(a_hi["early_pct"] - a_lo["early_pct"], 2),
            "gap_avg_balance_thb": a_hi["avg_balance_thb"] - a_lo["avg_balance_thb"],
            "n_provinces": n_prov_used,
        }

    # ---- The most contested branches, as a list someone can act on ---------------------------
    top = sorted(joined, key=lambda j: (-j["rivals"], -j["n"], j["name"] or ""))[:25]
    top_rows = [{
        "name": j["name"], "prov": j["prov"], "region": j["region"], "district": j["district"],
        "rivals": j["rivals"], "autox_in_district": j["autox_in_district"],
        "n_accounts": j["n"], "os_thb": round(j["os_sum"], 2),
        "dpd90p_pct": round(j["dpd90p_pct"], 2), "early_pct": round(j["early_pct"], 2),
        "top_brands": sorted(j["by_brand"].items(), key=lambda kv: (-kv[1], kv[0]))[:3],
    } for j in top]

    n_acc = sum(j["n"] for j in joined)

    # How much of the raw national gap was confounding? Compare the same top-vs-bottom contrast
    # WITHOUT the province control, so the file can state what the control actually bought
    # instead of just asserting that it was needed.
    raw_gap = None
    if raw and len(raw) >= 2:
        raw_gap = round(raw[-1]["dpd90p_pct"] - raw[0]["dpd90p_pct"], 2)

    verdict = None
    if within:
        g, gx = within["gap_dpd90p_pp"], within["gap_early_pp"]
        shrunk = ""
        if raw_gap is not None and abs(raw_gap) > abs(g):
            shrunk = (" The raw national gradient is %+.2fpp; controlling for province cuts it "
                      "to %+.2fpp, so roughly %d%% of the apparent effect was the fact that "
                      "rivals and our big branches both sit in cities."
                      % (raw_gap, g, round(100 * (1 - abs(g) / abs(raw_gap)))))
        if abs(g) < 0.25:
            verdict = ("NO MEASURABLE CREDIT COST. Within the same province, branches facing "
                       "more rivals carry a 90+ rate %+.2fpp different from those facing fewer "
                       "— indistinguishable from zero on this tape. If competition is costing "
                       "us, it is costing us in price or volume, which this tape cannot see.%s"
                       % (g, shrunk))
        elif (g > 0) != (gx > 0):
            # The two delinquency measures disagree in SIGN. That is the most informative
            # outcome available here and the easiest one to quietly drop, so it leads.
            verdict = ("MIXED — and the mix is the finding. Within the same province, more-"
                       "contested branches run %+.2fpp on 90+ but %+.2fpp on the early "
                       "(pre-30dpd) bucket, and carry %s THB more per account. Deeper "
                       "delinquency alongside a LOWER early bucket is not the shape of "
                       "\"competition makes borrowers worse\" — it is the shape of a bigger, "
                       "later-souring ticket. The most likely reading is that we write larger "
                       "loans to win contested ground, and larger loans fail harder when they "
                       "fail. That is a PRICING and underwriting question, not a collections "
                       "one.%s"
                       % (g, gx, format(within["gap_avg_balance_thb"], ","), shrunk))
        else:
            verdict = ("MEASURABLE GAP. Within the same province, branches facing more rivals "
                       "carry a 90+ rate %+.2fpp vs those facing fewer, and an early bucket "
                       "%+.2fpp. The province control removes region, urbanisation and crop-mix "
                       "effects, but not everything — a strong association, not proof of cause.%s"
                       % (g, gx, shrunk))

    return {
        "meta": {
            "title": "What competition does to our book",
            "generated_by": "pipeline/build_rival_book_impact.py",
            "label": (
                "MEASURED on both sides — MEASURED rival branch counts per district joined to "
                "the MEASURED real no-PII loan tape. The JOIN is exact (province + district); "
                "what is not certain is the CAUSATION, and the file publishes a within-province "
                "control rather than asking the reader to take the raw cross-section at face "
                "value."),
            "source": (
                "rivals: platform/data/rival_density.json (%d districts, %s rival branches, "
                "point-in-polygon join); book: platform/data/tape_geo_occ.json (real tape, "
                "branch cells >= %d accounts); join key: province + district from "
                "platform/data/branches.json."
                % (len(recs), format(rival.get("meta", {}).get("total_rivals", 0), ","),
                   MIN_CELL)),
            "how_to_read": (
                "Read WITHIN-PROVINCE, not RAW. Rivals cluster where demand is, and so do our "
                "biggest branches, so the raw national buckets partly measure urbanisation "
                "rather than competition — the median catchment population is printed on each "
                "bucket so that confound is visible instead of hidden. The within-province "
                "split compares each branch only against branches in the same province, which "
                "removes the region/urbanisation effect. Neither read is causal."),
            "verdict": verdict,
            "min_cell": MIN_CELL,
            "n_branches_joined": len(joined),
            "n_branches_total": len(rows),
            "n_accounts_covered": n_acc,
            "coverage_note": (
                "%d of %d branches carry BOTH a district rival count and a tape cell at or above "
                "the %d-account floor; the rest are absent from this read rather than estimated "
                "into it." % (len(joined), len(rows), MIN_CELL)),
        },
        "raw_buckets": raw,
        "within_province": within,
        "most_contested_branches": top_rows,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true",
                    help="re-run and byte-compare (exit 3 / SKIP when an input is absent)")
    args = ap.parse_args()

    data = build()
    if data is None:
        msg = "an input layer is absent — rival_book_impact not buildable here"
        print(("CHECK SKIP: " if args.check else "SKIP: ") + msg, file=sys.stderr)
        sys.exit(RC_ABSENT)

    text = dumps(data)
    if args.check:
        if not os.path.exists(OUT):
            print("CHECK FAIL: %s does not exist" % OUT)
            sys.exit(1)
        with open(OUT, encoding="utf-8") as fh:
            if fh.read() == text:
                print("CHECK OK: %s reproduces byte-for-byte (%d branches joined)"
                      % (OUT, data["meta"]["n_branches_joined"]))
                sys.exit(0)
        print("CHECK FAIL: %s differs from a fresh build" % OUT)
        sys.exit(1)

    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    m = data["meta"]
    print("wrote %s (%d branches, %s accounts)"
          % (OUT, m["n_branches_joined"], format(m["n_accounts_covered"], ",")))
    if m.get("verdict"):
        print("  " + m["verdict"][:140])


if __name__ == "__main__":
    main()
