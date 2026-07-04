#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_scene_places.py — dense Overture POI for the 3D scenes (objective: "who works nearby").

The 3D scene's POI columns are fed by catchment_poi.json (national OSM, ~69k points). Overture is
~24x denser (1.69M named places nationally, already pulled to source-data/occupation_places_named.json)
and carries real business NAMES. This builder CLIPS that set to each committed catchment city's bbox
(so the served file stays bounded — a national file would be ~34MB) and writes
platform/data/<city>_places.json: the 14 Overture economic buckets, each an array of [lng,lat] (name
dropped for the scene — the columns are density, names live in occupation_leads.json).

  python3 build_scene_places.py            # (re)build for every committed <city>_catchment.json
  python3 build_scene_places.py --check    # byte-exact reproduce gate

SKIP-PASS (exit 3) when source-data/occupation_places_named.json is absent (gitignored 147MB bulk
input; CI never has it) — the committed <city>_places.json outputs are the canonical artifact and the
gate does not fail for a missing re-pullable input (same pattern as build_occupation_leads.py).

NO fabrication: only real Overture points inside the bbox are written. Provinces served from the R2
CDN get their _places.json pulled on the desktop the same way the catchments are.
"""
import os, sys, json, argparse, hashlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "source-data", "occupation_places_named.json")
DATA = os.path.join(ROOT, "platform", "data")

def committed_cities():
    out = []
    for fn in sorted(os.listdir(DATA)):
        if fn.endswith("_catchment.json") and not fn.startswith("."):
            out.append(fn[:-len("_catchment.json")])
    return out

def bbox_of(city):
    d = json.load(open(os.path.join(DATA, city + "_catchment.json"), encoding="utf-8"))
    b = d.get("buildings") or []
    minx = miny = 1e9; maxx = maxy = -1e9
    for x in b:
        p = x.get("p")
        if not p:
            cx, cy = x.get("cx"), x.get("cy")
            if cx is None:
                continue
            p = [[cx, cy]]
        for pt in p:
            if pt[0] < minx: minx = pt[0]
            if pt[0] > maxx: maxx = pt[0]
            if pt[1] < miny: miny = pt[1]
            if pt[1] > maxy: maxy = pt[1]
    if minx > maxx:
        return None
    # small pad so fringe POI at the edge still show
    return [minx - 0.01, miny - 0.01, maxx + 0.01, maxy + 0.01]

# per-bucket cap so a mega-city file stays serve-able (Bangkok food alone is ~60k points). Above the
# cap we keep a DETERMINISTIC evenly-strided subset (every Nth after a stable sort) — visually still a
# dense mat, byte-reproducible, no RNG. Density, not a census (the census lives in occupation_leads).
CAP = 6000

def build_city(city, places, buckets):
    bb = bbox_of(city)
    if not bb:
        return None
    lo_x, lo_y, hi_x, hi_y = bb
    by = {i: [] for i in range(len(buckets))}
    for p in places:
        x, y, bi = p[0], p[1], p[2]
        if lo_x <= x <= hi_x and lo_y <= y <= hi_y:
            by.setdefault(bi, []).append([round(x, 5), round(y, 5)])
    for bi, arr in by.items():
        if len(arr) > CAP:
            arr.sort()                                   # stable spatial order (by lng then lat)
            stride = len(arr) / CAP
            by[bi] = [arr[int(k * stride)] for k in range(CAP)]
    return {
        "meta": {
            "city": city,
            "source": "Overture Maps named places (occupation_places_named.json), clipped to the "
                      "catchment bbox",
            "label": "MEASURED (Overture place points)",
            "buckets": buckets,
            "count": sum(len(v) for v in by.values()),
        },
        "bbox": [round(v, 5) for v in bb],
        "places": {buckets[i]: by.get(i, []) for i in range(len(buckets))},
    }

def dumps(d):
    return json.dumps(d, ensure_ascii=False, separators=(",", ":"))

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    cities = committed_cities()
    if not os.path.exists(SRC):
        # skip-pass: bulk input absent (CI). Verify the committed outputs are at least well-formed.
        for city in cities:
            outp = os.path.join(DATA, city + "_places.json")
            if os.path.exists(outp):
                d = json.load(open(outp, encoding="utf-8"))
                if "places" not in d or "bbox" not in d:
                    # same CHECK FAIL / exit-1 convention as every other builder, instead of an
                    # uncaught AssertionError (see build_branch_density.py's BucketDriftError).
                    print(f"CHECK FAIL: {city}_places.json malformed (missing 'places'/'bbox')", file=sys.stderr)
                    sys.exit(1)
        print("build_scene_places.py: SKIP (occupation_places_named.json absent; committed outputs valid)")
        sys.exit(3)
    src = json.load(open(SRC, encoding="utf-8"))
    places, buckets = src["places"], src["buckets"]
    drift = False
    for city in cities:
        payload = build_city(city, places, buckets)
        if payload is None:
            continue
        outp = os.path.join(DATA, city + "_places.json")
        new = dumps(payload)
        if a.check:
            cur = open(outp, encoding="utf-8").read() if os.path.exists(outp) else ""
            if cur != new:
                print(f"[DRIFT] {city}_places.json (run: python3 pipeline/build_scene_places.py)")
                drift = True
            else:
                print(f"[ok] {city}_places.json ({payload['meta']['count']} pts)")
        else:
            with open(outp, "w", encoding="utf-8") as f:
                f.write(new)
            print(f"{city}_places.json: {payload['meta']['count']} Overture pts "
                  f"({len(new)/1048576:.1f} MB)")
    if a.check and drift:
        sys.exit(1)

if __name__ == "__main__":
    main()
