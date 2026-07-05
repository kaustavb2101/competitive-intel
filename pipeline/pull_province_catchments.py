#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pull_province_catchments.py — RESUMABLE per-province building rollout (the light alternative to
the one national tile build).

WHY
---
The single national Overture pull is ~58.9M buildings and is dominated by the dense metros
(Bangkok/Central) — an 8-hour download that can stall. This driver instead pulls buildings ONE
PROVINCE AT A TIME (the same catchment files Rayong/Chon Buri already stream from R2), so the work
is bounded, resumable, and the ~73 rural/mid provinces finish in minutes each. Only the ~4 metros
are heavy, and you can defer or skip them.

WHAT IT DOES
------------
For each province (QUICKEST FIRST — fewest branches first, dense metros last) it shells to
    pull_overture_buildings.py --province <slug>
which writes platform/data/<slug>_catchment.json (capped ~180k buildings, ~30MB, R2-servable).
It SKIPS any province whose catchment file already exists, so re-running resumes where you left
off. A province that errors is logged and skipped — the batch keeps going.

The frontend already streams <slug>_catchment.json from R2 (catchments.baseUrl) on a local miss,
so each province lights up as its file lands — no config change needed.

USAGE (on the Thai desktop / any non-blocked network)
-----------------------------------------------------
    python3 pull_province_catchments.py --list            # show the plan, pull nothing
    python3 pull_province_catchments.py --limit 10         # pull the next 10 not-yet-done provinces
    python3 pull_province_catchments.py                    # pull ALL remaining (metros last)
    python3 pull_province_catchments.py --skip-metros      # everything except the heaviest metros
    python3 pull_province_catchments.py --only chon-buri   # just one province

After a run, upload the new platform/data/<slug>_catchment.json files to R2 (same bucket as
buildings_rayong.pmtiles), e.g. with wrangler/rclone. NO fabricated data — only real Overture
footprints are pulled.
"""
import argparse, json, os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "platform", "data")
PROVINCE_BBOX = os.path.join(DATA, "province_bbox.json")
BRANCHES = os.path.join(DATA, "branches.json")
PULLER = os.path.join(HERE, "pull_overture_buildings.py")

# provinces above this branch count are treated as "heavy metros" (dense, slow download) — done
# last, and skippable with --skip-metros.
METRO_MIN_BRANCHES = 80


def _load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def plan():
    """[(n_branches, slug, th, have_file)] ordered fewest-branches-first (metros last)."""
    pb = _load(PROVINCE_BBOX)["provinces"]
    br = _load(BRANCHES)
    items = br if isinstance(br, list) else br.get("items", br)
    from collections import Counter
    cnt = Counter(b.get("v", "") for b in items)
    rows = []
    for slug, meta in pb.items():
        n = cnt.get(meta.get("th", ""), 0)
        have = os.path.exists(os.path.join(DATA, slug + "_catchment.json"))
        rows.append((n, slug, meta.get("th", ""), have))
    rows.sort(key=lambda r: (r[0], r[1]))
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--list", action="store_true", help="print the plan and exit (pull nothing)")
    ap.add_argument("--limit", type=int, default=0, help="pull at most N not-yet-done provinces this run")
    ap.add_argument("--skip-metros", action="store_true",
                    help="skip the heaviest metros (>= %d branches)" % METRO_MIN_BRANCHES)
    ap.add_argument("--only", default=None, help="pull just this one province slug")
    ap.add_argument("--force", action="store_true", help="re-pull even if the catchment file exists")
    ap.add_argument("--cli", default="overturemaps", help="Overture CLI (passed through to the puller)")
    args = ap.parse_args()

    rows = plan()
    if args.only:
        rows = [r for r in rows if r[1] == args.only.strip().lower()]
        if not rows:
            sys.exit("unknown province slug %r (see province_bbox.json)" % args.only)

    todo = []
    for n, slug, th, have in rows:
        if have and not args.force:
            continue
        if args.skip_metros and n >= METRO_MIN_BRANCHES:
            continue
        todo.append((n, slug, th))

    done_ct = sum(1 for r in rows if r[3])
    print("Per-province building rollout — %d/%d already have a local catchment." % (done_ct, len(rows)))
    if args.list or not todo:
        print("\nplan (quickest first; metros last):")
        for n, slug, th, have in rows:
            mark = "done" if have else ("METRO" if n >= METRO_MIN_BRANCHES else "todo")
            print("  [%-5s] %-20s %3d branches  %s" % (mark, slug, n, th))
        if not todo and not args.list:
            print("\nNothing to pull — every province already has a catchment. (Use --force to re-pull.)")
        return

    if args.limit:
        todo = todo[:args.limit]
    print("\nwill pull %d province(s) this run (Ctrl-C to stop; re-run to resume):" % len(todo))
    for n, slug, th in todo:
        print("   %-20s %3d branches  %s" % (slug, n, th))
    print()

    ok, fail = [], []
    for i, (n, slug, th) in enumerate(todo, 1):
        print("=" * 64)
        print("[%d/%d] pulling %s (%s, %d branches) ..." % (i, len(todo), slug, th, n))
        cmd = [sys.executable, PULLER, "--province", slug, "--cli", args.cli]
        rc = subprocess.run(cmd, cwd=HERE).returncode
        if rc == 0 and os.path.exists(os.path.join(DATA, slug + "_catchment.json")):
            ok.append(slug)
        else:
            fail.append(slug)
            print("  ! %s failed (exit %d) — skipping, will retry on a later run." % (slug, rc),
                  file=sys.stderr)

    print("=" * 64)
    print("done this run: %d pulled, %d failed." % (len(ok), len(fail)))
    if ok:
        print("  upload these new files to R2 (same bucket as buildings_rayong.pmtiles):")
        for slug in ok:
            print("    platform/data/%s_catchment.json" % slug)
    if fail:
        print("  failed (re-run to retry): " + ", ".join(fail))


if __name__ == "__main__":
    main()
