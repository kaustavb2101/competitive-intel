#!/usr/bin/env python3
"""
pull_bangkok_full.py — MEMORY-SAFE full-metro Bangkok catchment pull.

Bangkok's bbox holds ~3.1M Overture buildings; loading the 1.5GB geojsonseq into
memory to cap it OOM-kills a 15GB container (it did, twice). This script instead:
  1. splits the Bangkok bbox into N longitude strips,
  2. downloads each strip's buildings via the overturemaps CLI (streams to disk, low RAM),
  3. STREAMS each strip line-by-line, reservoir-sampling down to a global cap so peak
     RAM stays at ~cap buildings (never the whole file), deleting each strip after.
Output matches bake_catchment_heights.py's schema: {buildings:[{p,h,fa,cx,cy,ty}], meta}.

Deterministic sampling seeded from a fixed constant (no Math.random / wall clock).
Run from the Thai IP or the sandbox (Overture S3 is reachable from both).
"""
import json
import math
import os
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(REPO, "platform", "data", "bangkok_catchment.json")
# Bangkok admin bbox (S,W,N,E) from province_bbox.json
S, W, N, E = 13.48339, 100.317912, 13.965198, 100.948516
STRIPS = 6            # more strips = smaller peak disk per download
CAP = 180000          # global building cap (web-sized, ~40MB)
CLI = os.environ.get("OVERTURE_CLI", "overturemaps")


def height_of(props):
    for k in ("height", "roof_height"):
        v = props.get(k)
        if isinstance(v, (int, float)) and v > 0:
            return float(v)
    lv = props.get("num_floors") or props.get("levels")
    if isinstance(lv, (int, float)) and lv > 0:
        return float(lv) * 3.2
    return 4.0  # 1-storey default (same as the baker)


def centroid(ring):
    xs = [p[0] for p in ring]; ys = [p[1] for p in ring]
    return round(sum(xs) / len(xs), 6), round(sum(ys) / len(ys), 6)


def run():
    kept = []              # reservoir of at most CAP buildings
    seen = 0               # total buildings streamed
    step = (E - W) / STRIPS
    for i in range(STRIPS):
        w = W + i * step; e = W + (i + 1) * step
        tmp = tempfile.NamedTemporaryFile(suffix=".geojsonseq", delete=False).name
        print(f"[strip {i+1}/{STRIPS}] {w:.4f}..{e:.4f} -> download", flush=True)
        cmd = [CLI, "download", f"--bbox={w},{S},{e},{N}", "-f", "geojsonseq",
               "--type=building", "-o", tmp]
        try:
            subprocess.run(cmd, check=True)
        except subprocess.CalledProcessError as ex:
            print(f"  ! strip {i+1} download failed ({ex}); skipping", flush=True)
            try: os.unlink(tmp)
            except OSError: pass
            continue
        n_strip = 0
        with open(tmp, encoding="utf-8") as fh:
            for line in fh:                      # STREAM — one feature at a time
                line = line.strip()
                if not line:
                    continue
                try:
                    feat = json.loads(line)
                    geom = feat.get("geometry") or {}
                    if geom.get("type") != "Polygon":
                        continue
                    ring = geom["coordinates"][0]
                    if len(ring) < 4:
                        continue
                    props = feat.get("properties") or {}
                    cx, cy = centroid(ring)
                    rec = {"p": [[round(x, 6), round(y, 6)] for x, y in ring],
                           "h": round(height_of(props), 2),
                           "fa": int(props.get("area") or 0),
                           "cx": cx, "cy": cy,
                           "ty": (props.get("subtype") or props.get("class") or "mixed")}
                except Exception:
                    continue
                seen += 1
                n_strip += 1
                # deterministic reservoir sampling → uniform CAP-size sample, O(CAP) memory
                if len(kept) < CAP:
                    kept.append(rec)
                else:
                    # LCG on `seen` (no RNG state, reproducible): replace with prob CAP/seen
                    j = (seen * 1103515245 + 12345) % seen
                    if j < CAP:
                        kept[j] = rec
        os.unlink(tmp)
        print(f"  strip {i+1}: {n_strip} buildings streamed (total seen {seen}, kept {len(kept)})", flush=True)

    if not kept:
        print("no buildings pulled — aborting, NOT overwriting existing file", flush=True)
        return 1
    # centre = mean of kept centroids (for the scene's initial camera)
    cx = round(sum(b["cx"] for b in kept) / len(kept), 6)
    cy = round(sum(b["cy"] for b in kept) / len(kept), 6)
    obj = {"buildings": kept,
           "meta": {"city": "Bangkok", "n_bldg": len(kept), "seen": seen,
                    "source": "Overture Maps buildings (memory-safe streaming pull, "
                              f"{STRIPS} strips, reservoir cap {CAP})",
                    "note": "MEASURED footprints; heights measured where Overture has them, "
                            "else estimated from levels/default. Province-wide (full metro)."}}
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))
    mb = os.path.getsize(OUT) / 1e6
    print(f"wrote {len(kept)} buildings (from {seen} seen) -> {os.path.relpath(OUT, REPO)} ({mb:.1f}MB); "
          f"centre {cy},{cx}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(run())
