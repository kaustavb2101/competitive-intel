#!/usr/bin/env python3
"""pull_isochrones.py — TRUE 15-minute drive-time isochrones (ORS) for the 3D catchment scene.

WHAT THIS DOES
--------------
Replaces the walk-radius / 10km-ring ESTIMATE on the 3D catchment scene
(platform/rayong-catchment.html) with a **MEASURED 15-minute driving isochrone** pulled from
**OpenRouteService (ORS)**. For each province it calls the ORS Isochrones API from a real AutoX
branch and writes the returned GeoJSON polygon to platform/data/<slug>_isochrone.json — the EXACT
filename + shape the scene already looks for (optScene('iso','_isochrone.json') / window.ISO).

This is the `td-isochrone` roadmap item ("true 15-min street-network isochrone", NEXT_STEPS §3).

NETWORK / KEY (why the real pull runs in CI, not locally)
---------------------------------------------------------
The pull needs an ORS API key in env **ORS_KEY**. The repo carries it as a **GitHub Actions secret**
(NOT in the local .env), so the measured pull runs in CI via .github/workflows/data-isochrones.yml.
ORS's public API is reachable from any normal network (it is NOT one of the Thai-IP-only sources),
so GitHub-hosted runners pull it fine.

Locally, without a key, you CANNOT (and must not) fabricate a polygon. You CAN still:
  * `--self-test`  — run the output shaping on a mocked ORS response and assert the shape/provenance
                     (no key, no network) — proves the file is syntactically correct + deterministic.
  * `--dry-run`    — resolve + print each province's isochrone ORIGIN (a real branch) with no network.

OUTPUT SHAPE (must match the scene exactly)
-------------------------------------------
platform/data/<slug>_isochrone.json is a GeoJSON FeatureCollection (ORS output PRESERVED) plus a
top-level `meta` provenance block. The scene reads `window.ISO.features`; isoMinutes() reads either
`properties.value` (ORS seconds) or the `properties.minutes` we add:

  { "type": "FeatureCollection",
    "meta": { "provenance": "measured",
              "source": "OpenRouteService isochrones (driving-car)",
              "measured": true, "profile": "driving-car",
              "range_minutes": 15, "range_seconds": 900,
              "vintage": "YYYY-MM", "generated_by": "pipeline/pull_isochrones.py",
              "slug": "...", "center": [lng, lat], "center_source": "..." },
    "features": [ { "type": "Feature",
                    "properties": { "group_index": 0, "value": 900.0, "minutes": 15, ... },
                    "geometry": { "type": "Polygon", "coordinates": [ ... ] } } ],
    "bbox": [ ... ] }

ISOCHRONE ORIGIN (deterministic, from committed data — no catchment file required)
----------------------------------------------------------------------------------
Per province the origin = the AutoX branch NEAREST the province centre, so the drive-time area is
anchored on a real branch (matching how the scene picks its default focal branch near the city core):
  * target point = the local <slug>_catchment.json `center` when that file exists (Rayong/Bangkok),
    else the province_bbox.json bbox centre.
  * origin = the branch in branches.json inside the province bbox nearest that target.
  * fallback = the bbox centre itself when the province has NO branch in the tape (logged).
Everything here reads only committed files (platform/data/province_bbox.json + branches.json), so the
ORIGIN is deterministic; only the ORS polygon itself is network-pulled (like branches/catchments).

POLITE + RESILIENT (never fabricates data)
------------------------------------------
  * throttled: --sleep seconds between provinces (default 1.6s; ORS free tier ~40 req/min).
  * retries 429 / 5xx with backoff (honours Retry-After on 429).
  * per-province failures are NON-FATAL: the province is SKIPPED + logged, the batch continues, and
    the script exits 2 if any province failed — so one rate-limit never loses the whole run, and a
    failed province simply gets no file (the scene keeps its 10km-ring fallback for it).

THE COMMANDS
------------
    # CI (with the ORS_KEY secret) — the real measured pull:
    ORS_KEY=... python3 pull_isochrones.py --only rayong
    ORS_KEY=... python3 pull_isochrones.py --all

    # local, no key — validate shape + plan origins:
    python3 pull_isochrones.py --self-test
    python3 pull_isochrones.py --only rayong,chon-buri --dry-run

Flags:
  --only a,b,c        pull just these province slugs (slugs = province_bbox.json / provinces/index.json)
  --all               pull EVERY province in province_bbox.json
  --range-min M       isochrone range in minutes (default 15 => range=[900] seconds)
  --profile P         ORS routing profile (default driving-car)
  --sleep S           seconds between provinces (default 1.6; be polite to the API)
  --out-dir DIR       output directory (default platform/data)
  --register-scenery  after writing, add the written slugs to platform/data/tiles_config.json's
                      "scenery" allowlist (the frontend gate that enables the iso toggle). Run
                      `python3 build_provenance.py` afterwards so the census stays in sync.
  --dry-run           resolve + print origins only; no network, no write
  --self-test         shape a MOCKED ORS response + assert the output shape/provenance; no key/network
"""
import argparse
import json
import math
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "platform", "data")
PROVINCE_BBOX = os.path.join(DATA, "province_bbox.json")
BRANCHES = os.path.join(DATA, "branches.json")
TILES_CONFIG = os.path.join(DATA, "tiles_config.json")

ORS_BASE = "https://api.openrouteservice.org/v2/isochrones"
DEFAULT_RANGE_MIN = 15
DEFAULT_PROFILE = "driving-car"
DEFAULT_SLEEP = 1.6
COORD_DP = 6                       # round polygon coords -> stable, web-sized files
D2R = math.pi / 180.0


def _log(*a):
    print(*a, file=sys.stderr, flush=True)


def _load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _provinces():
    """{slug: {"bbox":[S,W,N,E], "th":.., "en":..}} from the committed province_bbox.json."""
    doc = _load(PROVINCE_BBOX)
    provs = doc.get("provinces") if isinstance(doc, dict) else None
    if not isinstance(provs, dict) or not provs:
        raise SystemExit("province_bbox.json has no 'provinces' map — run "
                         "pipeline/pull_overture_buildings.py --bbox-only first.")
    return provs


def _branch_points():
    """Every AutoX branch as (lng, lat) from branches.json (x=lng, y=lat)."""
    d = _load(BRANCHES)
    items = d.get("items", d) if isinstance(d, dict) else d
    out = []
    for b in items:
        x, y = b.get("x"), b.get("y")
        if isinstance(x, (int, float)) and isinstance(y, (int, float)):
            out.append((float(x), float(y)))
    return out


def _catchment_center(slug):
    """The curated catchment centre {lat,lng} when a LOCAL <slug>_catchment.json exists (Rayong /
    Bangkok ship one); else None. Most provinces' catchments live on R2, not on disk, so this is a
    best-effort refinement — the bbox centre is the deterministic fallback."""
    path = os.path.join(DATA, f"{slug}_catchment.json")
    if not os.path.exists(path):
        return None
    try:
        c = _load(path).get("center") or {}
        lat, lng = c.get("lat"), c.get("lng")
        if isinstance(lat, (int, float)) and isinstance(lng, (int, float)):
            return (float(lng), float(lat))
    except Exception:  # noqa: BLE001 — unreadable catchment is not fatal; fall back to bbox centre
        pass
    return None


def _km(a, b):
    """Great-circle-ish distance (km) between (lng,lat) tuples — equirectangular, fine at province scale."""
    (x0, y0), (x1, y1) = a, b
    cosl = math.cos(((y0 + y1) / 2.0) * D2R) or 1.0
    dx = (x1 - x0) * cosl * 111.0
    dy = (y1 - y0) * 111.0
    return math.hypot(dx, dy)


def resolve_origin(slug, prov, branch_pts):
    """Deterministic isochrone origin for a province: the AutoX branch nearest the province centre
    (catchment centre when local, else bbox centre). Returns ((lng,lat), source_str). Falls back to
    the bbox centre when the province has no branch in the tape."""
    s, w, n, e = prov["bbox"]
    bbox_center = ((w + e) / 2.0, (s + n) / 2.0)                      # (lng, lat)
    target = _catchment_center(slug) or bbox_center
    tgt_src = "catchment centre" if _catchment_center(slug) else "province bbox centre"
    pad = 1.0 / 111.0                                                 # ~1km pad, matches pull_overture
    inside = [p for p in branch_pts
              if (w - pad) <= p[0] <= (e + pad) and (s - pad) <= p[1] <= (n + pad)]
    if not inside:
        return bbox_center, "province bbox centre (no AutoX branch in tape)"
    # nearest branch to the target; deterministic tie-break by (lng,lat)
    origin = min(inside, key=lambda p: (_km(p, target), p[0], p[1]))
    return origin, f"AutoX branch nearest {tgt_src}"


# ── ORS call ─────────────────────────────────────────────────────────────────────
def fetch_isochrone(lng, lat, key, range_s, profile, timeout=90, tries=4):
    """POST to ORS Isochrones and return the parsed GeoJSON. Retries 429/5xx with backoff.
    Raises on a non-retryable error or after exhausting retries (caller treats it as non-fatal)."""
    import urllib.request
    import urllib.error
    url = f"{ORS_BASE}/{profile}"
    body = json.dumps({"locations": [[round(lng, 6), round(lat, 6)]],
                       "range": [int(range_s)], "range_type": "time"}).encode("utf-8")
    last = None
    for attempt in range(1, tries + 1):
        req = urllib.request.Request(url, data=body, method="POST")
        req.add_header("Authorization", key)
        req.add_header("Content-Type", "application/json; charset=utf-8")
        req.add_header("Accept", "application/geo+json, application/json")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as ex:
            last = ex
            code = ex.code
            if code in (429, 500, 502, 503, 504) and attempt < tries:
                # honour Retry-After on 429, else exponential-ish backoff
                ra = ex.headers.get("Retry-After") if ex.headers else None
                try:
                    wait = float(ra) if ra else 0
                except (TypeError, ValueError):
                    wait = 0
                wait = max(wait, min(30.0, 3.0 * attempt))
                _log(f"    ORS HTTP {code} (attempt {attempt}/{tries}) — retrying in {wait:.0f}s")
                time.sleep(wait)
                continue
            detail = ""
            try:
                detail = ex.read().decode("utf-8")[:300]
            except Exception:  # noqa: BLE001
                pass
            raise RuntimeError(f"ORS HTTP {code}: {detail or ex.reason}") from ex
        except urllib.error.URLError as ex:
            last = ex
            if attempt < tries:
                wait = min(30.0, 3.0 * attempt)
                _log(f"    ORS network error ({ex.reason}) attempt {attempt}/{tries} — retry in {wait:.0f}s")
                time.sleep(wait)
                continue
            raise RuntimeError(f"ORS network error: {ex.reason}") from ex
    raise RuntimeError(f"ORS failed after {tries} attempts: {last}")


# ── output shaping (deterministic; the only thing --self-test exercises) ──────────
def _round_coords(x):
    if isinstance(x, list):
        return [_round_coords(v) for v in x]
    if isinstance(x, float):
        return round(x, COORD_DP)
    return x


def shape_output(ors, slug, origin, range_s, profile, center_source, vintage):
    """Turn a raw ORS FeatureCollection into the committed <slug>_isochrone.json shape:
    preserve geometry + ORS properties, add properties.minutes, attach a MEASURED meta block.
    Deterministic: coordinates rounded to COORD_DP dp. Raises ValueError on an unusable response."""
    if not isinstance(ors, dict) or ors.get("type") != "FeatureCollection":
        raise ValueError("ORS response is not a GeoJSON FeatureCollection")
    feats_in = ors.get("features")
    if not isinstance(feats_in, list) or not feats_in:
        raise ValueError("ORS response has no isochrone features")
    minutes = round(range_s / 60.0, 3)
    minutes = int(minutes) if float(minutes).is_integer() else minutes
    feats = []
    for ft in feats_in:
        geom = (ft or {}).get("geometry") or {}
        if geom.get("type") not in ("Polygon", "MultiPolygon") or not geom.get("coordinates"):
            raise ValueError("ORS feature has no polygon geometry")
        props = dict((ft.get("properties") or {}))
        # ORS emits properties.value (seconds); guarantee both value + minutes for the scene.
        val = props.get("value", range_s)
        try:
            props["value"] = float(val)
            props["minutes"] = round(float(val) / 60.0, 3)
            if float(props["minutes"]).is_integer():
                props["minutes"] = int(props["minutes"])
        except (TypeError, ValueError):
            props["value"] = float(range_s)
            props["minutes"] = minutes
        feats.append({
            "type": "Feature",
            "properties": props,
            "geometry": {"type": geom["type"], "coordinates": _round_coords(geom["coordinates"])},
        })
    doc = {
        "type": "FeatureCollection",
        "meta": {
            "provenance": "measured",
            "measured": True,
            "source": f"OpenRouteService isochrones ({profile})",
            "profile": profile,
            "range_minutes": minutes,
            "range_seconds": int(range_s),
            "vintage": vintage,
            "generated_by": "pipeline/pull_isochrones.py",
            "slug": slug,
            "center": [round(origin[0], 6), round(origin[1], 6)],
            "center_source": center_source,
            "note": ("MEASURED drive-time reach (ORS driving-car). Replaces the estimated walk/10km "
                     "reach ring on the 3D catchment scene; the ring remains the graceful fallback "
                     "where no isochrone exists."),
        },
        "features": feats,
    }
    if isinstance(ors.get("bbox"), list):
        doc["bbox"] = _round_coords(ors["bbox"])
    return doc


def _write(doc, out_dir, slug):
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"{slug}_isochrone.json")
    text = json.dumps(doc, ensure_ascii=False, separators=(",", ":"))
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path, len(text.encode("utf-8"))


def register_scenery(slugs):
    """Add slugs to platform/data/tiles_config.json's top-level "scenery" allowlist (the frontend
    gate window.HAS_SCENERY reads). Idempotent + sorted. Run build_provenance.py afterwards."""
    if not os.path.exists(TILES_CONFIG):
        _log("register-scenery: tiles_config.json absent — skipped")
        return
    cfg = _load(TILES_CONFIG)
    cur = cfg.get("scenery")
    cur = list(cur) if isinstance(cur, list) else []
    merged = sorted(set(cur) | set(slugs))
    if merged == cur:
        _log("register-scenery: no change (all slugs already in scenery)")
        return
    cfg["scenery"] = merged
    with open(TILES_CONFIG, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
        f.write("\n")
    _log(f"register-scenery: tiles_config.json scenery = {merged}")


# ── self-test: prove the shaping is correct + deterministic, no key/network ───────
_SYNTH_ORS = {
    "type": "FeatureCollection",
    "bbox": [101.15, 12.65, 101.25, 12.75],
    "features": [{
        "type": "Feature",
        "properties": {"group_index": 0, "value": 900.0, "center": [101.2000001, 12.7000001]},
        "geometry": {"type": "Polygon", "coordinates": [[
            [101.1500009, 12.6500009], [101.2500009, 12.6500009],
            [101.2500009, 12.7500009], [101.1500009, 12.7500009],
            [101.1500009, 12.6500009]]]},
    }],
    "metadata": {"engine": {"version": "self-test"}},
}


def self_test():
    doc = shape_output(_SYNTH_ORS, "rayong", (101.2, 12.7), 900, DEFAULT_PROFILE,
                       "AutoX branch nearest catchment centre", "2026-07")
    assert doc["type"] == "FeatureCollection", "top-level type must be FeatureCollection"
    assert doc["meta"]["provenance"] == "measured" and doc["meta"]["measured"] is True
    assert doc["meta"]["range_minutes"] == 15 and doc["meta"]["range_seconds"] == 900
    assert doc["meta"]["profile"] == DEFAULT_PROFILE
    assert isinstance(doc["features"], list) and len(doc["features"]) == 1
    f0 = doc["features"][0]
    assert f0["properties"]["value"] == 900.0, "ORS seconds preserved"
    assert f0["properties"]["minutes"] == 15, "minutes derived for isoMinutes()"
    assert f0["geometry"]["type"] == "Polygon" and f0["geometry"]["coordinates"]
    # coords rounded to COORD_DP dp -> deterministic + web-sized
    assert f0["geometry"]["coordinates"][0][0] == [round(101.1500009, COORD_DP), round(12.6500009, COORD_DP)]
    # re-serialising the same input is byte-identical (deterministic shape)
    a = json.dumps(shape_output(_SYNTH_ORS, "rayong", (101.2, 12.7), 900, DEFAULT_PROFILE, "x", "2026-07"),
                   ensure_ascii=False, separators=(",", ":"))
    b = json.dumps(shape_output(_SYNTH_ORS, "rayong", (101.2, 12.7), 900, DEFAULT_PROFILE, "x", "2026-07"),
                   ensure_ascii=False, separators=(",", ":"))
    assert a == b, "shaping must be deterministic"
    # the scene's isoMinutes() equivalent must read 15 from either property
    assert f0["properties"]["value"] / 60 == 15
    print("self-test OK — output is a MEASURED FeatureCollection the scene reads "
          "(features[].properties.value=900s / minutes=15, deterministic, coords@%ddp)." % COORD_DP)
    return 0


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", help="comma-separated province slugs to pull")
    ap.add_argument("--all", action="store_true", help="pull every province in province_bbox.json")
    ap.add_argument("--range-min", type=float, default=DEFAULT_RANGE_MIN,
                    help="isochrone range in minutes (default 15 => range=[900]s)")
    ap.add_argument("--profile", default=DEFAULT_PROFILE, help="ORS routing profile (default driving-car)")
    ap.add_argument("--sleep", type=float, default=DEFAULT_SLEEP,
                    help="seconds between provinces (default 1.6; be polite to ORS)")
    ap.add_argument("--out-dir", default=DATA, help="output directory (default platform/data)")
    ap.add_argument("--register-scenery", action="store_true",
                    help="add written slugs to tiles_config.json scenery allowlist")
    ap.add_argument("--dry-run", action="store_true", help="resolve + print origins only; no network/write")
    ap.add_argument("--self-test", action="store_true",
                    help="shape a MOCKED ORS response + assert the shape; no key/network")
    args = ap.parse_args()
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass

    if args.self_test:
        sys.exit(self_test())

    provs = _provinces()
    if args.all:
        slugs = sorted(provs.keys())
    elif args.only:
        slugs = [s.strip().lower() for s in args.only.split(",") if s.strip()]
    else:
        ap.error("give --only <slugs> or --all (or --self-test / --dry-run --only ...)")

    unknown = [s for s in slugs if s not in provs]
    if unknown:
        _log(f"WARNING: unknown province slug(s) dropped: {unknown} "
             f"(valid = keys of platform/data/province_bbox.json / provinces/index.json)")
    slugs = [s for s in slugs if s in provs]
    if not slugs:
        raise SystemExit("no valid province slugs to pull.")

    branch_pts = _branch_points()
    range_s = int(round(args.range_min * 60))
    vintage = time.strftime("%Y-%m", time.gmtime())

    key = os.environ.get("ORS_KEY") or os.environ.get("ORS_API_KEY")
    if not key and not args.dry_run:
        raise SystemExit(
            "ORS_KEY not set. The real pull runs in CI (.github/workflows/data-isochrones.yml, "
            "secret ORS_KEY). Locally use --dry-run (plan origins) or --self-test (validate shape).")

    print(f"isochrones: {len(slugs)} province(s), range={range_s}s ({args.range_min:g} min), "
          f"profile={args.profile}, vintage={vintage}"
          f"{'  [DRY-RUN]' if args.dry_run else ''}")

    written, failed = [], []
    for i, slug in enumerate(slugs):
        origin, src = resolve_origin(slug, provs[slug], branch_pts)
        en = provs[slug].get("en") or slug
        print(f"[{i + 1}/{len(slugs)}] {slug} ({en}): origin lng,lat = "
              f"{origin[0]:.5f},{origin[1]:.5f}  [{src}]")
        if args.dry_run:
            continue
        try:
            ors = fetch_isochrone(origin[0], origin[1], key, range_s, args.profile)
            doc = shape_output(ors, slug, origin, range_s, args.profile, src, vintage)
            path, nbytes = _write(doc, args.out_dir, slug)
            nfeat = len(doc["features"])
            print(f"    wrote {os.path.relpath(path, ROOT)}  ({nbytes / 1024.0:.1f} KB, "
                  f"{nfeat} band(s))  MEASURED (ORS {args.profile}, {args.range_min:g}-min)")
            written.append(slug)
        except Exception as ex:  # noqa: BLE001 — per-province NON-FATAL; skip + log, never fabricate
            _log(f"    SKIP {slug}: {ex}")
            failed.append(slug)
        if i + 1 < len(slugs):
            time.sleep(max(0.0, args.sleep))

    if args.dry_run:
        print(f"\nDRY-RUN: resolved {len(slugs)} origin(s); no network, no files written.")
        return 0

    if written and args.register_scenery:
        register_scenery(written)
        print("registered scenery — run: python3 pipeline/build_provenance.py "
              "(then commit tiles_config.json + provenance.json)")

    print(f"\n=== isochrones: wrote {len(written)}, skipped {len(failed)} "
          f"(of {len(slugs)}) → {os.path.relpath(args.out_dir, ROOT)} ===")
    if written:
        print("wrote: " + ", ".join(written))
    if failed:
        print("skipped (no file — scene keeps its 10km-ring fallback): " + ", ".join(failed))
    # exit 2 when any province failed so the CI step can warn without discarding what succeeded.
    return 2 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
