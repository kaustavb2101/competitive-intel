#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pull_province_ground.py — batch-pull the OSM "ground bed" (arterial ROADS + WATER) for every
province, so rayong-catchment.html?city=<slug> renders cased road ribbons + water under the
buildings nationwide (not just Rayong/Bangkok).

WHY: groundLayers() in platform/rayong-catchment.html reads two optional files per city —
  platform/data/<slug>_roads.json -> { "roads": [ { "path": [[lng,lat],...], "cls": "primary|secondary|tertiary" }, ... ] }
  platform/data/<slug>_water.json -> { "water": [ { "polygon": [[lng,lat],...], "nm": "<name or ''>" }, ... ] }
(absent file => that layer is skipped silently). Rayong + Bangkok already have theirs (from
pull_rayong_ground.py at catchment scale); this script generalizes the pull PROVINCE-WIDE for the
other 75, one bbox per slug from platform/data/province_bbox.json.

Each output also carries a "meta" sidecar (source/generated_by/simplify_m/counts) — the page
ignores it; the provenance gate (tests/validate_data.py) requires it.

WHAT IT PULLS (100% measured OSM geometry, no synthesis):
  roads : arterials only — motorway/trunk/primary/secondary/tertiary (+ _link). Province bboxes
          are huge; residential/service roads would blow the payload and read as noise at this zoom.
  water : natural=water/bay/wetland + water=* + waterway=riverbank + landuse=reservoir/basin.
          Server-side (if: length() > 400) on ways drops farm-pond noise; a client-side
          min-area filter (default 30,000 m²) is the real gate (per outer ring for relations).

SIZE BUDGET (2 MB per file): geometry is Douglas-Peucker-simplified at --simplify (default 12 m).
If a file still exceeds the budget, the tolerance is escalated x1.5 (up to 8 steps, ~12->~200 m)
and re-simplified FROM THE RAW GEOMETRY until it fits — coarser lines, never silently dropped
features. The tolerance actually used is recorded in meta.simplify_m. If even the coarsest pass
is over budget the file is still written but flagged OVERSIZED and listed in
docs/r2_ground_manifest.json — upload those to the catchments CDN (R2) instead of committing
(the page falls back to catchments.baseUrl on a local 404).

RESUMABLE BY DESIGN:
  * per-slug skip: a slug with both output files present is skipped (use --force to redo)
  * raw Overpass responses are cached in pipeline/cache/ keyed by query hash (gitignored),
    so a re-run after a crash re-processes from cache without re-hitting the network
  * 5 s sleep between provinces that actually hit the network; HTTP 429/504 => 60 s backoff;
    a province that ultimately fails is reported and the batch moves on

RUN
    cd pipeline && python3 pull_province_ground.py                  # all provinces missing files
    python3 pull_province_ground.py --only chiang-mai,khon-kaen     # just these slugs
    python3 pull_province_ground.py --force                         # re-emit even if files exist
    python3 pull_province_ground.py --no-cache                      # ignore cached raw responses

Flags: --endpoint URL  --simplify M  --min-water-area M2  --budget BYTES  --sleep S  --dry-run
"""
import argparse
import hashlib
import json
import math
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "platform", "data")
BBOX_JSON = os.path.join(DATA_DIR, "province_bbox.json")
CACHE_DIR = os.path.join(ROOT, "pipeline", "cache")
MANIFEST = os.path.join(ROOT, "docs", "r2_ground_manifest.json")

DEFAULT_MIRROR = "https://maps.mail.ru/osm/tools/overpass/api/interpreter"
BUDGET_BYTES = 2_000_000          # per-file cap (Rayong's committed roads file is ~924 KB)
TOL_STEPS = 8                     # 12m * 1.5^7 ≈ 205m coarsest
UA = "autox-province-ground/1.0"

# OSM highway -> the page's road class vocabulary (drives ribbon/casing width in groundLayers()).
# Arterials only at province scale; same vocabulary as pull_rayong_ground.py.
ROAD_CLASS = {
    "motorway": "primary", "motorway_link": "primary",
    "trunk": "primary", "trunk_link": "primary",
    "primary": "primary", "primary_link": "primary",
    "secondary": "secondary", "secondary_link": "secondary",
    "tertiary": "tertiary", "tertiary_link": "tertiary",
}

WATER_NATURAL = {"water", "bay", "wetland"}
WATER_LANDUSE = {"reservoir", "basin"}


# ---------------------------------------------------------------- overpass + cache
def _cache_path(query):
    h = hashlib.sha1(query.encode("utf-8")).hexdigest()[:20]
    return os.path.join(CACHE_DIR, f"ground_{h}.json")


def overpass(query, endpoint, use_cache=True, timeout=300, retries=4):
    """POST an Overpass query; cache the raw response in pipeline/cache/ keyed by query hash.
    Returns (parsed_json, hit_network). 429/504 => 60 s rate-limit backoff; other errors
    back off 15 s * attempt."""
    cp = _cache_path(query)
    if use_cache and os.path.exists(cp):
        try:
            with open(cp, encoding="utf-8") as f:
                return json.load(f), False
        except Exception:
            pass  # corrupt cache (e.g. killed mid-write) — refetch
    data = urllib.parse.urlencode({"data": query}).encode()
    last = None
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(endpoint, data=data, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                raw = r.read()
            d = json.loads(raw)
            os.makedirs(CACHE_DIR, exist_ok=True)
            tmp = cp + ".tmp"
            with open(tmp, "wb") as f:
                f.write(raw)
            os.replace(tmp, cp)   # atomic: a killed run never leaves a corrupt cache entry
            return d, True
        except Exception as ex:  # noqa: BLE001 — report, back off, retry
            last = ex
            code = getattr(ex, "code", None)
            wait = 60 if code in (429, 504) else 15 * attempt
            if attempt < retries:
                print(f"    overpass attempt {attempt} failed ({ex}); backing off {wait}s",
                      file=sys.stderr)
                time.sleep(wait)
    raise RuntimeError(f"Overpass failed after {retries} attempts: {last}")


# ---------------------------------------------------------------- geometry helpers
def _geom_to_lnglat(geom):
    """Overpass 'geometry' is [{lat,lon},...]; the page wants [lng,lat]. 6dp ≈ 0.11 m."""
    return [[round(g["lon"], 6), round(g["lat"], 6)]
            for g in geom if "lat" in g and "lon" in g]


def _outer_rings(el):
    """Outer rings of a multipolygon relation (silhouette-faithful; the page renders flat fills)."""
    rings = []
    for m in el.get("members", []):
        if m.get("role") == "outer" and m.get("geometry"):
            ring = _geom_to_lnglat(m["geometry"])
            if len(ring) >= 4:
                rings.append(ring)
    return rings


def _perp_dist_m(p, a, b):
    """Perpendicular distance (metres, equirectangular) of p from segment a-b."""
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
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def simplify(pts, tol_m):
    """Iterative Douglas-Peucker (explicit stack — province arterials can be long ways;
    no Python recursion-depth risk). Order-preserving; keeps endpoints."""
    n = len(pts)
    if tol_m <= 0 or n < 3:
        return list(pts)
    keep = [False] * n
    keep[0] = keep[n - 1] = True
    stack = [(0, n - 1)]
    while stack:
        i0, i1 = stack.pop()
        if i1 <= i0 + 1:
            continue
        a, b = pts[i0], pts[i1]
        dmax, idx = 0.0, 0
        for i in range(i0 + 1, i1):
            d = _perp_dist_m(pts[i], a, b)
            if d > dmax:
                dmax, idx = d, i
        if dmax > tol_m:
            keep[idx] = True
            stack.append((i0, idx))
            stack.append((idx, i1))
    return [p for p, k in zip(pts, keep) if k]


def ring_area_m2(ring):
    """Shoelace area (m², equirectangular) of a [lng,lat] ring — the min-area water gate."""
    if len(ring) < 3:
        return 0.0
    lat0 = math.radians(sum(p[1] for p in ring) / len(ring))
    sx = 111320.0 * math.cos(lat0)
    sy = 110540.0
    s = 0.0
    for i in range(len(ring)):
        x1, y1 = ring[i][0] * sx, ring[i][1] * sy
        x2, y2 = ring[(i + 1) % len(ring)][0] * sx, ring[(i + 1) % len(ring)][1] * sy
        s += x1 * y2 - x2 * y1
    return abs(s) / 2.0


# ---------------------------------------------------------------- per-province queries
def roads_query(bbox):
    return (f'[out:json][timeout:300];'
            f'way["highway"~"^(motorway|trunk|primary|secondary|tertiary)(_link)?$"]({bbox});'
            f'out body geom;')


def water_query(bbox):
    # (if: length() > 400) drops sub-~100m-wide farm ponds server-side (perimeter proxy);
    # the real gate is the client-side min-area filter. Relations (big lakes / riverbanks)
    # are few — pulled unfiltered, area-gated per outer ring client-side.
    return (f'[out:json][timeout:300];('
            f'way["natural"~"^(water|bay|wetland)$"]({bbox})(if: length() > 400);'
            f'relation["natural"~"^(water|bay|wetland)$"]({bbox});'
            f'way["water"]({bbox})(if: length() > 400);'
            f'way["waterway"="riverbank"]({bbox})(if: length() > 400);'
            f'way["landuse"~"^(reservoir|basin)$"]({bbox})(if: length() > 400);'
            f');out body geom;')


def extract_roads_raw(els):
    """-> [(raw_path, cls), ...] before simplification."""
    out = []
    for el in els:
        if el.get("type") != "way" or not el.get("geometry"):
            continue
        cls = ROAD_CLASS.get((el.get("tags") or {}).get("highway", ""))
        if not cls:
            continue
        path = _geom_to_lnglat(el["geometry"])
        if len(path) >= 2:
            out.append((path, cls))
    return out


def extract_water_raw(els, min_area_m2):
    """-> [(raw_ring, name), ...] before simplification; area-gated on the RAW ring."""
    out = []
    for el in els:
        tags = el.get("tags", {}) or {}
        is_water = (tags.get("natural") in WATER_NATURAL
                    or tags.get("water") is not None
                    or tags.get("waterway") == "riverbank"
                    or tags.get("landuse") in WATER_LANDUSE)
        if not is_water:
            continue
        nm = tags.get("name", "") or tags.get("name:en", "")
        rings = ([_geom_to_lnglat(el["geometry"])]
                 if el.get("type") == "way" and el.get("geometry")
                 else _outer_rings(el))
        for ring in rings:
            if len(ring) >= 4 and ring_area_m2(ring) >= min_area_m2:
                out.append((ring, nm))
    return out


def budgeted_dump(build, base_tol, budget, label):
    """Serialize build(tol); if over budget, escalate tolerance x1.5 (re-simplifying from RAW
    geometry) until it fits. Returns (payload_bytes, tol_used, oversized_bool)."""
    tol = base_tol
    for step in range(TOL_STEPS):
        payload = build(tol)
        blob = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        if len(blob) <= budget:
            if step:
                print(f"    {label}: over budget at {base_tol:g}m — fits at {tol:g}m "
                      f"({len(blob)/1024:.0f} KB)")
            return blob, tol, False
        tol *= 1.5
    print(f"    {label}: OVERSIZED even at {tol/1.5:g}m ({len(blob)/1024:.0f} KB) — "
          f"listing in the R2 manifest", file=sys.stderr)
    return blob, tol / 1.5, True


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(
        description="Batch Overpass ground beds (arterial roads + water) for all provinces.")
    ap.add_argument("--endpoint", default=DEFAULT_MIRROR)
    ap.add_argument("--only", help="comma-separated province slugs (default: all)")
    ap.add_argument("--force", action="store_true", help="re-emit even if output files exist")
    ap.add_argument("--no-cache", action="store_true", help="ignore cached raw responses")
    ap.add_argument("--simplify", type=float, default=12.0,
                    help="Douglas-Peucker tolerance in metres (default 12)")
    ap.add_argument("--min-water-area", type=float, default=30000.0,
                    help="min water-polygon area in m² (default 30,000 = 3 ha)")
    ap.add_argument("--budget", type=int, default=BUDGET_BYTES,
                    help=f"per-file byte budget (default {BUDGET_BYTES})")
    ap.add_argument("--sleep", type=float, default=5.0,
                    help="seconds between provinces that hit the network (default 5)")
    ap.add_argument("--dry-run", action="store_true", help="fetch + count but write nothing")
    args = ap.parse_args()

    try:
        bbox_doc = json.load(open(BBOX_JSON, encoding="utf-8"))
        provinces = bbox_doc["provinces"]
    except Exception as e:
        print(f"cannot read {BBOX_JSON}: {e}", file=sys.stderr)
        return 1

    slugs = sorted(provinces.keys())
    if args.only:
        want = {s.strip().lower() for s in args.only.split(",") if s.strip()}
        unknown = want - set(slugs)
        if unknown:
            print(f"unknown slugs: {sorted(unknown)}", file=sys.stderr)
            return 1
        slugs = [s for s in slugs if s in want]

    done, skipped, failed, oversized = [], [], [], []
    hit_network_last = False
    for i, slug in enumerate(slugs, 1):
        roads_out = os.path.join(DATA_DIR, f"{slug}_roads.json")
        water_out = os.path.join(DATA_DIR, f"{slug}_water.json")
        if not args.force and os.path.exists(roads_out) and os.path.exists(water_out):
            skipped.append(slug)
            print(f"[{i}/{len(slugs)}] {slug}: ground files exist — skip (--force to redo)")
            continue
        if hit_network_last and args.sleep > 0:
            time.sleep(args.sleep)   # be gentle with the mirror between real pulls
        s, w, n, e = provinces[slug]["bbox"]
        bbox = f"{s},{w},{n},{e}"
        print(f"[{i}/{len(slugs)}] {slug}: bbox={bbox}")
        try:
            t0 = time.time()
            rd_raw, net1 = overpass(roads_query(bbox), args.endpoint, not args.no_cache)
            wa_raw, net2 = overpass(water_query(bbox), args.endpoint, not args.no_cache)
            hit_network_last = net1 or net2
            roads = extract_roads_raw(rd_raw.get("elements", []))
            water = extract_water_raw(wa_raw.get("elements", []), args.min_water_area)
            src = "cache" if not hit_network_last else "network"
            print(f"    {len(roads)} arterial ways, {len(water)} water polygons "
                  f"({src}, {time.time()-t0:.1f}s)")
            if not roads and not water:
                raise RuntimeError("empty result (both roads and water) — bad bbox or mirror hiccup")
            if args.dry_run:
                done.append(slug)
                continue

            def meta(kind, tol, count):
                return {
                    "source": "OpenStreetMap via Overpass (maps.mail.ru mirror) — measured geometry",
                    "generated_by": "pipeline/pull_province_ground.py",
                    "province": slug, "bbox": [s, w, n, e], "kind": kind,
                    "simplify_m": round(tol, 2), "n": count,
                    **({"min_area_m2": args.min_water_area} if kind == "water" else {}),
                }

            def build_roads(tol):
                items = []
                for path, cls in roads:
                    sp = simplify(path, tol)
                    if len(sp) >= 2:
                        items.append({"path": sp, "cls": cls})
                return {"meta": meta("roads", tol, len(items)), "roads": items}

            def build_water(tol):
                items = []
                for ring, nm in water:
                    sr = simplify(ring, tol)
                    if len(sr) >= 4:
                        items.append({"polygon": sr, "nm": nm})
                return {"meta": meta("water", tol, len(items)), "water": items}

            for out_path, build, label in ((roads_out, build_roads, "roads"),
                                           (water_out, build_water, "water")):
                blob, tol, over = budgeted_dump(build, args.simplify, args.budget, label)
                tmp = out_path + ".tmp"
                with open(tmp, "wb") as f:
                    f.write(blob)
                os.replace(tmp, out_path)
                print(f"    wrote {os.path.basename(out_path)}  "
                      f"({len(blob)/1024:.0f} KB, simplify={tol:g}m)")
                if over:
                    oversized.append({"file": f"platform/data/{os.path.basename(out_path)}",
                                      "bytes": len(blob), "simplify_m": round(tol, 2)})
            done.append(slug)
        except Exception as ex:  # noqa: BLE001 — a bad province must not kill the batch
            failed.append(slug)
            print(f"    ! {slug} FAILED: {ex} — continuing", file=sys.stderr)

    print("\n==== ground-bed batch summary ====")
    print(f"pulled : {len(done)}")
    print(f"skipped: {len(skipped)} (already had roads+water files)")
    print(f"failed : {len(failed)}  {failed}")
    if oversized and not args.dry_run:
        manifest = {
            "what": "province ground-bed files exceeding the 2 MB commit budget — upload these "
                    "to the catchments CDN (R2 bucket behind tiles_config.json catchments.baseUrl) "
                    "instead of committing; rayong-catchment.html falls back to the CDN on a "
                    "local 404.",
            "generated_by": "pipeline/pull_province_ground.py",
            "files": oversized,
        }
        os.makedirs(os.path.dirname(MANIFEST), exist_ok=True)
        with open(MANIFEST, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)
        print(f"oversized: {len(oversized)} — R2 manifest written to {MANIFEST}")
        print("           do NOT commit those files; upload them to the CDN.")
    elif oversized:
        print(f"oversized (dry-run, no manifest): {oversized}")
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
