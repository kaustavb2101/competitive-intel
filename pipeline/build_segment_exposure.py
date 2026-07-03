#!/usr/bin/env python3
"""
build_segment_exposure.py — PORTFOLIO CONCENTRATION (objective #1).

Network-free, deterministic. Reads ONE local file:
  platform/data/branches.json   per-branch segment scores a (agri-PD), m (merchant),
                                 c (collateral) on a 0..100 scale, plus region r + province v.

It answers a single portfolio-risk question: HOW CONCENTRATED is the AutoX book — by
borrower SEGMENT — nationally, per region, and per province? A book heavily skewed to
one segment carries correlated risk (a shock to that segment hits more of the portfolio
at once); a balanced mix is more diversified.

WHAT IT COMPUTES (per REGION, per PROVINCE, and NATIONAL):
  segment_mix    share of BRANCHES whose DOMINANT segment is agri / merchant / collateral.
                 A branch's dominant segment = argmax(a, m, c), ties broken in the fixed
                 order agri > merchant > collateral (deterministic). The three shares sum
                 to 1.0 (each branch has exactly one dominant segment).
  counts         the raw branch counts behind each share (so the UI shows reality).
  hhi            Herfindahl-style concentration of the segment_mix, RESCALED to 0..1:
                   raw_hhi = agri_share^2 + merchant_share^2 + collateral_share^2
                   hhi     = (raw_hhi - 1/3) / (1 - 1/3)
                 0 = perfectly balanced across the 3 segments (each share 1/3),
                 1 = fully concentrated in one segment. Higher = more concentrated.
  dominant_segment  the single most common dominant segment (the concentration's direction).

PROVENANCE (read CLAUDE.md):
  The per-branch a/m/c segment scores are ESTIMATED PROXIES (built by the enrichment loop
  from OSM POI density etc.), NOT measured loan balances. Therefore segment_mix and hhi are
  an ESTIMATED STRUCTURAL measure of how the branch FOOTPRINT skews by segment — they are
  NOT a measured default rate, loss rate, or AUM concentration. Treat as a triage lens.

GRACEFUL: if branches.json is absent, write an honest absent-state file (meta.absent=true,
empty rollups) and --check skip-passes.

Run:
  python3 build_segment_exposure.py            # write platform/data/segment_exposure.json
  python3 build_segment_exposure.py --check    # re-run, byte-compare against committed file
"""
import json
import os
import sys
import argparse
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
BRANCHES = os.path.join(ROOT, "platform", "data", "branches.json")
OUT = os.path.join(ROOT, "platform", "data", "segment_exposure.json")

# the three borrower segments, in the fixed tie-break / display order.
SEGMENTS = ("agri", "merchant", "collateral")
# branch-record field -> segment key (a = agri-PD, m = merchant, c = collateral; per CLAUDE.md).
FIELD = {"agri": "a", "merchant": "m", "collateral": "c"}
N_SEG = len(SEGMENTS)
EVEN = 1.0 / N_SEG  # share when perfectly balanced across the 3 segments


def dominant_segment(branch):
    """argmax over (a, m, c); ties broken in the fixed SEGMENTS order (agri>merchant>collateral)."""
    best_seg = None
    best_val = None
    for seg in SEGMENTS:  # fixed order => deterministic tie-break
        v = branch.get(FIELD[seg])
        if not isinstance(v, (int, float)) or isinstance(v, bool):
            v = 0.0
        v = float(v)
        if best_val is None or v > best_val:
            best_val = v
            best_seg = seg
    return best_seg


def rescaled_hhi(shares):
    """Herfindahl of the segment shares, rescaled so 0=balanced(1/3 each), 1=single segment."""
    raw = sum(s * s for s in shares)
    # raw ranges [1/N_SEG, 1]; rescale to [0, 1].
    hhi = (raw - EVEN) / (1.0 - EVEN)
    # guard tiny FP drift outside [0,1]
    hhi = max(0.0, min(1.0, hhi))
    return raw, hhi


def summarize(counts):
    """counts = {seg: n}. Return a mix/hhi summary block for a group of branches."""
    total = sum(counts.get(s, 0) for s in SEGMENTS)
    if total <= 0:
        return None
    shares = [counts.get(s, 0) / total for s in SEGMENTS]
    raw_hhi, hhi = rescaled_hhi(shares)
    seg_share = dict(zip(SEGMENTS, shares))
    seg_count = {s: counts.get(s, 0) for s in SEGMENTS}
    # dominant = segment with the most branches; tie-break in fixed SEGMENTS order.
    dom = max(SEGMENTS, key=lambda s: (seg_count[s], -SEGMENTS.index(s)))
    return {
        "n_branches": total,
        "segment_mix": {s: round(seg_share[s], 4) for s in SEGMENTS},
        "counts": seg_count,
        "hhi": round(hhi, 4),
        "raw_hhi": round(raw_hhi, 4),
        "dominant_segment": dom,
    }


def absent_payload():
    meta = {
        "title": "Portfolio segment concentration (objective #1)",
        "generated_by": "pipeline/build_segment_exposure.py",
        "deterministic": True,
        "network_free": True,
        "absent": True,
        "label": "ESTIMATED — structural concentration of the branch footprint by segment.",
        "source": "platform/data/branches.json (absent at build time).",
        "note": "branches.json was not present when this file was built; honest absent-state.",
    }
    return {"meta": meta, "national": None, "regions": [], "provinces": [],
            "most_concentrated": {"regions": [], "provinces": []}}


def build():
    if not os.path.exists(BRANCHES):
        return absent_payload(), True  # (payload, is_absent)

    with open(BRANCHES, encoding="utf-8") as f:
        branches = json.load(f)

    national_counts = defaultdict(int)
    region_counts = defaultdict(lambda: defaultdict(int))   # region -> {seg: n}
    province_counts = defaultdict(lambda: defaultdict(int))  # prov -> {seg: n}
    province_region = {}  # prov -> region (first seen; provinces map 1:1 to a region)

    for b in branches:
        seg = dominant_segment(b)
        national_counts[seg] += 1
        region = b.get("r")
        prov = b.get("v")
        if region:
            region_counts[region][seg] += 1
        if prov:
            province_counts[prov][seg] += 1
            province_region.setdefault(prov, region)

    national = summarize(national_counts)

    regions = []
    for region in sorted(region_counts.keys()):
        block = summarize(region_counts[region])
        if block is None:
            continue
        block = {"region": region, **block}
        regions.append(block)
    # sort regions worst-first by concentration (hhi desc), tie-break by name for determinism
    regions.sort(key=lambda r: (-r["hhi"], r["region"]))

    provinces = []
    for prov in sorted(province_counts.keys()):
        block = summarize(province_counts[prov])
        if block is None:
            continue
        block = {"province": prov, "region": province_region.get(prov), **block}
        provinces.append(block)
    provinces.sort(key=lambda p: (-p["hhi"], p["province"]))

    # "most concentrated" leaderboards (top by hhi). Provinces with very few branches have a
    # noisy hhi (one branch flips a share a lot), so we surface n_branches in each row and add a
    # min-branch'd province board so the headline isn't a 1-branch province at hhi=1.0.
    most_regions = regions[:N_SEG + 2]  # all regions, already hhi-sorted (<=5)
    MIN_PROV_BRANCHES = 5
    prov_board = [p for p in provinces if p["n_branches"] >= MIN_PROV_BRANCHES]
    most_provinces = prov_board[:10]

    meta = {
        "title": "Portfolio segment concentration (objective #1)",
        "generated_by": "pipeline/build_segment_exposure.py",
        "deterministic": True,
        "network_free": True,
        "absent": False,
        "label": "ESTIMATED — structural concentration of the branch footprint by segment.",
        "source": "platform/data/branches.json — per-branch a/m/c segment scores.",
        "n_branches": national["n_branches"] if national else 0,
        "n_regions": len(regions),
        "n_provinces": len(provinces),
        "segments": {
            "agri": "agri-PD borrowers (field a) — ESTIMATED segment score.",
            "merchant": "merchant borrowers (field m) — ESTIMATED segment score.",
            "collateral": "collateral-rich borrowers (field c) — ESTIMATED segment score.",
        },
        "method": {
            "dominant_segment": "per branch = argmax(a, m, c); ties broken in the fixed order "
                                "agri > merchant > collateral (deterministic).",
            "segment_mix": "share of a group's branches whose dominant segment is each of the "
                           "three; the three shares sum to 1.0.",
            "hhi": "rescaled Herfindahl of segment_mix: (sum(share^2) - 1/3) / (1 - 1/3). "
                   "0 = perfectly balanced across the 3 segments, 1 = a single segment. "
                   "Higher = more concentrated.",
            "raw_hhi": "the un-rescaled Herfindahl sum(share^2), in [1/3, 1].",
            "dominant_segment_group": "the single most common dominant segment in the group "
                                      "(the direction of the concentration).",
            "sort": "regions and provinces sorted most-concentrated-first by hhi.",
            "most_concentrated.provinces": "top-10 provinces by hhi among those with >= %d "
                                           "branches (so a 1-branch province at hhi=1 isn't the "
                                           "headline)." % MIN_PROV_BRANCHES,
        },
        "label_detail": "PROVENANCE: the a/m/c segment scores are ESTIMATED proxies (built by the "
                        "enrichment loop from POI density etc.), NOT measured loan balances. So "
                        "segment_mix and hhi describe how the branch FOOTPRINT skews by segment — "
                        "a DERIVED STRUCTURAL index, NOT a measured default/loss rate or AUM "
                        "concentration. A triage lens, not an outcome.",
        "caveats": [
            "Segment scores are estimated proxies; this is a structural concentration measure, "
            "not a measured portfolio loss/default concentration.",
            "Concentration is over branch COUNTS (one dominant segment per branch), not over loan "
            "balances — a balance-weighted HHI needs the loan tape (objective #1, pending).",
            "Province hhi is noisy where a province has few branches; see each row's n_branches "
            "and the >= %d-branch filter on the most_concentrated.provinces board." % MIN_PROV_BRANCHES,
        ],
    }

    return {
        "meta": meta,
        "national": national,
        "regions": regions,
        "provinces": provinces,
        "most_concentrated": {
            "regions": most_regions,
            "provinces": most_provinces,
        },
    }, False


def dumps(obj):
    # deterministic: keep insertion key order, ensure_ascii=False to match meta.json convention.
    return json.dumps(obj, ensure_ascii=False, indent=2) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true",
                    help="re-run and byte-compare against the committed JSON; exit 1 on drift")
    args = ap.parse_args()

    data, is_absent = build()
    text = dumps(data)

    if args.check:
        if is_absent:
            # branches.json absent => nothing deterministic to reproduce; skip-pass.
            print("CHECK SKIP: branches.json absent — segment_exposure is an absent-state, nothing to reproduce")
            sys.exit(0)
        if not os.path.exists(OUT):
            print("CHECK FAIL: %s does not exist" % OUT)
            sys.exit(1)
        with open(OUT, encoding="utf-8") as f:
            existing = f.read()
        if existing == text:
            print("CHECK OK: %s reproduces byte-for-byte (%d regions, %d provinces)" %
                  (OUT, data["meta"]["n_regions"], data["meta"]["n_provinces"]))
            sys.exit(0)
        print("CHECK FAIL: %s differs from a fresh build" % OUT)
        sys.exit(1)

    with open(OUT, "w", encoding="utf-8") as f:
        f.write(text)

    if is_absent:
        print("wrote %s (ABSENT-state — branches.json not found)" % OUT)
        return
    nat = data["national"]
    print("wrote %s (%d regions, %d provinces, national hhi=%.4f dom=%s)" % (
        OUT, data["meta"]["n_regions"], data["meta"]["n_provinces"],
        nat["hhi"], nat["dominant_segment"]))
    for r in data["regions"]:
        m = r["segment_mix"]
        print("  %-12s hhi=%.4f dom=%-10s agri=%.2f merch=%.2f coll=%.2f (n=%d)" % (
            r["region"], r["hhi"], r["dominant_segment"],
            m["agri"], m["merchant"], m["collateral"], r["n_branches"]))


if __name__ == "__main__":
    main()
