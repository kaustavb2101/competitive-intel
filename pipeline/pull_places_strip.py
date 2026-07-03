#!/usr/bin/env python3
"""
pull_places_strip.py — memory-safe Overture Places pull for ONE bbox strip, KEEPING names + phones.

The original pull_overture_places.py dropped establishment names/phones (it only kept the 14-bucket
occupation index for COUNTS). To build NAMED occupation leads per branch (actual businesses staff can
call), we need the names back. This puller streams a strip's Overture Places and keeps, for every
occupation-relevant establishment, a compact record: [lng, lat, bucket_idx, name, phone].

MEASURED: every point is a real Overture Places establishment coordinate + its published name/phone.
No synthesis. Only occupation-relevant places (primary category maps to one of the 14 OCC_BUCKETS)
are kept; the rest are dropped. Coords rounded to 5dp (~1m).

Streams the geojsonseq line-by-line (never loads the whole strip into RAM), so a national-height
lng-strip is memory-safe. Deterministic sort (lng,lat,bucket).

Usage:
  python3 pull_places_strip.py --bbox S,W,N,E --out /path/strip.json
"""
import argparse, json, math, os, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from pull_overture_places import OCC_BUCKETS, bucket_index, _place_name  # reuse the taxonomy

CLI = os.environ.get("OVERTURE_CLI", "overturemaps")
TH = (5.4, 97.2, 20.7, 105.8)   # S,W,N,E sanity clamp


def _phone(props):
    ph = props.get("phones")
    if isinstance(ph, list) and ph:
        return str(ph[0])[:24]
    return ""


def pull(bbox_swne, out_path):
    s, w, n, e = bbox_swne
    tmp = tempfile.NamedTemporaryFile(suffix=".geojsonseq", delete=False).name
    cmd = [CLI, "download", f"--bbox={w},{s},{e},{n}", "-f", "geojsonseq", "--type=place", "-o", tmp]
    print(f"[places] {w:.2f},{s:.2f},{e:.2f},{n:.2f} -> download", flush=True)
    subprocess.run(cmd, check=True)
    kept, seen = [], 0
    with open(tmp, encoding="utf-8") as fh:
        for line in fh:                                  # STREAM one feature at a time
            line = line.strip()
            if not line:
                continue
            try:
                f = json.loads(line)
                geom = f.get("geometry") or {}
                if geom.get("type") != "Point":
                    continue
                lng, lat = geom["coordinates"][0], geom["coordinates"][1]
                if not (TH[1] <= lng <= TH[3] and TH[0] <= lat <= TH[2]):
                    continue
                props = f.get("properties") or {}
                cats = props.get("categories") or {}
                primary = cats.get("primary") if isinstance(cats, dict) else None
                bi = bucket_index(primary)
                if bi < 0:                               # not an occupation-relevant establishment
                    continue
                seen += 1
                nm = _place_name(props)[:48]
                ph = _phone(props)
                kept.append([round(float(lng), 5), round(float(lat), 5), bi, nm, ph])
            except Exception:
                continue
    os.unlink(tmp)
    kept.sort(key=lambda r: (r[0], r[1], r[2]))
    obj = {"bbox_swne": [s, w, n, e], "count": len(kept),
           "buckets": [b[0] for b in OCC_BUCKETS],
           "places": kept}
    with open(out_path, "w", encoding="utf-8") as fo:
        json.dump(obj, fo, ensure_ascii=False, separators=(",", ":"))
    mb = os.path.getsize(out_path) / 1e6
    print(f"[places] kept {len(kept)} occupation places -> {out_path} ({mb:.1f}MB)", flush=True)
    return len(kept)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--bbox", required=True, help="S,W,N,E")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    bb = [float(x) for x in a.bbox.split(",")]
    sys.exit(0 if pull(bb, a.out) >= 0 else 1)
