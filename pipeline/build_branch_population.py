#!/usr/bin/env python3
"""
build_branch_population.py — TRUE ~10km-perimeter population per branch.

THE QUESTION THIS ANSWERS
-------------------------
The 3D scene headlines "people" for a branch's catchment. It must be the population INSIDE the 10km
circle (which spans several districts in a city, a fraction of a big rural amphoe) — matching the
"≤10km" POI counts beside it, NOT the whole administrative district.

TWO METHODS (raster preferred; area-weight fallback)
----------------------------------------------------
  MEASURED (preferred)  Sum a gridded population RASTER over each branch's 10km circle:
                        source-data/worldpop_tha_2020_1km.tif — WorldPop 2020, 1km, UN-adjusted to
                        the official national total (~69.8M). Each 1km cell whose centre is within
                        10km is added. This is a real population count, not an interpolation.
  ESTIMATED (fallback)  If the raster / rasterio is unavailable, area-weight measured UNFPA/NSO
                        district populations over the circle (assumes even intra-district density).

The output records which method produced it (meta.method) and labels each value's provenance so the
UI can tag it MEASURED vs EST honestly.

Index-aligned to platform/data/branches.json (entry i <-> branch i). Byte-exact reproducible →
carries --check (the raster is committed, so the gate reproduces offline). rasterio OR shapely
required; if NEITHER is present build() returns None and --check skip-passes (exit 3).

Usage:
  python3 build_branch_population.py            # write platform/data/branch_population.json
  python3 build_branch_population.py --check    # verify byte-for-byte reproduce
"""
import argparse, json, math, os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "platform", "data")
GEO = os.path.join(ROOT, "source-data", "th_amphoe.geojson")
AMPHOE = os.path.join(DATA, "amphoe.json")
MASTER = os.path.join(ROOT, "source-data", "branches_final.json")
BRANCHES = os.path.join(DATA, "branches.json")
RASTER = os.path.join(ROOT, "source-data", "worldpop_tha_2020_1km.tif")
OUT = os.path.join(DATA, "branch_population.json")

RADIUS_M = 10000.0
MLAT = 110540.0


def _load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ── MEASURED: sample the WorldPop raster over each branch's 10km circle ─────────────────
def _build_raster(branches):
    try:
        import rasterio
        import numpy as np
    except Exception:
        return None
    if not os.path.exists(RASTER):
        return None
    with rasterio.open(RASTER) as r:
        arr = r.read(1)
        nodata = r.nodata
        T = r.transform
        H, W = arr.shape
    # cell centre lng/lat from the affine transform (EPSG:4326, axis-aligned)
    # lng = T.c + (col+0.5)*T.a ; lat = T.f + (row+0.5)*T.e   (T.e < 0)
    x0, dx, y0, dy = T.c, T.a, T.f, T.e
    deg_pad_lat = (RADIUS_M / MLAT) + abs(dy)
    out = []
    for b in branches:
        blng, blat = float(b["x"]), float(b["y"])
        mlon = 111320.0 * math.cos(math.radians(blat))
        deg_pad_lng = (RADIUS_M / mlon) + abs(dx)
        # window of rows/cols overlapping the circle bbox
        c_lo = int(math.floor((blng - deg_pad_lng - x0) / dx))
        c_hi = int(math.ceil((blng + deg_pad_lng - x0) / dx))
        r_lo = int(math.floor((blat + deg_pad_lat - y0) / dy))   # dy<0 → +pad gives smaller row
        r_hi = int(math.ceil((blat - deg_pad_lat - y0) / dy))
        c0, c1 = max(0, min(c_lo, c_hi)), min(W, max(c_lo, c_hi) + 1)
        r0, r1 = max(0, min(r_lo, r_hi)), min(H, max(r_lo, r_hi) + 1)
        pop = 0.0
        for row in range(r0, r1):
            clat = y0 + (row + 0.5) * dy
            dyy = (clat - blat) * MLAT
            for col in range(c0, c1):
                v = arr[row, col]
                if nodata is not None and v == nodata:
                    continue
                if not (v > 0):
                    continue
                clng = x0 + (col + 0.5) * dx
                dxx = (clng - blng) * mlon
                if dxx * dxx + dyy * dyy <= RADIUS_M * RADIUS_M:
                    pop += float(v)
        out.append(int(round(pop)))
    return out


# ── ESTIMATED fallback: area-weight measured district populations over the circle ──────
def _build_areaweight(branches):
    try:
        from shapely.geometry import Point, Polygon, MultiPolygon, box
        from shapely.strtree import STRtree
    except Exception:
        return None, 0
    for p in (GEO, AMPHOE, MASTER):
        if not os.path.exists(p):
            return None, 0
    geo = _load(GEO)["features"]
    amphoe = _load(AMPHOE)["amphoe"]
    master = _load(MASTER)
    dist_pop = {}
    for b in master:
        if b.get("dist_pop"):
            dist_pop[(b.get("prov"), b.get("district"))] = int(b["dist_pop"])
    id_to_pop = {a["id"]: dist_pop.get((a.get("province_th"), a.get("name"))) for a in amphoe}

    def to_local(ring, lat0, lng0):
        mlon = 111320.0 * math.cos(math.radians(lat0))
        return [((lng - lng0) * mlon, (lat - lat0) * MLAT) for lng, lat in ring]

    def area_m2(rings):
        lat0 = sum(pt[1] for pt in rings[0]) / len(rings[0])
        lng0 = sum(pt[0] for pt in rings[0]) / len(rings[0])
        return Polygon(to_local(rings[0], lat0, lng0), [to_local(h, lat0, lng0) for h in rings[1:]]).area

    polys, poly_pop, poly_area, poly_rings = [], [], [], []
    for f in geo:
        pid = f["properties"].get("shapeID"); pop = id_to_pop.get(pid)
        geom = f.get("geometry") or {}; gt, gc = geom.get("type"), geom.get("coordinates")
        rings_list = [gc] if gt == "Polygon" else (gc if gt == "MultiPolygon" else None)
        if rings_list is None:
            continue
        try:
            gll = Polygon(gc[0], gc[1:]) if gt == "Polygon" else MultiPolygon([(rl[0], rl[1:]) for rl in gc])
        except Exception:
            continue
        a = sum(area_m2(rl) for rl in rings_list)
        if a <= 0:
            continue
        polys.append(gll); poly_pop.append(pop); poly_area.append(a); poly_rings.append(rings_list)
    tree = STRtree(polys)
    circle = Point(0.0, 0.0).buffer(RADIUS_M)
    out, n_missing = [], 0
    for b in branches:
        blng, blat = float(b["x"]), float(b["y"])
        cand = tree.query(box(blng - 0.15, blat - 0.15, blng + 0.15, blat + 0.15))
        pop = 0.0; touched = False
        for idx in cand:
            i = int(idx); inter = 0.0
            for rl in poly_rings[i]:
                try:
                    pl = Polygon(to_local(rl[0], blat, blng), [to_local(h, blat, blng) for h in rl[1:]])
                    if not pl.is_valid:
                        pl = pl.buffer(0)
                    inter += pl.intersection(circle).area
                except Exception:
                    continue
            if inter <= 0:
                continue
            if poly_pop[i] is None:
                touched = True; continue
            pop += poly_pop[i] * min(1.0, inter / poly_area[i])
        if touched:
            n_missing += 1
        out.append(int(round(pop)))
    return out, n_missing


def build():
    if not os.path.exists(BRANCHES):
        return None
    branches = _load(BRANCHES)

    vals = _build_raster(branches)
    if vals is not None:
        method = "raster"
        prov = {
            "population": "MEASURED — WorldPop 2020 gridded population (1km, UN-adjusted to the "
                          "official national total ~69.8M): source-data/worldpop_tha_2020_1km.tif. "
                          "Each 1km cell whose centre falls within the 10km circle is summed.",
            "method": "MEASURED raster sum — a real population count over the 10km circle, not an "
                      "interpolation. 1km cells give ~±1 cell edge granularity on a 10km radius.",
        }
        gaps = ["WorldPop models population from census + built-area + ancillary layers; it is the "
                "standard measured gridded estimate but still a model, not a headcount.",
                "Vintage 2020 (latest WorldPop constrained release); refresh when a newer year lands."]
    else:
        vals, n_missing = _build_areaweight(branches)
        if vals is None:
            return None
        method = "areaweight"
        prov = {
            "population": "ESTIMATED — measured UNFPA/NSO district populations area-weighted over the "
                          "10km circle (WorldPop raster/rasterio unavailable; fallback method).",
            "method": "ESTIMATED area-weight — assumes uniform population density within a district.",
        }
        gaps = ["Fallback method (raster absent): area-weighting assumes even intra-district density. "
                "%d branches touch a district with no population on the master (contributes 0)." % n_missing,
                "Install rasterio + commit source-data/worldpop_tha_2020_1km.tif for a MEASURED count."]

    n_with = sum(1 for v in vals if v > 0)
    meta = {
        "generated_by": "pipeline/build_branch_population.py",
        "label": "TRUE ~10km-perimeter population per branch — the population INSIDE each branch's "
                 "10km circle, so 'people' matches the '≤10km' POI counts beside it. Index-aligned "
                 "to branches.json.",
        "objective": "Context for both objectives: how many people a branch's 10km catchment reaches "
                     "(not the whole administrative district).",
        "method": method,
        "measured": method == "raster",
        "provenance": prov,
        "radius_km": RADIUS_M / 1000.0,
        "index_note": "values[] is INDEX-ALIGNED to platform/data/branches.json (entry i <-> branch i).",
        "gaps": gaps,
        "n_branches": len(vals),
        "n_with_population": n_with,
    }
    return {"meta": meta, "values": vals}


def run(check=False):
    obj = build()
    if obj is None:
        if check:
            print("SKIP: rasterio+raster AND shapely both unavailable — branch_population not checkable")
            return 3
        print("missing dep/input: needs (rasterio + worldpop raster) OR (shapely + polygons).")
        return 1
    text = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    if check:
        if not os.path.exists(OUT) or open(OUT, encoding="utf-8").read() != text:
            print("DRIFT: %s" % os.path.relpath(OUT, ROOT))
            return 1
        print("OK: branch_population.json reproduces (%d branches, method=%s)"
              % (obj["meta"]["n_branches"], obj["meta"]["method"]))
        return 0
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(text)
    m = obj["meta"]
    print("wrote %d branches -> platform/data/branch_population.json (method=%s, %d with population)"
          % (m["n_branches"], m["method"], m["n_with_population"]))
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="true 10km-perimeter population per branch (raster sum / area-weight)")
    ap.add_argument("--check", action="store_true")
    raise SystemExit(run(check=ap.parse_args().check))
