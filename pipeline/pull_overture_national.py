#!/usr/bin/env python3
"""
pull_overture_national.py — TILED, RESUMABLE country-wide Overture Places pull.

WHY THIS EXISTS
---------------
`pull_overture_places.py --preset national` does ONE giant overturemaps download for the
whole Thailand bbox. That is too slow to finish in one sitting, and a Ctrl-C anywhere in the
middle throws away everything pulled so far. This wrapper makes the national harvest survive
interruptions:

  * It TILES the Thailand bbox into ~1.0-degree cells (configurable --tile-deg).
  * Each tile is pulled independently into source-data/.overture_tiles/<tile>.geojsonseq,
    written ATOMICALLY (temp file then os.replace) so an interrupted tile is never recorded
    as complete — on rerun it is simply re-pulled.
  * A manifest.json in the state dir records which tiles are complete. Rerunning SKIPS the
    completed tiles, so you can stop and restart as many times as you like until done.
  * When every tile is complete, it MERGES all per-tile geojsonseq files through the SAME
    convert() + harvest_competitors() functions that pull_overture_places.py uses, and writes
    byte-identical source-data/overture_places.json + platform/data/competitors_overture.json.

It imports and reuses pull_overture_places.py — the occupation-bucket logic, the geojsonseq
loader, the converter and the competitor harvester are NOT duplicated here.

THE WORKFLOW (owner, on a Thai/normal connection)
-------------------------------------------------
    cd pipeline
    python3 pull_overture_national.py            # pulls incomplete tiles; merges when all done
    # ...if it dies / you Ctrl-C, just run it again — it resumes:
    python3 pull_overture_national.py
    python3 pull_overture_national.py --status   # how many tiles done / remaining
    # rerun until --status shows 0 remaining, then:
    python3 build_occupations.py                 # per-branch 10km occupation rollup
    python3 build_amphoe_occupations.py          # per-district occupation rollup

FLAGS
  --tile-deg N    grid cell size in degrees (default 1.0)
  --merge-only    skip downloading; just merge whatever tiles are already complete
  --status        print tiles done / remaining and exit
  --bbox S,W,N,E  override the national bbox (same S,W,N,E order as pull_overture_places.py)
  --cli NAME      Overture CLI executable (default: overturemaps)
  --state-dir P   override the state dir (default ../source-data/.overture_tiles)
  --out PATH      overture_places.json output (default ../source-data/overture_places.json)
  --keep-tiles    after a successful merge, do NOT prompt to clean the state dir (it is kept
                  by default anyway; this flag exists for symmetry / future cleanup hooks)

The state dir (source-data/.overture_tiles/) is gitignored — never commit synthetic geo or
the tile cache.
"""
import argparse
import json
import math
import os
import sys
import tempfile

import pull_overture_places as base

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DEFAULT_STATE_DIR = os.path.join(ROOT, "source-data", ".overture_tiles")
DEFAULT_OUT = base.DEFAULT_OUT
NATIONAL_BBOX = base.NATIONAL_BBOX  # "5.5,97.3,20.5,105.7" (S,W,N,E)
MANIFEST_NAME = "manifest.json"


# ---------------------------------------------------------------------------
# Tiling math
# ---------------------------------------------------------------------------
def tile_grid(bbox, tile_deg):
    """Split a friendly S,W,N,E bbox into a deterministic list of sub-tiles.

    Returns a list of dicts {key, bbox} where bbox is also S,W,N,E (so each tile can be
    fed straight to base.download_seq). Tiles are clamped to the outer bbox, so the last
    row/column may be narrower than tile_deg. Ordered south->north, west->east for stable,
    resumable iteration. `key` is a stable id derived from the tile's SW corner.
    """
    s, w, n, e = base._bbox_parts(bbox)
    if n <= s or e <= w:
        raise ValueError(f"--bbox must have N>S and E>W (got S={s} W={w} N={n} E={e})")
    if tile_deg <= 0:
        raise ValueError("--tile-deg must be > 0")
    ny = int(math.ceil((n - s) / tile_deg))
    nx = int(math.ceil((e - w) / tile_deg))
    tiles = []
    for j in range(ny):
        ts = s + j * tile_deg
        tn = min(ts + tile_deg, n)
        for i in range(nx):
            tw = w + i * tile_deg
            te = min(tw + tile_deg, e)
            key = _tile_key(ts, tw)
            tiles.append({"key": key, "bbox": f"{ts},{tw},{tn},{te}"})
    return tiles


def _tile_key(s, w):
    """Stable filesystem-safe id from a tile's SW corner (3 decimals, sign-tagged)."""
    def tag(v):
        sign = "n" if v < 0 else "p"
        return f"{sign}{abs(v):07.3f}".replace(".", "_")
    return f"t_{tag(s)}_{tag(w)}"


def tile_path(state_dir, key):
    return os.path.join(state_dir, key + ".geojsonseq")


# ---------------------------------------------------------------------------
# Manifest (resume bookkeeping)
# ---------------------------------------------------------------------------
def load_manifest(state_dir):
    path = os.path.join(state_dir, MANIFEST_NAME)
    if not os.path.exists(path):
        return {"bbox": None, "tile_deg": None, "complete": {}}
    try:
        with open(path, encoding="utf-8") as f:
            m = json.load(f)
    except (json.JSONDecodeError, OSError):
        return {"bbox": None, "tile_deg": None, "complete": {}}
    m.setdefault("complete", {})
    return m


def save_manifest(state_dir, manifest):
    """Atomic manifest write (temp + os.replace) so a crash never leaves it half-written."""
    os.makedirs(state_dir, exist_ok=True)
    path = os.path.join(state_dir, MANIFEST_NAME)
    fd, tmp = tempfile.mkstemp(prefix=".manifest_", suffix=".tmp", dir=state_dir)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2, sort_keys=True)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def _tile_complete(manifest, state_dir, key):
    """A tile counts as complete only if the manifest says so AND its file still exists."""
    return key in manifest.get("complete", {}) and os.path.exists(tile_path(state_dir, key))


# ---------------------------------------------------------------------------
# Download (one tile at a time, atomic)
# ---------------------------------------------------------------------------
def download_tile(cli, tile, state_dir):
    """Pull one tile into the state dir ATOMICALLY: download to a temp file, then os.replace.
    If the download is interrupted the temp file is discarded, so the tile is never recorded
    as complete and gets re-pulled on the next run."""
    os.makedirs(state_dir, exist_ok=True)
    dest = tile_path(state_dir, tile["key"])
    fd, tmp = tempfile.mkstemp(prefix="." + tile["key"] + "_", suffix=".tmp", dir=state_dir)
    os.close(fd)
    try:
        base.download_seq(cli, tile["bbox"], tmp)
        os.replace(tmp, dest)  # atomic publish
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    return dest


# ---------------------------------------------------------------------------
# Merge (union all complete tiles -> identical-shape outputs)
# ---------------------------------------------------------------------------
def merge(state_dir, tiles, bbox, out_path):
    """Load every complete tile, run base.convert() + base.harvest_competitors() over the
    union, and write source-data/overture_places.json + competitors_overture.json with the
    EXACT shapes pull_overture_places.py produces (so build_occupations.py is unaffected)."""
    feats = []
    used = 0
    for t in tiles:
        p = tile_path(state_dir, t["key"])
        if not os.path.exists(p):
            continue
        feats.extend(base.load_features(p))
        used += 1
    if used == 0:
        sys.exit("merge: no completed tiles found in the state dir — nothing to merge.")

    # Dedup point features by Overture id (a feature can appear in two tiles if it sits on a
    # shared border). convert()/harvest both sort deterministically afterwards, so the merged
    # output is byte-stable regardless of tile order.
    deduped, seen = [], set()
    for ft in feats:
        if not isinstance(ft, dict):
            continue
        fid = ft.get("id")
        if fid is None:
            props = ft.get("properties") or {}
            fid = props.get("id")
        if fid is not None:
            if fid in seen:
                continue
            seen.add(fid)
        deduped.append(ft)

    print(f"merge: {used} tile(s), {len(feats)} raw features -> {len(deduped)} unique",
          file=sys.stderr)

    places, stats = base.convert(deduped)
    if not places:
        sys.exit("merge: 0 places produced from the completed tiles — check the pulls.")

    bpath = os.path.join(ROOT, "platform", "data", "branches.json")
    branches = json.load(open(bpath, encoding="utf-8")) if os.path.exists(bpath) else []
    competitors = base.harvest_competitors(deduped, branches)

    n = len(places)
    classified = n - stats["other"]
    pct = 100 * classified // n
    print(f"places: {n}  |  classified {classified} ({pct}%)  other {stats['other']} ({100 - pct}%)")
    for key, _label, _kw in base.OCC_BUCKETS:
        c = stats["by_bucket"].get(key, 0)
        if c:
            print(f"  {key:13s} {c}")

    out = {
        "meta": {
            "source": "Overture Maps Places — measured establishment points (a sample/lower bound, not a registry)",
            "bbox": bbox,
            "count": n,
            "radius_hint_km": 10,
            "generated_with": "pull_overture_national.py",
        },
        "buckets": [{"key": k, "label": lbl} for (k, lbl, _kw) in base.OCC_BUCKETS],
        "places": places,
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    print(f"wrote {out_path}  ({os.path.getsize(out_path) / 1024.0:.1f} KB)")

    by_brand = {}
    for it in competitors:
        by_brand[it["brand"]] = by_brand.get(it["brand"], 0) + 1
    comp_out = {
        "meta": {"source": "Overture Maps Places — competitor lenders by brand-name match "
                           "(a sample/lower bound, not a registry)",
                 "bbox": bbox, "count": len(competitors),
                 "generated_with": "pull_overture_national.py"},
        "brands": by_brand,
        "items": competitors,
    }
    cpath = os.path.join(ROOT, "platform", "data", "competitors_overture.json")
    with open(cpath, "w", encoding="utf-8") as f:
        json.dump(comp_out, f, ensure_ascii=False, separators=(",", ":"))
    print(f"wrote {cpath}: {len(competitors)} competitor branches  {by_brand}")
    print("NEXT: python3 build_occupations.py && python3 build_amphoe_occupations.py")


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------
def print_status(state_dir, tiles, manifest):
    done = [t for t in tiles if _tile_complete(manifest, state_dir, t["key"])]
    remaining = [t for t in tiles if not _tile_complete(manifest, state_dir, t["key"])]
    print(f"tiles: {len(tiles)} total | {len(done)} done | {len(remaining)} remaining")
    if remaining:
        print("remaining tile bboxes (S,W,N,E):")
        for t in remaining:
            print(f"  {t['key']}  {t['bbox']}")
    return len(remaining)


# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tile-deg", type=float, default=1.0, help="grid cell size in degrees (default 1.0)")
    ap.add_argument("--bbox", default=NATIONAL_BBOX, help="S,W,N,E (default whole Thailand)")
    ap.add_argument("--cli", default="overturemaps", help="Overture CLI executable name")
    ap.add_argument("--state-dir", default=DEFAULT_STATE_DIR)
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--merge-only", action="store_true", help="skip downloading; merge completed tiles")
    ap.add_argument("--status", action="store_true", help="print tiles done/remaining and exit")
    ap.add_argument("--keep-tiles", action="store_true", help="keep the state dir after merge (default)")
    args = ap.parse_args()

    tiles = tile_grid(args.bbox, args.tile_deg)
    manifest = load_manifest(args.state_dir)
    # If the grid definition changed since the last run, the old per-tile completions no longer
    # line up — start a fresh manifest (the old tile files stay on disk, harmless and ignored).
    if manifest.get("bbox") != args.bbox or manifest.get("tile_deg") != args.tile_deg:
        if manifest.get("complete"):
            print("note: bbox/tile-deg changed since last run — resetting completion manifest "
                  "(old tile files are left in place but ignored).", file=sys.stderr)
        manifest = {"bbox": args.bbox, "tile_deg": args.tile_deg, "complete": {}}

    if args.status:
        print_status(args.state_dir, tiles, manifest)
        return

    if args.merge_only:
        merge(args.state_dir, tiles, args.bbox, args.out)
        return

    remaining = [t for t in tiles if not _tile_complete(manifest, args.state_dir, t["key"])]
    print(f"national pull: {len(tiles)} tiles @ {args.tile_deg}deg | "
          f"{len(tiles) - len(remaining)} already done | {len(remaining)} to pull",
          file=sys.stderr)

    for idx, t in enumerate(remaining, 1):
        print(f"[{idx}/{len(remaining)}] tile {t['key']} bbox {t['bbox']}", file=sys.stderr)
        download_tile(args.cli, t, args.state_dir)
        manifest["complete"][t["key"]] = {"bbox": t["bbox"]}
        save_manifest(args.state_dir, manifest)  # persist after EVERY tile so we can resume

    still = [t for t in tiles if not _tile_complete(manifest, args.state_dir, t["key"])]
    if still:
        print(f"{len(still)} tile(s) still incomplete — rerun to finish, then merge.",
              file=sys.stderr)
        sys.exit(1)

    print("all tiles complete — merging.", file=sys.stderr)
    merge(args.state_dir, tiles, args.bbox, args.out)


if __name__ == "__main__":
    main()
