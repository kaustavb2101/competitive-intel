#!/usr/bin/env python3
"""
build_amphoe_occupations.py — per-DISTRICT (amphoe) occupation mix.

WHAT THIS DOES
--------------
Rolls the measured Overture Places source layer (source-data/overture_places.json,
written by pull_overture_places.py) up into each of the 928 amphoe (district)
polygons in source-data/th_amphoe.geojson via point-in-polygon, producing
platform/data/amphoe_occupations.json keyed by the SAME amphoe id (the GeoJSON
"shapeID") that build_amphoe.py uses. For every amphoe it emits the total places
inside the polygon, the per-occupation-bucket counts, and the dominant bucket.

This is the district-level companion to build_occupations.py (which rolls the same
source layer up per-branch within 10km). Where that answers "who works near this
branch", this answers "what's the occupation mix of this district" — including
zero-branch white-space amphoe, since the join is purely geometric.

DETERMINISTIC + NETWORK-FREE
----------------------------
No network. Given the same source layer + th_amphoe.geojson it reproduces
byte-for-byte, so it carries --check (the QA gate runs it). The point-in-polygon
join is build_amphoe.py's exactly (bbox prefilter + ray-cast with hole handling).
A spatial bbox grid index keeps it tractable for a national places pull.

OUTPUT (platform/data/amphoe_occupations.json):
  { "meta": {source, n_amphoe, n_places, n_placed, buckets:[labels], measured:true},
    "buckets": [ {"key","label"}, ... ],            # same order as the source layer
    "amphoe": { "<shapeID>": {"t": total, "o": [count per bucket], "dom": bucket_idx_or_-1}, ... } }
The "amphoe" map is keyed by shapeID (build_amphoe.py's amphoe record "id"), so the
frontend / build_amphoe.py can join district occupations to a district by its id.
Entries are emitted for EVERY amphoe (zero-filled where no places fall inside).

Usage:
  python3 build_amphoe_occupations.py            # build/refresh amphoe_occupations.json
  python3 build_amphoe_occupations.py --check    # verify the committed file reproduces byte-exact
                                                 # (passes quietly if the source layer is absent)
"""
import argparse, json, math, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, "source-data", "overture_places.json")
AMPHOE = os.path.join(ROOT, "source-data", "th_amphoe.geojson")
OUT = os.path.join(ROOT, "platform", "data", "amphoe_occupations.json")

CELL_DEG = 0.1          # ~11km grid cell for the bbox spatial index


def _load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def cell_key(lng, lat):
    return (math.floor(lng / CELL_DEG), math.floor(lat / CELL_DEG))


# ── point-in-polygon (identical to build_amphoe.py: bbox prefilter + ray-cast) ──
def _rings(geom):
    return geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]


def _bbox(geom):
    xs, ys = [], []
    for poly in _rings(geom):
        for x, y in poly[0]:
            xs.append(x); ys.append(y)
    return min(xs), min(ys), max(xs), max(ys)


def _pip(x, y, ring):
    inside = False; n = len(ring); j = n - 1
    for i in range(n):
        xi, yi = ring[i]; xj, yj = ring[j]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-12) + xi):
            inside = not inside
        j = i
    return inside


def _contains(geom, x, y):
    for poly in _rings(geom):
        if _pip(x, y, poly[0]) and not any(_pip(x, y, h) for h in poly[1:]):
            return True
    return False


def build():
    if not os.path.exists(SRC):
        return None  # no source layer yet — caller decides what to do
    src = _load(SRC)
    buckets = src.get("buckets", [])
    nbuckets = len(buckets)
    places = src.get("places", [])

    amphoe = _load(AMPHOE)["features"]
    polys = [(f, _bbox(f["geometry"])) for f in amphoe]

    # spatial grid over polygon bboxes: cell -> list of polygon indices whose bbox
    # touches that cell. A place only tests polygons in its own cell.
    grid = {}
    for pi, (f, (x0, y0, x1, y1)) in enumerate(polys):
        cx0, cy0 = cell_key(x0, y0)
        cx1, cy1 = cell_key(x1, y1)
        for cx in range(cx0, cx1 + 1):
            for cy in range(cy0, cy1 + 1):
                grid.setdefault((cx, cy), []).append(pi)

    # per-amphoe accumulator, keyed by shapeID (build_amphoe.py's record "id")
    totals = {f["properties"]["shapeID"]: 0 for f in amphoe}
    counts = {f["properties"]["shapeID"]: [0] * nbuckets for f in amphoe}

    n_placed = 0
    for p in places:
        lng, lat = p[0], p[1]
        bi = p[2]
        for pidx in grid.get(cell_key(lng, lat), ()):
            f, (x0, y0, x1, y1) = polys[pidx]
            if x0 <= lng <= x1 and y0 <= lat <= y1 and _contains(f["geometry"], lng, lat):
                sid = f["properties"]["shapeID"]
                totals[sid] += 1
                if 0 <= bi < nbuckets:
                    counts[sid][bi] += 1
                n_placed += 1
                break

    # assemble per-amphoe records (deterministic order: th_amphoe feature order)
    out_amphoe = {}
    for f in amphoe:
        sid = f["properties"]["shapeID"]
        o = counts[sid]
        t = totals[sid]
        # dominant bucket: max count; -1 when the amphoe has no placed establishments
        # (or no typed buckets). max(range(...), key=...) ties to the lowest index.
        if t > 0 and nbuckets and any(o):
            dom = max(range(nbuckets), key=lambda i: o[i])
        else:
            dom = -1
        out_amphoe[sid] = {"t": t, "o": o, "dom": dom}

    return {
        "meta": {
            "source": src.get("meta", {}).get("source", "Overture Maps Places"),
            "n_amphoe": len(amphoe),
            "n_places": len(places),
            "n_placed": n_placed,
            "buckets": [bk["label"] for bk in buckets],
            "measured": True,
        },
        "buckets": buckets,
        "amphoe": out_amphoe,
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
            print(f"build_amphoe_occupations.py --check: skip ({msg})")
            return
        sys.exit(f"build_amphoe_occupations.py: {msg}")

    payload = serialize(obj)

    if args.check:
        if not os.path.exists(OUT):
            sys.exit("build_amphoe_occupations.py --check: amphoe_occupations.json missing but a "
                     "source layer exists — run build_amphoe_occupations.py to generate it.")
        cur = open(OUT, encoding="utf-8").read()
        if cur != payload:
            sys.exit("build_amphoe_occupations.py --check: amphoe_occupations.json drifted from "
                     "source-data/overture_places.json — re-run build_amphoe_occupations.py.")
        print("build_amphoe_occupations.py --check: OK (byte-exact)")
        return

    with open(OUT, "w", encoding="utf-8") as f:
        f.write(payload)
    m = obj["meta"]
    nz = sum(1 for v in obj["amphoe"].values() if v["t"] > 0)
    kb = os.path.getsize(OUT) / 1024.0
    print(f"wrote {OUT}  ({kb:.1f} KB)")
    print(f"  {m['n_places']} places -> {m['n_placed']} placed in {nz}/{m['n_amphoe']} amphoe")


if __name__ == "__main__":
    main()
