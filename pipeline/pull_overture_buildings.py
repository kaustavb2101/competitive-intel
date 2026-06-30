#!/usr/bin/env python3
"""
pull_overture_buildings.py — THE "more buildings" win for the 3D catchment scene.

WHAT THIS DOES
--------------
Pulls **Overture Maps** building footprints for a Rayong bbox and rewrites
platform/data/rayong_catchment.json in the EXACT shape the 3D page already reads.

Why Overture (vs the current OSM pull):
  * DENSER footprints — Overture fuses OSM + Esri + Google/Microsoft ML buildings,
    so coverage in Thai cities is far higher than OSM alone (which is sparse here).
  * REAL heights — many Overture buildings carry a measured `height` (metres) or
    `num_floors`. Thai OSM has ~0% height tags, so today every catchment height is
    ESTIMATED. With Overture, height becomes **MEASURED where Overture has it**, and
    we fall back to the SAME footprint-area model (bake_catchment_heights.bldg_height)
    only where it doesn't — honest, mixed provenance.

A WIDER bbox than the current Mueang core means MANY more buildings reach the scene.

HONEST PROVENANCE
-----------------
  * Footprints: 100% measured Overture geometry.
  * height `h`: MEASURED when Overture provides properties.height; else num_floors*3.2
    (measured floor count); else ESTIMATED from building class + footprint area
    (the identical model the live branch-explorer + bake script use). Per-building
    provenance is summarised at the end so you can see the measured/estimated split.

NETWORK
-------
Overture is distributed as cloud Parquet on AWS/Azure; this script does NOT hit any of
the data.go.th-style blocked endpoints. Run it from a non-blocked network (Kaustav's
Thai laptop is fine; so is any normal connection). It needs the Overture CLI:

    pip install overturemaps

THE EXACT ONE COMMAND (owner, tonight)
--------------------------------------
    cd pipeline && python3 pull_overture_buildings.py \
        --city rayong --bbox "12.62,101.13,12.74,101.33" \
        --out ../platform/data/rayong_catchment.json

That OVERWRITES the baked rayong_catchment.json with the richer Overture data.

PER-PROVINCE BUILDING SCENE (the "real buildings everywhere" rollout)
---------------------------------------------------------------------
Every one of the 77 provinces can open the SAME 3D building scene as Rayong/Bangkok
(rayong-catchment.html?city=<slug>, which loads platform/data/<slug>_catchment.json).
To pull the buildings for a province in ONE command (bbox auto-derived from the
province's amphoe polygons in source-data/th_amphoe.geojson — no manual bbox):

    cd pipeline && python3 pull_overture_buildings.py --province chon-buri

That writes ../platform/data/chon-buri_catchment.json in the SAME catchment shape,
so rayong-catchment.html?city=chon-buri renders it exactly like Rayong. The slug is
the SAME slug build_province.py uses (see platform/data/provinces/index.json). Until
a province's file is pulled, the page degrades gracefully ("not pulled yet — showing
the district view"), so the rollout can be incremental.

A small deterministic platform/data/province_bbox.json (slug -> [S,W,N,E], derived
from the committed th_amphoe.geojson) is emitted/refreshed on every --province pull,
and can be (re)built on its own — network-free — with:

    cd pipeline && python3 pull_overture_buildings.py --bbox-only

The frontend can read province_bbox.json to show coverage; the owner can batch the
pulls slug-by-slug. --bbox-only touches no network.
BACKUP HINT: copy the current file first so you can roll back if you don't like it:
    cp ../platform/data/rayong_catchment.json ../platform/data/rayong_catchment.bak.json

Under the hood it shells to:
    overturemaps download --bbox=W,S,E,N -f geojson --type=building -o <tmp>.geojson
(note Overture wants W,S,E,N; our --bbox is the friendly S,W,N,E and we reorder it).
If you already have a GeoJSON, pass --geojson PATH to skip the download.

OUTPUT SHAPE (must match the page exactly)
------------------------------------------
  { "center": {lat,lng},                # preserved from the existing file if present
    "buildings": [ { "p":[[lng,lat],... closed ring],
                     "h": height_m, "fa": floor_area_m2,
                     "cx":centroid_lng, "cy":centroid_lat,
                     "nm": name_or_'', "ty": type_bucket }, ... ],
    "landmarks": [...] }                 # preserved from the existing file if present

Determinism: buildings are sorted by (cx,cy) so a re-pull of the same bbox/GeoJSON
produces a stable file order. Heights/areas are rounded (2dp / 0dp) to avoid float drift.

Flags:
  --city NAME        label only (default rayong)
  --bbox S,W,N,E     friendly bbox (default the WIDE Rayong box 12.62,101.13,12.74,101.33)
  --geojson PATH     use an existing Overture GeoJSON instead of downloading
  --cli NAME         Overture CLI executable (default: overturemaps)
  --out PATH         output file (default ../platform/data/rayong_catchment.json)
  --keep-geojson     don't delete the downloaded temp GeoJSON
  --dry-run          fetch + summarise but DO NOT write the output file
"""
import argparse, json, math, os, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DEFAULT_OUT = os.path.join(ROOT, "platform", "data", "rayong_catchment.json")
# WIDE Rayong bbox (S,W,N,E) — much larger than the Mueang core so many more buildings land.
DEFAULT_BBOX = "12.62,101.13,12.74,101.33"

D2R = math.pi / 180.0
FLOOR_M = 3.2  # metres per storey when only num_floors is known

# Import the SAME height/area/type model the baker + live page use, so estimated heights
# are byte-identical to bake_catchment_heights.py. Done via a tiny shim so this file runs
# even if run from another cwd.
sys.path.insert(0, HERE)
try:
    from bake_catchment_heights import ring_area_m2, bldg_height as _est_height, bldg_type as _osm_type
except Exception:  # pragma: no cover - defensive; baker is committed alongside
    def ring_area_m2(ring, lat):
        a = 0.0
        n = len(ring)
        for i in range(n):
            j = (i - 1) % n
            a += (ring[j][0] - ring[i][0]) * (ring[j][1] + ring[i][1])
        return abs(a / 2.0) * 111320.0 * (111320.0 * math.cos(lat * D2R))

    def _est_height(tags, fa):
        return 6.0 if (fa or 0) < 120 else (9.0 if fa < 400 else (11.0 if fa < 800 else 13.0))

    def _osm_type(tags):
        return "mixed"


# Overture building `class`/`subtype` -> our ty bucket (matches the page's TINT keys:
# residential|commercial|hotel|industrial|office|school + house/mixed).
OVT_CLASS = {
    "residential": "residential", "house": "house", "detached": "house",
    "apartments": "residential", "dormitory": "residential", "bungalow": "house",
    "terrace": "residential", "semidetached_house": "house",
    "commercial": "commercial", "retail": "commercial", "shop": "commercial",
    "supermarket": "commercial", "kiosk": "commercial", "office": "office",
    "industrial": "industrial", "warehouse": "industrial", "factory": "industrial",
    "manufacture": "industrial",
    "hotel": "hotel", "motel": "hotel",
    "school": "school", "university": "school", "college": "school",
    "kindergarten": "school", "education": "school",
}
# Overture `subtype` (coarser than class) -> ty bucket, used when class is absent.
OVT_SUBTYPE = {
    "residential": "residential", "commercial": "commercial",
    "industrial": "industrial", "education": "school",
    "transportation": "mixed", "civic": "mixed", "service": "mixed",
    "medical": "mixed", "entertainment": "commercial", "agricultural": "mixed",
    "religious": "mixed", "military": "mixed", "outbuilding": "house",
}


def _bbox_parts(bbox):
    p = [float(x) for x in bbox.split(",")]
    if len(p) != 4:
        raise ValueError("--bbox must be S,W,N,E")
    return p  # s, w, n, e


# ── per-province bbox from the amphoe polygons (TASK 1) ──────────────────────────
# A province has NO field on the amphoe geojson (only an English shapeName), so which
# amphoe polygons belong to a province is recovered the SAME way build_province.py
# does it: spatial-join the master branches into amphoe polygons (point-in-polygon),
# group by canonical province, and slug each province with the SAME rule build_province
# uses (PROVINCE_EN override -> "Mueang <prov>" amphoe English name -> first amphoe).
# We import build_province's helpers so the slug + geometry logic can never drift from
# the file that actually writes platform/data/provinces/<slug>.json.
#
# Everything here is NETWORK-FREE and deterministic (reads only committed source-data).
PROVINCE_BBOX_OUT = os.path.join(ROOT, "platform", "data", "province_bbox.json")
SRC_DIR = os.path.join(ROOT, "source-data")
# pad the union of amphoe bboxes a touch so buildings on the very rim of the rim
# amphoe still land in the Overture pull (degrees; ~1.1km lat).
_PROV_BBOX_PAD = 0.01


def _slug_extents():
    """Return {slug: {"th":prov, "en":en, "bbox":[S,W,N,E], "amphoe":n}} for every
    province, with bbox = padded union of that province's amphoe polygon bboxes.
    Pure / network-free; mirrors build_province.py's province->amphoe spatial join."""
    import build_province as bp
    from regionmap import canonical, REGION, PROVINCE_EN

    master = bp._load(os.path.join(SRC_DIR, "branches_final.json"))
    amphoe = bp._load(os.path.join(SRC_DIR, "th_amphoe.geojson"))["features"]
    polys = [(f, bp._bbox(f["geometry"])) for f in amphoe]
    poly_by_id = {f["properties"]["shapeID"]: f for f in amphoe}

    # branch -> amphoe polygon (same PIP + bbox prefilter as build_province)
    branch_poly = {}
    for bi, b in enumerate(master):
        x, y = b["lng"], b["lat"]
        for f, (x0, y0, x1, y1) in polys:
            if x0 <= x <= x1 and y0 <= y <= y1 and bp._contains(f["geometry"], x, y):
                branch_poly[bi] = f["properties"]["shapeID"]
                break

    # group branch indices by canonical province
    prov_idx = {}
    for bi, b in enumerate(master):
        prov_idx.setdefault(canonical(b["prov"]), []).append(bi)

    out = {}
    for prov, idxs in sorted(prov_idx.items()):
        if prov not in REGION:
            continue
        # province's amphoe polygons = those containing its branches (insertion order)
        dist_ids = []
        seen = set()
        for bi in idxs:
            sid = branch_poly.get(bi)
            if sid and sid not in seen:
                seen.add(sid); dist_ids.append(sid)
        if not dist_ids:
            continue
        feats = [poly_by_id[sid] for sid in dist_ids]
        # slug — IDENTICAL rule to build_province.py
        en = PROVINCE_EN.get(prov, "")
        if not en:
            for f in feats:
                sn = f["properties"]["shapeName"]
                if sn.startswith("Mueang "):
                    en = sn[len("Mueang "):]; break
        if not en:
            en = feats[0]["properties"]["shapeName"]
        slug = bp.slugify(en) or bp.slugify(prov)
        # union of amphoe bboxes -> friendly S,W,N,E (build_province._bbox gives x0,y0,x1,y1)
        bxs = [bp._bbox(f["geometry"]) for f in feats]
        w = min(b[0] for b in bxs); s = min(b[1] for b in bxs)
        e = max(b[2] for b in bxs); n = max(b[3] for b in bxs)
        out[slug] = {
            "th": prov, "en": en, "amphoe": len(feats),
            "bbox": [round(s - _PROV_BBOX_PAD, 6), round(w - _PROV_BBOX_PAD, 6),
                     round(n + _PROV_BBOX_PAD, 6), round(e + _PROV_BBOX_PAD, 6)],
        }
    return out


def write_province_bbox(check=False):
    """Build platform/data/province_bbox.json:
        { "meta": {source, generated_by, ...},
          "provinces": { slug -> {th, en, amphoe, bbox:[S,W,N,E]} } }
    bbox is MEASURED — the union of the province's amphoe polygon extents in the
    committed th_amphoe.geojson. Deterministic; --check verifies byte-for-byte."""
    provinces = _slug_extents()
    doc = {
        "meta": {
            # MEASURED geometry derivation — no estimate, no network.
            "source": "GeoBoundaries THA ADM2 (source-data/th_amphoe.geojson) — measured polygon extents",
            "generated_by": "pipeline/pull_overture_buildings.py (write_province_bbox)",
            "provenance": "measured",
            "description": "Per-province bounding box [S,W,N,E] = union of that province's amphoe "
                           "polygon extents, padded ~1.1km. Drives per-province Overture building "
                           "pulls and frontend coverage display. Slugs match provinces/index.json.",
            "pad_deg": _PROV_BBOX_PAD,
            "count": len(provinces),
        },
        "provinces": provinces,
    }
    text = json.dumps(doc, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    if check:
        if not os.path.exists(PROVINCE_BBOX_OUT) or \
                open(PROVINCE_BBOX_OUT, encoding="utf-8").read() != text:
            print(f"DRIFT: {os.path.relpath(PROVINCE_BBOX_OUT, ROOT)}")
            return 1, provinces
        print(f"OK: province_bbox.json reproduces ({len(provinces)} provinces)")
        return 0, provinces
    with open(PROVINCE_BBOX_OUT, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"wrote {os.path.relpath(PROVINCE_BBOX_OUT, ROOT)}  "
          f"({len(provinces)} provinces, deterministic from th_amphoe.geojson)")
    return 0, provinces


def download_geojson(cli, bbox, dest):
    """Shell to the Overture CLI. Our --bbox is S,W,N,E; Overture wants W,S,E,N."""
    s, w, n, e = _bbox_parts(bbox)
    ovt_bbox = f"{w},{s},{e},{n}"
    if not shutil.which(cli):
        raise RuntimeError(
            f"'{cli}' not found on PATH. Install it first:\n"
            f"    pip install overturemaps\n"
            f"(or pass --geojson PATH to use an existing export, or --cli to point at the binary).")
    # Use line-delimited GeoJSON (geojsonseq): Overture's per-feature streaming
    # writer. The single-FeatureCollection 'geojson' writer crashes in
    # write_batch() on newer pyarrow / Python 3.14; geojsonseq avoids that path.
    cmd = [cli, "download", f"--bbox={ovt_bbox}", "-f", "geojsonseq",
           "--type=building", "-o", dest]
    print("running:", " ".join(cmd), file=sys.stderr)
    # Capture stderr so the CLI's real failure is surfaced, not swallowed behind a bare traceback.
    # Force UTF-8: the overturemaps GeoJSON writer does open(out,'w') without an encoding, so on
    # Windows it defaults to cp1252 and dies with UnicodeEncodeError ('charmap') on Thai names.
    env = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
    proc = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "").strip()
        raise RuntimeError(
            f"overturemaps download failed (exit {proc.returncode}).\n"
            f"--- CLI output ---\n{tail or '(no output captured)'}\n"
            f"------------------\n"
            f"If you see a UnicodeEncodeError ('charmap' codec), set PYTHONUTF8=1 in the shell and "
            f"retry. Otherwise: no network reach to Overture S3, an outdated pyarrow, or too-large "
            f"a bbox timing out. Try a tiny bbox first, e.g. --bbox 12.68,101.27,12.70,101.29")
    return dest


def _outer_rings(geom):
    """Yield outer-ring [lng,lat] vertex lists from a Polygon/MultiPolygon GeoJSON geometry."""
    if not geom:
        return
    t = geom.get("type")
    coords = geom.get("coordinates")
    if t == "Polygon" and coords:
        yield [[float(c[0]), float(c[1])] for c in coords[0]]
    elif t == "MultiPolygon" and coords:
        for poly in coords:
            if poly:
                yield [[float(c[0]), float(c[1])] for c in poly[0]]


def _ovt_height(props):
    """(height_m, is_measured). height -> num_floors*3.2 -> None (caller estimates)."""
    h = props.get("height")
    if h is not None:
        try:
            hv = float(h)
            if hv > 0:
                return hv, True
        except (TypeError, ValueError):
            pass
    nf = props.get("num_floors") or props.get("numFloors")
    if nf is not None:
        try:
            n = float(nf)
            if n > 0:
                return n * FLOOR_M, True
        except (TypeError, ValueError):
            pass
    return None, False


def _ovt_type(props):
    cls = (props.get("class") or "").lower()
    if cls in OVT_CLASS:
        return OVT_CLASS[cls]
    sub = (props.get("subtype") or "").lower()
    if sub in OVT_SUBTYPE:
        return OVT_SUBTYPE[sub]
    return "mixed"


def _name(props):
    nm = props.get("name")
    if isinstance(nm, dict):  # Overture names are structured {primary, common, ...}
        nm = nm.get("primary") or ""
    if isinstance(nm, list) and nm:
        nm = nm[0]
    return (nm or "").strip() if isinstance(nm, str) else ""


def _centroid(ring):
    """Area-weighted polygon centroid (lng,lat); falls back to vertex mean for slivers."""
    n = len(ring)
    a = cx = cy = 0.0
    for i in range(n):
        x0, y0 = ring[i]
        x1, y1 = ring[(i + 1) % n]
        cross = x0 * y1 - x1 * y0
        a += cross
        cx += (x0 + x1) * cross
        cy += (y0 + y1) * cross
    if abs(a) < 1e-12:
        xs = [p[0] for p in ring]
        ys = [p[1] for p in ring]
        return sum(xs) / n, sum(ys) / n
    a *= 0.5
    return cx / (6 * a), cy / (6 * a)


def convert(features):
    """GeoJSON building features -> (buildings list, stats dict)."""
    out = []
    measured = estimated = 0
    for ft in features:
        props = ft.get("properties") or {}
        for ring in _outer_rings(ft.get("geometry")):
            if len(ring) < 4:
                continue
            # ensure a closed ring (page expects a closed polygon)
            if ring[0] != ring[-1]:
                ring = ring + [ring[0]]
            cx, cy = _centroid(ring)
            fp = ring_area_m2(ring, cy)         # footprint area (m2)
            if fp < 8:                          # drop degenerate slivers
                continue
            ty = _ovt_type(props)
            h, is_meas = _ovt_height(props)
            if h is None:
                # estimate with the SAME model as the baker (pass an OSM-style tag dict so
                # the type branches line up with our ty bucket).
                h = _est_height({"building": ty if ty != "mixed" else "yes"}, fp)
                estimated += 1
            else:
                h = min(h, 300.0)               # sanity cap (no clamp to the old 60m carpet)
                measured += 1
            floors = max(1.0, round(h / FLOOR_M))
            fa = fp * floors                    # floor area (m2) = footprint * storeys
            out.append({
                "p": [[round(x, 6), round(y, 6)] for x, y in ring],
                "h": round(h, 2),
                "fa": round(fa),
                "cx": round(cx, 6), "cy": round(cy, 6),
                "nm": _name(props),
                "ty": ty,
            })
    # deterministic order: sort by centroid so a re-pull is stable
    out.sort(key=lambda b: (b["cx"], b["cy"]))
    return out, {"measured": measured, "estimated": estimated}


def load_features(path):
    text = open(path, encoding="utf-8").read()
    # Try whole-file JSON first (a FeatureCollection / Feature / list — e.g. a
    # user-supplied --geojson export).
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        data = None
    if data is not None:
        if isinstance(data, dict) and data.get("type") == "FeatureCollection":
            return data.get("features", [])
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and data.get("type") == "Feature":
            return [data]
        raise ValueError(f"{path} is not a GeoJSON FeatureCollection/Feature(s)")
    # Otherwise treat as line-delimited GeoJSON (geojsonseq): one Feature per line.
    feats, skipped = [], 0
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            ft = json.loads(line)
        except json.JSONDecodeError:
            skipped += 1   # skip a truncated/malformed record instead of killing the whole pull
            continue
        if isinstance(ft, dict) and ft.get("type") == "FeatureCollection":
            feats.extend(ft.get("features", []))
        else:
            feats.append(ft)
    if skipped:
        print(f"load_features: skipped {skipped} malformed line(s)", file=sys.stderr)
    return feats


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--city", default="rayong")
    ap.add_argument("--bbox", default=None, help="S,W,N,E (default WIDE Rayong; auto-set by --province)")
    ap.add_argument("--province", help="province SLUG (e.g. chon-buri) — auto-derives bbox + out "
                                       "from th_amphoe.geojson and writes <slug>_catchment.json")
    ap.add_argument("--bbox-only", action="store_true",
                    help="just (re)build platform/data/province_bbox.json (network-free) and exit")
    ap.add_argument("--bbox-check", action="store_true",
                    help="verify province_bbox.json reproduces byte-for-byte (network-free) and exit")
    ap.add_argument("--geojson", help="use an existing Overture GeoJSON instead of downloading")
    ap.add_argument("--cli", default="overturemaps", help="Overture CLI executable name")
    ap.add_argument("--out", default=None, help="output path (default Rayong; auto-set by --province)")
    ap.add_argument("--keep-geojson", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    # network-free province_bbox.json (re)build / verify — exits without touching Overture.
    if args.bbox_check:
        rc, _ = write_province_bbox(check=True)
        sys.exit(rc)
    if args.bbox_only:
        write_province_bbox(check=False)
        return

    # --province SLUG: derive the bbox from the amphoe polygons + set the output file, then
    # refresh province_bbox.json so coverage stays in sync. Network is hit only for the pull.
    if args.province:
        slug = args.province.strip().lower()
        write_province_bbox(check=False)   # keep coverage map current (deterministic)
        ext = _slug_extents().get(slug)
        if not ext:
            print(f"ERROR: unknown province slug '{slug}'. Valid slugs are the keys in "
                  f"platform/data/provinces/index.json (e.g. chon-buri, khon-kaen).",
                  file=sys.stderr)
            sys.exit(2)
        s, w, n, e = ext["bbox"]
        if args.bbox is None:
            args.bbox = f"{s},{w},{n},{e}"
        if args.out is None:
            args.out = os.path.join(ROOT, "platform", "data", f"{slug}_catchment.json")
            args.out = os.path.normpath(args.out)
        if args.city == "rayong":
            args.city = slug
        print(f"province '{slug}' ({ext['en']} / {ext['th']}): {ext['amphoe']} amphoe  "
              f"bbox S,W,N,E = {args.bbox}  -> {os.path.relpath(args.out, ROOT)}")

    # defaults for a plain (non-province) run stay byte-identical to before.
    if args.bbox is None:
        args.bbox = DEFAULT_BBOX
    if args.out is None:
        args.out = DEFAULT_OUT

    tmp = None
    gj = args.geojson
    if not gj:
        fd, tmp = tempfile.mkstemp(prefix=f"overture_{args.city}_", suffix=".geojson")
        os.close(fd)
        download_geojson(args.cli, args.bbox, tmp)
        gj = tmp

    try:
        feats = load_features(gj)
        print(f"loaded {len(feats)} Overture features from {gj}", file=sys.stderr)
        buildings, stats = convert(feats)
    finally:
        if tmp and not args.keep_geojson and os.path.exists(tmp):
            os.remove(tmp)

    n = len(buildings)
    if n == 0:
        print("ERROR: no buildings produced — check the bbox / GeoJSON.", file=sys.stderr)
        sys.exit(2)

    pct_meas = 100 * stats["measured"] // n
    print(f"bbox (S,W,N,E): {args.bbox}")
    print(f"buildings: {n}  |  height MEASURED {stats['measured']} ({pct_meas}%)  "
          f"ESTIMATED {stats['estimated']} ({100 - pct_meas}%)")
    hs = sorted(b["h"] for b in buildings)
    print(f"height range: {hs[0]:.1f}–{hs[-1]:.1f} m  |  median {hs[n // 2]:.1f} m  "
          f"|  distinct {len(set(hs))}")

    # preserve center + landmarks from the existing file (curated for Rayong) if present
    out = {"buildings": buildings}
    if os.path.exists(args.out):
        try:
            cur = json.load(open(args.out))
            for k in ("center", "landmarks"):
                if k in cur:
                    out[k] = cur[k]
        except Exception:  # noqa: BLE001 - existing file unreadable; just emit buildings
            pass
    if "center" not in out:
        s, w, nn, e = _bbox_parts(args.bbox)
        out["center"] = {"lat": (s + nn) / 2, "lng": (w + e) / 2}

    if args.dry_run:
        print("--dry-run: not writing.")
        return

    print(f"\nBACKUP HINT (roll back if needed):\n"
          f"    cp {args.out} {args.out.replace('.json', '.bak.json')}", file=sys.stderr)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    kb = os.path.getsize(args.out) / 1024.0
    reload_hint = ("rayong-catchment.html" if args.city == "rayong"
                   else f"rayong-catchment.html?city={args.city}")
    print(f"wrote {args.out}  ({kb:.1f} KB)  — reload {reload_hint}.")
    print("NOTE: heights are MEASURED where Overture has them, ESTIMATED (type+footprint) otherwise.")


if __name__ == "__main__":
    main()
