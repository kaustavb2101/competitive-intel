#!/usr/bin/env python3
"""
fix_provinces.py — normalize the master's province/region fields
================================================================
The master arrived with 116 distinct province strings (should be 77): ISO codes
(TH-38), English names (Lamphun), a "จังหวัด " prefix, and a few blanks. Those 87
records fell into a junk region "Other" and were silently dropped from every
by-region rollup. This folds each variant to its canonical Thai province (see
regionmap.canonical) and recomputes `region`, so by-province / by-region views are
complete. Deterministic, offline, and idempotent (safe to re-run).

    python3 fix_provinces.py            # apply to source-data/branches_final.json + report
    python3 fix_provinces.py --check    # report what WOULD change; exit 1 if anything unresolved
"""
import os, json, argparse, collections
from lib.regionmap import canonical, region_of, REGION

ROOT = os.path.dirname(os.path.abspath(__file__))
MASTER = os.path.join(os.path.dirname(ROOT), "source-data", "branches_final.json")


def run(check=False):
    master = json.load(open(MASTER, encoding="utf-8"))
    changed, unresolved = [], collections.Counter()
    for b in master:
        cp = canonical(b.get("prov", ""), b.get("district"))
        cr = region_of(b.get("prov", ""), b.get("district"))
        if cp != b.get("prov") or cr != b.get("region"):
            changed.append((b["name"], b.get("prov"), cp, b.get("region"), cr))
            if not check:
                b["prov"], b["region"] = cp, cr
        if cr == "Other":
            unresolved[b.get("prov") or "(blank)"] += 1

    print(f"{len(changed)} records normalized "
          f"({len(set(c[1] for c in changed))} distinct bad province strings)")
    for name, op, cp, oreg, creg in changed[:60]:
        print(f"  {op!r:24} -> {cp!r:14} [{oreg} -> {creg}]  {name[:30]}")
    if len(changed) > 60:
        print(f"  … and {len(changed) - 60} more")

    distinct_after = len({(canonical(b.get('prov',''), b.get('district'))) for b in master})
    print(f"distinct provinces after: {distinct_after}  (canonical set = {len(REGION)})")
    if unresolved:
        print(f"STILL UNRESOLVED -> region 'Other': {sum(unresolved.values())} records")
        for p, c in unresolved.most_common():
            print(f"  {p!r}: {c}")

    if check:
        return 1 if unresolved else 0
    json.dump(master, open(MASTER, "w"), ensure_ascii=False)
    print(f"wrote {MASTER}")
    print("next: run `python3 derive.py` to push the corrected regions into platform/data")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="normalize province/region in the master")
    ap.add_argument("--check", action="store_true",
                    help="report changes without writing; exit 1 if any record stays unresolved")
    raise SystemExit(run(check=ap.parse_args().check))
