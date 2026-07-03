#!/usr/bin/env python3
"""
build_amphoe_geo.py — SIMPLIFIED district (amphoe) polygon export for the map
============================================================================
The National Leaflet map (#map in the SPA) paints a choropleth of the 928 amphoe
polygons, coloured by the active DISTRICT lens (white-space / risk). The raw
boundary file — source-data/th_amphoe.geojson — is 8.4MB and too heavy to ship to
a browser. This builder produces a lean, shippable polygon layer:

  platform/data/amphoe_geo.json

For every one of the 928 features it keeps ONLY:
  - id       : properties.shapeID  (the SAME key build_amphoe.py emits as amphoe[].id,
               so the frontend joins polygon -> amphoe record 1:1 on id)
  - geometry : the ORIGINAL rings, simplified with a pure-python Douglas–Peucker
               (epsilon ~0.003° ≈ 300m), coords rounded to 4 decimals (~11m), and
               tiny sliver rings dropped. No new data is invented — this is the real
               boundary geometry, only decimated.

Deterministic + network-free (matches the other builders). Carries --check for a
byte-exact reproduce, so it belongs in the QA determinism gate.

    python3 build_amphoe_geo.py            # write platform/data/amphoe_geo.json
    python3 build_amphoe_geo.py --check    # verify committed output byte-reproduces
"""
import os, json, argparse

ROOT = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(ROOT)
SRC  = os.path.join(REPO, "source-data")
GEO  = os.path.join(SRC, "th_amphoe.geojson")
OUT  = os.path.join(REPO, "platform", "data", "amphoe_geo.json")

EPS   = 0.003     # Douglas–Peucker tolerance in degrees (~300m at Thai latitudes)
NDEC  = 4         # round coords to 4 decimals (~11m) — plenty for a national choropleth
MIN_RING_PTS = 4  # a valid closed ring needs >=4 points (first==last); drop slivers below


def _rings(geom):
    """Yield (poly_index, ring_index, ring) for Polygon/MultiPolygon uniformly."""
    if geom["type"] == "MultiPolygon":
        for pi, poly in enumerate(geom["coordinates"]):
            for ri, ring in enumerate(poly):
                yield pi, ri, ring
    else:  # Polygon
        for ri, ring in enumerate(geom["coordinates"]):
            yield 0, ri, ring


def _perp_dist2(p, a, b):
    """Squared perpendicular distance from point p to segment a-b (planar, deg space)."""
    ax, ay = a; bx, by = b; px, py = p
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return (px - ax) ** 2 + (py - ay) ** 2
    t = ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)
    if t < 0:
        cx, cy = ax, ay
    elif t > 1:
        cx, cy = bx, by
    else:
        cx, cy = ax + t * dx, ay + t * dy
    return (px - cx) ** 2 + (py - cy) ** 2


def _dp(pts, eps2):
    """Iterative Douglas–Peucker on an open polyline. Returns kept points (in order)."""
    n = len(pts)
    if n < 3:
        return pts[:]
    keep = [False] * n
    keep[0] = keep[n - 1] = True
    stack = [(0, n - 1)]
    while stack:
        lo, hi = stack.pop()
        if hi - lo < 2:
            continue
        a, b = pts[lo], pts[hi]
        dmax = -1.0; idx = -1
        for i in range(lo + 1, hi):
            d = _perp_dist2(pts[i], a, b)
            if d > dmax:
                dmax = d; idx = i
        if dmax > eps2 and idx != -1:
            keep[idx] = True
            stack.append((lo, idx)); stack.append((idx, hi))
    return [pts[i] for i in range(n) if keep[i]]


def _simplify_ring(ring):
    """Simplify a closed ring: DP on the open path, re-close, round, dedupe consecutive.
    Returns None if the result collapses below a valid ring."""
    if len(ring) < MIN_RING_PTS:
        return None
    closed = ring[0] == ring[-1]
    path = ring[:-1] if closed else ring[:]  # DP on the open polyline
    if len(path) < 3:
        simp = path[:]
    else:
        # DP wants both endpoints pinned; for a ring, pin the first point and run over
        # the open path, then re-close. Good enough + deterministic for choropleth fills.
        simp = _dp(path, EPS * EPS)
    # round + drop consecutive duplicates
    out = []
    for x, y in simp:
        rx, ry = round(x, NDEC), round(y, NDEC)
        if not out or out[-1][0] != rx or out[-1][1] != ry:
            out.append([rx, ry])
    # re-close
    if len(out) < 3:
        return None
    if out[0] != out[-1]:
        out.append([out[0][0], out[0][1]])
    if len(out) < MIN_RING_PTS:
        return None
    return out


def _simplify_geom(geom):
    """Simplify a Polygon/MultiPolygon; keep only the outer ring per polygon-part
    plus any holes that survive. Returns (type, coordinates) or None if it collapses."""
    if geom["type"] == "MultiPolygon":
        polys_out = []
        for poly in geom["coordinates"]:
            rings_out = []
            for ri, ring in enumerate(poly):
                s = _simplify_ring(ring)
                if s is None:
                    if ri == 0:
                        break  # outer ring gone → drop this whole part
                    continue   # a hole vanished → fine
                rings_out.append(s)
            if rings_out:
                polys_out.append(rings_out)
        if not polys_out:
            return None
        # a single surviving part → emit a plain Polygon (smaller + simpler client-side)
        if len(polys_out) == 1:
            return "Polygon", polys_out[0]
        return "MultiPolygon", polys_out
    else:  # Polygon
        rings_out = []
        for ri, ring in enumerate(geom["coordinates"]):
            s = _simplify_ring(ring)
            if s is None:
                if ri == 0:
                    return None
                continue
            rings_out.append(s)
        if not rings_out:
            return None
        return "Polygon", rings_out


def build():
    src = json.load(open(GEO, encoding="utf-8"))
    feats = src["features"]
    out_feats = []
    n_in_verts = 0; n_out_verts = 0; n_dropped = 0
    for f in feats:
        sid = f["properties"]["shapeID"]
        geom = f["geometry"]
        for _, _, ring in _rings(geom):
            n_in_verts += len(ring)
        simp = _simplify_geom(geom)
        if simp is None:
            # never expected (would mean a whole amphoe collapsed) — do NOT fabricate a
            # replacement; count it and skip so the map simply omits that polygon.
            n_dropped += 1
            continue
        gtype, coords = simp
        # count output vertices
        if gtype == "MultiPolygon":
            for poly in coords:
                for ring in poly:
                    n_out_verts += len(ring)
        else:
            for ring in coords:
                n_out_verts += len(ring)
        out_feats.append({
            "type": "Feature",
            "properties": {"id": sid},
            "geometry": {"type": gtype, "coordinates": coords},
        })
    obj = {
        "type": "FeatureCollection",
        "meta": {
            "generated_by": "pipeline/build_amphoe_geo.py",
            "source": "GADM/th_amphoe.geojson boundaries, simplified",
            "label": "MEASURED boundaries (geometry only) — Douglas–Peucker simplified for the map, "
                     "no attributes; join to amphoe.json on properties.id (== shapeID) for lens values",
            "simplify": {"algorithm": "douglas-peucker", "epsilon_deg": EPS,
                         "round_decimals": NDEC, "min_ring_points": MIN_RING_PTS},
            "n_features": len(out_feats),
            "n_features_dropped": n_dropped,
            "vertices_in": n_in_verts,
            "vertices_out": n_out_verts,
            "join_key": "properties.id == amphoe.json amphoe[].id (== th_amphoe.geojson shapeID)",
        },
        "features": out_feats,
    }
    return obj


def run(check=False):
    obj = build()
    text = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    if check:
        if not os.path.exists(OUT) or open(OUT, encoding="utf-8").read() != text:
            print(f"DRIFT: {os.path.relpath(OUT, REPO)}"); return 1
        print(f"OK: amphoe_geo.json reproduces ({obj['meta']['n_features']} features)")
        return 0
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(text)
    m = obj["meta"]
    print(f"wrote {m['n_features']} amphoe polygons -> platform/data/amphoe_geo.json")
    print(f"  vertices {m['vertices_in']} -> {m['vertices_out']} "
          f"({100*m['vertices_out']//max(1,m['vertices_in'])}% kept), dropped {m['n_features_dropped']}")
    print(f"  size {os.path.getsize(OUT)/1e6:.2f} MB")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="simplified amphoe polygon export for the map")
    ap.add_argument("--check", action="store_true")
    raise SystemExit(run(check=ap.parse_args().check))
