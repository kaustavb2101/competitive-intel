#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pull_all_provinces.py — ONE command to pull the 3D catchment buildings for EVERY province.

WHY: the 3D scene (rayong-catchment.html?city=<slug>) renders full buildings for any province
that has platform/data/<slug>_catchment.json. Rayong + Bangkok ship with theirs; this batches
the Overture pull for all 77 provinces so the whole country gets the full "buildings around every
branch" render — instead of pulling them one slug at a time.

RUN FROM A THAI / UNRESTRICTED NETWORK (Overture's S3 is geo-blocked from the cloud sandbox):

    cd pipeline
    python pull_all_provinces.py                 # pull every province missing a catchment file
    python pull_all_provinces.py --force         # re-pull even provinces that already have one
    python pull_all_provinces.py --only chon-buri,phuket,chiang-mai   # just these slugs
    python pull_all_provinces.py --cli "C:\\path\\to\\overturemaps.exe"   # explicit CLI (Windows PATH)

It simply loops pull_overture_buildings.py --province <slug> for each province (which applies the
--max-buildings size cap, so every file stays web-sized ~≤25MB). Already-present catchment files
are SKIPPED unless --force. Deterministic per-province; no fabrication — it only pulls real Overture
building footprints. Commit the resulting platform/data/<slug>_catchment.json files.
"""
import argparse, json, os, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PULLER = os.path.join(ROOT, "pipeline", "pull_overture_buildings.py")
BBOX_JSON = os.path.join(ROOT, "platform", "data", "province_bbox.json")
DATA_DIR = os.path.join(ROOT, "platform", "data")


def _run(args_list):
    """Run the puller as a subprocess with the same Python; return exit code."""
    return subprocess.call([sys.executable, PULLER] + args_list)


def main():
    ap = argparse.ArgumentParser(description="Batch-pull Overture 3D catchments for all provinces.")
    ap.add_argument("--force", action="store_true", help="re-pull even if the catchment file exists")
    ap.add_argument("--only", help="comma-separated province slugs to pull (default: all)")
    ap.add_argument("--cli", default=None, help="Overture CLI path (passed through to the puller)")
    ap.add_argument("--max-buildings", type=int, default=None, help="override per-province cap")
    args = ap.parse_args()

    # 1) refresh province_bbox.json (network-free) so we have the full, current slug list.
    print("→ refreshing province_bbox.json (offline) ...")
    if _run(["--bbox-only"]) != 0:
        print("could not build province_bbox.json — aborting", file=sys.stderr)
        return 1
    try:
        bbox = json.load(open(BBOX_JSON, encoding="utf-8"))
    except Exception as e:
        print(f"could not read {BBOX_JSON}: {e}", file=sys.stderr)
        return 1
    slugs = sorted(bbox.get("provinces", bbox).keys()) if isinstance(bbox, dict) else []
    if args.only:
        want = {s.strip().lower() for s in args.only.split(",") if s.strip()}
        slugs = [s for s in slugs if s in want]
    if not slugs:
        print("no province slugs found", file=sys.stderr)
        return 1

    done, skipped, failed = [], [], []
    for i, slug in enumerate(slugs, 1):
        out = os.path.join(DATA_DIR, f"{slug}_catchment.json")
        if os.path.exists(out) and not args.force:
            skipped.append(slug)
            print(f"[{i}/{len(slugs)}] {slug}: catchment exists — skip (use --force to re-pull)")
            continue
        print(f"[{i}/{len(slugs)}] {slug}: pulling ...")
        call = ["--province", slug]
        if args.cli:
            call += ["--cli", args.cli]
        if args.max_buildings:
            call += ["--max-buildings", str(args.max_buildings)]
        code = _run(call)
        (done if code == 0 else failed).append(slug)
        if code != 0:
            print(f"    ! {slug} failed (exit {code}) — continuing", file=sys.stderr)

    print("\n==== batch summary ====")
    print(f"pulled : {len(done)}  {done}")
    print(f"skipped: {len(skipped)} (already had a catchment file)")
    print(f"failed : {len(failed)}  {failed}")
    print("\nCommit the new platform/data/<slug>_catchment.json files, then every province's "
          "3D scene (rayong-catchment.html?city=<slug>) renders its full buildings.")
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
