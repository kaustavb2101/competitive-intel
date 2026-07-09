#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_branch_workforce.py — per-branch 10km WORKFORCE mix (occupations, not storefronts).

WHY THIS EXISTS
---------------
branch_occupations.json answers "what BUSINESSES are within 10km" (Overture establishment
points). That undercounts the occupations that have no storefront — above all FARMERS, who
are ~60-90% of the rural/Isan workforce yet have zero map pins. So the occupation panel makes
agriculture look like a rank-10 rounding error in Thailand's rice bowl. This layer fixes that
by estimating the actual WORKFORCE in each branch's 10km perimeter, taking each occupation
from the source that actually measures it:

  * AGRICULTURE (farmers)      SPAM 2010 crop grid (spatial cropland, 5-arcmin cells) gives the
                               SHAPE; OAE per-province planted area (crop_stress.json) gives the
                               current MAGNITUDE; both anchored so the national agricultural
                               workforce sums to the NSO Labour-Force-Survey figure (~12.0M).
                               ESTIMATED (model-allocated), labelled as such.
  * FACTORY / production       DIW factory workers, already allocated per-branch in
                               branch_labor.json (factory_workers). MEASURED source.
  * the other 12 storefront    Overture POI counts in the perimeter (branch_occupations.json)
    occupations                x an assumed average headcount per establishment — Overture IS
                               storefront-accurate for these (shops, food, clinics, schools…).

Everything is converted to the SAME unit — people — so the resulting MIX (% of the perimeter
workforce by occupation) is comparable across occupations and reflective of who really works
there. That mix is the lead-targeting signal: "this catchment is 61% farmers, 12% merchants,
9% factory…". Businesses-nearby stays available as the separate, coarser branch_occupations.

HONEST PROVENANCE
-----------------
ESTIMATED overall. The agriculture spatial layer is SPAM 2010 (cropland barely moves, but it
is the oldest input); the magnitude is current OAE crop area; the anchor is the NSO agri
headline. Storefront headcounts are assumptions (documented in HEADCOUNT). No number is a
census; every number traces to a real source. There is NO real-time occupation feed for
Thailand at perimeter level — this is the reflective estimate, not a live count.

DETERMINISTIC + NETWORK-FREE. All inputs are committed (branches.json, branch_occupations.json,
branch_labor.json, crop_stress.json, spam2010_th_cropgrid.json), so it reproduces byte-for-byte
and carries --check (the QA gate runs it).

OUTPUT (platform/data/branch_workforce.json), INDEX-ALIGNED to branches.json:
  { "meta": {source, label, radius_km, buckets:[labels], constants, provenance, national,
             branches_fingerprint, measured:false},
    "buckets": [ {"key","label"}, ... ],           # same 14 as branch_occupations
    "branches": [ {"w":[people per bucket], "mix":[pct per bucket], "top":[idx,idx,idx],
                   "dom": idx, "t": total_workers}, ... ] }

Usage:
  python3 build_branch_workforce.py            # build/refresh branch_workforce.json
  python3 build_branch_workforce.py --check    # verify committed file reproduces byte-exact
"""
import argparse, json, math, os, sys

from fingerprint import branches_fingerprint
from regionmap import canonical

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
BRANCHES = os.path.join(ROOT, "platform", "data", "branches.json")
OCC = os.path.join(ROOT, "platform", "data", "branch_occupations.json")
LABOR = os.path.join(ROOT, "platform", "data", "branch_labor.json")
CROP_STRESS = os.path.join(ROOT, "platform", "data", "crop_stress.json")
SPAM = os.path.join(ROOT, "source-data", "spam2010_th_cropgrid.json")
OUT = os.path.join(ROOT, "platform", "data", "branch_workforce.json")

RADIUS_KM = 10.0
CELL_DEG = 0.1
EARTH_KM = 6371.0
D2R = math.pi / 180.0

# National agricultural workforce anchor — NSO Labour Force Survey, "agriculture" branch of
# employment (~11.5-12.5M of ~40M employed, 2023-24). The per-province OAE planted area is
# scaled so the sum of all branch agri-workforce estimates lands on this headline. Stated, not
# fitted — bump it here if a fresher LFS agri figure lands.
NAT_AGRI_WORKERS = 12_000_000

# Assumed average WORKERS PER ESTABLISHMENT for the storefront occupations (small Thai SME
# scale). ESTIMATED conversion so POI counts become people, comparable to farm/factory workers.
# factory + agriculture are NOT here (they come from DIW workers / the crop model).
HEADCOUNT = {
    "auto": 3.0, "retail": 2.5, "food": 3.0, "hospitality": 8.0, "finance": 6.0,
    "health": 7.0, "education": 18.0, "public": 12.0, "professional": 5.0,
    "personal": 2.5, "logistics": 6.0, "construction": 5.0,
}


def haversine_km(lng1, lat1, lng2, lat2):
    dlat = (lat2 - lat1) * D2R
    dlng = (lng2 - lng1) * D2R
    a = (math.sin(dlat / 2) ** 2
         + math.cos(lat1 * D2R) * math.cos(lat2 * D2R) * math.sin(dlng / 2) ** 2)
    return 2 * EARTH_KM * math.asin(min(1.0, math.sqrt(a)))


def cell_key(lng, lat):
    return (math.floor(lng / CELL_DEG), math.floor(lat / CELL_DEG))


def _load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def _branch_items(d):
    return d if isinstance(d, list) else d.get("items", d)


def spam_cropland_cells():
    """[(lng, lat, cropland_ha)] for SPAM cells with any cropland. Cell centre from the grid
    origin/resolution in the file's own meta (lng=x0+(col+.5)*res, lat=y0-(row+.5)*res)."""
    s = _load(SPAM)
    g = s["meta"]["grid"]
    x0, y0, res = g["x0"], g["y0"], g["res_deg"]
    out = []
    for c in s["cells"]:
        ha = sum(c[2:])            # rice+cassava+maize+oilpalm+sugarcane hectares
        if ha > 0:
            out.append((x0 + (c[0] + 0.5) * res, y0 - (c[1] + 0.5) * res, ha))
    return out


def crop_ha_per_branch(branches, cells):
    """Cropland hectares within RADIUS_KM of each branch (grid-accelerated haversine)."""
    grid = {}
    for (lng, lat, ha) in cells:
        grid.setdefault(cell_key(lng, lat), []).append((lng, lat, ha))
    out = []
    for b in branches:
        lng, lat = b.get("x"), b.get("y")
        tot = 0.0
        if lng is not None and lat is not None:
            cx, cy = cell_key(lng, lat)
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for (cl, ca, ha) in grid.get((cx + dx, cy + dy), ()):
                        if haversine_km(lng, lat, cl, ca) <= RADIUS_KM:
                            tot += ha
        out.append(tot)
    return out


def province_agri_workers():
    """{canonical_province: estimated agricultural workers}, from OAE planted area scaled so the
    national total equals NAT_AGRI_WORKERS."""
    provs = _load(CROP_STRESS)["provinces"]
    rai = {}
    for p in provs:
        comp = p.get("components") or {}
        r = comp.get("total_crop_rai")
        if isinstance(r, (int, float)) and r > 0:
            rai[canonical(p.get("th", ""))] = rai.get(canonical(p.get("th", "")), 0.0) + r
    nat_rai = sum(rai.values()) or 1.0
    wpr = NAT_AGRI_WORKERS / nat_rai
    return {k: v * wpr for k, v in rai.items()}, nat_rai, wpr


def build():
    branches = _branch_items(_load(BRANCHES))
    occ = _load(OCC)
    buckets = occ["buckets"]                        # [{key,label} x14]
    keys = [bk["key"] for bk in buckets]
    kidx = {k: i for i, k in enumerate(keys)}
    n = len(buckets)
    occ_rows = occ["branches"]
    labor_rows = _load(LABOR)["branches"]
    if not (len(occ_rows) == len(labor_rows) == len(branches)):
        sys.exit("build_branch_workforce.py: input layers are not index-aligned to branches.json "
                 f"(branches={len(branches)} occ={len(occ_rows)} labor={len(labor_rows)}).")

    cells = spam_cropland_cells()
    crop_ha = crop_ha_per_branch(branches, cells)
    agri_prov, nat_rai, wpr = province_agri_workers()

    # province-conserving agriculture allocation: split each province's estimated agri workforce
    # across ITS branches in proportion to the cropland in each branch's perimeter (equal split
    # as a fallback when a province's branches touch no SPAM cropland).
    prov_of = [canonical(b.get("v", "") or b.get("prov", "")) for b in branches]
    prov_crop_sum, prov_bcount = {}, {}
    for i, pr in enumerate(prov_of):
        prov_crop_sum[pr] = prov_crop_sum.get(pr, 0.0) + crop_ha[i]
        prov_bcount[pr] = prov_bcount.get(pr, 0) + 1

    ai = kidx["agriculture"]
    fi = kidx["factory"]
    out_branches = []
    agri_total = 0.0
    for i, b in enumerate(branches):
        pr = prov_of[i]
        w = [0.0] * n
        # agriculture — province anchor x local cropland share
        A = agri_prov.get(pr, 0.0)
        if A > 0:
            s = prov_crop_sum.get(pr, 0.0)
            if s > 0:
                w[ai] = A * (crop_ha[i] / s)
            else:
                w[ai] = A / max(1, prov_bcount.get(pr, 1))
        agri_total += w[ai]
        # factory — DIW workers allocated per branch (measured)
        fw = labor_rows[i].get("factory_workers")
        w[fi] = float(fw) if isinstance(fw, (int, float)) else 0.0
        # storefront occupations — POI counts x assumed headcount
        o = occ_rows[i].get("o") or []
        for k, key in enumerate(keys):
            if key in HEADCOUNT and k < len(o):
                w[k] = (o[k] or 0) * HEADCOUNT[key]
        wi = [int(round(v)) for v in w]
        tot = sum(wi)
        mix = [round(100.0 * v / tot, 1) if tot else 0.0 for v in wi]
        order = sorted(range(n), key=lambda k: -wi[k])
        top = [k for k in order[:3] if wi[k] > 0]
        dom = order[0] if tot else -1
        out_branches.append({"w": wi, "mix": mix, "top": top, "dom": dom, "t": tot})

    return {
        "meta": {
            "source": "Hybrid per-occupation workforce estimate — SPAM2010 cropland (spatial) x "
                      "OAE planted area (magnitude) anchored to NSO agri headline; DIW factory "
                      "workers; Overture POI x assumed headcount for storefront occupations.",
            "label": "ESTIMATED (reflective workforce mix, not a census; no real-time occupation "
                     "feed exists at perimeter level)",
            "measured": False,
            "radius_km": RADIUS_KM,
            "buckets": [bk["label"] for bk in buckets],
            "branches_fingerprint": branches_fingerprint(branches),
            "n_branches": len(branches),
            "constants": {
                "nat_agri_workers": NAT_AGRI_WORKERS,
                "worker_per_rai": round(wpr, 6),
                "national_planted_rai": round(nat_rai),
                "headcount_per_establishment": HEADCOUNT,
            },
            "provenance": {
                "agriculture": "ESTIMATED — SPAM 2010 5-arcmin cropland (spatial shape) x OAE "
                               "current planted area (per-province magnitude), scaled to NSO LFS "
                               "~12.0M national agricultural workers.",
                "factory": "MEASURED source — DIW factory worker counts, allocated per branch "
                           "(branch_labor.factory_workers).",
                "storefront_occupations": "ESTIMATED — Overture Places establishment counts within "
                                          "10km x assumed average headcount per establishment.",
            },
            "national": {
                "agri_workers_allocated": int(round(agri_total)),
                "agri_workers_anchor": NAT_AGRI_WORKERS,
            },
        },
        "buckets": buckets,
        "branches": out_branches,
    }


def serialize(obj):
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true",
                    help="verify the committed output reproduces byte-exact (no write)")
    args = ap.parse_args()

    obj = build()
    payload = serialize(obj)

    if args.check:
        if not os.path.exists(OUT):
            sys.exit("build_branch_workforce.py --check: branch_workforce.json missing — run "
                     "build_branch_workforce.py to generate it.")
        if open(OUT, encoding="utf-8").read() != payload:
            sys.exit("build_branch_workforce.py --check: branch_workforce.json drifted — re-run "
                     "python3 pipeline/build_branch_workforce.py.")
        print("build_branch_workforce.py --check: OK (byte-exact)")
        return

    with open(OUT, "w", encoding="utf-8") as f:
        f.write(payload)
    m = obj["meta"]
    kb = os.path.getsize(OUT) / 1024.0
    # dominant-occupation tally for a quick sanity read
    from collections import Counter
    dom = Counter(m["buckets"][b["dom"]] for b in obj["branches"] if b["dom"] >= 0)
    print(f"wrote {OUT}  ({kb:.1f} KB)")
    print(f"  national agri workforce allocated: {m['national']['agri_workers_allocated']:,} "
          f"(anchor {NAT_AGRI_WORKERS:,})")
    print("  dominant occupation across branches:")
    for label, c in dom.most_common():
        print(f"    {label:<26} {c:>4} branches")


if __name__ == "__main__":
    main()
