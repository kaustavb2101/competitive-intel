#!/usr/bin/env python3
"""check_peer_rollup.py — tripwire: the two obj-#2 peer surfaces must agree per brand.

WHY THIS EXISTS
    The exec competitive read (objective #2) is served by TWO committed layers that both
    count the same big-4 rival field — but reach their per-brand branch counts by DIFFERENT
    paths off the SAME census (source-data/competitors_census.json):

        platform/data/competitor_coverage.json  (build_competitor_coverage.py)
            de-duplicates the census DIRECTLY into a national `found` count per brand.
        platform/data/peer_province.json         (build_peer_province.py)
            census -> rival_density.json (district PIP rollup) -> province rollup, then the
            per-province `by_brand` counts sum back up to a national count per brand.

    Each builder already has a `--check` in tests/run.sh, but every `--check` only proves a
    file reproduces from ITS OWN input — NOT that the two surfaces agree with each other. A
    future change to the de-dup radius in build_competitor_coverage.py, or to the district
    assignment in build_rival_density.py, would move ONE path's per-brand count while both
    `--check`s stay green, and the exec would read two silently-diverging peer boards. That
    cross-layer-consistency class is exactly what this repo's determinism gate exists to
    catch — the 2026-08-11(b) SERVICE_AUDIT verified the AutoX-book link this way but the
    per-brand branch rollup was left unasserted. This closes it.

WHAT IT DOES
    Nothing is written — a pure cross-consistency assertion (no platform/data output, no
    provenance regen). Reads both committed layers and asserts, for the big-4 rivals:

      (1) sum(peer_province.by_brand[brand] over all provinces) == competitor_coverage
          brands[brand].found                                  — per-brand national rollup
      (2) sum of all four brand rollups == competitor_coverage meta.totals.found
                                                                — the 16,503-rival total
      (3) sum(peer_province.autox over all provinces) == competitor_coverage
          meta.national_standing.autox_branches                — the AutoX anchor (2,015)

    Values are DERIVED from the live files, never re-typed here, so a census refresh that
    rebuilds both surfaces consistently stays green while a one-sided logic change trips it.
    Both `check_peer_rollup.py` and the `--check` alias run the same verification (there is
    nothing to "build"), exiting 1 on any mismatch — a clean tripwire for tests/run.sh and
    rederive_drift.py alike.

    python3 pipeline/check_peer_rollup.py            # report each figure, exit 1 on drift
    python3 pipeline/check_peer_rollup.py --check     # identical (gate-convention alias)
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "platform", "data")
CC = os.path.join(DATA, "competitor_coverage.json")
PP = os.path.join(DATA, "peer_province.json")


def _load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _pp_rollup(pp):
    """Sum peer_province.by_brand across all provinces -> {brand: national count}, plus the
    AutoX total. Guards the shape it depends on so a truncated file fails loud, not silent."""
    provs = pp.get("provinces")
    if not isinstance(provs, list) or not provs:
        sys.exit("FATAL: peer_province.json has no non-empty 'provinces' list")
    by_brand = {}
    autox = 0
    for p in provs:
        autox += int(p.get("autox", 0) or 0)
        bb = p.get("by_brand", {})
        if not isinstance(bb, dict):
            sys.exit("FATAL: peer_province.json province %r has a non-dict 'by_brand'"
                     % p.get("province_th"))
        for brand, n in bb.items():
            by_brand[brand] = by_brand.get(brand, 0) + int(n or 0)
    return by_brand, autox


def _cc_found(cc):
    """competitor_coverage.brands -> {brand: found}."""
    brands = cc.get("brands")
    if not isinstance(brands, list) or not brands:
        sys.exit("FATAL: competitor_coverage.json has no non-empty 'brands' list")
    out = {}
    for b in brands:
        if "brand" not in b or "found" not in b:
            sys.exit("FATAL: competitor_coverage.json brand row missing brand/found: %r" % b)
        out[b["brand"]] = int(b["found"])
    return out


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true",
                    help="gate-convention alias; identical behaviour (nothing is written)")
    ap.parse_args()

    cc = _load(CC)
    pp = _load(PP)

    cc_found = _cc_found(cc)
    pp_by_brand, pp_autox = _pp_rollup(pp)

    # (3) AutoX anchor
    cc_autox = int(cc.get("meta", {}).get("national_standing", {}).get("autox_branches", -1))
    # (2) rival total
    cc_total = int(cc.get("meta", {}).get("totals", {}).get("found", -1))

    checks = []  # (label, derived_expected, actual)
    # (1) per-brand national rollup — every brand competitor_coverage counts must reconcile.
    for brand in sorted(cc_found):
        checks.append((
            "per-brand rollup [%s]" % brand,
            cc_found[brand],                       # expected: the direct-census `found`
            pp_by_brand.get(brand, 0),             # actual:   the province-rollup sum
        ))
    # (2) all-rival national total
    checks.append(("all-rival total (found)", cc_total, sum(pp_by_brand.values())))
    # (3) AutoX anchor
    checks.append(("AutoX anchor (branches)", cc_autox, pp_autox))

    mism = []
    for label, expected, actual in checks:
        ok = expected == actual
        print("  [%s] %-30s competitor_coverage=%-7s  peer_province_rollup=%-7s"
              % ("OK " if ok else "MISS", label, expected, actual))
        if not ok:
            mism.append((label, expected, actual))

    if mism:
        print("\nFAIL check_peer_rollup: %d peer figure(s) disagree between the two obj-#2 "
              "surfaces —" % len(mism))
        for label, expected, actual in mism:
            print("    %s: competitor_coverage.json=%s vs peer_province.json rollup=%s"
                  % (label, expected, actual))
        print("  The direct-census count (build_competitor_coverage.py) and the province "
              "rollup (build_rival_density.py -> build_peer_province.py) have diverged. "
              "Rebuild both from the current census and reconcile the de-dup / district "
              "assignment logic (run: python3 pipeline/build_rival_density.py && "
              "python3 pipeline/build_peer_province.py && "
              "python3 pipeline/build_competitor_coverage.py).")
        sys.exit(1)

    print("\nOK check_peer_rollup: all %d cross-surface peer counts reconcile "
          "(competitor_coverage.json == peer_province.json rollup)." % len(checks))


if __name__ == "__main__":
    main()
