#!/usr/bin/env python3
"""
pull_rayong_ground.py — fetch the OSM "ground bed" (roads + water + landuse) for the
Mueang Rayong catchment and emit the three files the 3D page consumes.

WHY THIS EXISTS
---------------
platform/rayong-catchment.html already renders a "full city" floor under the extruded
buildings (DataProteins look): tinted landuse + flat water + cased road ribbons, lit and
vignetted. Its groundLayers() reads three optional files; if any is missing it silently
skips that layer. This script produces those files from real OpenStreetMap geometry.

It writes EXACTLY the shapes the page expects (do not change these or the page won't plug in):

  platform/data/rayong_roads.json   -> { "roads":   [ { "path":    [[lng,lat],...], "cls": "primary|secondary|tertiary|residential|service" }, ... ] }
  platform/data/rayong_water.json   -> { "water":   [ { "polygon": [[lng,lat],...], "nm": "<name or ''>" }, ... ] }
  platform/data/rayong_landuse.json -> { "landuse": [ { "polygon": [[lng,lat],...], "kind": "park|forest|grass|recreation|meadow|farmland|industrial|commercial|residential|retail" }, ... ] }

DATA PROVENANCE: 100% measured OpenStreetMap geometry (no estimation, no synthesis).
The bbox matches pull_wide.py (the same area the buildings were pulled from) so the bed
lines up under the existing 3,631-building catchment exactly.

NETWORK
-------
Uses the same Overpass mirror as the other pullers (maps.mail.ru). The main openstreetmap
Overpass endpoint is usually reachable from Thailand too; pass --endpoint to override.
Overpass is rate-limited; this issues ONE combined query and is gentle.

RUN
---
  cd pipeline && python3 pull_rayong_ground.py
  # then refresh nothing else — these are leaf data files the page fetches directly.
  # verify locally:  cd platform && python3 -m http.server 8000  ->  open /rayong-catchment.html

Flags:
  --endpoint URL   Overpass interpreter URL (default: maps.mail.ru mirror)
  --bbox S,W,N,E   override the catchment bbox (default matches pull_wide.py)
  --out DIR        output directory (default: ../platform/data)
  --simplify M     douglas-peucker tolerance in metres for road/polygon vertices (default 6)
  --dry-run        fetch + summarise counts but DO NOT write files
"""
import argparse, json, math, os, sys, time, urllib.request, urllib.parse

DEFAULT_MIRROR = "https://maps.mail.ru/osm/tools/overpass/api/interpreter"
# Matches pull_wide.py — the exact area the catchment buildings were pulled from.
DEFAULT_BBOX = "12.655,101.155,12.725,101.310"

# OSM highway -> the page's road class vocabulary (drives width/casing in groundLayers()).
ROAD_CLASS = {
    "motorway": "primary", "motorway_link": "primary",
    "trunk": "primary", "trunk_link": "primary",
    "primary": "primary", "primary_link": "primary",
    "secondary": "secondary", "secondary_link": "secondary",
    "tertiary": "tertiary", "tertiary_link": "tertiary",
    "unclassified": "residential", "residential": "residential",
    "living_street": "residential", "road": "residential",
    "service": "service", "track": "service",
}

# OSM landuse/leisure/natural -> the page's landuse "kind" vocabulary (drives tint).
LANDUSE_KIND = {
    # green
    "park": "park", "garden": "park", "recreation_ground": "recreation",
    "pitch": "recreation", "playground": "recreation", "golf_course": "recreation",
    "forest": "forest", "wood": "forest", "nature_reserve": "forest",
    "grass": "grass", "grassland": "grass", "village_green": "grass",
    "meadow": "meadow", "scrub": "meadow",
    "farmland": "farmland", "farmyard": "farmland", "orchard": "farmland",
    "plant_nursery": "farmland", "paddy": "farmland",
    # built
    "industrial": "industrial", "quarry": "industrial",
    "commercial": "commercial", "retail": "retail",
    "residential": "residential",
}

WATER_NATURAL = {"water", "bay", "wetland"}
WATER_LANDUSE = {"reservoir", "basin"}


def overpass(query, endpoint, timeout=180, retries=2):
    data = urllib.parse.urlencode({"data": query}).encode()
    last = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(
                endpoint, data=data,
                headers={"User-Agent": "autox-rayong-ground/1.0"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.load(r)
        except Exception as ex:  # noqa: BLE001 - report and back off
            last = ex
            if attempt < retries:
                wait = 8 * (attempt + 1)
                print(f"  overpass attempt {attempt+1} failed ({ex}); retrying in {wait}s",
                      file=sys.stderr)
                time.sleep(wait)
    raise RuntimeError(f"Overpass failed after {retries+1} attempts: {last}")


def _geom_to_lnglat(geom):
    """Overpass 'geometry' is a list of {lat,lon}; the page wants [lng,lat]."""
    return [[g["lon"], g["lat"]] for g in geom if "lat" in g and "lon" in g]


def _ring_from_relation(el):
    """Best-effort outer ring for a multipolygon relation (uses 'outer' member geometry).
    Real OSM multipolygons can have holes/multiple outers; the page renders flat fills, so a
    single outer ring per outer member is a faithful-enough silhouette for the ground bed."""
    rings = []
    for m in el.get("members", []):
        if m.get("role") == "outer" and m.get("geometry"):
            ring = _geom_to_lnglat(m["geometry"])
            if len(ring) >= 4:
                rings.append(ring)
    return rings


def _perp_dist_m(p, a, b):
    """Perpendicular distance (metres, equirectangular) of point p from segment a-b."""
    lat0 = math.radians(a[1])
    sx = 111320.0 * math.cos(lat0)
    sy = 110540.0
    ax, ay = a[0] * sx, a[1] * sy
    bx, by = b[0] * sx, b[1] * sy
    px, py = p[0] * sx, p[1] * sy
    dx, dy = bx - ax, by - ay
    seg2 = dx * dx + dy * dy
    if seg2 == 0:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / seg2))
    cx, cy = ax + t * dx, ay + t * dy
    return math.hypot(px - cx, py - cy)


def simplify(pts, tol_m):
    """Douglas-Peucker. Keeps the shape, drops redundant vertices to shrink the payload."""
    if tol_m <= 0 or len(pts) < 3:
        return pts
    a, b = pts[0], pts[-1]
    dmax, idx = 0.0, 0
    for i in range(1, len(pts) - 1):
        d = _perp_dist_m(pts[i], a, b)
        if d > dmax:
            dmax, idx = d, i
    if dmax > tol_m:
        left = simplify(pts[:idx + 1], tol_m)
        right = simplify(pts[idx:], tol_m)
        return left[:-1] + right
    return [a, b]


def pull(endpoint, bbox, tol_m):
    # ONE combined query: roads (lines), water (polygons), landuse/leisure/natural (polygons).
    q = f"""[out:json][timeout:180];
(
  way["highway"~"^(motorway|trunk|primary|secondary|tertiary|unclassified|residential|living_street|service|road|track)(_link)?$"]({bbox});
  way["natural"~"^(water|bay|wetland)$"]({bbox});
  relation["natural"~"^(water|bay|wetland)$"]({bbox});
  way["water"]({bbox});
  way["waterway"="riverbank"]({bbox});
  way["landuse"="reservoir"]({bbox});
  way["landuse"="basin"]({bbox});
  way["landuse"~"^(forest|grass|meadow|scrub|farmland|farmyard|orchard|plant_nursery|industrial|commercial|retail|residential|quarry|recreation_ground|village_green)$"]({bbox});
  relation["landuse"~"^(forest|farmland|industrial|commercial|residential)$"]({bbox});
  way["leisure"~"^(park|garden|recreation_ground|pitch|playground|golf_course|nature_reserve)$"]({bbox});
  way["natural"~"^(wood|grassland|scrub)$"]({bbox});
);
out body geom;
"""
    print(f"querying Overpass ({endpoint}) bbox={bbox} …", file=sys.stderr)
    t0 = time.time()
    d = overpass(q, endpoint)
    els = d.get("elements", [])
    print(f"  {len(els)} elements in {time.time()-t0:.1f}s", file=sys.stderr)

    roads, water, landuse = [], [], []
    for el in els:
        tags = el.get("tags", {}) or {}
        etype = el.get("type")

        # ---- roads (ways with geometry) ----
        hw = tags.get("highway")
        if hw and etype == "way" and el.get("geometry"):
            path = simplify(_geom_to_lnglat(el["geometry"]), tol_m)
            if len(path) >= 2:
                roads.append({"path": path, "cls": ROAD_CLASS.get(hw, "residential")})
            continue

        # ---- water ----
        is_water = (
            tags.get("natural") in WATER_NATURAL
            or tags.get("water") is not None
            or tags.get("waterway") == "riverbank"
            or tags.get("landuse") in WATER_LANDUSE
        )
        if is_water:
            nm = tags.get("name", "") or tags.get("name:en", "")
            rings = ([simplify(_geom_to_lnglat(el["geometry"]), tol_m)]
                     if etype == "way" and el.get("geometry")
                     else [simplify(r, tol_m) for r in _ring_from_relation(el)])
            for ring in rings:
                if len(ring) >= 4:
                    water.append({"polygon": ring, "nm": nm})
            continue

        # ---- landuse / leisure / natural-green ----
        kind = (LANDUSE_KIND.get(tags.get("landuse", ""))
                or LANDUSE_KIND.get(tags.get("leisure", ""))
                or LANDUSE_KIND.get(tags.get("natural", "")))
        if kind:
            rings = ([simplify(_geom_to_lnglat(el["geometry"]), tol_m)]
                     if etype == "way" and el.get("geometry")
                     else [simplify(r, tol_m) for r in _ring_from_relation(el)])
            for ring in rings:
                if len(ring) >= 4:
                    landuse.append({"polygon": ring, "kind": kind})
            continue

    return roads, water, landuse


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--endpoint", default=DEFAULT_MIRROR)
    ap.add_argument("--bbox", default=DEFAULT_BBOX)
    ap.add_argument("--out", default=os.path.join(here, "..", "platform", "data"))
    ap.add_argument("--simplify", type=float, default=6.0,
                    help="Douglas-Peucker tolerance in metres (default 6)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    roads, water, landuse = pull(args.endpoint, args.bbox, args.simplify)

    # class / kind breakdown so the operator can sanity-check what came back
    def tally(items, key):
        out = {}
        for it in items:
            out[it[key]] = out.get(it[key], 0) + 1
        return out

    print(f"roads:   {len(roads):5d}  {tally(roads,'cls')}")
    print(f"water:   {len(water):5d}")
    print(f"landuse: {len(landuse):5d}  {tally(landuse,'kind')}")

    if not (roads or water or landuse):
        print("ERROR: nothing returned — check connectivity / bbox / endpoint.", file=sys.stderr)
        sys.exit(2)

    if args.dry_run:
        print("--dry-run: not writing files.")
        return

    out = os.path.abspath(args.out)
    os.makedirs(out, exist_ok=True)
    targets = {
        "rayong_roads.json": {"roads": roads},
        "rayong_water.json": {"water": water},
        "rayong_landuse.json": {"landuse": landuse},
    }
    for name, payload in targets.items():
        path = os.path.join(out, name)
        with open(path, "w") as f:
            json.dump(payload, f, separators=(",", ":"))
        kb = os.path.getsize(path) / 1024.0
        print(f"wrote {path}  ({kb:.1f} KB)")
    print("done. Reload rayong-catchment.html — the ground bed plugs in with no code change.")


if __name__ == "__main__":
    main()
