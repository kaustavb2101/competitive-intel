#!/usr/bin/env python3
"""
build_branch_population.py — TRUE ~10km-perimeter population per branch (objective #1/#2 context).

THE QUESTION THIS ANSWERS
-------------------------
The 3D scene headlines "people" for a branch's catchment. v1 used the branch's whole DISTRICT
population (NSO) — but a 10km circle rarely equals a district (it spills into neighbours in cities,
covers a fraction of a big rural amphoe). This builder computes the population inside each branch's
actual 10km circle by AREA-WEIGHTING measured district populations over that circle — so the number
matches the "≤10km" POI counts shown right beside it.

METHOD (deterministic, network-free)
------------------------------------
For every branch: take its 10km circle; for each district polygon it overlaps, add
    district_population x (area of circle ∩ district / area of district).
Geometry via shapely in a per-branch local-metre frame (x=(Δlng)·111320·cos(lat), y=(Δlat)·110540 —
accurate well within a 10km radius). District polygons: source-data/th_amphoe.geojson (928). District
populations: the MEASURED UNFPA/NSO district totals carried on the master (branches_final.dist_pop),
joined polygon→(province_th, district_th) via amphoe.json's id map.

MEASURED vs ESTIMATED (data-mandate — stated in meta)
-----------------------------------------------------
  MEASURED   the district populations (UNFPA/NSO) and the district polygons (geoBoundaries ADM2).
  ESTIMATED  the 10km figure itself — area-weighting assumes population is spread UNIFORMLY within a
             district (it isn't). It's a principled interpolation of measured inputs, not a raw
             measurement; a true raster count needs WorldPop (a heavier pull, flagged in meta.gaps).
  UNDERCOUNT 86 of 928 districts have no population on the master (white-space amphoe with no branch);
             their slice of a circle contributes 0. Rural circles touching them read slightly low —
             meta records how many branches are affected.

Index-aligned to platform/data/branches.json (entry i <-> branch i), like every per-branch layer.
Byte-exact reproducible → carries --check. shapely required; absent => build() returns None and
--check skip-passes (mirrors build_branch_peers.py's numpy guard, exit 3).

Usage:
  python3 build_branch_population.py            # write platform/data/branch_population.json
  python3 build_branch_population.py --check    # verify byte-for-byte reproduce
"""
import argparse, json, math, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "platform", "data")
GEO = os.path.join(ROOT, "source-data", "th_amphoe.geojson")
AMPHOE = os.path.join(DATA, "amphoe.json")
MASTER = os.path.join(ROOT, "source-data", "branches_final.json")
BRANCHES = os.path.join(DATA, "branches.json")
OUT = os.path.join(DATA, "branch_population.json")

RADIUS_M = 10000.0        # 10km catchment, same as the k10 POI counts
MLAT = 110540.0           # metres per degree latitude (mean)


def _load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _to_local(coords, lat0, lng0):
    # project [lng,lat] ring -> local metres frame centred on (lat0,lng0)
    mlon = 111320.0 * math.cos(math.radians(lat0))
    return [((lng - lng0) * mlon, (lat - lat0) * MLAT) for lng, lat in coords]


def build():
    try:
        from shapely.geometry import Point, Polygon, MultiPolygon
        from shapely.strtree import STRtree
    except Exception:
        return None
    for p in (GEO, AMPHOE, MASTER, BRANCHES):
        if not os.path.exists(p):
            return None

    geo = _load(GEO)["features"]
    amphoe = _load(AMPHOE)["amphoe"]
    master = _load(MASTER)
    branches = _load(BRANCHES)

    # district population lookup: (province_th, district_th) -> MEASURED dist_pop (from the master)
    dist_pop = {}
    for b in master:
        pop = b.get("dist_pop")
        if pop:
            dist_pop[(b.get("prov"), b.get("district"))] = int(pop)
    # amphoe.json: polygon id -> (province_th, district_th) so a polygon can resolve its population
    id_to_pop = {}
    for a in amphoe:
        id_to_pop[a["id"]] = dist_pop.get((a.get("province_th"), a.get("name")))

    # build per-polygon geometry (lat/lng) + population + true area (m², per-polygon local frame)
    def _poly_area_m2(rings):
        lat0 = sum(pt[1] for pt in rings[0]) / len(rings[0])
        lng0 = sum(pt[0] for pt in rings[0]) / len(rings[0])
        ext = Polygon(_to_local(rings[0], lat0, lng0),
                      [_to_local(h, lat0, lng0) for h in rings[1:]])
        return ext.area

    polys, poly_pop, poly_area, poly_rings = [], [], [], []
    for f in geo:
        pid = f["properties"].get("shapeID")
        pop = id_to_pop.get(pid)
        geom = f.get("geometry") or {}
        gtype, gcoords = geom.get("type"), geom.get("coordinates")
        if gtype == "Polygon":
            rings_list = [gcoords]
        elif gtype == "MultiPolygon":
            rings_list = gcoords
        else:
            continue
        # lat/lng shapely geom for the spatial index (bbox queries only)
        try:
            if gtype == "Polygon":
                gll = Polygon(gcoords[0], gcoords[1:])
            else:
                gll = MultiPolygon([(rl[0], rl[1:]) for rl in gcoords])
        except Exception:
            continue
        area = sum(_poly_area_m2(rl) for rl in rings_list)
        if area <= 0:
            continue
        polys.append(gll); poly_pop.append(pop); poly_area.append(area); poly_rings.append(rings_list)

    tree = STRtree(polys)
    circle_local = Point(0.0, 0.0).buffer(RADIUS_M)   # 10km disk in the branch-local metre frame

    out = []
    n_missing_touch = 0     # branches whose circle touched a no-population district
    for b in branches:
        blng, blat = float(b["x"]), float(b["y"])
        # candidate districts: bbox within ~0.15° (~16km) of the branch
        pad = 0.15
        from shapely.geometry import box
        cand = tree.query(box(blng - pad, blat - pad, blng + pad, blat + pad))
        pop10 = 0.0
        touched_missing = False
        for idx in cand:
            i = int(idx)
            rings_list = poly_rings[i]
            # intersect the circle with this district IN the branch-local frame
            inter_area = 0.0
            for rl in rings_list:
                try:
                    plocal = Polygon(_to_local(rl[0], blat, blng),
                                     [_to_local(h, blat, blng) for h in rl[1:]])
                    if not plocal.is_valid:
                        plocal = plocal.buffer(0)
                    inter_area += plocal.intersection(circle_local).area
                except Exception:
                    continue
            if inter_area <= 0:
                continue
            pop = poly_pop[i]
            if pop is None:
                touched_missing = True
                continue
            ratio = min(1.0, inter_area / poly_area[i])
            pop10 += pop * ratio
        if touched_missing:
            n_missing_touch += 1
        out.append(int(round(pop10)))

    n_with = sum(1 for v in out if v > 0)
    meta = {
        "generated_by": "pipeline/build_branch_population.py",
        "label": "TRUE ~10km-perimeter population per branch — measured district populations "
                 "(UNFPA/NSO) area-weighted over each branch's 10km circle, so 'people' matches the "
                 "'≤10km' POI counts beside it. Index-aligned to branches.json.",
        "objective": "Context for both objectives: how many people a branch's 10km catchment actually "
                     "reaches (not the whole administrative district).",
        "provenance": {
            "populations": "MEASURED — UNFPA/NSO district populations (branches_final.dist_pop).",
            "polygons": "MEASURED — geoBoundaries ADM2 district polygons (source-data/th_amphoe.geojson).",
            "method": "ESTIMATED — area-weighting assumes uniform population density within each "
                      "district; a principled interpolation of measured inputs, not a raster count.",
        },
        "radius_km": RADIUS_M / 1000.0,
        "index_note": "values[] is INDEX-ALIGNED to platform/data/branches.json (entry i <-> branch i).",
        "gaps": [
            "86 of 928 districts carry no population on the master (white-space amphoe with no "
            "branch); their share of a circle contributes 0, so rural circles touching them read "
            "slightly low. %d branches touch at least one such district." % n_missing_touch,
            "A true count needs a gridded population raster (WorldPop/Kontur, ~100m) sampled per "
            "circle — heavier pull, not yet wired. This area-weighted estimate is the honest interim.",
        ],
        "n_branches": len(out),
        "n_with_population": n_with,
        "n_touch_missing_district": n_missing_touch,
    }
    return {"meta": meta, "values": out}


def run(check=False):
    obj = build()
    if obj is None:
        if check:
            print("SKIP: shapely missing or inputs absent — branch_population not checkable "
                  "(pip install --break-system-packages shapely)")
            return 3
        print("missing dep/input: needs shapely + th_amphoe.geojson + amphoe.json + branches.")
        return 1
    text = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    if check:
        if not os.path.exists(OUT) or open(OUT, encoding="utf-8").read() != text:
            print("DRIFT: %s" % os.path.relpath(OUT, ROOT))
            return 1
        print("OK: branch_population.json reproduces (%d branches, %d with pop)"
              % (obj["meta"]["n_branches"], obj["meta"]["n_with_population"]))
        return 0
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(text)
    m = obj["meta"]
    print("wrote %d branches -> platform/data/branch_population.json (%d with population, "
          "%d touch a no-pop district)"
          % (m["n_branches"], m["n_with_population"], m["n_touch_missing_district"]))
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="true 10km-perimeter population per branch (area-weighted)")
    ap.add_argument("--check", action="store_true")
    raise SystemExit(run(check=ap.parse_args().check))
