#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""plan_overture_matrix.py — compute the GitHub Actions matrix for the resilient Overture pull.

The Overture 3D catchment pull used to run ALL provinces in one long job. GitHub-hosted runners
get preempted ("The runner has received a shutdown signal") on long jobs, and because the commit +
PR step only runs at the very end, a mid-run preemption threw away EVERY province pulled so far.

Fix: fan the work out across many SHORT matrix jobs (a few provinces each). Each job pulls its chunk
and uploads its catchment files as an artifact, so a preempted runner only loses its own chunk — every
other chunk's artifact survives and a final collect job commits them all in one PR.

This script decides which provinces to pull and splits them into chunks. It writes two GITHUB_OUTPUT
values: `matrix` (JSON array of {idx, slugs} objects for strategy.matrix) and `count` (int).

Inputs (env):
  PROVINCES   comma-separated slugs (used when not an all/scheduled run)
  PULL_ALL    "true" => pull every province still MISSING a committed catchment
  EVENT       github.event_name; "schedule" is treated as PULL_ALL
  CHUNK_SIZE  provinces per matrix job (default 3 — small enough to finish before preemption)

Deterministic + network-free: reads the committed platform/data/province_bbox.json for the full
slug list and platform/data/*_catchment.json for what already exists.
"""
import json, os, sys, glob

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA = os.path.join(ROOT, "platform", "data")
BBOX = os.path.join(DATA, "province_bbox.json")


def all_slugs():
    d = json.load(open(BBOX, encoding="utf-8"))
    provs = d.get("provinces", d)
    return sorted(provs.keys())


def existing_catchments():
    return {os.path.basename(p)[: -len("_catchment.json")]
            for p in glob.glob(os.path.join(DATA, "*_catchment.json"))}


def main():
    event = os.environ.get("EVENT", "")
    pull_all = os.environ.get("PULL_ALL", "").strip().lower() == "true" or event == "schedule"
    try:
        chunk_size = max(1, int(os.environ.get("CHUNK_SIZE", "3") or "3"))
    except ValueError:
        chunk_size = 3

    slugs = all_slugs()
    valid = set(slugs)

    if pull_all:
        have = existing_catchments()
        want = [s for s in slugs if s not in have]
    else:
        raw = os.environ.get("PROVINCES", "") or ""
        req = [s.strip().lower() for s in raw.split(",") if s.strip()]
        # keep only real slugs, drop dupes, preserve request order
        seen, want = set(), []
        for s in req:
            if s in valid and s not in seen:
                seen.add(s)
                want.append(s)
        bad = [s for s in req if s not in valid]
        if bad:
            print(f"::warning::ignoring unknown province slugs: {','.join(bad)}", file=sys.stderr)

    chunks = [want[i:i + chunk_size] for i in range(0, len(want), chunk_size)]
    matrix = [{"idx": i, "slugs": ",".join(c)} for i, c in enumerate(chunks)]

    print(f"planning {len(want)} province(s) in {len(chunks)} chunk(s) of <= {chunk_size} "
          f"(all={pull_all}, event={event or 'dispatch'})", file=sys.stderr)
    for m in matrix:
        print(f"  chunk {m['idx']}: {m['slugs']}", file=sys.stderr)

    out = os.environ.get("GITHUB_OUTPUT")
    payload = json.dumps(matrix, separators=(",", ":"))
    if out:
        with open(out, "a", encoding="utf-8") as f:
            f.write(f"matrix={payload}\n")
            f.write(f"count={len(want)}\n")
    else:
        # local/dry-run
        print(payload)
        print(f"count={len(want)}")


if __name__ == "__main__":
    main()
