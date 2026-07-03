#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pull_osm_gapcheck.py — close the MEASURED-POI gaps for the branches the audit flagged.

THE GAP (objective #1/#2 data hygiene)
--------------------------------------
Two overlapping audit findings, both tracing to source-data/osm_layers.json (the 13-layer
national Overpass pull) simply having NO points near a handful of rural branches:

  * ZERO-k10   branches where sum(branches.json[i].k10.values()) == 0 — no OSM POI of ANY
               of the 13 layers within 10 km (k10 is projected from the master's ind10..sch10,
               which are count_within() over osm_layers.json — verified byte-exact).
  * EMPTY-SITES branches where lead_sites.json branches[i] == [] — no LEAD-relevant OSM point
               within 10 km (build_lead_sites.py, a 9-layer subset of osm_layers.json).

The zero-k10 set is a subset of the empty-sites set; the union is the "gap set" this script
re-queries.

WHAT IT DOES (100% measured OSM, no synthesis)
----------------------------------------------
For every gap branch it re-queries Overpass — the SAME 13 layer tag-sets the enrichment loop
registers (imported from autox_enrich_loop.OSM_LAYERS, so the taxonomy can never drift) — but
bounded to a 10 km bbox around THAT branch instead of the national area. Any point Overpass
returns that is NOT already in source-data/osm_layers.json (dedup on 5-dp [lng,lat]) is MERGED
in, appended in file order. NOTHING is fabricated: if Overpass genuinely returns zero for a
rural branch, that is a real MEASURED zero and the branch is recorded as verified-sparse (the
stamp build_lead_sites.py reads to distinguish "measured zero" from "never pulled").

Then it re-projects the merged layers into the master's per-branch features (ind10..sch10) with
the enrichment loop's own count_within() — network-free, byte-identical for every UNAFFECTED
branch (verified: recomputing the current master reproduces it with 0 field mismatches), so the
downstream diff is confined to the gap branches. Run

    cd pipeline && python3 autox_enrich_loop.py --derive-only   # project master -> platform/data
    cd pipeline && bash refresh_all.sh                          # rebuild derived layers
    cd pipeline && python3 build_lead_sites.py && python3 build_branch_leads.py

afterwards (or just `bash refresh_all.sh` + the two lead builders) to land the refresh in the app.

RESUMABLE / CACHED
------------------
Each (branch, layer) Overpass response is cached in pipeline/cache/ keyed by query hash
(gitignored), written atomically, so a re-run after a crash re-reads from cache without
re-hitting the mirror. 429/504 => 60 s backoff; other errors 15 s * attempt.

Usage:
  python3 pull_osm_gapcheck.py                 # re-query the gap set, merge, re-project master
  python3 pull_osm_gapcheck.py --dry-run       # query + report, write NOTHING
  python3 pull_osm_gapcheck.py --no-cache      # ignore cached raw responses
  python3 pull_osm_gapcheck.py --endpoint URL  # override the Overpass endpoint
"""
import argparse
import hashlib
import json
import math
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "platform", "data")
CACHE = os.path.join(HERE, "cache")
OSM = os.path.join(ROOT, "source-data", "osm_layers.json")
MASTER = os.path.join(ROOT, "source-data", "branches_final.json")
BRANCHES = os.path.join(DATA, "branches.json")
LEAD_SITES = os.path.join(DATA, "lead_sites.json")
META = os.path.join(DATA, "meta.json")
GAPCHECK = os.path.join(ROOT, "source-data", "osm_gapcheck.json")

DEFAULT_MIRROR = "https://maps.mail.ru/osm/tools/overpass/api/interpreter"
UA = {"User-Agent": "autox-osm-gapcheck/1.0"}

# reuse the loop's registry + geometry so the taxonomy/algorithm can NEVER drift from enrichment
from autox_enrich_loop import OSM_LAYERS, bucket, count_within  # noqa: E402

# master feature field per OSM layer (mirror of stage_features keymap in autox_enrich_loop)
KEYMAP = {"industrial": "ind10", "bank": "bank10", "atm": "atm10", "convenience": "cvs10",
          "hotel": "hotel10", "fresh_market": "fmkt10", "restaurant": "rest10",
          "supermarket": "super10", "pharmacy": "pharm10", "gold": "gold10",
          "vehicle_commerce": "veh10", "school": "sch10", "civic": "civic10"}
RADIUS_KM = 10.0


# ---------------------------------------------------------------- overpass + cache
def _cache_path(query):
    h = hashlib.sha1(query.encode("utf-8")).hexdigest()[:20]
    return os.path.join(CACHE, f"gapcheck_{h}.json")


def overpass(query, endpoint, use_cache=True, timeout=180, retries=4):
    """POST an Overpass query; cache the raw response keyed by query hash.
    Returns (elements, hit_network). 429/504 => 60 s backoff, else 15 s * attempt."""
    cp = _cache_path(query)
    if use_cache and os.path.exists(cp):
        try:
            with open(cp, encoding="utf-8") as f:
                return json.load(f).get("elements", []), False
        except Exception:
            pass  # corrupt cache (killed mid-write) — refetch
    data = urllib.parse.urlencode({"data": query}).encode()
    last = None
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(endpoint, data=data, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                raw = r.read()
            d = json.loads(raw)
            os.makedirs(CACHE, exist_ok=True)
            tmp = cp + ".tmp"
            with open(tmp, "wb") as f:
                f.write(raw)
            os.replace(tmp, cp)   # atomic: a killed run never leaves a corrupt cache entry
            return d.get("elements", []), True
        except Exception as ex:  # noqa: BLE001 — report, back off, retry
            last = ex
            code = getattr(ex, "code", None)
            wait = 60 if code in (429, 504) else 15 * attempt
            if attempt < retries:
                print(f"      overpass attempt {attempt} failed ({ex}); backing off {wait}s",
                      file=sys.stderr)
                time.sleep(wait)
    raise RuntimeError(f"Overpass failed after {retries} attempts: {last}")


def _pts_from_elements(elements):
    """[lng,lat] rounded to 5 dp (matching osm_layers.json / the loop's overpass())."""
    pts = []
    for e in elements:
        la = e.get("lat")
        lo = e.get("lon")
        if la is None:
            c = e.get("center") or {}
            la, lo = c.get("lat"), c.get("lon")
        if la is not None and lo is not None:
            pts.append([round(lo, 5), round(la, 5)])
    return pts


def _bbox(lat, lng, radius_km):
    """Degree bbox whose edges are radius_km from (lat,lng); its corners reach ~1.4x, but
    count_within() applies the exact haversine 10 km gate, so over-capture is harmless (the
    extra points are real measured establishments, merged honestly)."""
    dlat = radius_km / 110.574
    dlng = radius_km / (111.320 * max(0.2, math.cos(math.radians(lat))))
    return (round(lat - dlat, 6), round(lng - dlng, 6),
            round(lat + dlat, 6), round(lng + dlng, 6))


def _layer_query(selector, bbox):
    """Rebind a national OSM_LAYERS selector to a bbox: swap every (area.th) for the bbox."""
    s, w, n, e = bbox
    bounded = selector.replace("(area.th)", f"({s},{w},{n},{e})")
    return f"[out:json][timeout:120];({bounded})->.s;.s out center;"


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description="re-query Overpass for the audit's POI-gap branches")
    ap.add_argument("--endpoint", default=DEFAULT_MIRROR)
    ap.add_argument("--no-cache", action="store_true", help="ignore cached raw responses")
    ap.add_argument("--dry-run", action="store_true", help="query + report, write nothing")
    ap.add_argument("--sleep", type=float, default=1.0,
                    help="seconds between network queries (default 1)")
    args = ap.parse_args()

    branches = json.load(open(BRANCHES, encoding="utf-8"))
    master = json.load(open(MASTER, encoding="utf-8"))
    lead_sites = json.load(open(LEAD_SITES, encoding="utf-8"))
    meta = json.load(open(META, encoding="utf-8")) if os.path.exists(META) else {}
    vintage = meta.get("updated", "unknown")
    if not (len(branches) == len(master) == len(lead_sites.get("branches", []))):
        print("index misalignment across branches/master/lead_sites — abort", file=sys.stderr)
        return 1

    zero_k10 = [i for i, b in enumerate(branches) if sum(b["k10"].values()) == 0]
    empty_sites = [i for i, s in enumerate(lead_sites["branches"]) if not s]
    gap = sorted(set(zero_k10) | set(empty_sites))
    print(f"gap set: {len(gap)} branches  (zero-k10={len(zero_k10)}, empty-sites={len(empty_sites)})")
    print(f"vintage (meta.updated): {vintage}\n")

    layers = json.load(open(OSM, encoding="utf-8"))
    # existing point set per layer for O(1) dedup (tuples of the stored coords)
    existing = {name: set(tuple(p) for p in layers.get(name, [])) for name in OSM_LAYERS}

    added_per_layer = {name: 0 for name in OSM_LAYERS}
    records = []
    hit_net_last = False
    for rank, i in enumerate(gap, 1):
        b = branches[i]
        lat, lng = float(b["y"]), float(b["x"])
        mb = master[i]
        code = mb.get("code", "")
        name = mb.get("name", "")
        prov = mb.get("prov", "")
        bbox = _bbox(lat, lng, RADIUS_KM)
        print(f"[{rank}/{len(gap)}] idx={i} {code} {name[:26]} ({prov})  bbox={bbox}")
        rec = {"idx": i, "code": code, "name": name, "prov": prov,
               "lat": round(lat, 5), "lng": round(lng, 5),
               "added": {}, "within10km_by_layer": {}}
        new_total = 0
        for lname, (selector, _ttl) in OSM_LAYERS.items():
            q = _layer_query(selector, bbox)
            try:
                els, net = overpass(q, args.endpoint, use_cache=not args.no_cache)
            except Exception as ex:  # noqa: BLE001 — a failed layer must not kill the batch
                print(f"      ! {lname} FAILED: {ex}", file=sys.stderr)
                rec.setdefault("errors", []).append(lname)
                continue
            if net and args.sleep > 0:
                time.sleep(args.sleep)
            hit_net_last = hit_net_last or net
            pts = _pts_from_elements(els)
            fresh = 0
            for p in pts:
                t = tuple(p)
                if t not in existing[lname]:
                    existing[lname].add(t)
                    layers[lname].append(p)
                    fresh += 1
            added_per_layer[lname] += fresh
            if fresh:
                rec["added"][lname] = fresh
                new_total += fresh
        # measured within-10km count per layer AFTER merge (exact haversine gate)
        buckets = {ln: bucket(layers[ln]) for ln in OSM_LAYERS}
        for ln in OSM_LAYERS:
            c = count_within(lat, lng, buckets[ln], RADIUS_KM)
            if c:
                rec["within10km_by_layer"][ln] = c
        rec["new_points"] = new_total
        rec["total_within10km"] = sum(rec["within10km_by_layer"].values())
        records.append(rec)
        tag = "ENRICHED" if new_total else "verified-sparse (measured zero)"
        print(f"      -> {new_total} new points merged; "
              f"within-10km total now {rec['total_within10km']}  [{tag}]")

    total_added = sum(added_per_layer.values())
    print(f"\n==== gapcheck summary ====")
    print(f"branches re-queried : {len(gap)}")
    print(f"new points merged   : {total_added}  {[ (k,v) for k,v in added_per_layer.items() if v ]}")
    enriched = [r["idx"] for r in records if r["new_points"]]
    sparse = [r["idx"] for r in records if not r["new_points"]]
    print(f"enriched            : {len(enriched)} {enriched}")
    print(f"verified-sparse     : {len(sparse)} {sparse}")

    if args.dry_run:
        print("\n(dry-run) nothing written.")
        return 0

    # 1) merged OSM layers (only if changed)
    if total_added:
        with open(OSM, "w", encoding="utf-8") as f:
            json.dump(layers, f, ensure_ascii=False)
        print(f"wrote source-data/osm_layers.json (+{total_added} points)")
    else:
        print("source-data/osm_layers.json UNCHANGED (all gap branches are measured zeros)")

    # 2) re-project the master's per-branch features from the merged layers (network-free;
    #    byte-identical for unaffected branches). This is stage_features, standalone. Only
    #    rewrite the master when a field actually moved — a no-op merge (all measured zeros)
    #    must not churn branches_final.json / the downstream diff.
    B = {ln: bucket(layers[ln]) for ln in OSM_LAYERS}
    changed = 0
    for mb in master:
        for lname, g in B.items():
            fld = KEYMAP[lname]
            v = count_within(mb["lat"], mb["lng"], g, RADIUS_KM)
            if mb.get(fld, 0) != v:
                changed += 1
            mb[fld] = v
    if changed:
        with open(MASTER, "w", encoding="utf-8") as f:
            json.dump(master, f, ensure_ascii=False)
        print(f"re-projected master features ({changed} field(s) changed) -> branches_final.json")
    else:
        print("master features unchanged (all gap branches are measured zeros) — not rewritten")

    # 3) provenance sidecar — records which branches were re-queried at which vintage, so
    #    build_lead_sites.py can stamp the still-empty ones 'verified sparse — measured zero'.
    sidecar = {
        "generated_by": "pipeline/pull_osm_gapcheck.py",
        "what": "Per-branch Overpass re-query of the audit's POI-gap branches (zero-k10 / "
                "empty lead-sites). Records which branches were re-queried at which network "
                "vintage so a MEASURED zero is distinguishable from a never-pulled gap. "
                "Points are merged into source-data/osm_layers.json; NONE are fabricated.",
        "provenance": "MEASURED — OpenStreetMap via Overpass (maps.mail.ru mirror), same 13 "
                      "layer tag-sets as autox_enrich_loop.OSM_LAYERS, bbox-bounded to 10 km "
                      "per branch. Absence of a point after re-query is a real measured zero.",
        "vintage": vintage,
        "radius_km": RADIUS_KM,
        "requeried_idx": gap,
        "requeried_codes": [master[i].get("code", "") for i in gap],
        "enriched_idx": enriched,
        "verified_sparse_idx": sparse,
        "new_points_total": total_added,
        "new_points_by_layer": {k: v for k, v in added_per_layer.items() if v},
        "branches": records,
    }
    with open(GAPCHECK, "w", encoding="utf-8") as f:
        json.dump(sidecar, f, ensure_ascii=False, indent=2)
    print(f"wrote source-data/osm_gapcheck.json ({len(gap)} branches, vintage '{vintage}')")
    print("\nNEXT: python3 autox_enrich_loop.py --derive-only && bash refresh_all.sh "
          "&& python3 build_lead_sites.py && python3 build_branch_leads.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
