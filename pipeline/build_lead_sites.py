#!/usr/bin/env python3
"""
build_lead_sites.py — WHERE the leads are: measured lead-site pins per branch (objective #2, local).

THE QUESTION THIS ANSWERS
-------------------------
"When I select a branch on the map, WHERE exactly are the lead-relevant establishments
around it?" branch_leads.json says WHICH occupations to court (counts + fit); this layer
gives the map the COORDINATES: for every one of the 2,015 branches, the K=12 nearest
lead-relevant establishment points within 10 km, so the UI can drop pins.

MEASURED vs ESTIMATED (the data-mandate — stated explicitly, repeated in meta)
------------------------------------------------------------------------------
  MEASURED   every point: OSM POI coordinates from source-data/osm_layers.json
             (the 13-layer national Overpass pull, ~79k points, items [lng,lat]).
             NO synthesis, NO jitter, NO fabricated points — coordinates are published
             as pulled, only ROUNDED to 4 decimals (~11 m; fine for map pins).
  ESTIMATED  nothing numeric. The only judgement is WHICH OSM layers count as
             "lead-relevant" (the editorial layer→bucket map below, mirroring the
             branch_leads.json occupation-bucket taxonomy) — documented in meta.

WHY OSM AND NOT OVERTURE PLACES
-------------------------------
branch_leads.json counts come from Overture Maps Places (2.27M points), but the raw
coordinate file (source-data/overture_places.json, written by pull_overture_places.py)
is NOT checked into the repo (too large; gitignored) — only derived per-branch COUNTS
exist here, with no reusable coordinates. osm_layers.json IS committed, measured, and
carries per-point coordinates, so it is the honest pin source. When the Overture raw
layer lands in source-data a richer rebuild is possible — flagged in meta.gaps.

SELECTION (fully deterministic)
-------------------------------
For each branch: haversine distance to every point of the lead-relevant layers within a
10 km radius (grid-hash spatial index, 0.1° cells, so the national build runs in
seconds), keep the K=12 NEAREST overall (all categories pooled — pins show the branch's
immediate commercial fabric, so dense categories like restaurants dominate by design;
the per-category counts live in branch_leads.json / branches.json k10). Ordering is
dist asc, then lng, then lat, then category index (byte-stable tie-break).

PAYLOAD DISCIPLINE
------------------
2,015 × ≤12 sites as compact arrays [cat_idx, lng, lat, dist_km] with a categories[]
legend in meta; lng/lat rounded to 4 decimals, dist to 0.1 km. Well under the 2.5 MB
budget (~0.8 MB).

DETERMINISTIC + NETWORK-FREE: no network, no wall clock (vintage is read from
platform/data/meta.json 'updated' — osm_layers.json carries no internal timestamp).
Byte-exact reproducible → carries --check (the QA gate runs it). Inputs may be absent
in a stripped sandbox: build() then returns None, --check skip-passes, a plain run
exits non-zero with a clear message (mirrors build_macro_exposure.py).

Usage:
  python3 build_lead_sites.py            # write platform/data/lead_sites.json
  python3 build_lead_sites.py --check    # verify byte-for-byte reproduce
"""
import argparse, json, math, os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "platform", "data")
OSM = os.path.join(ROOT, "source-data", "osm_layers.json")
BRANCHES = os.path.join(DATA, "branches.json")
LEADS = os.path.join(DATA, "branch_leads.json")
META = os.path.join(DATA, "meta.json")
OUT = os.path.join(DATA, "lead_sites.json")

K = 12                 # pins per branch
RADIUS_KM = 10.0       # same catchment radius as branches.json k10 / branch_leads.json
CELL_DEG = 0.1         # grid-hash cell (~11 km) — one ring of cells covers the radius
R_EARTH = 6371.0088    # km, IUGG mean

# ── the lead-relevant category legend (ORDER IS FIXED — it is the cat_idx space) ─
# EDITORIAL layer→bucket map: each OSM layer is tied to the branch_leads.json occupation
# bucket it evidences, so the map pins and the lead board speak the same taxonomy.
# Excluded OSM layers (documented, not silently dropped): bank/atm (competitor & banked-
# population markers, not leads — already surfaced in branches.json k10), pharmacy
# (health: salaried, bank-served, low title-loan fit), civic (public sector, low fit).
CATEGORIES = (
    # key           label                       osm layer           lead bucket (branch_leads.json)
    ("fresh_mkt",   "Fresh market",             "fresh_market",     "retail"),
    ("gold",        "Gold shop",                "gold",             "finance"),
    ("vehicle",     "Vehicle shop / garage",    "vehicle_commerce", "auto"),
    ("industrial",  "Factory / industrial",     "industrial",       "factory"),
    ("supermarket", "Supermarket",              "supermarket",      "retail"),
    ("convenience", "Convenience store",        "convenience",      "retail"),
    ("restaurant",  "Restaurant / food",        "restaurant",       "food"),
    ("hotel",       "Hotel / guesthouse",       "hotel",            "hospitality"),
    ("school",      "School",                   "school",           "education"),
)
EXCLUDED_LAYERS = {
    "bank": "competitor / banked-population marker, not a lead (kept in branches.json k10)",
    "atm": "competitor / banked-population marker, not a lead (kept in branches.json k10)",
    "pharmacy": "health bucket: salaried + bank-served, low title-loan fit",
    "civic": "public-sector bucket: salaried with GSB/co-op access, low fit",
}


def _haversine_km(lng1, lat1, lng2, lat2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = p2 - p1
    dlmb = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2.0) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2.0) ** 2
    return 2.0 * R_EARTH * math.asin(math.sqrt(a))


def _load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def build():
    for p in (OSM, BRANCHES, LEADS):
        if not os.path.exists(p):
            return None
    layers = _load(OSM)
    branches = _load(BRANCHES)
    leads = _load(LEADS)
    vintage = None
    if os.path.exists(META):
        vintage = (_load(META) or {}).get("updated")

    # sanity: our editorial bucket map must reference real branch_leads.json buckets
    lead_buckets = {b.get("k") for b in leads.get("buckets", []) if isinstance(b, dict)}
    for _, _, _, bucket in CATEGORIES:
        if bucket not in lead_buckets:
            raise SystemExit("lead bucket %r not in branch_leads.json buckets — taxonomies drifted" % bucket)

    # ── grid-hash spatial index over every lead-relevant point ──────────────
    # cell -> list of (lng, lat, cat_idx); insertion order follows the fixed
    # CATEGORIES order then the source file's own point order (deterministic).
    grid = {}
    layer_counts = []
    for ci, (_, _, layer_key, _) in enumerate(CATEGORIES):
        pts = layers.get(layer_key) or []
        layer_counts.append(len(pts))
        for pt in pts:
            lng, lat = float(pt[0]), float(pt[1])
            cell = (int(math.floor(lng / CELL_DEG)), int(math.floor(lat / CELL_DEG)))
            grid.setdefault(cell, []).append((lng, lat, ci))

    # ── per branch: K nearest within RADIUS_KM ──────────────────────────────
    out = []
    n_sites = 0
    cat_tally = [0] * len(CATEGORIES)
    for br in branches:
        blng, blat = float(br["x"]), float(br["y"])
        # candidate cells: the radius as a degree box around the branch
        dlat = RADIUS_KM / 110.574
        dlng = RADIUS_KM / (111.320 * max(0.2, math.cos(math.radians(blat))))
        cx0 = int(math.floor((blng - dlng) / CELL_DEG))
        cx1 = int(math.floor((blng + dlng) / CELL_DEG))
        cy0 = int(math.floor((blat - dlat) / CELL_DEG))
        cy1 = int(math.floor((blat + dlat) / CELL_DEG))
        cand = []
        for cx in range(cx0, cx1 + 1):
            for cy in range(cy0, cy1 + 1):
                for (lng, lat, ci) in grid.get((cx, cy), ()):
                    d = _haversine_km(blng, blat, lng, lat)
                    if d <= RADIUS_KM:
                        # deterministic order: dist, then lng, then lat, then cat_idx
                        cand.append((d, lng, lat, ci))
        cand.sort()
        sites = [[ci, round(lng, 4), round(lat, 4), round(d, 1)]
                 for (d, lng, lat, ci) in cand[:K]]
        for s in sites:
            cat_tally[s[0]] += 1
        n_sites += len(sites)
        out.append(sites)

    meta = {
        "generated_by": "pipeline/build_lead_sites.py",
        "label": "LEAD-SITE PINS per branch — MEASURED OSM establishment coordinates: the K nearest "
                 "lead-relevant sites within 10 km of each branch, for map pin-drops when a branch "
                 "is selected. Companion to branch_leads.json (WHICH occupations) — this is WHERE.",
        "objective": "Acquisition (objective #2, local flavor): show branch staff exactly where the "
                     "lead-relevant establishments around their branch are.",
        "provenance": {
            "coordinates": "MEASURED — OpenStreetMap POI points (source-data/osm_layers.json, the "
                           "13-layer national Overpass pull; items [lng,lat]). Published as pulled, "
                           "rounded to 4 decimals (~11 m); NO synthesis, NO jitter, no fabricated points.",
            "category_map": "ESTIMATED / EDITORIAL — which OSM layers count as lead-relevant and which "
                            "branch_leads.json occupation bucket each evidences (categories[].bucket). "
                            "The points themselves are measured; only this inclusion map is judgement.",
            "vintage": "osm_layers.json carries no internal timestamp; network vintage from "
                       "platform/data/meta.json 'updated' = %s (the enrichment-loop refresh that "
                       "last pulled the layers)." % (vintage or "unknown"),
        },
        "index_note": "branches[] is INDEX-ALIGNED to platform/data/branches.json (entry i <-> branch i), "
                      "identical to branch_leads.json / branch_occupations.json / macro_exposure.json.",
        "site_format": "each site is a compact array [cat_idx, lng, lat, dist_km]: cat_idx into "
                       "meta.categories[], lng/lat rounded 4 dp (~11 m), dist_km rounded 0.1. "
                       "Sites sorted nearest-first.",
        "selection": "the K nearest lead-relevant sites overall (all categories pooled) within "
                     "radius_km — dense categories (restaurants, convenience) dominate by design; "
                     "per-category catchment counts live in branch_leads.json / branches.json k10. "
                     "Tie-break: dist, then lng, then lat, then cat_idx (deterministic).",
        "k": K,
        "radius_km": RADIUS_KM,
        "categories": [
            {"k": k, "label": label, "osm_layer": layer, "bucket": bucket, "n_points": layer_counts[i]}
            for i, (k, label, layer, bucket) in enumerate(CATEGORIES)
        ],
        "excluded_osm_layers": EXCLUDED_LAYERS,
        "gaps": [
            "Overture Places raw coordinates (source-data/overture_places.json, 2.27M points — the "
            "branch_leads.json count source) are not checked into the repo (gitignored bulk pull); "
            "only derived counts exist here. Re-run this builder against it once the raw layer lands "
            "for denser, category-richer pins.",
            "OSM POI coverage is a sample/lower bound, not a registry — absence of a pin is NOT "
            "absence of an establishment.",
        ],
        "n_branches": len(out),
        "n_sites": n_sites,
        "sites_by_category": {CATEGORIES[i][0]: cat_tally[i] for i in range(len(CATEGORIES)) if cat_tally[i]},
    }
    return {"meta": meta, "branches": out}


def run(check=False):
    obj = build()
    if obj is None:
        if check:
            print("SKIP: osm_layers.json / branches.json / branch_leads.json absent — "
                  "lead_sites not checkable (optional layer)")
            return 0
        print("missing input: needs source-data/osm_layers.json + platform/data/branches.json "
              "+ platform/data/branch_leads.json.")
        return 1
    text = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    if check:
        if not os.path.exists(OUT) or open(OUT, encoding="utf-8").read() != text:
            print("DRIFT: %s" % os.path.relpath(OUT, ROOT))
            return 1
        print("OK: lead_sites.json reproduces (%d branches, %d sites)"
              % (obj["meta"]["n_branches"], obj["meta"]["n_sites"]))
        return 0
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(text)
    m = obj["meta"]
    print("wrote %d branches, %d sites -> platform/data/lead_sites.json (%.0f KB)"
          % (m["n_branches"], m["n_sites"], len(text.encode("utf-8")) / 1024))
    print("  sites by category: %s" % m["sites_by_category"])
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="measured lead-site pins per branch (map pin-drop layer)")
    ap.add_argument("--check", action="store_true")
    raise SystemExit(run(check=ap.parse_args().check))
