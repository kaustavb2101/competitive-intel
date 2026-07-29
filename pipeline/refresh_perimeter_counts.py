#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
refresh_perimeter_counts.py — recompute per-branch 10km building counts from the in-repo
77-province Overture catchments (the 2026-07-20 province-wide pull; still CAPPED at 180k
buildings/province by pull_overture_buildings.py --max-buildings — most large provinces hit the
cap exactly, so dense-core counts are FLOORS, not totals. Upgrade vs the 2026-07-02 counts:
Bangkok/Rayong previously carried city-core-only files; now every province is province-wide).

  in : platform/data/<slug>_catchment.json  x77   (full-province, slim-canonical)
       platform/data/branches.json                (defines counts[] index alignment)
       platform/data/provinces/index.json         (Thai name -> slug join)
  out: source-data/perimeter_counts.json          {meta, counts:[int x n_branches]}

Method parity with the original perimeter audit: per province, bin building centroids (cx,cy)
onto a 0.1-degree grid, then count buildings within 10km (equirectangular) of each branch;
branch -> province by Thai name join. Border branches only see their own province's buildings
(same limitation as the original — kept for comparability).

Downstream: build_branch_density.py projects this into platform/data/branch_density.json.
"""
import collections
import json
import math
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "platform", "data")
OUT = os.path.join(ROOT, "source-data", "perimeter_counts.json")
R_KM = 10.0

from lib.fingerprint import branches_fingerprint  # noqa: E402  (pipeline-local helper)


def bucket(n):
    if n >= 1000: return "rich_1000plus"
    if n >= 200: return "good_200_999"
    if n >= 50: return "thin_50_199"
    if n >= 1: return "sparse_1_49"
    return "empty_0"


def main():
    branches = json.load(open(os.path.join(DATA, "branches.json"), encoding="utf-8"))
    idx = json.load(open(os.path.join(DATA, "provinces", "index.json"), encoding="utf-8"))
    provs = idx if isinstance(idx, list) else (idx.get("provinces") or [])
    th2slug = {}
    for p in provs:
        th = p.get("th") or p.get("name_th") or p.get("name")
        if th:
            th2slug[th] = p.get("slug")

    by_slug = collections.defaultdict(list)   # slug -> [(i, lat, lng)]
    missing = collections.Counter()
    for i, b in enumerate(branches):
        slug = th2slug.get(b.get("v"))
        if slug:
            by_slug[slug].append((i, b["y"], b["x"]))
        else:
            missing[b.get("v")] += 1

    counts = [0] * len(branches)
    for slug, blist in sorted(by_slug.items()):
        path = os.path.join(DATA, "%s_catchment.json" % slug)
        if not os.path.exists(path):
            continue
        d = json.load(open(path, encoding="utf-8"))
        grid = collections.defaultdict(list)
        for bd in d.get("buildings", []):
            cx, cy = bd.get("cx"), bd.get("cy")
            if cx is None or cy is None:
                continue
            grid[(int(cx * 10), int(cy * 10))].append((cx, cy))
        for i, lat, lng in blist:
            lat_r = math.radians(lat)
            dlat = R_KM / 111.32
            dlng = R_KM / (111.32 * math.cos(lat_r))
            n = 0
            for gx in range(int((lng - dlng) * 10), int((lng + dlng) * 10) + 1):
                for gy in range(int((lat - dlat) * 10), int((lat + dlat) * 10) + 1):
                    for cx, cy in grid.get((gx, gy), ()):
                        dx = (cx - lng) * 111.32 * math.cos(lat_r)
                        dy = (cy - lat) * 111.32
                        if dx * dx + dy * dy <= R_KM * R_KM:
                            n += 1
            counts[i] = n
        print("  %-24s %6d buildings-> %d branches" % (slug, len(d.get("buildings", [])), len(blist)), flush=True)

    tally = collections.Counter(bucket(c) for c in counts)
    obj = {"meta": {
        "generated_by": "pipeline/refresh_perimeter_counts.py — counts from the 77 in-repo "
                        "province-wide Overture catchments (2026-07-20 pull, capped 180k/province)",
        "label": "MEASURED — building count within 10km (equirect) of each branch, from the "
                 "province-wide catchment pulls (capped 180k buildings/province; most large "
                 "provinces hit the cap, so counts near dense cores are FLOORS, not totals). "
                 "A zero means the capped catchment has no buildings there; border branches "
                 "only see their own province's buildings.",
        "method": "per province: bin catchment building centroids into 0.1-degree grid; count "
                  "within 10km of each branch; branch->province by Thai name join",
        "n_branches": len(branches),
        "branches_fingerprint": branches_fingerprint(branches),
        "buckets": {k: tally.get(k, 0) for k in
                    ("rich_1000plus", "good_200_999", "thin_50_199", "sparse_1_49", "empty_0")},
        "unjoined_provinces": dict(missing),
        "index_note": "counts[i] is index-aligned to platform/data/branches.json record i",
    }, "counts": counts}
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False, separators=(",", ":")))
    print("wrote %s — %d branches, buckets %s, unjoined %s"
          % (OUT, len(branches), obj["meta"]["buckets"], dict(missing) or "none"))


if __name__ == "__main__":
    main()
