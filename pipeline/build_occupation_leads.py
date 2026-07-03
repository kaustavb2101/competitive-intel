#!/usr/bin/env python3
"""
build_occupation_leads.py — NAMED occupation leads per branch (objective: leads near each branch).

branch_occupations.json gives COUNTS of establishments by occupation bucket within 10km. This layer
gives the ACTUAL businesses: for every one of the 2,015 branches, the nearest NAMED establishments
(with phone where published) in each occupation bucket within 10km — so branch staff can literally
call the factories / auto shops / markets whose workers are the title-loan customer base.

INPUT (source-data/occupation_places_named.json — assembled from pull_places_strip.py strips):
  { "buckets": [<14 keys>], "places": [ [lng, lat, bucket_idx, name, phone], ... ] }
  MEASURED Overture Places points; only occupation-relevant, name kept. See pull_places_strip.py.

OUTPUT (platform/data/occupation_leads.json), index-aligned to platform/data/branches.json:
  { "meta": {...provenance..., buckets:[{key,label}], k_per_bucket, radius_km},
    "branches": [ { "L": [ [bucket_idx, name, phone, dist_km], ... ] }, ... ] }
  Per branch: the K nearest NAMED establishments in EACH bucket present within 10km (sorted by
  bucket order, then distance). Only named places qualify (a lead you can't name is not a lead).

MEASURED: coordinates, names, phones are all real Overture Places fields — no synthesis. The only
judgement is the OCC_BUCKETS category map (shared with pull_overture_places.py).

DETERMINISTIC + NETWORK-FREE. Byte-exact reproducible → --check. The raw named-places source is a
bulk pull (gitignored); when absent build() returns None and --check skip-passes (like build_occupations).

Usage:
  python3 build_occupation_leads.py            # write platform/data/occupation_leads.json
  python3 build_occupation_leads.py --check    # verify byte-for-byte reproduce
"""
import argparse, json, math, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from pull_overture_places import OCC_BUCKETS  # the shared occupation taxonomy (14 buckets)

DATA = os.path.join(ROOT, "platform", "data")
SRC = os.path.join(ROOT, "source-data", "occupation_places_named.json")
BRANCHES = os.path.join(DATA, "branches.json")
META = os.path.join(DATA, "meta.json")
OUT = os.path.join(DATA, "occupation_leads.json")

K_PER_BUCKET = 3       # nearest named establishments to keep per occupation bucket per branch
RADIUS_KM = 10.0
CELL_DEG = 0.1
R_EARTH = 6371.0088


def _hav(lng1, lat1, lng2, lat2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = p2 - p1
    dlmb = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * R_EARTH * math.asin(math.sqrt(a))


def _load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def build():
    if not os.path.exists(SRC) or not os.path.exists(BRANCHES):
        return None
    src = _load(SRC)
    branches = _load(BRANCHES)
    vintage = (_load(META).get("updated") if os.path.exists(META) else None)
    places = src.get("places") or []

    # grid-hash spatial index over NAMED occupation places only (a nameless place is not a lead).
    grid = {}
    n_named = 0
    for rec in places:
        try:
            lng, lat, bi = float(rec[0]), float(rec[1]), int(rec[2])
            name = (rec[3] or "").strip()
        except (TypeError, ValueError, IndexError):
            continue
        if not name:
            continue
        phone = rec[4] if len(rec) > 4 and rec[4] else ""
        cell = (int(math.floor(lng / CELL_DEG)), int(math.floor(lat / CELL_DEG)))
        grid.setdefault(cell, []).append((lng, lat, bi, name, phone))
        n_named += 1

    out = []
    n_leads = 0
    for br in branches:
        blng, blat = float(br["x"]), float(br["y"])
        dlat = RADIUS_KM / 110.574
        dlng = RADIUS_KM / (111.320 * max(0.2, math.cos(math.radians(blat))))
        cx0 = int(math.floor((blng - dlng) / CELL_DEG)); cx1 = int(math.floor((blng + dlng) / CELL_DEG))
        cy0 = int(math.floor((blat - dlat) / CELL_DEG)); cy1 = int(math.floor((blat + dlat) / CELL_DEG))
        # per bucket: collect (dist, name, phone) within radius, keep K nearest.
        per_bucket = {}
        for cx in range(cx0, cx1 + 1):
            for cy in range(cy0, cy1 + 1):
                for (lng, lat, bi, name, phone) in grid.get((cx, cy), ()):
                    d = _hav(blng, blat, lng, lat)
                    if d <= RADIUS_KM:
                        per_bucket.setdefault(bi, []).append((round(d, 2), name, phone, lng, lat))
        leads = []
        for bi in range(len(OCC_BUCKETS)):
            cand = per_bucket.get(bi)
            if not cand:
                continue
            # nearest first; tie-break by name then coords for byte-stability
            cand.sort(key=lambda t: (t[0], t[1], t[3], t[4]))
            for (d, name, phone, _lng, _lat) in cand[:K_PER_BUCKET]:
                leads.append([bi, name, phone, d])
        n_leads += len(leads)
        out.append({"L": leads})

    meta = {
        "generated_by": "pipeline/build_occupation_leads.py",
        "label": "NAMED occupation leads per branch — the nearest real establishments (name + phone) "
                 "in each occupation bucket within 10 km of every branch, so staff can contact the "
                 "workplaces whose employees are the title-loan customer base. MEASURED Overture Places.",
        "objective": "Acquisition / leads (the reframed core objective): WHO to call near each branch, "
                     "by occupation — companion to branch_occupations.json (how MANY by occupation).",
        "provenance": {
            "establishments": "MEASURED — Overture Maps Places (name, phone, coordinates published "
                              "as pulled; occupation-relevant only). No synthesis, no fabricated leads.",
            "bucket_map": "EDITORIAL — Overture primary category -> one of 14 OCC_BUCKETS (shared with "
                          "pull_overture_places.py). The places are measured; only the bucket map is judgement.",
            "vintage": "Overture Places pull; app vintage from meta.json 'updated' = %s." % (vintage or "unknown"),
        },
        "index_note": "branches[] is INDEX-ALIGNED to platform/data/branches.json (entry i <-> branch i).",
        "lead_format": "each lead is [bucket_idx, name, phone, dist_km]; grouped by bucket order then "
                       "nearest-first. Only NAMED establishments qualify. phone is '' when unpublished.",
        "k_per_bucket": K_PER_BUCKET,
        "radius_km": RADIUS_KM,
        "buckets": [{"key": k, "label": lab} for (k, lab, _kw) in OCC_BUCKETS],
        "gaps": [
            "Overture Places is a sample/lower bound, not a business registry — absence of a lead is "
            "not absence of a business. Phones are as published (may be stale).",
        ],
        "n_branches": len(out),
        "n_named_places_indexed": n_named,
        "n_leads": n_leads,
    }
    return {"meta": meta, "branches": out}


def run(check=False):
    obj = build()
    if obj is None:
        if check:
            print("SKIP: source-data/occupation_places_named.json absent — occupation_leads not "
                  "checkable (bulk pull; run pull_places_strip.py + merge)")
            return 0
        print("missing input: needs source-data/occupation_places_named.json + platform/data/branches.json")
        return 1
    text = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    if check:
        if not os.path.exists(OUT) or open(OUT, encoding="utf-8").read() != text:
            print("DRIFT: %s" % os.path.relpath(OUT, ROOT)); return 1
        print("OK: occupation_leads.json reproduces (%d branches, %d leads)"
              % (obj["meta"]["n_branches"], obj["meta"]["n_leads"]))
        return 0
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(text)
    m = obj["meta"]
    print("wrote %d branches, %d named leads -> platform/data/occupation_leads.json (%.0f KB)"
          % (m["n_branches"], m["n_leads"], len(text.encode("utf-8")) / 1024))
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="named occupation leads per branch (Overture Places)")
    ap.add_argument("--check", action="store_true")
    raise SystemExit(run(check=ap.parse_args().check))
