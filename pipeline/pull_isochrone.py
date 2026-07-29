#!/usr/bin/env python3
"""
pull_isochrone.py — pull a travel-time ISOCHRONE for a city's focal branch and write the exact
FeatureCollection the 3D scene (platform/rayong-catchment.html) renders as graded drive-time bands.

WHAT IT MAKES
-------------
For a city slug + a point (lat/lng) it calls a routing provider's isochrone API and writes:

    platform/data/<slug>_isochrone.json

shaped EXACTLY as the page's GeoJsonLayer expects — a GeoJSON FeatureCollection of Polygon
features, one per requested minute band, each carrying BOTH conventions so the layer reads it
no matter the provider:

    {
      "type": "FeatureCollection",
      "features": [
        { "type": "Feature",
          "properties": { "minutes": 5, "value": 300 },   # value = seconds (ORS native)
          "geometry": { "type": "Polygon", "coordinates": [[[lng,lat],...]] } },
        ... 10, 15 ...
      ]
    }

The page (rayong-catchment.html → isoMinutes / isoColor / isoLayers) colours near bands warm red
and far bands cool green, draws them translucent above the ground bed and under the buildings,
and shows a "Drive time" legend + an Isochrone toggle. The layer is null-guarded: until this file
exists the scene renders exactly as before. So this is a pure leaf-data drop — NO code change after
it runs, just re-open the page (these are fetched directly, no rebuild).

PROVIDERS (pick with --provider; default ors)
---------------------------------------------
  ors     OpenRouteService  https://api.openrouteservice.org/v2/isochrones/driving-car
          Key env: ORS_KEY  (free tier: https://openrouteservice.org/dev/#/signup)
          Native units = seconds; --minutes are converted to seconds for the "range" param.

  gistda  GISTDA (Thai government geospatial)  https://api.sphere.gistda.or.th
          Key env: GISTDA_SPHERE_KEY (repo secret name; legacy GISTDA_API_KEY also accepted)
          GISTDA's routing/isochrone endpoint shape varies by plan; this script targets the
          documented isochrone resource and normalises whatever Polygon geometry it returns into
          the same FeatureCollection above. Verify the exact path against your GISTDA plan docs.

The key is read from the environment OR from a git-ignored repo-root .env (via pipeline/envload.py).
NEVER commit the key. NEVER paste it on the command line where a shell history would keep it.

NETWORK — RUN FROM A NON-BLOCKED NETWORK
----------------------------------------
Both providers are reachable from a normal/residential network. They may be geo/Cloudflare-blocked
from this sandbox's foreign IP (like data.go.th), so run this from Kaustav's Thai laptop. This script
makes ONE outbound HTTPS call per run; it does no other network I/O.

THE EXACT COMMAND (run this once the key is in .env)
---------------------------------------------------
    # 1) put your key in repo-root .env (git-ignored), e.g.:  ORS_KEY=eyJ...your-key...
    # 2) run (focal branch auto-read from platform/data/<slug>_catchment.json center):
    cd pipeline && python3 pull_isochrone.py --city rayong --minutes "5,10,15"

    # explicit point + provider:
    cd pipeline && python3 pull_isochrone.py --city rayong --lat 12.686 --lng 101.245 \
        --provider ors --minutes "5,10,15"

Then just re-open:  http://localhost:8000/rayong-catchment.html  (Isochrone toggle, top bar).

Flags:
  --city SLUG       city slug (drives the output filename + the focal-point lookup). required.
  --lat / --lng     focal point. If omitted, read from platform/data/<slug>_catchment.json
                    ("center", else "focal"). One of (lat&lng) or that file is required.
  --minutes "5,10,15"  comma-separated drive-time bands (default "5,10,15").
  --provider ors|gistda   routing provider (default ors).
  --profile         travel profile (ors: driving-car|cycling-regular|foot-walking; default driving-car).
  --out DIR         output directory (default ../platform/data).
  --dry-run         build + print the request, but DO NOT call the API or write the file.
"""
import argparse
import json
import os
import sys
import urllib.request
import urllib.error

try:
    from lib.envload import load_env
except Exception:  # pragma: no cover - envload is co-located, but degrade gracefully
    def load_env(*_a, **_k):
        return None


HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_OUT = os.path.normpath(os.path.join(HERE, "..", "platform", "data"))

ORS_URL = "https://api.openrouteservice.org/v2/isochrones/{profile}"
GISTDA_URL = "https://api.sphere.gistda.or.th/services/route/isochrone"


def _focal_from_catchment(out_dir, slug):
    """Best-effort: read the city's focal point from its catchment file (center, else focal)."""
    path = os.path.join(out_dir, f"{slug}_catchment.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
    except Exception:
        return None
    c = d.get("center")
    if c and c.get("lat") is not None and c.get("lng") is not None:
        return float(c["lat"]), float(c["lng"])
    fo = d.get("focal")
    if fo and fo.get("y") is not None and fo.get("x") is not None:
        return float(fo["y"]), float(fo["x"])
    return None


def _http_post(url, headers, payload, dry_run=False):
    body = json.dumps(payload).encode("utf-8")
    if dry_run:
        safe = {k: ("***" if k.lower() in ("authorization", "api-key") else v) for k, v in headers.items()}
        print(f"[dry-run] POST {url}\n  headers={safe}\n  body={json.dumps(payload)}")
        return None
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:500]
        sys.exit(f"[error] {url} -> HTTP {e.code}: {detail}")
    except urllib.error.URLError as e:
        sys.exit(f"[error] {url} -> {e.reason} (run from a non-blocked network)")


def _normalise(fc, minutes_secs):
    """Coerce a provider FeatureCollection into our exact shape: Polygon features with both
    properties.minutes (int) and properties.value (seconds). Maps each feature to its band by the
    closest 'value' (seconds) it reports, else by index order against the requested bands."""
    feats_in = (fc or {}).get("features") or []
    out = []
    by_sec = {s: m for m, s in [(int(round(s / 60)), s) for s in minutes_secs]}
    for i, ft in enumerate(feats_in):
        geom = ft.get("geometry") or {}
        if geom.get("type") not in ("Polygon", "MultiPolygon"):
            continue
        props = ft.get("properties") or {}
        secs = props.get("value")
        if secs is None and i < len(minutes_secs):
            secs = minutes_secs[i]
        try:
            secs = float(secs)
        except (TypeError, ValueError):
            secs = minutes_secs[min(i, len(minutes_secs) - 1)]
        mins = by_sec.get(int(secs), int(round(secs / 60)))
        out.append({
            "type": "Feature",
            "properties": {"minutes": int(mins), "value": int(round(secs))},
            "geometry": geom,
        })
    return {"type": "FeatureCollection", "features": out}


def pull_ors(lat, lng, minutes_secs, profile, key, dry_run):
    url = ORS_URL.format(profile=profile)
    headers = {"Authorization": key, "Content-Type": "application/json",
               "Accept": "application/json"}
    payload = {
        "locations": [[lng, lat]],          # ORS is [lng, lat]
        "range": minutes_secs,               # seconds
        "range_type": "time",
        "location_type": "start",
        "attributes": ["total_pop"],
    }
    fc = _http_post(url, headers, payload, dry_run=dry_run)
    return _normalise(fc, minutes_secs)


def pull_gistda(lat, lng, minutes_secs, key, dry_run):
    # GISTDA's exact request differs by plan; this targets a documented isochrone POST and
    # normalises the Polygon geometry it returns. Adjust the URL/params to your plan if needed.
    url = f"{GISTDA_URL}?key={'***' if dry_run else key}"
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    payload = {
        "lat": lat, "lon": lng,
        "ranges": minutes_secs,   # seconds
        "mode": "car",
    }
    fc = _http_post(url, headers, payload, dry_run=dry_run)
    return _normalise(fc, minutes_secs)


def main():
    load_env()
    ap = argparse.ArgumentParser(description="Pull a drive-time isochrone -> <slug>_isochrone.json")
    ap.add_argument("--city", required=True, help="city slug (output filename + focal lookup)")
    ap.add_argument("--lat", type=float, default=None)
    ap.add_argument("--lng", type=float, default=None)
    ap.add_argument("--minutes", default="5,10,15", help='comma-separated bands, e.g. "5,10,15"')
    ap.add_argument("--provider", choices=["ors", "gistda"], default="ors")
    ap.add_argument("--profile", default="driving-car", help="ORS travel profile")
    ap.add_argument("--out", default=DEFAULT_OUT, help="output directory")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    slug = args.city.strip().lower()
    out_dir = os.path.abspath(args.out)

    lat, lng = args.lat, args.lng
    if lat is None or lng is None:
        focal = _focal_from_catchment(out_dir, slug)
        if not focal:
            sys.exit("[error] no --lat/--lng and no center/focal in "
                     f"{slug}_catchment.json — pass the point explicitly.")
        lat, lng = focal
        print(f"[info] focal point read from {slug}_catchment.json: lat={lat} lng={lng}")

    try:
        minutes = [int(x) for x in args.minutes.split(",") if x.strip()]
    except ValueError:
        sys.exit("[error] --minutes must be comma-separated integers, e.g. 5,10,15")
    if not minutes:
        sys.exit("[error] --minutes is empty")
    minutes_secs = [m * 60 for m in sorted(set(minutes))]

    if args.provider == "ors":
        key = os.environ.get("ORS_KEY")
        if not key and not args.dry_run:
            sys.exit("[error] ORS_KEY not set (export it or put it in repo-root .env). NEVER commit it.")
        fc = pull_ors(lat, lng, minutes_secs, args.profile, key or "DRYRUN", args.dry_run)
    else:
        # Repo secret is named GISTDA_SPHERE_KEY (sphere.gistda.or.th); accept the legacy
        # GISTDA_API_KEY name too so an .env carrying either still works.
        key = os.environ.get("GISTDA_SPHERE_KEY") or os.environ.get("GISTDA_API_KEY")
        if not key and not args.dry_run:
            sys.exit("[error] GISTDA_SPHERE_KEY (or GISTDA_API_KEY) not set (export it or put it in repo-root .env). NEVER commit it.")
        fc = pull_gistda(lat, lng, minutes_secs, key or "DRYRUN", args.dry_run)

    if args.dry_run:
        print("[dry-run] no API call made, no file written.")
        return

    n = len(fc.get("features") or [])
    if n == 0:
        sys.exit("[error] provider returned no polygon bands — check the key/point/quota.")
    out_path = os.path.join(out_dir, f"{slug}_isochrone.json")
    os.makedirs(out_dir, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(fc, f, ensure_ascii=False, separators=(",", ":"))
    print(f"[ok] wrote {out_path}  ({n} band(s): {minutes} min)")
    print("     Re-open rayong-catchment.html — the Isochrone toggle + legend appear automatically.")


if __name__ == "__main__":
    main()
