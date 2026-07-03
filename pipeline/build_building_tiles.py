#!/usr/bin/env python3
"""
build_building_tiles.py — national BUILDING VECTOR-TILE plan for the streaming deck.gl layer
============================================================================================
The 3D pages today bake a small, per-city slice of buildings into JSON. This script
instead PLANS a single national vector-tile archive (PMTiles) of REAL Overture Maps
building footprints covering the 10 km catchment around EVERY AutoX branch (2,015) AND
every competitor branch (competitors_national.json). The frontend team wires a deck.gl
streaming tile layer to it; this script just produces the run-plan + coverage geometry.

WHAT IT PRODUCES
----------------
  * pipeline/tiles_out/coverage_bbox.json — the overall download bbox + the 10 km
    buffer-union geometry (GeoJSON; shapely if available, else point set) + counts.
  * pipeline/tiles_out/RUN_TILES.sh — the EXACT three shell commands the owner runs on
    his Thai desktop: Overture download -> tippecanoe PMTiles -> (optional) MVT pyramid.
Both live in pipeline/tiles_out/, which is GITIGNORED (large, CDN-hosted, never committed).

ABSOLUTE RULE — NO FABRICATED DATA
----------------------------------
This script never invents a single building. It only computes a coverage bbox from the
committed branch/competitor coordinates and emits the commands that PULL real Overture
footprints. The heavy lifting (Overture pull + tippecanoe) happens on the owner's desktop;
the sandbox can't reach Overture from a foreign IP and may lack tippecanoe.

NETWORK
-------
This script is NETWORK-FREE. The emitted RUN_TILES.sh hits Overture (cloud Parquet on
AWS/Azure) — NOT any data.go.th-style blocked endpoint — but must still run from the
owner's Thai network for reliability. See docs/BUILDING_TILES.md for the runbook.

USAGE
-----
    python3 build_building_tiles.py            # write coverage_bbox.json + RUN_TILES.sh, print plan
    python3 build_building_tiles.py --check    # network-free sanity check (bbox finite/sane), exit 0
    python3 build_building_tiles.py --pad 0.09 # override the ~10 km bbox pad (degrees)

Standard library + shapely only (shapely is already used across the pipeline). If shapely
is missing we degrade gracefully to a plain bbox (no buffer-union geometry) and say so.
Never crashes on a missing optional dep.
"""
import os, json, math, argparse, sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
SRC = os.path.join(REPO, "source-data")
OUT_DIR = os.path.join(HERE, "tiles_out")            # GITIGNORED
BBOX_JSON = os.path.join(OUT_DIR, "coverage_bbox.json")
RUN_SH = os.path.join(OUT_DIR, "RUN_TILES.sh")

BRANCHES = os.path.join(SRC, "branches_final.json")
COMPETITORS = os.path.join(REPO, "platform", "data", "competitors_national.json")
PROV_INDEX = os.path.join(REPO, "platform", "data", "provinces", "index.json")

# ~10 km in degrees. 1 deg lat ~= 111 km, so 10 km ~= 0.09 deg. We pad the OVERALL bbox by
# this on every side so the Overture download covers the full 10 km ring of edge points.
DEFAULT_PAD = 0.09
EXPECT_BRANCHES = 2015  # sanity guard for --check; coordinates are committed source-data.


def _load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _resolve_province(arg):
    """Map a --province token (slug | English | Thai name, case-insensitive) to the Thai
    `prov` string used in branches_final.json + a short slug for output filenames. Reads the
    committed provinces/index.json. Returns (prov_th, slug) or raises SystemExit with a hint."""
    idx = _load(PROV_INDEX)
    a = str(arg).strip().lower()
    for row in idx:
        cands = {str(row.get("slug", "")).lower(),
                 str(row.get("en", "")).lower(),
                 str(row.get("th", "")).lower()}
        if a in cands and a:
            return row.get("th"), row.get("slug")
    # soft match: slug/en contains the token
    for row in idx:
        if a and (a in str(row.get("slug", "")).lower() or a in str(row.get("en", "")).lower()):
            return row.get("th"), row.get("slug")
    hint = ", ".join(sorted(str(r.get("slug", "")) for r in idx)[:12])
    raise SystemExit("Unknown province %r. Use a slug/en/th from provinces/index.json, e.g.: %s ..." % (arg, hint))


def _branch_points(prov_th=None):
    """[(lng, lat), ...] for every branch with finite coords. If `prov_th` is given, keep only
    branches in that province (used by --province to scope a small first run)."""
    rows = _load(BRANCHES)
    sel = [r for r in rows if (prov_th is None or r.get("prov") == prov_th)]
    pts = []
    for r in sel:
        lat, lng = r.get("lat"), r.get("lng")
        if isinstance(lat, (int, float)) and isinstance(lng, (int, float)):
            pts.append((float(lng), float(lat)))
    return pts, len(sel)


def _competitor_points():
    """[(lng, lat), ...] for every competitor with finite coords."""
    doc = _load(COMPETITORS)
    items = doc.get("items", doc) if isinstance(doc, dict) else doc
    pts = []
    for r in items:
        lat, lng = r.get("lat"), r.get("lng")
        if isinstance(lat, (int, float)) and isinstance(lng, (int, float)):
            pts.append((float(lng), float(lat)))
    return pts, len(items)


def _bbox(points, pad):
    """Overall (minx, miny, maxx, maxy) padded by `pad` degrees on every side."""
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return (min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad)


def _buffer_union_geojson(points, km=10.0):
    """Union of ~`km` circular buffers around each point as a GeoJSON geometry.
    Returns (geometry_dict | None, used_shapely: bool). Buffer radius is converted
    from km to degrees at the mean latitude so circles stay roughly circular.
    Degrades to None (caller falls back to the plain bbox) if shapely is absent."""
    try:
        from shapely.geometry import Point, mapping
        from shapely.ops import unary_union
    except Exception:
        return None, False
    if not points:
        return None, True
    mean_lat = sum(p[1] for p in points) / len(points)
    deg_lat = km / 111.0
    deg_lng = km / (111.320 * max(0.1, math.cos(math.radians(mean_lat))))
    # shapely buffers in the coordinate's own units; we buffer in lat-degrees then scale x.
    # Simpler + deterministic: buffer each point by deg_lat, after pre-scaling x so the
    # circle becomes an ellipse matching deg_lng. We approximate with an average radius.
    radius = (deg_lat + deg_lng) / 2.0
    circles = [Point(x, y).buffer(radius, quad_segs=8) for x, y in points]
    union = unary_union(circles)
    return mapping(union), True


def build(pad, province=None):
    os.makedirs(OUT_DIR, exist_ok=True)
    prov_th = slug = None
    if province:
        prov_th, slug = _resolve_province(province)

    bpts, n_branch_rows = _branch_points(prov_th)
    if province and not bpts:
        print("ERROR: no branches with coords for province %r — aborting." % province, file=sys.stderr)
        return 1

    if province:
        # Scope competitors to the province-branch bbox so a small first run doesn't drag in
        # the whole nation. (National mode keeps ALL competitors, unchanged.)
        pminx, pminy, pmaxx, pmaxy = _bbox(bpts, pad)
        cpts_all, _n_all = _competitor_points()
        cpts = [(x, y) for (x, y) in cpts_all if pminx <= x <= pmaxx and pminy <= y <= pmaxy]
        n_comp_rows = len(cpts)
    else:
        cpts, n_comp_rows = _competitor_points()

    allpts = bpts + cpts
    if not allpts:
        print("ERROR: no coordinates found in branches or competitors — aborting.", file=sys.stderr)
        return 1

    minx, miny, maxx, maxy = _bbox(allpts, pad)
    union_geom, used_shapely = _buffer_union_geojson(allpts)

    scope = ("province: %s (%s)" % (prov_th, slug)) if province else "national (all branches + competitors)"
    coverage = {
        "_doc": "Coverage plan for the Overture building tile pull. tiles_out/ is "
                "gitignored; regenerate with pipeline/build_building_tiles.py. NO synthetic data.",
        "scope": scope,
        "branches": {"rows": n_branch_rows, "with_coords": len(bpts)},
        "competitors": {"rows": n_comp_rows, "with_coords": len(cpts)},
        "total_points": len(allpts),
        "pad_deg": pad,
        "buffer_km": 10.0,
        # Overture CLI wants W,S,E,N == minx,miny,maxx,maxy.
        "bbox": {"minx": round(minx, 6), "miny": round(miny, 6),
                 "maxx": round(maxx, 6), "maxy": round(maxy, 6)},
        "bbox_overture": "%.6f,%.6f,%.6f,%.6f" % (minx, miny, maxx, maxy),
        "coverage_union": union_geom,  # null if shapely unavailable
        "coverage_union_source": "shapely buffer-union" if union_geom else "bbox-only (shapely absent)",
    }
    if not province:
        # National plan predates the `scope` key; keep it byte-for-byte as historically emitted.
        del coverage["scope"]
        coverage["_doc"] = ("Coverage plan for the national Overture building tile pull. tiles_out/ is "
                            "gitignored; regenerate with pipeline/build_building_tiles.py. NO synthetic data.")

    bbox_json = BBOX_JSON if not slug else os.path.join(OUT_DIR, "coverage_bbox_%s.json" % slug)
    run_sh = RUN_SH if not slug else os.path.join(OUT_DIR, "RUN_TILES_%s.sh" % slug)
    tile_label = "buildings" if not slug else "buildings_%s" % slug
    tiles_dir = "tiles" if not slug else "tiles_%s" % slug

    with open(bbox_json, "w", encoding="utf-8") as f:
        json.dump(coverage, f, ensure_ascii=False, indent=2)

    bbox_str = coverage["bbox_overture"]
    sh = _run_script(bbox_str, tile_label, tiles_dir, os.path.basename(run_sh))
    with open(run_sh, "w", encoding="utf-8") as f:
        f.write(sh)
    try:
        os.chmod(run_sh, 0o755)
    except Exception:
        pass

    # ---- print the plan (lead with the answer) ----
    print(("Province building-tile coverage plan — %s (%s)" % (prov_th, slug)) if province
          else "National building-tile coverage plan")
    print("=" * 60)
    print("Branches:    %d rows, %d with coords" % (n_branch_rows, len(bpts)))
    print("Competitors: %d rows, %d with coords" % (n_comp_rows, len(cpts)))
    print("Total points: %d   |   10 km buffer, bbox pad %.3f deg" % (len(allpts), pad))
    print("Overall bbox (W,S,E,N): %s" % bbox_str)
    print("Coverage union geometry: %s" % coverage["coverage_union_source"])
    print()
    print("Wrote:")
    print("  %s" % bbox_json)
    print("  %s" % run_sh)
    print()
    print("NEXT — on the Thai desktop, run the three commands in %s "
          "(see docs/BUILDING_TILES.md). They pull REAL Overture buildings; nothing is fabricated."
          % os.path.basename(run_sh))
    print()
    print(sh)
    return 0


def _run_script(bbox_str, tile_label="buildings", tiles_dir="tiles", script_name="RUN_TILES.sh"):
    """The exact shell commands the owner runs on his desktop. Paths are repo-relative so
    the script is run from the repo root. tile_label/tiles_dir/script_name are 'buildings'/
    'tiles'/'RUN_TILES.sh' for the national plan (byte-for-byte unchanged) and slug-suffixed
    for a --province scoped plan so a small first run never clobbers the national artifacts."""
    geojsonseq = "pipeline/tiles_out/%s.geojsonseq" % tile_label
    pmtiles = "pipeline/tiles_out/%s.pmtiles" % tile_label
    tiles = "pipeline/tiles_out/%s" % tiles_dir
    tpl = """#!/usr/bin/env bash
# __SCRIPT__ — GENERATED by pipeline/build_building_tiles.py. Do not edit by hand.
# Run from the REPO ROOT on the Thai-IP desktop. Pulls REAL Overture buildings (no synthetic).
# Prereqs:  pip install overturemaps     (Overture CLI)
#           install tippecanoe           (felt/tippecanoe — vector-tile builder)
#           install pmtiles              (optional; for inspecting the archive)
# Honest about size: national buildings can be MANY GB. To start small, replace the bbox
# below with one region's bbox before the first full run.
set -euo pipefail
mkdir -p pipeline/tiles_out

# 1) DOWNLOAD real Overture building footprints for the national coverage bbox (W,S,E,N).
#    geojsonseq avoids the parquet/geojson writer crashes; PYTHONUTF8=1 avoids a Windows
#    cp1252 UnicodeEncodeError on Thai names.
PYTHONUTF8=1 overturemaps download \\
    --bbox=__BBOX__ \\
    -f geojsonseq \\
    --type=building \\
    -o __GEOJSONSEQ__

# 2) BUILD the PMTiles archive (single file, range-request friendly). Buildings render at
#    ~z13-15; we keep z9-15 and drop densest features only when a tile is too big, so the
#    height/class attributes are preserved for the 3D extrusion.
tippecanoe \\
    -o __PMTILES__ \\
    -l buildings \\
    -Z9 -z15 \\
    --drop-densest-as-needed \\
    --extend-zooms-if-still-dropping \\
    --read-parallel \\
    --force \\
    __GEOJSONSEQ__

# 3) (OPTIONAL) MVT tile PYRAMID ({z}/{x}/{y}.pbf) for static hosts that can't serve
#    PMTiles HTTP range requests. Skip this if your CDN serves .pmtiles directly.
tippecanoe \\
    --output-to-directory __TILESDIR__ \\
    -l buildings \\
    -Z9 -z15 \\
    --drop-densest-as-needed \\
    --extend-zooms-if-still-dropping \\
    --read-parallel \\
    --no-tile-compression \\
    --force \\
    __GEOJSONSEQ__

# 4) UPLOAD: copy __PMTILES__ (or the tiles/ dir) to your CDN
#    bucket (Cloudflare R2 / S3 / Vercel Blob), then paste the PUBLIC URL into
#    platform/data/tiles_config.json so the frontend's deck.gl tile layer can read it.
echo "Done. Upload __PMTILES__ to the CDN and set its URL in platform/data/tiles_config.json"
"""
    return (tpl.replace("__BBOX__", bbox_str)
               .replace("__GEOJSONSEQ__", geojsonseq)
               .replace("__PMTILES__", pmtiles)
               .replace("__TILESDIR__", tiles)
               .replace("__SCRIPT__", script_name))


def check(pad):
    """NETWORK-FREE sanity check. Recompute the bbox in memory and assert it is finite/sane.
    Exits 0 on success so it can gate offline in CI. Never touches the network or tiles_out/."""
    bpts, n_branch_rows = _branch_points()
    cpts, n_comp_rows = _competitor_points()
    problems = []
    if n_branch_rows != EXPECT_BRANCHES:
        problems.append("expected %d branch rows, got %d" % (EXPECT_BRANCHES, n_branch_rows))
    if len(bpts) != EXPECT_BRANCHES:
        problems.append("expected %d branches with coords, got %d" % (EXPECT_BRANCHES, len(bpts)))
    if not cpts:
        problems.append("competitors_national.json has no coordinates")
    allpts = bpts + cpts
    if not allpts:
        problems.append("no coordinates at all")
    else:
        minx, miny, maxx, maxy = _bbox(allpts, pad)
        for name, v in (("minx", minx), ("miny", miny), ("maxx", maxx), ("maxy", maxy)):
            if not math.isfinite(v):
                problems.append("bbox %s is not finite" % name)
        if minx >= maxx or miny >= maxy:
            problems.append("degenerate bbox (min >= max)")
        # Thailand sits roughly in lng 96..106, lat 5..21 — sanity, not a hard fail boundary.
        if not (90 < minx < 110 and 0 < miny < 25 and 90 < maxx < 115 and 0 < maxy < 30):
            problems.append("bbox outside the plausible Thailand window: %r"
                            % ((round(minx, 3), round(miny, 3), round(maxx, 3), round(maxy, 3)),))
    if problems:
        print("FAIL build_building_tiles --check:", file=sys.stderr)
        for p in problems:
            print("  - " + p, file=sys.stderr)
        return 1
    minx, miny, maxx, maxy = _bbox(allpts, pad)
    print("OK build_building_tiles --check: %d branches + %d competitors, bbox W,S,E,N=%.4f,%.4f,%.4f,%.4f"
          % (len(bpts), len(cpts), minx, miny, maxx, maxy))
    return 0


def main():
    ap = argparse.ArgumentParser(description="Plan the national Overture building vector-tile pull.")
    ap.add_argument("--check", action="store_true",
                    help="network-free sanity check of the coverage bbox; exit 0 if sane")
    ap.add_argument("--pad", type=float, default=DEFAULT_PAD,
                    help="bbox pad in degrees (~10 km = 0.09; default %(default)s)")
    ap.add_argument("--province", default=None,
                    help="scope the plan to ONE province's branch set (slug/en/th, e.g. 'rayong') "
                         "for a small, safe first run; writes slug-suffixed RUN_TILES_<slug>.sh. "
                         "Omit for the full national plan.")
    args = ap.parse_args()
    if args.check:
        return check(args.pad)
    return build(args.pad, args.province)


if __name__ == "__main__":
    sys.exit(main())
