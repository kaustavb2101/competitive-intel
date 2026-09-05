#!/usr/bin/env python3
"""
build_catchment_poi.py — nationwide POI point layer for the 3D catchment scene (all 77 provinces).

THE QUESTION THIS ANSWERS
-------------------------
The 3D building scene (platform/rayong-catchment.html?city=<slug>) drops small colour-coded
POI columns (vehicle shops, gold dealers, banks, fresh markets, …) between the buildings so a
branch's commercial fabric is legible in 3D. Those pins were once populated ONLY from a
curated Rayong-only POI seed — so EVERY other province's scene
(Bangkok, Chiang Mai, Phuket, …) rendered buildings but NO POI pins.

This builder projects the committed national OSM POI pull into one bbox-filterable file the scene
loads for ANY province, then slices to the scene's viewport client-side (mirroring how the scene
already bbox-filters competitors_census.json). Result: every province gets the same POI richness.

MEASURED vs ESTIMATED (the data-mandate — stated in meta)
---------------------------------------------------------
  MEASURED   every point: OSM POI coordinates from source-data/osm_layers.json (the 13-layer
             national Overpass pull, items [lng,lat]). Published as pulled, only SWAPPED to
             [lat,lng] (the order the scene's ColumnLayer expects) and ROUNDED to 4 decimals
             (~11 m; fine for a 42 m-radius pin). NO synthesis, NO jitter, NO fabricated points.
  ESTIMATED  nothing. The only judgement is WHICH OSM layers map to the scene's 11 pin types
             (a 1:1 rename table below); atm + civic are dropped (the scene has no such pin).

DETERMINISTIC + NETWORK-FREE: no network, no wall clock (vintage read from platform/data/meta.json
'updated' — osm_layers.json carries no internal timestamp). Byte-exact reproducible → carries
--check (the QA gate runs it). Input may be absent in a stripped sandbox: build() returns None,
--check skip-passes, a plain run exits non-zero with a clear message (mirrors build_lead_sites.py).

Usage:
  python3 build_catchment_poi.py            # write platform/data/catchment_poi.json
  python3 build_catchment_poi.py --check    # verify byte-for-byte reproduce
"""
import argparse, json, os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "platform", "data")
OSM = os.path.join(ROOT, "source-data", "osm_layers.json")
META = os.path.join(DATA, "meta.json")
OUT = os.path.join(DATA, "catchment_poi.json")

# scene pin type (rayong-catchment.html POI_ORDER) -> OSM layer key in osm_layers.json.
# ORDER IS FIXED (it is the scene's relevance order: collateral & finance, then demand, then economy).
# Here the names are 1:1 with the OSM layer keys; the map is explicit so a future OSM rename is caught.
TYPE_TO_LAYER = (
    ("vehicle_commerce", "vehicle_commerce"),
    ("gold",             "gold"),
    ("bank",             "bank"),
    ("fresh_market",     "fresh_market"),
    ("supermarket",      "supermarket"),
    ("convenience",      "convenience"),
    ("industrial",       "industrial"),
    ("restaurant",       "restaurant"),
    ("hotel",            "hotel"),
    ("school",           "school"),
    ("pharmacy",         "pharmacy"),
)
# OSM layers deliberately NOT surfaced as scene pins (documented, not silently dropped):
EXCLUDED_LAYERS = {
    "atm": "the scene has no ATM pin type — ATMs ride under the 'bank' finance read already",
    "civic": "public-sector points; the scene has no civic pin type",
}
NDP = 4   # coordinate decimals (~11 m) — plenty for a 42 m-radius column, keeps the file small


def _load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def build():
    if not os.path.exists(OSM):
        return None
    layers = _load(OSM)
    vintage = None
    if os.path.exists(META):
        vintage = (_load(META) or {}).get("updated")

    poi = {}
    counts = {}
    total = 0
    for scene_type, layer_key in TYPE_TO_LAYER:
        pts = layers.get(layer_key) or []
        arr = []
        for pt in pts:                       # osm items are [lng,lat]; scene wants [lat,lng]
            try:
                lng, lat = float(pt[0]), float(pt[1])
            except (TypeError, ValueError, IndexError):
                continue
            arr.append([round(lat, NDP), round(lng, NDP)])
        poi[scene_type] = arr
        counts[scene_type] = len(arr)
        total += len(arr)

    meta = {
        "generated_by": "pipeline/build_catchment_poi.py",
        "label": "NATIONWIDE POI PINS for the 3D catchment scene — MEASURED OSM establishment "
                 "coordinates for all 11 scene pin types, bbox-filtered client-side so every "
                 "province's 3D scene shows the same commercial fabric (not just curated Rayong).",
        "objective": "Portfolio + acquisition (both): make each branch's 10 km commercial fabric "
                     "legible in 3D for every province, not only the Rayong pilot.",
        "provenance": {
            "coordinates": "MEASURED — OpenStreetMap POI points (source-data/osm_layers.json, the "
                           "13-layer national Overpass pull; source items [lng,lat]). Swapped to "
                           "[lat,lng] (the order the scene ColumnLayer expects) and rounded to "
                           "%d decimals (~11 m). NO synthesis, NO jitter, no fabricated points." % NDP,
            "type_map": "EDITORIAL — which OSM layer backs each of the scene's 11 pin types "
                        "(meta.type_map); a 1:1 rename here, atm/civic excluded. The points "
                        "themselves are measured; only this inclusion map is judgement.",
            "vintage": "osm_layers.json carries no internal timestamp; network vintage from "
                       "platform/data/meta.json 'updated' = %s (the enrichment-loop refresh that "
                       "last pulled the layers)." % (vintage or "unknown"),
        },
        "usage": "the scene (rayong-catchment.html) loads this once and bbox-filters poi[type] to "
                 "the current city's building extent — the SAME pattern it uses for "
                 "competitors_census.json. Curated per-province .poi (Rayong) still wins when present.",
        "point_format": "poi[<scene_type>] = [[lat,lng], ...], lat/lng rounded %d dp; source order "
                        "preserved (deterministic)." % NDP,
        "type_map": {t: layer for t, layer in TYPE_TO_LAYER},
        "excluded_osm_layers": EXCLUDED_LAYERS,
        "gaps": [
            "OSM POI coverage is a sample/lower bound, not a registry — absence of a pin is NOT "
            "absence of an establishment.",
            "Nationwide file (no per-province split); the scene bbox-filters it in the browser. "
            "Fine at this size (~1.4 MB); revisit if the POI pull grows much larger.",
        ],
        "n_types": len(poi),
        "n_points": total,
        "points_by_type": counts,
    }
    return {"meta": meta, "poi": poi}


def run(check=False):
    obj = build()
    if obj is None:
        if check:
            print("SKIP: source-data/osm_layers.json absent — catchment_poi not checkable (optional layer)")
            return 0
        print("missing input: needs source-data/osm_layers.json.")
        return 1
    text = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    if check:
        if not os.path.exists(OUT) or open(OUT, encoding="utf-8").read() != text:
            print("DRIFT: %s" % os.path.relpath(OUT, ROOT))
            return 1
        print("OK: catchment_poi.json reproduces (%d types, %d points)"
              % (obj["meta"]["n_types"], obj["meta"]["n_points"]))
        return 0
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(text)
    m = obj["meta"]
    print("wrote %d types, %d points -> platform/data/catchment_poi.json (%.0f KB)"
          % (m["n_types"], m["n_points"], len(text.encode("utf-8")) / 1024))
    print("  points by type: %s" % m["points_by_type"])
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="nationwide POI pin layer for the 3D catchment scene")
    ap.add_argument("--check", action="store_true")
    raise SystemExit(run(check=ap.parse_args().check))
