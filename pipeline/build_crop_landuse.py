#!/usr/bin/env python3
"""
build_crop_landuse.py — AGRICULTURAL LAND-USE-BY-CROP per district (amphoe) + province rollup.

THE QUESTION THIS ANSWERS
-------------------------
Objective #1 (portfolio risk) and the agri-stress work want to know WHAT each district grows —
the credit-relevant crop mix (rice / cassava / maize / oil palm / sugarcane) — so a branch's
customer base can be read against the macro move hitting that crop. No per-district crop table
exists in Thai open data (OAE publishes province-level only; OSM crop tagging is ~5% sparse).

SOURCE (the honest best available): IFPRI/MapSPAM SPAM 2010 v2.0 (V2r0) physical-area GeoTIFFs,
Harvard Dataverse doi:10.7910/DVN/PRFF8V, CC BY 4.0. SPAM is a MODELED spatial disaggregation of
measured subnational crop statistics onto a 5-arcmin (~9.25km) grid — so the per-cell crop area is
ESTIMATED (model-allocated), NOT a field census. Rubber is absent (SPAM folds it into "rest of
crops"), so this layer covers the 5 credit-relevant crops SPAM carries.

METHOD (raster grid-sampling + point-in-polygon — same shape as build_branch_population.py)
-------------------------------------------------------------------------------------------
Each SPAM grid cell (centre lng/lat) carries a physical-area value in hectares for each of the 5
crops. We assign every cell to the amphoe polygon that CONTAINS its centre (point-in-polygon over
source-data/th_amphoe.geojson, STRtree bbox-prefiltered), and sum the crop hectares per amphoe.
Then per amphoe: dominant_crop (arg-max), shares{crop:frac of the 5-crop total}, and cropland_share
(5-crop physical area / amphoe land area). Province rollup sums the amphoe hectares.

The RAW rasters (~37MB each, git-ignored under source-data/.crop_scout/spam/) are NOT needed by the
build: a compact committed intermediate — source-data/spam2010_th_cropgrid.json (~0.36MB, the
Thailand-window non-zero cells, produced by `--extract`) — is the canonical input, so `--check`
reproduces byte-for-byte offline. If BOTH the intermediate is absent AND shapely is unavailable,
build() returns None and --check skip-passes (exit 3) — the branch_population.py pattern.

CROSS-CHECK (honesty): the per-province SPAM rice physical area is correlated (Pearson) against the
measured OAE rice planting area (source-data/rice_prov_area.json). The r is reported in meta so the
UI can label the layer honestly if the agreement is poor.

Usage:
  python3 build_crop_landuse.py --extract   # (re)build the committed grid intermediate from raw rasters (needs rasterio + the git-ignored tifs)
  python3 build_crop_landuse.py             # write platform/data/crop_landuse.json
  python3 build_crop_landuse.py --check     # verify byte-for-byte reproduce (offline)
"""
import argparse, json, math, os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, "source-data")
DATA = os.path.join(ROOT, "platform", "data")
GEO = os.path.join(SRC, "th_amphoe.geojson")
AMPHOE = os.path.join(DATA, "amphoe.json")
GRID = os.path.join(SRC, "spam2010_th_cropgrid.json")
RICE_OAE = os.path.join(SRC, "rice_prov_area.json")
RAW_SPAM = os.path.join(SRC, ".crop_scout", "spam")
OUT = os.path.join(DATA, "crop_landuse.json")

CROPS = ["rice", "cassava", "maize", "oilpalm", "sugarcane"]
MLAT = 110540.0


def _load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


# ── --extract: rebuild the committed grid intermediate from the raw git-ignored SPAM GeoTIFFs ──
def extract():
    import rasterio  # only needed for extraction, never for build/--check
    codes = [("rice", "RICE"), ("cassava", "CASS"), ("maize", "MAIZ"),
             ("oilpalm", "OILP"), ("sugarcane", "SUGC")]
    W, S, E, N = 97.2, 5.4, 105.8, 20.7   # Thailand-region window (border cells clipped by PIP downstream)
    A = 0.083333
    X0, Y0 = -180.0, 90.0
    c_lo = int((W - X0) / A); c_hi = int((E - X0) / A) + 1
    r_lo = int((Y0 - N) / A); r_hi = int((Y0 - S) / A) + 1
    mats = {}
    for name, code in codes:
        tif = os.path.join(RAW_SPAM, "spam2010V2r0_global_A_%s_A.tif" % code)
        if not os.path.exists(tif):
            print("missing raw raster: %s (run the crop scout first)" % os.path.relpath(tif, ROOT))
            return 1
        with rasterio.open(tif) as r:
            mats[name] = r.read(1)[r_lo:r_hi, c_lo:c_hi]
    H, Wd = mats["rice"].shape
    cells = []
    for ri in range(H):
        for ci in range(Wd):
            vals = [float(mats[n][ri, ci]) for n, _ in codes]
            vals = [v if v > 0 else 0.0 for v in vals]
            if any(v > 0 for v in vals):
                cells.append([c_lo + ci, r_lo + ri] + [round(v, 3) for v in vals])
    obj = {
        "meta": {
            "source": "IFPRI/MapSPAM SPAM 2010 v2.0 (V2r0), Harvard Dataverse doi:10.7910/DVN/PRFF8V, CC BY 4.0",
            "variable": "physical area (hectares per grid cell), all-technology (_A) aggregate",
            "note": "SPAM is a MODELED spatial disaggregation of measured subnational crop statistics onto a 5-arcmin grid; ESTIMATED (model-allocated crop areas), not a field census. Rubber is NOT a standalone SPAM crop (folded into 'rest of crops') so it is absent.",
            "grid": {"res_deg": A, "x0": X0, "y0": Y0,
                     "note": "cell centre lng = x0+(col+0.5)*res ; lat = y0-(row+0.5)*res"},
            "bbox_window": {"west": W, "south": S, "east": E, "north": N,
                            "note": "Thailand-region window; includes some border-country cells (clipped out by point-in-polygon into Thai amphoe)."},
            "crops": [n for n, _ in codes],
            "columns": ["global_col", "global_row", "rice_ha", "cassava_ha", "maize_ha", "oilpalm_ha", "sugarcane_ha"],
            "n_cells": len(cells),
            "extracted_by": "pipeline/build_crop_landuse.py --extract (from raw SPAM GeoTIFFs in source-data/.crop_scout/spam/, git-ignored)",
        },
        "cells": cells,
    }
    with open(GRID, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))
    print("wrote %d cells -> %s (%.2f MB)" % (len(cells), os.path.relpath(GRID, ROOT),
                                              os.path.getsize(GRID) / 1e6))
    return 0


# ── geometry helpers (local equirectangular projection, same convention as build_branch_population) ──
def _to_local(ring, lat0, lng0):
    mlon = 111320.0 * math.cos(math.radians(lat0))
    return [((lng - lng0) * mlon, (lat - lat0) * MLAT) for lng, lat in ring]


def _rings_of(geom):
    """Return a list of rings-lists ([outer, hole...]) for a Polygon/MultiPolygon geometry."""
    gt = geom.get("type"); gc = geom.get("coordinates")
    if gt == "Polygon":
        return [gc]
    if gt == "MultiPolygon":
        return list(gc)
    return []


def _pearson(xs, ys):
    n = len(xs)
    if n < 3:
        return None
    mx = sum(xs) / n; my = sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    if sxx <= 0 or syy <= 0:
        return None
    return sxy / math.sqrt(sxx * syy)


def build():
    try:
        from shapely.geometry import Point, Polygon, MultiPolygon
        from shapely.strtree import STRtree
    except Exception:
        return None
    for p in (GEO, AMPHOE, GRID):
        if not os.path.exists(p):
            return None

    grid = _load(GRID)
    gmeta = grid.get("meta", {})
    gg = gmeta.get("grid", {})
    A = gg.get("res_deg", 0.083333); X0 = gg.get("x0", -180.0); Y0 = gg.get("y0", 90.0)
    cells = grid.get("cells", [])

    amp = _load(AMPHOE)["amphoe"]

    # Build shapely polygons for every amphoe + its land area (ha), keyed by shapeID.
    feats = _load(GEO)["features"]
    polys, pids, pareas = [], [], {}
    for f in feats:
        pid = (f.get("properties") or {}).get("shapeID")
        geom = f.get("geometry") or {}
        rings_list = _rings_of(geom)
        if not pid or not rings_list:
            continue
        try:
            if geom["type"] == "Polygon":
                gll = Polygon(geom["coordinates"][0], geom["coordinates"][1:])
            else:
                gll = MultiPolygon([(rl[0], rl[1:]) for rl in geom["coordinates"]])
        except Exception:
            continue
        # land area (ha) via local projection about the polygon's first-ring centroid
        area_m2 = 0.0
        for rl in rings_list:
            outer = rl[0]
            lat0 = sum(pt[1] for pt in outer) / len(outer)
            lng0 = sum(pt[0] for pt in outer) / len(outer)
            try:
                area_m2 += Polygon(_to_local(outer, lat0, lng0),
                                   [_to_local(h, lat0, lng0) for h in rl[1:]]).area
            except Exception:
                continue
        polys.append(gll); pids.append(pid); pareas[pid] = area_m2 / 1e4  # m² -> ha

    tree = STRtree(polys)

    # accumulate crop hectares per amphoe id (point-in-polygon of each cell centre)
    acc = {}
    n_assigned = 0
    for c in cells:
        col, row = c[0], c[1]
        lng = X0 + (col + 0.5) * A
        lat = Y0 - (row + 0.5) * A
        pt = Point(lng, lat)
        hit = None
        for idx in tree.query(pt):
            i = int(idx)
            if polys[i].contains(pt):
                hit = pids[i]
                break
        if hit is None:
            continue
        n_assigned += 1
        a = acc.setdefault(hit, [0.0] * len(CROPS))
        for k in range(len(CROPS)):
            a[k] += c[2 + k]

    # ── per-amphoe records ────────────────────────────────────────────────────────────────
    amphoe_out = []
    prov_acc = {}   # province_th -> {region, ha[]}
    for a in amp:
        pid = a["id"]
        ha = acc.get(pid, [0.0] * len(CROPS))
        total = sum(ha)
        prov = a.get("province_th")
        if prov is not None:
            pa = prov_acc.setdefault(prov, {"region": a.get("region"), "ha": [0.0] * len(CROPS)})
            for k in range(len(CROPS)):
                pa["ha"][k] += ha[k]
        rec = {"id": pid, "name": a.get("name"), "name_en": a.get("name_en"),
               "province_th": prov, "region": a.get("region")}
        if total > 0:
            shares = {CROPS[k]: round(ha[k] / total, 4) for k in range(len(CROPS))}
            dom = max(range(len(CROPS)), key=lambda k: ha[k])
            land_ha = pareas.get(pid, 0.0)
            cropland = round(min(1.0, total / land_ha), 4) if land_ha > 0 else None
            rec.update({"dominant_crop": CROPS[dom], "shares": shares,
                        "crop_area_ha": round(total, 1), "cropland_share": cropland})
        else:
            rec.update({"dominant_crop": None, "shares": None,
                        "crop_area_ha": 0.0, "cropland_share": 0.0})
        amphoe_out.append(rec)

    # ── province rollup ───────────────────────────────────────────────────────────────────
    prov_out = []
    for prov, pa in sorted(prov_acc.items()):
        ha = pa["ha"]; total = sum(ha)
        if total > 0:
            shares = {CROPS[k]: round(ha[k] / total, 4) for k in range(len(CROPS))}
            dom = max(range(len(CROPS)), key=lambda k: ha[k])
            rec = {"province_th": prov, "region": pa["region"], "dominant_crop": CROPS[dom],
                   "shares": shares,
                   "crop_area_ha": {CROPS[k]: round(ha[k], 1) for k in range(len(CROPS))},
                   "total_ha": round(total, 1), "rice_share": round(ha[0] / total, 4)}
        else:
            rec = {"province_th": prov, "region": pa["region"], "dominant_crop": None,
                   "shares": None, "crop_area_ha": None, "total_ha": 0.0, "rice_share": None}
        prov_out.append(rec)

    # ── OAE rice cross-check: Pearson r of SPAM province rice-ha vs OAE rice planting area ──
    rice_r = None; n_match = 0
    if os.path.exists(RICE_OAE):
        oae = _load(RICE_OAE)
        xs, ys = [], []
        for rec in prov_out:
            prov = rec["province_th"]
            spam_rice = rec["crop_area_ha"]["rice"] if rec.get("crop_area_ha") else 0.0
            if prov in oae and isinstance(oae[prov], (int, float)):
                xs.append(spam_rice); ys.append(float(oae[prov]))
        n_match = len(xs)
        rice_r = _pearson(xs, ys)

    n_amp_with = sum(1 for r in amphoe_out if r.get("dominant_crop"))
    dom_tally = {}
    for r in amphoe_out:
        d = r.get("dominant_crop")
        if d:
            dom_tally[d] = dom_tally.get(d, 0) + 1

    if rice_r is None:
        oae_note = "OAE cross-check unavailable (rice_prov_area.json absent or no province match)."
    else:
        quality = ("strong" if rice_r >= 0.85 else "good" if rice_r >= 0.7
                   else "moderate" if rice_r >= 0.5 else "WEAK — treat crop shares with caution")
        oae_note = ("SPAM per-province rice physical area vs MEASURED OAE rice planting area "
                    "(source-data/rice_prov_area.json): Pearson r=%.3f over %d matched provinces (%s). "
                    "This validates the SPAM spatial allocation against Thai ground truth for the "
                    "dominant crop; the other four crops share the same allocation method."
                    % (rice_r, n_match, quality))

    meta = {
        "generated_by": "pipeline/build_crop_landuse.py",
        "source": gmeta.get("source"),
        "label": "Agricultural land-use by crop per district (amphoe) + province rollup — the "
                 "credit-relevant crop mix (rice / cassava / maize / oil palm / sugarcane). "
                 "ESTIMATED (model-allocated crop areas): SPAM 2010 v2.0 is a modeled spatial "
                 "disaggregation of measured subnational statistics onto a ~9.25km grid, sampled "
                 "into the 928 amphoe polygons by point-in-polygon. Rubber is absent from SPAM.",
        "measured": False,
        "estimated_label": "ESTIMATED (model-allocated crop areas)",
        "objective": "Objective #1 (portfolio risk / agri-stress): which crop a district's borrower "
                     "base depends on, so a macro move against that crop maps to exposure.",
        "method": "SPAM 5-arcmin physical-area grid → point-in-polygon into th_amphoe.geojson (928 "
                  "amphoe), crop hectares summed per district; shares/dominant_crop/cropland_share "
                  "derived; province rollup sums the amphoe hectares.",
        "crops": CROPS,
        "fields": {
            "amphoe[].dominant_crop": "arg-max crop by SPAM physical area in the district (null if no tracked crop)",
            "amphoe[].shares": "fraction of the 5-crop total physical area held by each crop (sums ~1)",
            "amphoe[].crop_area_ha": "total physical area (ha) of the 5 tracked crops in the district",
            "amphoe[].cropland_share": "5-crop physical area ÷ district land area (0–1); a tracked-crop intensity, NOT total cropland",
        },
        "grid_note": gmeta.get("note"),
        "grid_cells_assigned": n_assigned,
        "grid_cells_total": len(cells),
        "n_amphoe": len(amphoe_out),
        "n_amphoe_with_crop": n_amp_with,
        "n_provinces": len(prov_out),
        "dominant_crop_tally": dom_tally,
        "oae_rice_crosscheck": {"pearson_r": (round(rice_r, 4) if rice_r is not None else None),
                                "n_matched_provinces": n_match, "note": oae_note},
        "gaps": [
            "SPAM is MODELED (spatial disaggregation of measured subnational totals), vintage 2010 v2.0 — "
            "ESTIMATED per-cell crop area, not a field census; refresh when SPAM 2020 opens (guestbook-locked today).",
            "Rubber is NOT a SPAM crop (folded into 'rest of crops'), so a rubber-dominant district reads "
            "as its next-largest tracked crop — a known blind spot for the South/East rubber belt.",
            "~9.25km cells straddle small amphoe boundaries; a cell is assigned wholly to the amphoe "
            "containing its centre (no fractional split), so tiny districts carry more allocation noise.",
        ],
    }
    return {"meta": meta, "amphoe": amphoe_out, "provinces": prov_out}


def run(check=False):
    obj = build()
    if obj is None:
        if check:
            print("SKIP: shapely unavailable OR grid intermediate/polygons missing — crop_landuse not checkable")
            return 3
        print("missing dep/input: needs shapely + source-data/spam2010_th_cropgrid.json + th_amphoe.geojson + amphoe.json")
        return 1
    text = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    if check:
        if not os.path.exists(OUT):
            print("DRIFT: %s (missing)" % os.path.relpath(OUT, ROOT))
            return 1
        committed = open(OUT, encoding="utf-8").read()
        if committed != text:
            print("DRIFT: %s" % os.path.relpath(OUT, ROOT))
            return 1
        m = obj["meta"]
        print("OK: crop_landuse.json reproduces (%d amphoe, %d with crop, rice-OAE r=%s)"
              % (m["n_amphoe"], m["n_amphoe_with_crop"], m["oae_rice_crosscheck"]["pearson_r"]))
        return 0
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(text)
    m = obj["meta"]
    print("wrote %d amphoe (%d with crop) + %d provinces -> platform/data/crop_landuse.json"
          % (m["n_amphoe"], m["n_amphoe_with_crop"], m["n_provinces"]))
    print("  OAE rice cross-check: Pearson r=%s over %d provinces"
          % (m["oae_rice_crosscheck"]["pearson_r"], m["oae_rice_crosscheck"]["n_matched_provinces"]))
    print("  dominant-crop tally:", m["dominant_crop_tally"])
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="crop land-use by amphoe + province rollup (SPAM raster sampling)")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--extract", action="store_true", help="rebuild the committed grid intermediate from raw SPAM rasters")
    args = ap.parse_args()
    if args.extract:
        raise SystemExit(extract())
    raise SystemExit(run(check=args.check))
