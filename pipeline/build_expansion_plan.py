#!/usr/bin/env python3
"""
build_expansion_plan.py — SEQUENCED Road-to-3,000 placement plan (objective #2)
===============================================================================
DORMANT — The network is CONSOLIDATING (not expanding). The output
(platform/data/expansion_plan.json) is generated but NOT rendered by any page
in the platform. The script and file are kept for reversibility; re-surface by
wiring expansion_plan.json into app.js when/if the strategic direction changes.
See CLAUDE.md for context.
-------------------------------------------------------------------------------
The Acquisition tab's "Road to 3,000" splits the ~985 net-new branches across
5 regions proportional to workforce headroom — useful, but it never says WHERE
or IN WHAT ORDER. This builder produces that missing decision product: an
ordered list of every net-new branch placement at DISTRICT (amphoe) level.

Method — greedy divisor allocation (the D'Hondt / Jefferson method used to
apportion parliamentary seats), extended with cross-district cannibalization:

  For district i with risk-adjusted demand D_i and effective outlet count e_i,
  the marginal value of the NEXT branch there is
      v_i = D_i / (1 + e_i)
  where
      D_i = demand_i x (1 - RISK_ALPHA x risk_proxy_i/100)
      e_i = own_i + placed_i + NB_W x SUM_j w_ij x (own_j + placed_j)
      w_ij = max(0, 1 - dist_km(i,j)/NB_KM)   (centroid distance)
  Each of the net-new branches is placed, one at a time, in the district with
  the highest current v_i; placements in a district (and, damped, in its
  neighbors) shrink every later v there — diminishing returns and
  cannibalization fall out of the divisor naturally. For the no-neighbor case
  this greedy IS the provably optimal allocation for total captured
  demand-per-outlet (classic divisor-method result).

Provenance — the plan is an ESTIMATED PLANNING SEQUENCE built from:
  demand_i      MEASURED-derived  amphoe.json demand leg (OSM footfall + workers
                                  + vehicles), 0-100.
  risk_proxy_i  ESTIMATED         amphoe.json district risk proxy, 0-100.
  own_i         MEASURED          AutoX branches PIP-joined per district.
  net_new       MEASURED          3,000 target minus branches.json count.
It is NOT a committed branch plan; confirm every site with a local survey.

Deterministic + network-free. Ties broken by district id (stable). No wall
clock anywhere. --check reproduces byte-for-byte.

Output: platform/data/expansion_plan.json
  { meta:{...}, sequence:[first SEQ_N individual placements],
    by_amphoe:[every district getting >=1 branch], by_region:[...], by_province:[...] }
"""
import argparse
import heapq
import json
import math
import os

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AMPHOE = os.path.join(REPO, "platform", "data", "amphoe.json")
BRANCHES = os.path.join(REPO, "platform", "data", "branches.json")
OUT = os.path.join(REPO, "platform", "data", "expansion_plan.json")

TARGET = 3000     # legacy planning target (script dormant; network is consolidating)
RISK_ALPHA = 0.25 # demand discount at risk_proxy=100 (0.25 -> a max-risk district loses 1/4 of its pull)
NB_KM = 15.0      # cannibalization radius between district centroids
NB_W = 0.35       # a fully-adjacent neighbor outlet counts as 0.35 of an own-district outlet
MAX_ADD = 8       # sanity cap of net-new branches per district
SEQ_N = 150       # individual placements published in `sequence` (full plan is in by_amphoe)

KM_PER_DEG_LAT = 110.574


def build():
    am = json.load(open(AMPHOE, encoding="utf-8"))
    n_branches = len(json.load(open(BRANCHES, encoding="utf-8")))
    net_new = TARGET - n_branches

    dist, skipped = [], 0
    for r in am["amphoe"]:
        demand = float(r.get("demand") or 0.0)
        if demand <= 0:
            skipped += 1
            continue
        risk = float(r.get("risk_proxy") or 0.0)
        dist.append({
            "id": r["id"],
            "name": r.get("name_en") or r.get("name"),
            "prov": r.get("province_th"),
            "region": r.get("region"),
            "cx": float(r["cx"]), "cy": float(r["cy"]),
            "own": int(r.get("branches") or 0),
            "D": demand * (1.0 - RISK_ALPHA * risk / 100.0),
            "demand": demand, "risk": risk, "ws": r.get("whitespace"),
            "placed": 0, "first_rank": None, "first_v": None,
        })

    # neighbor pairs within NB_KM (equirectangular approx is fine at 15 km)
    n = len(dist)
    nbrs = [[] for _ in range(n)]
    for i in range(n):
        ci, yi = dist[i]["cx"], dist[i]["cy"]
        for j in range(i + 1, n):
            dy = (yi - dist[j]["cy"]) * KM_PER_DEG_LAT
            if abs(dy) > NB_KM:
                continue
            km_lng = 111.320 * math.cos(math.radians((yi + dist[j]["cy"]) / 2.0))
            dd = math.hypot((ci - dist[j]["cx"]) * km_lng, dy)
            if dd >= NB_KM:
                continue
            w = 1.0 - dd / NB_KM
            nbrs[i].append((j, w))
            nbrs[j].append((i, w))

    def marginal(i):
        e = dist[i]["own"] + dist[i]["placed"]
        for j, w in nbrs[i]:
            e += NB_W * w * (dist[j]["own"] + dist[j]["placed"])
        return dist[i]["D"] / (1.0 + e)

    # lazy max-heap with version counters; ties broken by district id (stable)
    ver = [0] * n
    heap = [(-marginal(i), dist[i]["id"], i, 0) for i in range(n)]
    heapq.heapify(heap)

    seq = []
    while len(seq) < net_new and heap:
        neg_v, _id, i, v = heapq.heappop(heap)
        if v != ver[i] or dist[i]["placed"] >= MAX_ADD:
            continue
        d = dist[i]
        d["placed"] += 1
        if d["first_rank"] is None:
            d["first_rank"] = len(seq) + 1
            d["first_v"] = -neg_v
        seq.append({
            "rank": len(seq) + 1, "id": d["id"], "name": d["name"],
            "prov": d["prov"], "region": d["region"],
            "k": d["own"] + d["placed"],       # this becomes the k-th outlet in the district
            "v": round(-neg_v, 2),
        })
        for j in [i] + [jj for jj, _ in nbrs[i]]:
            ver[j] += 1
            if dist[j]["placed"] < MAX_ADD:
                heapq.heappush(heap, (-marginal(j), dist[j]["id"], j, ver[j]))

    by_amphoe = [{
        "id": d["id"], "name": d["name"], "prov": d["prov"], "region": d["region"],
        "now": d["own"], "add": d["placed"], "first_rank": d["first_rank"],
        "first_v": round(d["first_v"], 2), "demand": d["demand"],
        "risk": d["risk"], "ws": d["ws"], "cx": d["cx"], "cy": d["cy"],
    } for d in dist if d["placed"] > 0]
    by_amphoe.sort(key=lambda r: (-r["add"], r["first_rank"]))

    def rollup(key):
        agg = {}
        for r in by_amphoe:
            o = agg.setdefault(r[key], {"name": r[key], "add": 0, "districts": 0})
            o["add"] += r["add"]
            o["districts"] += 1
        return sorted(agg.values(), key=lambda o: (-o["add"], o["name"]))

    meta = {
        "generated_by": "pipeline/build_expansion_plan.py",
        "provenance": "ESTIMATED planning sequence over MEASURED inputs — demand (amphoe.json demand leg, OSM+workers+vehicles), own branches (PIP-joined, measured), risk_proxy (estimated). NOT a committed branch plan; confirm every site with a local survey.",
        "method": ("greedy divisor allocation (D'Hondt/Jefferson): each of the net-new branches goes, one at a time, "
                   "to the district with the highest marginal value v = risk-adjusted demand / (1 + effective outlets). "
                   "Effective outlets include distance-damped neighbor outlets, so nearby placements cannibalize each other."),
        "formulas": {
            "v_i": "D_i / (1 + e_i)",
            "D_i": f"demand_i * (1 - {RISK_ALPHA} * risk_proxy_i/100)",
            "e_i": f"own_i + placed_i + {NB_W} * sum_j w_ij * (own_j + placed_j)",
            "w_ij": f"max(0, 1 - centroid_km(i,j)/{NB_KM})",
        },
        "params": {"target": TARGET, "branches_now": n_branches, "net_new": net_new,
                   "risk_alpha": RISK_ALPHA, "nb_km": NB_KM, "nb_w": NB_W,
                   "max_add_per_district": MAX_ADD, "seq_published": SEQ_N},
        "n_districts_eligible": n,
        "n_districts_skipped_zero_demand": skipped,
        "n_districts_receiving": len(by_amphoe),
        "n_placed": len(seq),
        "id_note": "id is the th_amphoe.geojson shapeID — identical key to amphoe.json amphoe[].id.",
        "sorted_by": "sequence: placement order; by_amphoe: add desc then first_rank asc",
    }
    return {"meta": meta, "sequence": seq[:SEQ_N], "by_amphoe": by_amphoe,
            "by_region": rollup("region"), "by_province": rollup("prov")}


def run(check=False):
    obj = build()
    text = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    if check:
        if not os.path.exists(OUT) or open(OUT, encoding="utf-8").read() != text:
            print(f"DRIFT: {os.path.relpath(OUT, REPO)}")
            return 1
        print(f"OK: expansion_plan.json reproduces ({obj['meta']['n_placed']} placements, "
              f"{obj['meta']['n_districts_receiving']} districts)")
        return 0
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(text)
    m = obj["meta"]
    print(f"wrote {m['n_placed']} sequenced placements across {m['n_districts_receiving']} districts "
          f"-> platform/data/expansion_plan.json")
    for p in obj["sequence"][:5]:
        print(f"  #{p['rank']:>3}  {p['name']} ({p['region']})  outlet {p['k']}  v={p['v']}")
    print("  top by add: " + " | ".join(f"{r['name']} +{r['add']}" for r in obj["by_amphoe"][:5]))
    print("  regions: " + " | ".join(f"{r['name']} +{r['add']}" for r in obj["by_region"]))
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="sequenced Road-to-3,000 district placement plan")
    ap.add_argument("--check", action="store_true")
    raise SystemExit(run(check=ap.parse_args().check))
