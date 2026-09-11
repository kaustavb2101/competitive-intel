#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_flood_book_exposure.py — REAL loan book × repeated-flood hazard (MEASURED × MEASURED).

Objective #1 (portfolio / collateral risk). Re-weights the GISTDA repeated-flood hazard by the REAL
loan tape: instead of "685 branches sit in a chronic-flood district" (a branch COUNT), it answers
"how much of the actual outstanding book (฿) sits on repeatedly-flooded ground" — a baht-weighted
concentration of a latent recovery / collateral-impairment hazard on the network we already run.

WHAT IT JOINS (both already committed, both MEASURED, no network)
  - platform/data/tape_geo_occ.json  branches[] — per-branch no-PII aggregates from the real loan
    tape (382,735 accounts, 2026-07-21): n accounts, os_sum outstanding, early_pct (<30dpd watch),
    dpd90p_pct (WHOLE-BOOK 90+, incl. the 180+ legacy — the tape's own published branch figure).
  - platform/data/flood_hazard.json  branches[] — per-branch repeated-flood MAX(flood_freq), 0-12,
    INDEX-ALIGNED to platform/data/branches.json (build_flood_hazard.py, GISTDA 2005-2016 census).

THE CROSSWALK (tape branch name+prov -> master index -> flood_freq)
  The tape names a branch "สาขา<place> [<province>]"; the master (branches.json .n) often stores the
  bare place ("ปลวกแดง") and sometimes the prefixed form. So both sides are normalised — strip the
  brand ("เงินไชโย") and a leading "สาขา", drop a trailing province token, collapse spaces — and matched
  on (normalised-name, province) with an English/name-only fallback. Matching is EXACT-key only (no
  fuzzy / edit-distance), and any key that resolves to more than one master branch is left UNMATCHED,
  never force-picked — so a matched pair is high-confidence. Whatever does not match cleanly is
  excluded and DISCLOSED in meta.coverage (count + baht + samples), not silently dropped. On the
  2026-07-21 tape this matches 96.9% of tape branches / 97.1% of outstanding — the residual ~3% is
  name variance, excluded honestly.

HONEST SCOPE
  - flood_freq is a DISTRICT hazard (does the branch's district contain ground that repeatedly floods,
    2005-2016) — NOT a claim that this branch's collateral flooded. Same MAX(flood_freq) the app
    already shows on #map; no flooded AREA is claimed anywhere (the GISTDA polygons overlap — see
    docs/NEXT_STEPS.md §0 and build_flood_hazard.py).
  - dpd90p_pct is the tape's WHOLE-BOOK 90+ (incl. 180+ legacy) at branch grain — the geo layer does
    not carry the live/legacy split per branch, so this is re-aggregated exactly as published and
    LABELLED whole-book, never re-derived into a new blended NPL number.
  - Every published band clears the tape's ≥30-account disclosure floor (asserted); os/accounts by
    band sum EXACTLY to the matched totals (asserted). The read is a concentration of hazard, and it
    makes NO open / close / expand recommendation.

INPUT  platform/data/tape_geo_occ.json   (real-tape per-branch no-PII aggregates)
       platform/data/flood_hazard.json    (per-branch repeated-flood freq, index-aligned)
       platform/data/branches.json        (identity/order — the crosswalk target + fingerprint)
OUTPUT platform/data/flood_book_exposure.json
       { meta, bands:[{band,freq_lo,freq_hi,n_branches,n_accounts,os_sum,pct_book,
                       dpd90p_pct,early_pct}], chronic_rollup:{...}, coverage:{...} }

DETERMINISTIC + NETWORK-FREE. Carries --check; SKIP-passes (exit 3) when an input layer is absent,
same convention as build_flood_hazard.py / build_branch_density.py.

  python3 build_flood_book_exposure.py
  python3 build_flood_book_exposure.py --check
"""
import argparse, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.fingerprint import branches_fingerprint

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
TAPE_GEO = os.path.join(ROOT, "platform", "data", "tape_geo_occ.json")
FLOOD = os.path.join(ROOT, "platform", "data", "flood_hazard.json")
BRANCHES = os.path.join(ROOT, "platform", "data", "branches.json")
OUT = os.path.join(ROOT, "platform", "data", "flood_book_exposure.json")

MIN_CELL = 30   # the real-tape disclosure floor — no published band may rest on fewer accounts
CHRONIC = 7     # flooded in >=7 of 12 years — mirrors build_flood_hazard.CHRONIC (asserted in sync)

# (freq_lo, freq_hi, label) — mirrors build_flood_hazard.py BANDS vocabulary exactly, most-severe first
BANDS = [
    (10, 12, "chronic (10-12/12 yrs)"),
    (7, 9, "frequent (7-9/12 yrs)"),
    (4, 6, "recurrent (4-6/12 yrs)"),
    (1, 3, "occasional (1-3/12 yrs)"),
    (0, 0, "none on record"),
]


def _load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def dumps(obj):
    return json.dumps(obj, ensure_ascii=False, indent=1) + "\n"


def _base_norm(s):
    """Strip the brand and a leading 'สาขา'; keep interior spaces for the trailing-province rule."""
    s = (s or "").strip()
    if s.startswith("บริษัท "):
        s = s[len("บริษัท "):]
    s = s.replace("เงินไชโย", "").strip()
    while s.startswith("สาขา"):
        s = s[len("สาขา"):]
    return s.strip()


def _variants(name, prov):
    """Deterministic candidate keys for one tape branch, most-specific first."""
    b = _base_norm(name)
    out = [b.replace(" ", "")]
    if prov and b.endswith(prov):
        out.append(b[:-len(prov)].strip().replace(" ", ""))   # drop a trailing province token
    if " " in b:
        out.append(b.split(" ", 1)[0].replace(" ", ""))       # leading place token
    # de-dup preserving order, drop empties, then longest-first (most specific)
    seen, uniq = set(), []
    for v in out:
        if v and v not in seen:
            seen.add(v)
            uniq.append(v)
    return sorted(uniq, key=len, reverse=True)


def _crosswalk(tape_branches, master):
    """tape-branch index -> master index. Exact-key only; ambiguous keys left unmatched."""
    from collections import defaultdict
    idx, idxname = defaultdict(set), defaultdict(set)
    for i, b in enumerate(master):
        nn = _base_norm(b.get("n")).replace(" ", "")
        idx[(nn, b.get("v"))].add(i)
        idxname[nn].add(i)
    matched, unmatched, ambiguous = {}, [], []
    for ti, t in enumerate(tape_branches):
        hit = None
        for vk in _variants(t.get("branch"), t.get("prov")):
            cand = idx.get((vk, t.get("prov")))
            if cand and len(cand) == 1:
                hit = next(iter(cand)); break
            if cand and len(cand) > 1:
                hit = "AMB"; break
        if hit is None:
            for vk in _variants(t.get("branch"), t.get("prov")):
                cand = idxname.get(vk)
                if cand and len(cand) == 1:
                    hit = next(iter(cand)); break
        if isinstance(hit, int):
            matched[ti] = hit
        elif hit == "AMB":
            ambiguous.append(ti)
        else:
            unmatched.append(ti)
    return matched, unmatched, ambiguous


def _band_index(freq):
    for k, (lo, hi, _lab) in enumerate(BANDS):
        if lo <= freq <= hi:
            return k
    return len(BANDS) - 1   # defensive: treat anything else as "none"


def build():
    for p in (TAPE_GEO, FLOOD, BRANCHES):
        if not os.path.exists(p):
            return None

    tape = _load(TAPE_GEO)
    flood = _load(FLOOD)
    master = _load(BRANCHES)
    master = master["branches"] if isinstance(master, dict) else master
    tb = tape.get("branches") or []
    fb = flood.get("branches") or []

    # drift guard: our chronic band must agree with the flood layer's own threshold
    fthr = (flood.get("meta") or {}).get("chronic_threshold")
    if fthr is not None and int(fthr) != CHRONIC:
        raise ValueError("CHRONIC (%d) diverged from flood_hazard chronic_threshold (%s) — "
                         "re-sync BANDS/CHRONIC before shipping" % (CHRONIC, fthr))
    if len(fb) != len(master):
        raise ValueError("flood_hazard.branches (%d) not index-aligned to branches.json (%d)"
                         % (len(fb), len(master)))

    matched, unmatched, ambiguous = _crosswalk(tb, master)

    # per-band accumulators
    acc = [{"nb": 0, "n": 0, "os": 0.0, "dpd_wn": 0.0, "early_wn": 0.0} for _ in BANDS]
    m_n = m_os = 0
    for ti, mi in matched.items():
        t = tb[ti]
        n = int(t.get("n") or 0)
        osum = float(t.get("os_sum") or 0.0)
        k = _band_index(int(fb[mi] or 0))
        a = acc[k]
        a["nb"] += 1
        a["n"] += n
        a["os"] += osum
        a["dpd_wn"] += float(t.get("dpd90p_pct") or 0.0) * n
        a["early_wn"] += float(t.get("early_pct") or 0.0) * n
        m_n += n
        m_os += osum

    # self-verify: band sums reproduce the matched totals exactly
    if sum(a["nb"] for a in acc) != len(matched):
        raise ValueError("band branch counts do not sum to matched count")
    if sum(a["n"] for a in acc) != m_n:
        raise ValueError("band account counts do not sum to matched accounts")
    if round(sum(a["os"] for a in acc), 2) != round(m_os, 2):
        raise ValueError("band outstanding does not sum to matched outstanding")

    def _wpct(wn, n):
        return round(wn / n, 2) if n else None

    def _row(k, a):
        lo, hi, lab = BANDS[k]
        # every PUBLISHED band must clear the disclosure floor (bands are huge here; assert anyway)
        if 0 < a["n"] < MIN_CELL:
            raise ValueError("band '%s' has %d accounts (<%d floor) — would under-disclose"
                             % (lab, a["n"], MIN_CELL))
        return {
            "band": lab, "freq_lo": lo, "freq_hi": hi,
            "n_branches": a["nb"], "n_accounts": a["n"],
            "os_sum": round(a["os"], 0),
            "pct_book": round(100.0 * a["os"] / m_os, 2) if m_os else None,
            "dpd90p_pct": _wpct(a["dpd_wn"], a["n"]),
            "early_pct": _wpct(a["early_wn"], a["n"]),
        }

    bands = [_row(k, acc[k]) for k in range(len(BANDS))]

    # chronic rollup (freq >= CHRONIC): frequent + chronic bands combined — the headline exposure
    cn = sum(a["n"] for k, a in enumerate(acc) if BANDS[k][0] >= CHRONIC)
    cos = sum(a["os"] for k, a in enumerate(acc) if BANDS[k][0] >= CHRONIC)
    cnb = sum(a["nb"] for k, a in enumerate(acc) if BANDS[k][0] >= CHRONIC)
    cdpd = sum(a["dpd_wn"] for k, a in enumerate(acc) if BANDS[k][0] >= CHRONIC)
    cearly = sum(a["early_wn"] for k, a in enumerate(acc) if BANDS[k][0] >= CHRONIC)
    chronic_rollup = {
        "threshold": CHRONIC,
        "label": "chronic repeat-flood districts (flooded ≥%d of 12 yrs 2005-2016)" % CHRONIC,
        "n_branches": cnb, "n_accounts": cn, "os_sum": round(cos, 0),
        "pct_book": round(100.0 * cos / m_os, 2) if m_os else None,
        "dpd90p_pct": _wpct(cdpd, cn), "early_pct": _wpct(cearly, cn),
    }
    # any repeat-flood exposure (freq >= 1)
    an = sum(a["n"] for k, a in enumerate(acc) if BANDS[k][1] >= 1)
    aos = sum(a["os"] for k, a in enumerate(acc) if BANDS[k][1] >= 1)
    any_flood = {"n_accounts": an, "os_sum": round(aos, 0),
                 "pct_book": round(100.0 * aos / m_os, 2) if m_os else None}

    # coverage disclosure
    tot_n = sum(int(t.get("n") or 0) for t in tb)
    tot_os = sum(float(t.get("os_sum") or 0.0) for t in tb)
    unm_os = sum(float(tb[ti].get("os_sum") or 0.0) for ti in unmatched + ambiguous)
    unm_samples = sorted(
        ({"branch": tb[ti].get("branch"), "prov": tb[ti].get("prov")}
         for ti in unmatched + ambiguous),
        key=lambda r: (r["prov"] or "", r["branch"] or ""))[:20]
    coverage = {
        "tape_branches": len(tb), "matched": len(matched),
        "unmatched": len(unmatched), "ambiguous_dropped": len(ambiguous),
        "pct_branches_matched": round(100.0 * len(matched) / len(tb), 2) if tb else None,
        "pct_outstanding_matched": round(100.0 * m_os / tot_os, 2) if tot_os else None,
        "pct_accounts_matched": round(100.0 * m_n / tot_n, 2) if tot_n else None,
        "unmatched_os_sum": round(unm_os, 0),
        "unmatched_samples": unm_samples,
        "note": ("Exact-key crosswalk (tape branch name+prov → master → flood_freq); ambiguous keys "
                 "dropped, unmatched excluded and disclosed here, never force-matched. The excluded "
                 "residual is name variance, not a flood signal."),
    }

    tmeta = tape.get("meta") or {}
    fmeta = flood.get("meta") or {}
    meta = {
        "generated_by": "build_flood_book_exposure.py",
        "label": ("MEASURED × MEASURED — real outstanding loan book (tape_geo_occ.json, 2026-07-21) "
                  "weighted onto the GISTDA repeated-flood hazard (flood_hazard.json, 2005-2016). "
                  "Baht-weighted concentration of a latent recovery/collateral hazard, not a claim "
                  "any collateral flooded, and no open/close/expand recommendation."),
        "method": ("Each matched branch's whole outstanding book (os_sum) and account count are "
                   "bucketed by its district repeated-flood MAX(flood_freq), 0-12. dpd90p_pct and "
                   "early_pct are account-weighted (Σ pct·n / Σ n) across the band; dpd90p_pct is the "
                   "tape's WHOLE-BOOK 90+ (incl. 180+ legacy), re-aggregated exactly as published, "
                   "not a new blended NPL. Chronic band = flood_freq ≥ %d (mirrors flood_hazard)." % CHRONIC),
        "caveats": [
            "flood_freq is a district STRUCTURAL hazard (does the ground repeatedly flood 2005-2016), "
            "NOT a claim this branch's collateral flooded; no flooded AREA is claimed.",
            "dpd90p_pct is WHOLE-BOOK 90+ incl. the 180+ legacy — the geo layer carries no per-branch "
            "live/legacy split, so it is labelled whole-book, never re-derived.",
            "%.1f%% of tape branches / %.1f%% of outstanding are matched; the excluded residual is "
            "name variance and is disclosed in coverage (count, baht, samples)."
            % (coverage["pct_branches_matched"] or 0, coverage["pct_outstanding_matched"] or 0),
            "Every published band clears the ≥%d-account tape floor; band os/accounts sum exactly to "
            "the matched totals (both asserted at build)." % MIN_CELL,
        ],
        "min_cell": MIN_CELL,
        "chronic_threshold": CHRONIC,
        "bands_vocab": [lab for _lo, _hi, lab in BANDS],
        "tape_source": tmeta.get("label", ""),
        "tape_n_accounts": tmeta.get("n_accounts"),
        "tape_mob_anchor": tmeta.get("mob_anchor"),
        "flood_source": fmeta.get("source", ""),
        "flood_service": fmeta.get("service", ""),
        "matched_n_accounts": m_n,
        "matched_os_sum": round(m_os, 0),
        "any_flood": any_flood,
        "branches_fingerprint": branches_fingerprint(master),
    }
    return {"meta": meta, "bands": bands, "chronic_rollup": chronic_rollup, "coverage": coverage}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true",
                    help="re-run and byte-compare against the committed JSON; exit 1 on drift, "
                         "exit 3 / SKIP when an input layer is absent")
    args = ap.parse_args()

    try:
        data = build()
    except ValueError as e:
        print("CHECK FAIL: %s" % e, file=sys.stderr)
        sys.exit(1)

    if args.check:
        if data is None:
            print("CHECK SKIP: an input layer (tape_geo_occ/flood_hazard/branches) absent — "
                  "flood_book_exposure not byte-checkable", file=sys.stderr)
            sys.exit(3)
        text = dumps(data)
        if not os.path.exists(OUT):
            print("CHECK FAIL: %s does not exist" % OUT)
            sys.exit(1)
        with open(OUT, encoding="utf-8") as f:
            existing = f.read()
        if existing == text:
            c = data["chronic_rollup"]
            print("CHECK OK: %s reproduces byte-for-byte (%d matched branches; chronic ฿%.2fbn = %.1f%%)"
                  % (OUT, data["coverage"]["matched"], (c["os_sum"] or 0) / 1e9, c["pct_book"] or 0))
            sys.exit(0)
        print("CHECK FAIL: %s differs from a fresh build" % OUT)
        sys.exit(1)

    if data is None:
        print("SKIP: an input layer absent — nothing to build", file=sys.stderr)
        sys.exit(3)

    text = dumps(data)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(text)
    c = data["chronic_rollup"]
    cov = data["coverage"]
    print("wrote %s (%d/%d tape branches matched, %.1f%% of outstanding; chronic ฿%.2fbn = %.1f%% of book)"
          % (OUT, cov["matched"], cov["tape_branches"], cov["pct_outstanding_matched"] or 0,
             (c["os_sum"] or 0) / 1e9, c["pct_book"] or 0))


if __name__ == "__main__":
    main()
