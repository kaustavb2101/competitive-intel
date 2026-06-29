#!/usr/bin/env python3
"""
pull_city_3d.py — ONE generalized Overpass pull that produces a full 3D city scene for
platform/rayong-catchment.html?city=<slug>, with NO further code work after it runs.

WHAT IT MAKES
-------------
For a given city slug + bbox it pulls, in a single combined Overpass query:
  * BUILDINGS  -> platform/data/<slug>_catchment.json
  * ROADS / WATER / LANDUSE (the "ground bed") -> platform/data/<slug>_{roads,water,landuse}.json

Those are EXACTLY the files the page loads for ?city=<slug>:
  ?city=bangkok  ->  data/bangkok_catchment.json + data/bangkok_{roads,water,landuse}.json

The page derives its camera from the building bounding box, so any city frames itself; the
Rayong-only extras (competitors, province panel, branch cascade) degrade gracefully when their
files are absent. The default ?city=rayong view is unchanged — this script does NOT touch the
existing rayong_* files.

SHAPES (must match the page — do not change them or the scene won't plug in)
---------------------------------------------------------------------------
  <slug>_catchment.json -> { "buildings":[ {"p":[[lng,lat],...],"h":<m>,"fa":<m2>,
                                            "cx":<lng>,"cy":<lat>,"nm":<name|null>,"ty":<type>}, ... ],
                             "meta":{ "city":"<Label>", "n_bldg":N, "floor_area_m2":F } }
  <slug>_roads.json     -> { "roads":  [ {"path":[[lng,lat],...],"cls":"primary|secondary|tertiary|residential|service"}, ... ] }
  <slug>_water.json     -> { "water":  [ {"polygon":[[lng,lat],...],"nm":"<name or ''>"}, ... ] }
  <slug>_landuse.json   -> { "landuse":[ {"polygon":[[lng,lat],...],"kind":"park|forest|grass|...|industrial|commercial|residential|retail"}, ... ] }

HEIGHTS / TYPES
---------------
Thai OSM almost never tags building height, so heights are ESTIMATED from building type +
footprint area. To stay consistent with the rest of the platform, this REUSES the exact
deterministic model from bake_catchment_heights.py (bldg_height / bldg_type / ring_area_m2 /
jitter) — same per-building hash, same caps. Honesty label in the UI ("estimated from type +
footprint") therefore still holds. The ground geometry is 100% measured OSM (no estimation),
reusing pull_rayong_ground.py's class/kind mapping + Douglas-Peucker simplifier.

NETWORK — RUN FROM A THAI NETWORK
---------------------------------
Uses the maps.mail.ru Overpass mirror (reachable from the sandbox AND from Thailand). A dense
central-Bangkok bbox returns a LOT of geometry; the query is gentle (one combined request) but
can take a minute or two and may need a retry. Run it from Kaustav's Thai laptop.

THE EXACT BANGKOK COMMAND (run this tonight)
--------------------------------------------
  cd pipeline && python3 pull_city_3d.py --preset bangkok

  # equivalently, fully explicit:
  cd pipeline && python3 pull_city_3d.py --city bangkok --bbox "13.715,100.515,13.765,100.565"

Then open the page (no rebuild needed — these are leaf data files the page fetches directly):
  cd platform && python3 -m http.server 8000   ->   http://localhost:8000/rayong-catchment.html?city=bangkok

Other flags:
  --endpoint URL   Overpass interpreter URL (default: maps.mail.ru mirror)
  --out DIR        output directory (default: ../platform/data)
  --simplify M     Douglas-Peucker tolerance in metres for ground polylines/polygons (default 6)
  --dry-run        fetch + summarise counts but DO NOT write files
"""
import argparse
import importlib.util
import json
import math
import os
import sys
import time
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

DEFAULT_MIRROR = "https://maps.mail.ru/osm/tools/overpass/api/interpreter"

# Curated dense bboxes for one-flag pulls (S,W,N,E). Bangkok = a dense central slab
# (Siam / Pathum Wan / Ratchathewi) so the extruded skyline reads as a real city.
PRESETS = {
    "bangkok": "13.715,100.515,13.765,100.565",
}


def _load(modname, filename):
    """Import a sibling pipeline script as a module so we reuse its functions verbatim
    (no copy-paste drift). These modules are import-safe: their work is under __main__."""
    spec = importlib.util.spec_from_file_location(modname, os.path.join(HERE, filename))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

# REUSE the canonical, deterministic logic — single source of truth.
_bake = _load("bake_catchment_heights", "bake_catchment_heights.py")  # bldg_height/type/ring/jitter
_ground = _load("pull_rayong_ground", "pull_rayong_ground.py")        # ROAD_CLASS/LANDUSE_KIND/pull/etc.


# ---------------------------------------------------------------------------
def overpass(query, endpoint, timeout=240, retries=2):
    data = urllib.parse.urlencode({"data": query}).encode()
    last = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(
                endpoint, data=data, headers={"User-Agent": "autox-city-3d/1.0"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.load(r)
        except Exception as ex:  # noqa: BLE001
            last = ex
            if attempt < retries:
                wait = 10 * (attempt + 1)
                print(f"  overpass attempt {attempt+1} failed ({ex}); retrying in {wait}s",
                      file=sys.stderr)
                time.sleep(wait)
    raise RuntimeError(f"Overpass failed after {retries+1} attempts: {last}")


def _ring_lnglat(geom):
    return [[g["lon"], g["lat"]] for g in geom if "lat" in g and "lon" in g]


def _centroid(ring):
    n = len(ring)
    if n == 0:
        return 0.0, 0.0
    return sum(p[0] for p in ring) / n, sum(p[1] for p in ring) / n


def build_buildings(elements):
    """Map OSM building ways -> the page's building shape, reusing the bake model for h/ty/fa.
    Deterministic: pure function of the OSM geometry + tags."""
    out = []
    floor_area_total = 0.0
    for el in elements:
        if el.get("type") != "way":
            continue
        tags = el.get("tags", {}) or {}
        if "building" not in tags:
            continue
        geom = el.get("geometry")
        if not geom or len(geom) < 3:
            continue
        ring = _ring_lnglat(geom)
        if len(ring) < 3:
            continue
        # ensure a closed ring (first == last), matching the rayong catchment shape
        if ring[0] != ring[-1]:
            ring = ring + [ring[0]]
        cx, cy = _centroid(ring)
        fp = _bake.ring_area_m2(ring, cy)                       # footprint m2
        h = round(_bake.jitter(_bake.bldg_height(tags, fp), ring), 2)
        ty = _bake.bldg_type(tags)
        floors = max(1, round(h / 3.2))
        fa = int(round(fp * floors))                           # floor area m2 (footprint x floors)
        floor_area_total += fa
        nm = tags.get("name") or tags.get("name:en") or None
        out.append({"p": [[round(x, 5), round(y, 5)] for x, y in ring],
                    "h": h, "fa": fa, "cx": round(cx, 5), "cy": round(cy, 5),
                    "nm": nm, "ty": ty})
    return out, int(round(floor_area_total))


def build_ground(elements, tol_m):
    """Map OSM line/polygon elements -> roads/water/landuse, reusing pull_rayong_ground vocab."""
    roads, water, landuse = [], [], []
    for el in elements:
        tags = el.get("tags", {}) or {}
        etype = el.get("type")

        hw = tags.get("highway")
        if hw and etype == "way" and el.get("geometry"):
            path = _ground.simplify(_ring_lnglat(el["geometry"]), tol_m)
            if len(path) >= 2:
                roads.append({"path": path, "cls": _ground.ROAD_CLASS.get(hw, "residential")})
            continue

        is_water = (
            tags.get("natural") in _ground.WATER_NATURAL
            or tags.get("water") is not None
            or tags.get("waterway") == "riverbank"
            or tags.get("landuse") in _ground.WATER_LANDUSE
        )
        if is_water:
            nm = tags.get("name", "") or tags.get("name:en", "")
            rings = ([_ground.simplify(_ring_lnglat(el["geometry"]), tol_m)]
                     if etype == "way" and el.get("geometry")
                     else [_ground.simplify(r, tol_m) for r in _ground._ring_from_relation(el)])
            for ring in rings:
                if len(ring) >= 4:
                    water.append({"polygon": ring, "nm": nm})
            continue

        kind = (_ground.LANDUSE_KIND.get(tags.get("landuse", ""))
                or _ground.LANDUSE_KIND.get(tags.get("leisure", ""))
                or _ground.LANDUSE_KIND.get(tags.get("natural", "")))
        if kind:
            rings = ([_ground.simplify(_ring_lnglat(el["geometry"]), tol_m)]
                     if etype == "way" and el.get("geometry")
                     else [_ground.simplify(r, tol_m) for r in _ground._ring_from_relation(el)])
            for ring in rings:
                if len(ring) >= 4:
                    landuse.append({"polygon": ring, "kind": kind})
            continue

    return roads, water, landuse


def pull(endpoint, bbox, tol_m):
    """ONE combined query: buildings + roads + water + landuse for the bbox."""
    q = f"""[out:json][timeout:240];
(
  way["building"]({bbox});
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
    return els


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--city", help="city slug (e.g. bangkok); lowercased, [a-z0-9_-] only")
    ap.add_argument("--bbox", help="S,W,N,E (overrides --preset's bbox)")
    ap.add_argument("--preset", choices=sorted(PRESETS), help="curated city: " + ", ".join(sorted(PRESETS)))
    ap.add_argument("--endpoint", default=DEFAULT_MIRROR)
    ap.add_argument("--out", default=os.path.join(ROOT, "platform", "data"))
    ap.add_argument("--simplify", type=float, default=6.0,
                    help="Douglas-Peucker tolerance in metres for ground geometry (default 6)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    city = (args.city or args.preset)
    if not city:
        ap.error("need --city <slug> or --preset <name>")
    city = "".join(c for c in city.lower() if c.isalnum() or c in "-_")
    if not city:
        ap.error("city slug is empty after sanitising")
    if city == "rayong":
        ap.error("refusing to overwrite the curated rayong_* files; pick a different slug")

    bbox = args.bbox or PRESETS.get(args.preset or city)
    if not bbox:
        ap.error(f"no bbox: pass --bbox 'S,W,N,E' (no preset for '{city}')")
    parts = bbox.split(",")
    if len(parts) != 4:
        ap.error("--bbox must be 'S,W,N,E'")

    label = city.capitalize().replace("-", " ").replace("_", " ")

    els = pull(args.endpoint, bbox, args.simplify)
    buildings, floor_area = build_buildings(els)
    roads, water, landuse = build_ground(els, args.simplify)

    def tally(items, key):
        out = {}
        for it in items:
            out[it[key]] = out.get(it[key], 0) + 1
        return out

    print(f"buildings: {len(buildings):6d}  types={tally(buildings,'ty')}")
    print(f"roads:     {len(roads):6d}  {tally(roads,'cls')}")
    print(f"water:     {len(water):6d}")
    print(f"landuse:   {len(landuse):6d}  {tally(landuse,'kind')}")

    if not buildings:
        print("ERROR: no buildings returned — check connectivity / bbox / endpoint.", file=sys.stderr)
        sys.exit(2)

    if args.dry_run:
        print("--dry-run: not writing files.")
        return

    out = os.path.abspath(args.out)
    os.makedirs(out, exist_ok=True)
    targets = {
        f"{city}_catchment.json": {
            "buildings": buildings,
            "meta": {"city": label, "n_bldg": len(buildings), "floor_area_m2": floor_area},
        },
        f"{city}_roads.json": {"roads": roads},
        f"{city}_water.json": {"water": water},
        f"{city}_landuse.json": {"landuse": landuse},
    }
    for name, payload in targets.items():
        path = os.path.join(out, name)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
        kb = os.path.getsize(path) / 1024.0
        print(f"wrote {path}  ({kb:.1f} KB)")
    print(f"done. open  rayong-catchment.html?city={city}  — the scene plugs in with no code change.")


if __name__ == "__main__":
    main()
