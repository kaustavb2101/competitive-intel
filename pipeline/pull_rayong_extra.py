#!/usr/bin/env python3
"""
pull_rayong_extra.py — fetch OPTIONAL extra OSM layers for the 3D catchment scene:
TREES (natural=tree points) and RAILWAYS (railway=rail/subway/tram/light_rail lines).

These dress the scene with the small details that sell "real city": tree dots/columns
standing between the buildings, and a dark dashed rail line threading under the roads.

It writes EXACTLY the shapes the page expects (additive, null-guarded — absent file =>
the page simply skips that layer):

  platform/data/rayong_trees.json  -> { "trees": [ [lng,lat], [lng,lat], ... ] }
  platform/data/rayong_rail.json   -> { "rail":  [ { "path": [[lng,lat],...] }, ... ] }

DATA PROVENANCE: 100% measured OpenStreetMap geometry (no estimation). The default bbox
is the WIDE Rayong box (matches pull_overture_buildings.py) so trees/rail line up under
the richer building set.

NETWORK
-------
Uses the same Overpass mirror as the other pullers (maps.mail.ru). Overpass is reachable
from Thailand. Run from a non-blocked network.

THE EXACT ONE COMMAND (owner, tonight)
--------------------------------------
    cd pipeline && python3 pull_rayong_extra.py \
        --bbox "12.62,101.13,12.74,101.33"

(then reload rayong-catchment.html — trees + rail plug in with no code change.)

Flags:
  --endpoint URL   Overpass interpreter URL (default: maps.mail.ru mirror)
  --bbox S,W,N,E   override the bbox (default the WIDE Rayong box)
  --out DIR        output directory (default ../platform/data)
  --simplify M     douglas-peucker tolerance in metres for rail vertices (default 6)
  --dry-run        fetch + summarise counts but DO NOT write files
"""
import argparse, json, math, os, sys, time, urllib.request, urllib.parse

DEFAULT_MIRROR = "https://maps.mail.ru/osm/tools/overpass/api/interpreter"
# WIDE Rayong box (S,W,N,E) — matches pull_overture_buildings.py default.
DEFAULT_BBOX = "12.62,101.13,12.74,101.33"

RAIL_KINDS = {"rail", "subway", "tram", "light_rail", "narrow_gauge", "monorail"}


def overpass(query, endpoint, timeout=180, retries=2):
    data = urllib.parse.urlencode({"data": query}).encode()
    last = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(
                endpoint, data=data,
                headers={"User-Agent": "autox-rayong-extra/1.0"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.load(r)
        except Exception as ex:  # noqa: BLE001
            last = ex
            if attempt < retries:
                wait = 8 * (attempt + 1)
                print(f"  overpass attempt {attempt+1} failed ({ex}); retrying in {wait}s",
                      file=sys.stderr)
                time.sleep(wait)
    raise RuntimeError(f"Overpass failed after {retries+1} attempts: {last}")


def _geom_to_lnglat(geom):
    return [[g["lon"], g["lat"]] for g in geom if "lat" in g and "lon" in g]


def _perp_dist_m(p, a, b):
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
    # ONE combined query: tree points (nodes) + railway lines (ways).
    q = f"""[out:json][timeout:180];
(
  node["natural"="tree"]({bbox});
  way["railway"~"^(rail|subway|tram|light_rail|narrow_gauge|monorail)$"]({bbox});
);
out body geom;
"""
    print(f"querying Overpass ({endpoint}) bbox={bbox} …", file=sys.stderr)
    t0 = time.time()
    d = overpass(q, endpoint)
    els = d.get("elements", [])
    print(f"  {len(els)} elements in {time.time()-t0:.1f}s", file=sys.stderr)

    trees, rail = [], []
    for el in els:
        etype = el.get("type")
        tags = el.get("tags", {}) or {}
        if etype == "node" and tags.get("natural") == "tree":
            if "lon" in el and "lat" in el:
                trees.append([el["lon"], el["lat"]])
            continue
        if etype == "way" and tags.get("railway") in RAIL_KINDS and el.get("geometry"):
            path = simplify(_geom_to_lnglat(el["geometry"]), tol_m)
            if len(path) >= 2:
                rail.append({"path": path})
    return trees, rail


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--endpoint", default=DEFAULT_MIRROR)
    ap.add_argument("--bbox", default=DEFAULT_BBOX)
    ap.add_argument("--out", default=os.path.join(here, "..", "platform", "data"))
    ap.add_argument("--simplify", type=float, default=6.0)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    trees, rail = pull(args.endpoint, args.bbox, args.simplify)
    print(f"trees: {len(trees):6d}")
    print(f"rail:  {len(rail):6d} lines")

    if not (trees or rail):
        print("NOTE: nothing returned (Rayong may have few mapped trees/rail). "
              "Files not written.", file=sys.stderr)
        sys.exit(0 if args.dry_run else 3)

    if args.dry_run:
        print("--dry-run: not writing files.")
        return

    out = os.path.abspath(args.out)
    os.makedirs(out, exist_ok=True)
    base_meta = {
        "city": "Rayong",
        "source": f"OpenStreetMap (Overpass, {args.endpoint}) — pipeline/pull_rayong_extra.py",
        "bbox": args.bbox,
        "note": "MEASURED OSM geometry, no estimation.",
    }
    targets = {}
    if trees:
        targets["rayong_trees.json"] = {"trees": trees, "meta": {**base_meta, "n_features": len(trees)}}
    if rail:
        targets["rayong_rail.json"] = {"rail": rail, "meta": {**base_meta, "n_features": len(rail)}}
    for name, payload in targets.items():
        path = os.path.join(out, name)
        with open(path, "w") as f:
            json.dump(payload, f, separators=(",", ":"))
        kb = os.path.getsize(path) / 1024.0
        print(f"wrote {path}  ({kb:.1f} KB)")
    print("done. Reload rayong-catchment.html — trees + rail plug in with no code change.")


if __name__ == "__main__":
    main()
