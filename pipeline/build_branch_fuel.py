#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_branch_fuel.py — per-branch MEASURED fuel-station density (≤10 km), from the committed
source-data/fuel_stations.json (pull_fuel_stations.py, OSM Overpass).

Why (objective #1 + #2): fuel stations are a direct vehicle-economy signal — where fuel sells,
the vehicles that back AutoX's title book live and move. Dense fuel + few rivals = collateral-rich
white space; the popup line gives every branch its measured count.

Deterministic + network-free over committed inputs; INDEX-ALIGNED to branches.json + fingerprinted;
--check byte-exact. Exits 3 (SKIP, not drift) when the source pull is absent — mirrors
build_branch_density.py's honest ABSENT state.

  python3 build_branch_fuel.py
  python3 build_branch_fuel.py --check
"""
import argparse, json, math, os, sys
from collections import defaultdict
from lib.fingerprint import branches_fingerprint

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "source-data", "fuel_stations.json")
BRANCHES = os.path.join(ROOT, "platform", "data", "branches.json")
OUT = os.path.join(ROOT, "platform", "data", "branch_fuel.json")
RADIUS_KM = 10.0
CELL = 0.1  # ~11 km grid cell — one-ring neighborhood covers the 10 km radius


def _hav_km(lng1, lat1, lng2, lat2):
    rl1, rl2 = math.radians(lat1), math.radians(lat2)
    dlat, dlng = rl2 - rl1, math.radians(lng2 - lng1)
    a = math.sin(dlat / 2) ** 2 + math.cos(rl1) * math.cos(rl2) * math.sin(dlng / 2) ** 2
    return 2 * 6371.0088 * math.asin(math.sqrt(a))


def build():
    src = json.load(open(SRC, encoding="utf-8"))
    pts = src["items"]
    branches = json.load(open(BRANCHES, encoding="utf-8"))
    items = branches if isinstance(branches, list) else branches.get("items", branches)

    grid = defaultdict(list)
    for lng, lat in pts:
        grid[(int(lng / CELL), int(lat / CELL))].append((lng, lat))

    out = []
    for b in items:
        blng, blat = b["x"], b["y"]
        cx, cy = int(blng / CELL), int(blat / CELL)
        n = 0
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for lng, lat in grid.get((cx + dx, cy + dy), ()):
                    if _hav_km(blng, blat, lng, lat) <= RADIUS_KM:
                        n += 1
        out.append({"n10": n})

    vals = sorted(x["n10"] for x in out)
    return {
        "meta": {
            "title": "Fuel stations within 10 km of each branch (OSM, measured)",
            "generated_by": "pipeline/build_branch_fuel.py",
            "label": "MEASURED — OSM amenity=fuel count ≤10 km per branch (vehicle-economy / rural-reach signal). "
                     "Coverage caveat: OSM completeness varies by area; treat as a floor, not a census.",
            "source": "source-data/fuel_stations.json (pull_fuel_stations.py — Overpass; pulled %s, %d stations)" % (
                src["meta"].get("pulled") or "n/a", src["meta"].get("n", len(pts))),
            "radius_km": RADIUS_KM,
            "branches_fingerprint": branches_fingerprint(items),
            "n_branches": len(items),
            "median_n10": vals[len(vals) // 2] if vals else 0,
            "max_n10": vals[-1] if vals else 0,
        },
        "branches": out,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    if not os.path.exists(SRC):
        print("build_branch_fuel.py: source-data/fuel_stations.json absent — run pull_fuel_stations.py (SKIP).")
        sys.exit(3)
    payload = json.dumps(build(), ensure_ascii=False, separators=(",", ":"))
    if args.check:
        if not os.path.exists(OUT):
            print("build_branch_fuel.py --check: SKIP (branch_fuel.json not generated yet)")
            sys.exit(3)
        if open(OUT, encoding="utf-8").read() != payload:
            sys.exit("build_branch_fuel.py --check: drifted — re-run the builder.")
        print("build_branch_fuel.py --check: OK (byte-exact)")
        return
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(payload)
    obj = json.loads(payload)
    print("wrote %s — median ≤10km: %d, max: %d" % (OUT, obj["meta"]["median_n10"], obj["meta"]["max_n10"]))


if __name__ == "__main__":
    main()
