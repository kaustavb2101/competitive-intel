#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_national_places.py — ONE national dense-POI file for EVERY province's 3D scene.

The problem: the per-city <city>_places.json files (build_scene_places.py) only exist for the
committed catchment cities (Rayong/Bangkok/Chiang Mai). The other 74 provinces fall back to the
sparse national OSM set (catchment_poi.json, ~69k pts). This builder gives ALL of them Overture
density from a SINGLE committed file — no per-province hosting, no R2.

The whole 1.69M-point Overture set is ~34MB (too big to serve). So we SPATIALLY GRID-THIN it: keep at
most one point per ~GRID-degree cell per bucket (deterministic — the first point per cell in a stable
sort). That preserves the national spatial pattern (dense cities stay dense, empty land stays empty)
while bounding the file. Cities that ALSO have a per-city file get full density there; everywhere else
gets this. Output: platform/data/national_places.json (Overture buckets -> [lng,lat] arrays).

  python3 build_national_places.py            # rebuild
  python3 build_national_places.py --check    # byte-exact gate (SKIP-3 when the bulk source absent)

NO fabrication: only real Overture points survive the thinning. MEASURED (Overture place points).
"""
import os, sys, json, argparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "source-data", "occupation_places_named.json")
OUT = os.path.join(ROOT, "platform", "data", "national_places.json")

GRID = 0.02    # ~2.2km cells: national file lands ~4MB, dense cities still read

def build(src):
    places, buckets = src["places"], src["buckets"]
    by = {i: {} for i in range(len(buckets))}   # bucket -> {cellkey: [lng,lat]} (first wins)
    for p in places:
        x, y, bi = p[0], p[1], p[2]
        cell = (int(x / GRID), int(y / GRID))
        d = by.get(bi)
        if d is None:
            continue
        if cell not in d:
            d[cell] = [round(x, 5), round(y, 5)]
    # deterministic order: sort each bucket's kept points by (lng,lat)
    out = {}
    for bi, d in by.items():
        pts = sorted(d.values())
        out[buckets[bi]] = pts
    total = sum(len(v) for v in out.values())
    return {
        "meta": {
            "source": "Overture Maps named places, spatially grid-thinned to ~%gkm cells" % (GRID * 111),
            "label": "MEASURED (Overture place points, thinned for national coverage)",
            "grid_deg": GRID, "buckets": buckets, "count": total,
            "note": "national fallback for every province's 3D scene; per-city <city>_places.json "
                    "supplies full density where present.",
            "generated_by": "pipeline/build_national_places.py",
        },
        "places": out,
    }

def dumps(d):
    return json.dumps(d, ensure_ascii=False, separators=(",", ":"))

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    if not os.path.exists(SRC):
        if os.path.exists(OUT):
            d = json.load(open(OUT, encoding="utf-8"))
            if "places" not in d:
                # same CHECK FAIL / exit-1 convention as every other builder, instead of an
                # uncaught AssertionError — a corrupted committed file should read like any
                # other gate failure, not a crash (see build_branch_density.py's BucketDriftError).
                print("CHECK FAIL: national_places.json malformed (missing 'places' key)", file=sys.stderr)
                sys.exit(1)
        print("build_national_places.py: SKIP (occupation_places_named.json absent; committed output valid)")
        sys.exit(3)
    payload = build(json.load(open(SRC, encoding="utf-8")))
    new = dumps(payload)
    if a.check:
        cur = open(OUT, encoding="utf-8").read() if os.path.exists(OUT) else ""
        if cur != new:
            print("[DRIFT] national_places.json (run: python3 pipeline/build_national_places.py)")
            sys.exit(1)
        print("[ok] national_places.json (%d pts)" % payload["meta"]["count"])
    else:
        with open(OUT, "w", encoding="utf-8") as f:
            f.write(new)
        print("national_places.json: %d Overture pts (%.1f MB)" % (payload["meta"]["count"], len(new) / 1048576))

if __name__ == "__main__":
    main()
