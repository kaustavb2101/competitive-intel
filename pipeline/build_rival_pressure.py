#!/usr/bin/env python3
"""
build_rival_pressure.py — per-branch RIVAL PRESSURE (objective #1 + #2, MEASURED)
=================================================================================
For each of the 2,015 AutoX branches, against the MERGED measured competitor census
(platform/data/competitors_census.json — official store-locator networks for
Muangthai / Srisawad / Tidlor, Google∪Overture sample for Heng):

  - distance to the NEAREST rival of EACH brand (km, great-circle haversine);
  - how many rival branches sit within 2 km and within 5 km (all brands);
  - a "siege" flag: >= SIEGE_MIN rivals within 2 km — this branch is fighting for
    the same walk-in traffic on the same street.

Everything here is MEASURED geometry over real pulled coordinates — no scores, no
weights, no synthesis. The only editorial choice is the siege threshold, which is
stated in meta and in the UI.

Output: platform/data/rival_pressure.json  (INDEX-ALIGNED to branches.json)
  { meta:     {... full provenance + siege rule + branches_fingerprint ...},
    brands:   ["Heng","Muangthai","Srisawad","Tidlor"],        # stable sorted order
    branches: [{d:[km per brand], n2, n5, s?:1} x2015],        # s present only when besieged
    besieged: [top-25 siege branches with names, for the #trend table] }

Deterministic + network-free. Pure stdlib. Grid-hash spatial index (same pattern as
build_lead_sites.py) so the national build runs in seconds.
    python3 build_rival_pressure.py            # write the JSON
    python3 build_rival_pressure.py --check    # verify byte-for-byte reproduce
"""
import argparse, json, math, os

from fingerprint import branches_fingerprint

ROOT = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(ROOT)
DATA = os.path.join(REPO, "platform", "data")
OUT  = os.path.join(DATA, "rival_pressure.json")

R_EARTH   = 6371.0088     # km, IUGG mean Earth radius (same constant family as other builders)
CELL_DEG  = 0.1           # grid-hash cell (~11 km) — one ring of cells covers the 5 km radius
NEAR_KM   = 2.0           # inner pressure radius (same-street / same-market fight)
MID_KM    = 5.0           # outer pressure radius (matches the app's COMP_RADIUS_KM read)
SIEGE_MIN = 3             # siege = >= this many rivals within NEAR_KM
TOP_SIEGE = 25            # besieged records shipped (UI shows top 10)
BRUTE_MAX = 2500          # brands with fewer points than this: nearest by brute-force scan
# a 0.1° cell is >= ~10.4 km wide anywhere in Thailand (lat <= ~20.5°, cos >= 0.937), so an
# expanding ring search may stop once (ring-1)*MIN_CELL_KM exceeds the best distance found.
MIN_CELL_KM = 10.4


def _load(name):
    with open(os.path.join(DATA, name), encoding="utf-8") as f:
        return json.load(f)


def _hav_km(lng1, lat1, lng2, lat2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2.0) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2.0) ** 2
    return 2.0 * R_EARTH * math.asin(math.sqrt(a))


def _cell(lng, lat):
    return (int(math.floor(lng / CELL_DEG)), int(math.floor(lat / CELL_DEG)))


def _nearest_grid(blng, blat, grid):
    """Nearest point in a per-brand grid via expanding Chebyshev rings.
    Correct: keeps expanding until the ring's minimum possible distance exceeds the
    best haversine found. Deterministic (pure arithmetic over a fixed point set)."""
    cx, cy = _cell(blng, blat)
    best = None
    ring = 0
    while True:
        if best is not None and (ring - 1) * MIN_CELL_KM > best:
            return best
        found_any = False
        for gx in range(cx - ring, cx + ring + 1):
            for gy in range(cy - ring, cy + ring + 1):
                if max(abs(gx - cx), abs(gy - cy)) != ring:
                    continue  # perimeter cells only
                pts = grid.get((gx, gy))
                if not pts:
                    continue
                found_any = True
                for (lng, lat) in pts:
                    d = _hav_km(blng, blat, lng, lat)
                    if best is None or d < best:
                        best = d
        ring += 1
        if ring > 2000:            # safety net — can never trigger over Thailand extents
            return best


def build():
    branches = _load("branches.json")
    census   = _load("competitors_census.json")

    rivals, skipped = [], 0
    for it in census.get("items", []):
        lat, lng, brand = it.get("lat"), it.get("lng"), it.get("brand")
        if lat is None or lng is None or not brand:
            skipped += 1
            continue
        rivals.append((float(lng), float(lat), brand))
    brands = sorted({r[2] for r in rivals})
    b_idx  = {b: i for i, b in enumerate(brands)}

    # grid-hash: one ALL-brands grid for the radius counts + per-brand grids/lists for nearest
    grid_all   = {}
    grid_brand = [dict() for _ in brands]
    list_brand = [[] for _ in brands]
    for (lng, lat, brand) in rivals:
        c = _cell(lng, lat)
        grid_all.setdefault(c, []).append((lng, lat))
        bi = b_idx[brand]
        grid_brand[bi].setdefault(c, []).append((lng, lat))
        list_brand[bi].append((lng, lat))
    brute = [len(list_brand[i]) <= BRUTE_MAX for i in range(len(brands))]

    rows, siege_rows = [], []
    n2_total = n5_total = 0
    for i, br in enumerate(branches):
        blng, blat = br["x"], br["y"]

        # counts within NEAR_KM / MID_KM (all brands) + per-brand 2 km split for the siege table
        dlat = MID_KM / 110.574
        dlng = MID_KM / (111.320 * max(0.2, math.cos(math.radians(blat))))
        cx0 = int(math.floor((blng - dlng) / CELL_DEG)); cx1 = int(math.floor((blng + dlng) / CELL_DEG))
        cy0 = int(math.floor((blat - dlat) / CELL_DEG)); cy1 = int(math.floor((blat + dlat) / CELL_DEG))
        n2 = n5 = 0
        b2 = {}
        for gx in range(cx0, cx1 + 1):
            for gy in range(cy0, cy1 + 1):
                for bi, g in enumerate(grid_brand):
                    for (lng, lat) in g.get((gx, gy), ()):
                        d = _hav_km(blng, blat, lng, lat)
                        if d <= MID_KM:
                            n5 += 1
                            if d <= NEAR_KM:
                                n2 += 1
                                b2[brands[bi]] = b2.get(brands[bi], 0) + 1

        # nearest rival per brand (km): brute-force scan for sparse brands, expanding
        # grid rings for the dense official-locator networks
        dists = []
        for bi in range(len(brands)):
            if brute[bi]:
                best = None
                for (lng, lat) in list_brand[bi]:
                    d = _hav_km(blng, blat, lng, lat)
                    if best is None or d < best:
                        best = d
            else:
                best = _nearest_grid(blng, blat, grid_brand[bi])
            dists.append(round(best, 2) if best is not None else None)

        row = {"d": dists, "n2": n2, "n5": n5}
        if n2 >= SIEGE_MIN:
            row["s"] = 1
            nb = min((dv, bi) for bi, dv in enumerate(dists) if dv is not None)
            siege_rows.append({
                "i": i, "name": br.get("n"), "prov": br.get("v"),
                "district": br.get("d"), "region": br.get("r"),
                "n2": n2, "n5": n5,
                "nb": brands[nb[1]], "nd": nb[0],
                "by2": sorted(b2.items(), key=lambda kv: (-kv[1], kv[0])),
            })
        n2_total += n2; n5_total += n5
        rows.append(row)

    siege_rows.sort(key=lambda s: (-s["n2"], -s["n5"], s["nd"], s["i"]))
    n_siege = len(siege_rows)
    besieged = siege_rows[:TOP_SIEGE]

    meta = {
        "generated_by": "pipeline/build_rival_pressure.py",
        "label": "RIVAL PRESSURE per branch — MEASURED distance to the nearest rival of each brand, "
                 "rival counts within 2 km / 5 km, and a 'siege' flag (>= %d rivals within 2 km), "
                 "computed over the merged measured competitor census. Pure geometry over real pulled "
                 "coordinates — no scores, no synthesis." % SIEGE_MIN,
        "objective": "Both objectives: #1 (a besieged branch fights price/LTV pressure on its own "
                     "doorstep) and #2 (rival proximity tells expansion where the ground is already "
                     "contested vs open).",
        "provenance": {
            "rivals": "MEASURED — platform/data/competitors_census.json .items (%d usable points; %d "
                      "skipped for missing coords/brand). Official store-locator networks for "
                      "Muangthai/Srisawad/Tidlor (measured-complete); Heng is a Google∪Overture "
                      "SAMPLE (lower bound), so its nearest-distance can only be an UPPER bound."
                      % (len(rivals), skipped),
            "distances": "MEASURED — great-circle haversine (R=%.4f km) between the branch coordinate "
                         "and each rival coordinate; nearest-per-brand exact over the census point set." % R_EARTH,
            "counts": "MEASURED — rivals (all brands) within %.0f km and %.0f km of the branch." % (NEAR_KM, MID_KM),
            "siege": "RULE, stated: s=1 when >= %d rivals sit within %.0f km. The threshold is an "
                     "editorial cutoff; the underlying counts are measured." % (SIEGE_MIN, NEAR_KM),
        },
        "brands": brands,
        "radii_km": [NEAR_KM, MID_KM],
        "siege_rule": "n2 >= %d" % SIEGE_MIN,
        "n_branches": len(rows),
        "n_rivals": len(rivals),
        "n_rivals_skipped": skipped,
        "n_siege": n_siege,
        "mean_n2": round(n2_total / len(rows), 2) if rows else None,
        "mean_n5": round(n5_total / len(rows), 2) if rows else None,
        "branches_fingerprint": branches_fingerprint(branches),
        "index_note": "branches[] is INDEX-ALIGNED to platform/data/branches.json (entry i <-> branch i), "
                      "identical to branch_population.json / branch_leads.json.",
        "fields": {
            "brands":         "stable sorted brand order; branches[].d aligns to it.",
            "branches[].d":   "MEASURED — km to the NEAREST rival of each brand (2 dp), aligned to brands[]; "
                              "null only if a brand had zero census points.",
            "branches[].n2":  "MEASURED — rival branches (all brands) within %.0f km." % NEAR_KM,
            "branches[].n5":  "MEASURED — rival branches (all brands) within %.0f km." % MID_KM,
            "branches[].s":   "present (1) only when besieged: n2 >= %d (stated rule over measured counts)." % SIEGE_MIN,
            "besieged[]":     "top-%d siege branches (n2 desc, n5 desc, nearest asc): i (branch index), "
                              "name/prov/district/region, n2/n5, nb+nd (nearest brand + km), by2 "
                              "([brand, count-within-2km] pairs)." % TOP_SIEGE,
        },
        "gaps": [
            "Heng census is a Places/Overture sample, not the operator's full network — Heng pressure "
            "is understated and its nearest-distance is an upper bound.",
            "Sub-scale local operators (the long tail facing the Q1-2026 BoT registration deadline) are "
            "not in the census at all — total pressure is a lower bound.",
        ],
        "inputs": ["branches.json (branch coordinates)",
                   "competitors_census.json (merged measured rival census)"],
    }
    return {"meta": meta, "brands": brands, "branches": rows, "besieged": besieged}


def run(check=False):
    obj = build()
    text = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    if check:
        if not os.path.exists(OUT) or open(OUT, encoding="utf-8").read() != text:
            print(f"DRIFT: {os.path.relpath(OUT, REPO)}"); return 1
        print(f"OK: rival_pressure.json reproduces ({obj['meta']['n_branches']} branches, "
              f"{obj['meta']['n_siege']} besieged)")
        return 0
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(text)
    m = obj["meta"]
    print(f"wrote {m['n_branches']} branches -> platform/data/rival_pressure.json "
          f"({len(text)/1024:.0f} KB; {m['n_rivals']} rivals, {m['n_siege']} besieged, "
          f"mean {m['mean_n2']} rivals <=2km / {m['mean_n5']} <=5km)")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="per-branch rival pressure (measured distances/counts vs the competitor census)")
    ap.add_argument("--check", action="store_true")
    raise SystemExit(run(check=ap.parse_args().check))
