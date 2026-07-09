#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pull_fuel_stations.py — MEASURED national fuel-station POI layer (OSM Overpass, keyless).

Fuel stations are the one genuinely-additive POI category left (docs/CKAN_SOURCES.md §POI):
dense in Thai OSM (~8.7k incl. way-centroids) and a direct vehicle-economy + rural-reach signal
for a title lender — where fuel sells, vehicles (the collateral) live and move.

Pulls nodes AND ways (out center) for amenity=fuel across Thailand from the reachable Overpass
mirror → source-data/fuel_stations.json ({meta, items:[[lng,lat],...]}, the osm_layers.json item
convention). Downstream: build_branch_fuel.py projects per-branch ≤10km counts (deterministic,
gated); THIS puller is network-bound and NOT in the determinism gate.

  python3 pull_fuel_stations.py                 # pull + write source-data/fuel_stations.json
  python3 pull_fuel_stations.py --stamp 2026-07-09
"""
import argparse, json, os, sys, time, urllib.parse, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "source-data", "fuel_stations.json")
MIRROR = "https://maps.mail.ru/osm/tools/overpass/api/interpreter"
QL = ('[out:json][timeout:150];area["ISO3166-1"="TH"][admin_level=2]->.a;'
      '(node["amenity"="fuel"](area.a);way["amenity"="fuel"](area.a););out center tags;')


def pull(tries=3):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(MIRROR, data=urllib.parse.urlencode({"data": QL}).encode(),
                                         headers={"User-Agent": "autox-credit-intel/1.0"})
            with urllib.request.urlopen(req, timeout=200) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            last = e
            time.sleep(5 * (i + 1))
    raise RuntimeError("Overpass pull failed after %d tries: %s" % (tries, last))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stamp", default="")
    args = ap.parse_args()
    d = pull()
    pts, brands = [], {}
    for e in d.get("elements", []):
        lat = e.get("lat") or (e.get("center") or {}).get("lat")
        lng = e.get("lon") or (e.get("center") or {}).get("lon")
        if lat is None or lng is None:
            continue
        pts.append([round(lng, 5), round(lat, 5)])
        b = (e.get("tags") or {}).get("brand") or ""
        if b:
            brands[b] = brands.get(b, 0) + 1
    if len(pts) < 3000:
        sys.exit("pull_fuel_stations.py: only %d points — Overpass likely truncated; not writing." % len(pts))
    pts.sort()  # stable order → byte-stable output for unchanged upstream data
    doc = {
        "meta": {
            "source": "OpenStreetMap via Overpass (mirror maps.mail.ru) — amenity=fuel nodes + way-centroids, Thailand",
            "label": "MEASURED — national fuel-station POI layer (vehicle-economy / rural-reach signal)",
            "generated_by": "pipeline/pull_fuel_stations.py",
            "pulled": args.stamp,
            "n": len(pts),
            "top_brands": dict(sorted(brands.items(), key=lambda x: -x[1])[:10]),
            "items_format": "[lng, lat] (the osm_layers.json convention)",
        },
        "items": pts,
    }
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(json.dumps(doc, ensure_ascii=False, separators=(",", ":")))
    print("wrote %s — %d stations, top brands: %s" % (
        OUT, len(pts), ", ".join(list(doc["meta"]["top_brands"])[:5])))


if __name__ == "__main__":
    main()
