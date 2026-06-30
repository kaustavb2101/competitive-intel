#!/usr/bin/env python3
"""
pull_overture_places.py — SUPER-GRANULAR employment/occupation source layer.

WHAT THIS DOES
--------------
Pulls **Overture Maps Places** (64M+ real-world establishment points worldwide,
each with a controlled category taxonomy) for a bbox and writes a COMPACT, measured
occupation source layer to source-data/overture_places.json.

Each place is a workplace. We map its Overture primary category onto one of ~14
occupation buckets (factory, auto trade, retail, food service, healthcare, …) so a
downstream rollup (build_occupations.py) can count, within 10km of every AutoX branch,
WHAT KIND of work surrounds it — point-level and MEASURED, far more granular than the
province-level NSO informal-workforce number or the OSM-POI "who works nearby" proxy.

Why Overture Places (vs the OSM POI proxy we use today):
  * POINT-level establishments with a real, controlled category taxonomy.
  * Denser than OSM in Thailand (Overture fuses OSM + Meta + Microsoft + partner data).
  * Free, no geo-block — distributed as cloud Parquet on AWS/Azure (NOT a data.go.th
    style blocked endpoint), so it runs from any normal connection.

NETWORK / DEPENDENCY
--------------------
Needs the Overture CLI (same one the buildings puller uses):

    pip install overturemaps

THE ONE COMMAND (owner)
-----------------------
    cd pipeline && python3 pull_overture_places.py \
        --bbox "12.62,101.13,12.74,101.33"            # WIDE Rayong (default)

For the whole country (large pull, tens of MB of points):
    cd pipeline && python3 pull_overture_places.py --preset national

Under the hood it shells to (geojsonseq — the per-feature streaming writer that
avoids the buggy single-FeatureCollection writer on newer pyarrow / Python 3.14):
    overturemaps download --bbox=W,S,E,N -f geojsonseq --type=place -o <tmp>
(Overture wants W,S,E,N; our friendly --bbox is S,W,N,E and we reorder it.)
If you already have an Overture places export, pass --geojson PATH to skip the download.

OUTPUT (source-data/overture_places.json) — compact + deterministic:
  { "meta": {source, bbox, count, radius_hint_km, generated_with},
    "buckets": [ {"key","label"}, ... ],          # occupation buckets, stable order
    "places":  [ [lng, lat, bucket_idx], ... ] }  # bucket_idx into buckets; -1 = other
Places are sorted by (lng,lat,bucket_idx) so a re-pull of the same bbox is byte-stable.

Flags:
  --bbox S,W,N,E   friendly bbox (default WIDE Rayong 12.62,101.13,12.74,101.33)
  --preset national  use the whole-Thailand bbox (overrides --bbox)
  --geojson PATH   use an existing Overture places GeoJSON/seq instead of downloading
  --cli NAME       Overture CLI executable (default: overturemaps)
  --out PATH       output (default ../source-data/overture_places.json)
  --keep-geojson   don't delete the downloaded temp file
  --dry-run        fetch + summarise but DO NOT write the output file
"""
import argparse, json, os, subprocess, sys, tempfile, shutil

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DEFAULT_OUT = os.path.join(ROOT, "source-data", "overture_places.json")
# WIDE Rayong bbox (S,W,N,E) — matches the buildings puller so the 3D scene + occupation
# layer cover the same ground on a first run.
DEFAULT_BBOX = "12.62,101.13,12.74,101.33"
# Whole-Thailand bbox (S,W,N,E) for --preset national.
NATIONAL_BBOX = "5.5,97.3,20.5,105.7"

# Occupation buckets, in PRIORITY order (first matching keyword wins). Keys are stable;
# labels surface in the "Who works nearby" panel. Keyword lists are matched as substrings
# against the Overture primary category string (lowercased), which is itself a leaf in
# Overture's controlled taxonomy (e.g. "automotive_repair", "shopping", "restaurant").
OCC_BUCKETS = [
    ("factory",      "Factory / production",   ["factory", "manufactur", "industrial", "warehouse", "plant", "mill", "fabrica"]),
    ("auto",         "Auto trade & mechanics", ["automotive", "car_", "auto_", "motorcycle", "vehicle", "tire", "tyre", "gas_station", "fuel", "dealership"]),
    ("retail",       "Market vendors & retail", ["shopping", "retail", "market", "supermarket", "grocery", "convenience", "mall", "store", "shop"]),
    ("food",         "Food service",           ["restaurant", "eat_and_drink", "cafe", "coffee", "bar_", "bakery", "street_food", "food"]),
    ("hospitality",  "Hospitality / tourism",  ["hotel", "accommodation", "lodging", "resort", "guest", "travel", "tour"]),
    ("finance",      "Finance & pawn",         ["bank", "financial", "atm", "pawn", "insurance", "credit", "money"]),
    ("health",       "Healthcare",             ["hospital", "health", "medical", "clinic", "pharmacy", "dental", "doctor", "nursing"]),
    ("education",    "Education",              ["school", "education", "university", "college", "kindergarten", "tutor", "library"]),
    ("public",       "Public sector",          ["government", "public_service", "police", "fire_", "post_office", "embassy", "court", "municipal", "civic"]),
    ("professional", "Professional & office",  ["professional", "office", "business_to_business", "consult", "legal", "account", "real_estate", "software", "it_service"]),
    ("agriculture",  "Agriculture",            ["farm", "agricultur", "plantation", "fishery", "ranch", "livestock", "crop"]),
    ("personal",     "Personal services",      ["beauty", "salon", "spa", "barber", "laundry", "tailor", "massage", "repair"]),
    ("logistics",    "Logistics & transport",  ["logistics", "transport", "shipping", "freight", "courier", "delivery", "cargo", "moving"]),
    ("construction", "Construction & trades",  ["construction", "building_materials", "contractor", "hardware", "plumb", "electrician", "carpenter"]),
]
BUCKET_KEYS = [b[0] for b in OCC_BUCKETS]


def bucket_index(primary):
    """Overture primary category string -> bucket index, or -1 (other/unmatched)."""
    if not primary:
        return -1
    p = primary.lower()
    for i, (_key, _label, kws) in enumerate(OCC_BUCKETS):
        for kw in kws:
            if kw in p:
                return i
    return -1


def _bbox_parts(bbox):
    parts = [float(x) for x in bbox.split(",")]
    if len(parts) != 4:
        raise ValueError("--bbox must be S,W,N,E")
    return parts  # s, w, n, e


def download_seq(cli, bbox, dest):
    """Shell to the Overture CLI for places. Our --bbox is S,W,N,E; Overture wants W,S,E,N."""
    s, w, n, e = _bbox_parts(bbox)
    ovt_bbox = f"{w},{s},{e},{n}"
    if not shutil.which(cli):
        raise RuntimeError(
            f"'{cli}' not found on PATH. Install it first:\n"
            f"    pip install overturemaps\n"
            f"(or pass --geojson PATH to use an existing export, or --cli to point at the binary).")
    cmd = [cli, "download", f"--bbox={ovt_bbox}", "-f", "geojsonseq",
           "--type=place", "-o", dest]
    print("running:", " ".join(cmd), file=sys.stderr)
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "").strip()
        raise RuntimeError(
            f"overturemaps download failed (exit {proc.returncode}).\n"
            f"--- CLI output ---\n{tail or '(no output captured)'}\n"
            f"------------------\n"
            f"Common causes: no network reach to the Overture S3 bucket, an outdated "
            f"pyarrow, or too-large a bbox timing out. Try a smaller bbox first.")
    return dest


def _primary_category(props):
    cats = props.get("categories")
    if isinstance(cats, dict):
        return cats.get("primary") or ""
    if isinstance(cats, str):
        return cats
    # some exports flatten it
    return props.get("category") or props.get("class") or ""


def load_features(path):
    """Handle both whole-file GeoJSON (FeatureCollection/Feature/list) and line-delimited seq."""
    text = open(path, encoding="utf-8").read()
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
    feats = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        ft = json.loads(line)
        if isinstance(ft, dict) and ft.get("type") == "FeatureCollection":
            feats.extend(ft.get("features", []))
        else:
            feats.append(ft)
    return feats


def convert(features):
    """Place features -> (places list [[lng,lat,bucket_idx]], stats dict)."""
    out = []
    by_bucket = {}
    other = 0
    for ft in features:
        geom = ft.get("geometry") or {}
        if geom.get("type") != "Point":
            continue
        coords = geom.get("coordinates")
        if not coords or len(coords) < 2:
            continue
        try:
            lng, lat = float(coords[0]), float(coords[1])
        except (TypeError, ValueError):
            continue
        props = ft.get("properties") or {}
        bi = bucket_index(_primary_category(props))
        out.append([round(lng, 6), round(lat, 6), bi])
        if bi < 0:
            other += 1
        else:
            by_bucket[BUCKET_KEYS[bi]] = by_bucket.get(BUCKET_KEYS[bi], 0) + 1
    # deterministic order: a re-pull of the same bbox produces a byte-stable file
    out.sort(key=lambda p: (p[0], p[1], p[2]))
    return out, {"by_bucket": by_bucket, "other": other}


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bbox", default=DEFAULT_BBOX, help="S,W,N,E (default WIDE Rayong)")
    ap.add_argument("--preset", choices=["national"], help="use a named bbox (national = whole Thailand)")
    ap.add_argument("--geojson", help="use an existing Overture places GeoJSON/seq instead of downloading")
    ap.add_argument("--cli", default="overturemaps", help="Overture CLI executable name")
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--keep-geojson", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    bbox = NATIONAL_BBOX if args.preset == "national" else args.bbox

    tmp = None
    gj = args.geojson
    if not gj:
        fd, tmp = tempfile.mkstemp(prefix="overture_places_", suffix=".geojsonseq")
        os.close(fd)
        download_seq(args.cli, bbox, tmp)
        gj = tmp

    try:
        feats = load_features(gj)
        print(f"loaded {len(feats)} Overture place features from {gj}", file=sys.stderr)
        places, stats = convert(feats)
    finally:
        if tmp and not args.keep_geojson and os.path.exists(tmp):
            os.remove(tmp)

    n = len(places)
    if n == 0:
        print("ERROR: no places produced — check the bbox / GeoJSON.", file=sys.stderr)
        sys.exit(2)

    classified = n - stats["other"]
    pct = 100 * classified // n
    print(f"places: {n}  |  classified into occupation buckets {classified} ({pct}%)  "
          f"other/unmatched {stats['other']} ({100 - pct}%)")
    for key, _label, _kw in OCC_BUCKETS:
        c = stats["by_bucket"].get(key, 0)
        if c:
            print(f"  {key:13s} {c}")

    out = {
        "meta": {
            "source": "Overture Maps Places — measured establishment points (a sample/lower bound, not a registry)",
            "bbox": bbox,
            "count": n,
            "radius_hint_km": 10,
            "generated_with": "pull_overture_places.py",
        },
        "buckets": [{"key": k, "label": lbl} for (k, lbl, _kw) in OCC_BUCKETS],
        "places": places,
    }

    if args.dry_run:
        print("--dry-run: not writing.")
        return

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    kb = os.path.getsize(args.out) / 1024.0
    print(f"wrote {args.out}  ({kb:.1f} KB)")
    print("NEXT: cd pipeline && python3 build_occupations.py   "
          "(rolls these points up into per-branch 10km occupation mix for the app)")


if __name__ == "__main__":
    main()
