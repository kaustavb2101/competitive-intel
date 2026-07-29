#!/usr/bin/env python3
"""
build_occupations.py — per-branch 10km occupation mix (the granular employment layer).

WHAT THIS DOES
--------------
Projects the measured Overture Places source layer (source-data/overture_places.json,
written by pull_overture_places.py) onto the AutoX branch network: for every one of the
2,015 branches it counts the establishment points of each occupation bucket within 10km
(client-of-the-data haversine), producing platform/data/branch_occupations.json.

This is the MEASURED upgrade to the "Who works nearby" panel, which today shows an
ESTIMATED occupation proxy derived from the ~13 OSM POI within-10km counts (k10). When
this file is present the panel shows real, point-level establishment counts by occupation;
when it is absent the app falls back to the estimate (fully graceful).

DETERMINISTIC + NETWORK-FREE
----------------------------
No network. Given the same source layer + branches.json it reproduces byte-for-byte, so
it carries --check (the QA gate runs it). A spatial grid index keeps it fast even for a
national places pull (only candidate cells within the 10km radius are scanned).

OUTPUT (platform/data/branch_occupations.json):
  { "meta": {source, radius_km, n_branches, n_places, buckets:[labels], measured:true},
    "buckets": [ {"key","label"}, ... ],            # same order as the source layer
    "branches": [ {"t": total_within_10km, "o": [count per bucket]}, ... ] }
The "branches" array is INDEX-ALIGNED to platform/data/branches.json (entry i ↔ branch i),
so the frontend reads occupations for a branch by its index. Entries are emitted for every
branch (zero-filled where no places fall in range).

Usage:
  python3 build_occupations.py            # build/refresh branch_occupations.json
  python3 build_occupations.py --check    # verify the committed file reproduces byte-exact
                                          # (passes quietly if the source layer is absent)
"""
import argparse, json, math, os, sys

from lib.fingerprint import branches_fingerprint

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, "source-data", "overture_places.json")
BRANCHES = os.path.join(ROOT, "platform", "data", "branches.json")
OUT = os.path.join(ROOT, "platform", "data", "branch_occupations.json")

RADIUS_KM = 10.0
CELL_DEG = 0.1          # ~11km grid cell; a branch scans its cell ± 1 to cover 10km
EARTH_KM = 6371.0
D2R = math.pi / 180.0


def haversine_km(lng1, lat1, lng2, lat2):
    dlat = (lat2 - lat1) * D2R
    dlng = (lng2 - lng1) * D2R
    a = (math.sin(dlat / 2) ** 2
         + math.cos(lat1 * D2R) * math.cos(lat2 * D2R) * math.sin(dlng / 2) ** 2)
    return 2 * EARTH_KM * math.asin(min(1.0, math.sqrt(a)))


def cell_key(lng, lat):
    return (math.floor(lng / CELL_DEG), math.floor(lat / CELL_DEG))


def build():
    if not os.path.exists(SRC):
        return None  # no source layer yet — caller decides what to do
    src = json.load(open(SRC, encoding="utf-8"))
    buckets = src.get("buckets", [])
    nbuckets = len(buckets)
    places = src.get("places", [])

    # spatial grid: cell -> list of (lng, lat, bucket_idx)
    grid = {}
    for p in places:
        grid.setdefault(cell_key(p[0], p[1]), []).append(p)

    branches = json.load(open(BRANCHES, encoding="utf-8"))
    out_branches = []
    for b in branches:
        lng, lat = b.get("x"), b.get("y")
        counts = [0] * nbuckets
        total = 0
        if lng is not None and lat is not None:
            cx, cy = cell_key(lng, lat)
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for p in grid.get((cx + dx, cy + dy), ()):
                        if haversine_km(lng, lat, p[0], p[1]) <= RADIUS_KM:
                            total += 1
                            bi = p[2]
                            if 0 <= bi < nbuckets:
                                counts[bi] += 1
        out_branches.append({"t": total, "o": counts})

    return {
        "meta": {
            "source": src.get("meta", {}).get("source", "Overture Maps Places"),
            "radius_km": RADIUS_KM,
            "n_branches": len(branches),
            "branches_fingerprint": branches_fingerprint(branches),
            "n_places": len(places),
            "buckets": [bk["label"] for bk in buckets],
            "measured": True,
        },
        "buckets": buckets,
        "branches": out_branches,
    }


def serialize(obj):
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true",
                    help="verify the committed output reproduces byte-exact (no write)")
    args = ap.parse_args()

    obj = build()
    if obj is None:
        msg = ("no source-data/overture_places.json yet — run pull_overture_places.py "
               "(from a normal/Thai network) first.")
        if args.check:
            print(f"build_occupations.py --check: skip ({msg})")
            return
        sys.exit(f"build_occupations.py: {msg}")

    payload = serialize(obj)

    if args.check:
        if not os.path.exists(OUT):
            sys.exit("build_occupations.py --check: branch_occupations.json missing but a "
                     "source layer exists — run build_occupations.py to generate it.")
        cur = open(OUT, encoding="utf-8").read()
        if cur != payload:
            sys.exit("build_occupations.py --check: branch_occupations.json drifted from "
                     "source-data/overture_places.json — re-run build_occupations.py.")
        print("build_occupations.py --check: OK (byte-exact)")
        return

    with open(OUT, "w", encoding="utf-8") as f:
        f.write(payload)
    m = obj["meta"]
    nz = sum(1 for b in obj["branches"] if b["t"] > 0)
    kb = os.path.getsize(OUT) / 1024.0
    print(f"wrote {OUT}  ({kb:.1f} KB)")
    print(f"  {m['n_places']} places -> {nz}/{m['n_branches']} branches have establishments "
          f"within {int(RADIUS_KM)}km")


if __name__ == "__main__":
    main()
