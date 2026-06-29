#!/usr/bin/env python3
"""Re-bake Rayong catchment building HEIGHTS (local, network-free, deterministic).

Problem this fixes: platform/data/rayong_catchment.json shipped a near-flat 6m carpet
(~96% of 3,631 buildings at one height, only 5 distinct values) because the original
bake used a uniform ~2-floor assumption. The 3D catchment scene therefore looked flat.

What this does: recomputes each building's height with the SAME type+footprint model
the branch-explorer page uses live (bldgHeight(tags, footprint_area)), reading OSM tags
back from source-data/bldg_wide.json (the raw Overpass pull these buildings came from).
Only the per-building `h` is rewritten; `fa` (floor-area, drives the reachable-population
card), `p`, `cx`, `cy`, `nm` and every other top-level key are preserved byte-compatibly.

Determinism: pure function of two committed files; no network. Re-run reproduces the
same output. Heights are rounded to 2dp so JS float vs Python float can't drift.

Provenance: OSM tags ARE present for all bldg_wide elements, but only ~0.4% carry a
measured height/levels tag — so the vast majority of heights are ESTIMATED from building
type + footprint area (OSM rarely tags height in Thailand). Same honest caveat the UI
already shows ("heights estimated from type + footprint").

Usage:
  python3 bake_catchment_heights.py            # rewrite platform/data/rayong_catchment.json
  python3 bake_catchment_heights.py --check     # verify committed file already matches (no write)
"""
import json, math, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CATCH = os.path.join(ROOT, 'platform', 'data', 'rayong_catchment.json')
WIDE  = os.path.join(ROOT, 'source-data', 'bldg_wide.json')

D2R = math.pi / 180.0


def ring_area_m2(ring, lat):
    """Footprint area (m2) of a lon/lat ring — mirrors branch-explorer.html ringAreaM2,
    but uses the building's own latitude for the lon->m scale (more accurate per-building)."""
    a = 0.0
    n = len(ring)
    for i in range(n):
        j = (i - 1) % n
        a += (ring[j][0] - ring[i][0]) * (ring[j][1] + ring[i][1])
    latm = 111320.0
    lngm = 111320.0 * math.cos(lat * D2R)
    return abs(a / 2.0) * latm * lngm


def bldg_height(tags, fa):
    """Faithful port of bldgHeight(tags, fa) from branch-explorer.html.
    `fa` here is FOOTPRINT area in m2 (not floor area)."""
    tags = tags or {}
    if tags.get('height'):
        try:
            h = float(str(tags['height']).split()[0])
            if h > 0:
                return min(h, 60.0)
        except ValueError:
            pass
    if tags.get('building:levels'):
        try:
            lv = float(str(tags['building:levels']).split(';')[0])
            if lv > 0:
                return min(lv * 3.2, 60.0)
        except ValueError:
            pass
    b = tags.get('building', 'yes')
    L = math.log2(max(fa or 60.0, 30.0))
    if b == 'house':
        return 6.0
    if b in ('residential', 'apartments') or 'residential' in b or 'apartments' in b:
        return max(12.0, min(45.0, 14.0 + L * 2.0))
    if any(k in b for k in ('retail', 'commercial', 'shop')):
        return 8.0
    if b == 'office':
        return 24.0
    if 'industrial' in b or 'warehouse' in b:
        return 11.0
    if b == 'school':
        return 9.0
    if b == 'hotel':
        return max(14.0, min(45.0, 18.0 + L * 2.0))
    if b == 'roof':
        return 4.0
    return 6.0 if fa < 120 else (9.0 if fa < 400 else (11.0 if fa < 800 else 13.0))


def jitter(h, ring):
    """Deterministic +-8% jitter, exactly as the live page (seed from first vertex)."""
    seed = abs(math.sin(ring[0][0] * 12.9898 + ring[0][1] * 78.233)) % 1.0
    return min(60.0, h * (0.92 + 0.16 * seed))


def tag_index(wide):
    """Map rounded first-vertex (lon,lat @5dp) -> tags, matching how `p` was stored."""
    idx = {}
    for el in wide.get('elements', []):
        geom = el.get('geometry')
        if not geom or len(geom) < 3:
            continue
        key = (round(geom[0]['lon'], 5), round(geom[0]['lat'], 5))
        # first writer wins; collisions are rare and the height model is robust to either
        idx.setdefault(key, el.get('tags') or {})
    return idx


def rebake(catch):
    wide = json.load(open(WIDE))
    idx = tag_index(wide)
    matched = 0
    measured = 0
    for bld in catch['buildings']:
        ring = bld['p']
        key = (round(ring[0][0], 5), round(ring[0][1], 5))
        tags = idx.get(key)
        if tags is not None:
            matched += 1
        else:
            tags = {}
        if tags.get('height') or tags.get('building:levels'):
            measured += 1
        # footprint area from the ring (NOT the stored `fa`, which is floor area)
        fp = ring_area_m2(ring, bld.get('cy', 12.7))
        h = jitter(bldg_height(tags, fp), ring)
        bld['h'] = round(h, 2)
    return catch, matched, measured


def dumps(obj):
    return json.dumps(obj, ensure_ascii=False, separators=(',', ':'))


def main():
    check = '--check' in sys.argv
    catch = json.load(open(CATCH))
    n = len(catch['buildings'])
    new, matched, measured = rebake(catch)
    out = dumps(new)
    if check:
        cur = open(CATCH, encoding='utf-8').read()
        if cur.strip() == out:
            print('OK: rayong_catchment.json heights reproduce exactly.')
            return 0
        print('MISMATCH: committed rayong_catchment.json does not match a fresh bake.', file=sys.stderr)
        return 1
    with open(CATCH, 'w', encoding='utf-8') as f:
        f.write(out)
    dist = {}
    for b in new['buildings']:
        dist[b['h']] = dist.get(b['h'], 0) + 1
    print(f"baked {n} buildings | tag-matched {matched} ({100*matched//n}%) | "
          f"measured height/levels {measured} | distinct heights now {len(dist)}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
