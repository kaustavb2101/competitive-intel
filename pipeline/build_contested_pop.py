#!/usr/bin/env python3
"""
build_contested_pop.py — CONTESTED POPULATION per branch (objective #2, MEASURED)
==================================================================================
THE QUESTION THIS ANSWERS
-------------------------
Of the people a branch can actually reach (its 10km catchment), how many are ALSO on a
rival's doorstep? "61% contested" means 61% of this branch's catchment population lives
within 2km of at least one competitor branch — AutoX and the rivals are fighting for the
same people, not just the same street.

METHOD (both factors measured; the overlay is pure geometry)
------------------------------------------------------------
  pop10      Sum the WorldPop 2020 1km gridded-population raster over the branch's 10km
             circle — a direct raster sample (source-data/worldpop_tha_2020_1km.tif,
             UN-adjusted to the official national total ~69.8M; each 1km cell whose centre
             falls inside the circle is added). This is NOT the same number as
             branch_population.json, whose shipped values are a district-population
             AREA-WEIGHT estimate (build_branch_population.py's rasterio path was
             unavailable and fell back); pop10 is the genuine raster count.
  contested  The same sum restricted to CONTESTED cells: a 1km cell is contested when its
             centre lies within 2km of ANY rival in the merged measured competitor census
             (platform/data/competitors_census.json — official store-locator networks for
             Muangthai/Srisawad/Tidlor, Google∪Overture sample for Heng).
  share      contested / pop10 — computed client-side from the two shipped integers.

Output: platform/data/contested_pop.json (INDEX-ALIGNED to branches.json, stamped with
branches_fingerprint like rival_pressure.json):
  { meta: {... provenance + WorldPop vintage + census lower-bound caveat ...},
    rows: [[pop10, contested_pop] x2015],
    top:  [top-25 most-contested branches (pop10 >= MIN_POP), for the #exposure table] }

Deterministic + network-free (raster + census are committed). Needs rasterio; when
rasterio or the raster is absent, --check SKIP-passes (exit 3) like build_branch_peers.
    python3 build_contested_pop.py            # write the JSON
    python3 build_contested_pop.py --check    # verify byte-for-byte reproduce
"""
import argparse, json, math, os

from lib.fingerprint import branches_fingerprint

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
DATA = os.path.join(REPO, "platform", "data")
RASTER = os.path.join(REPO, "source-data", "worldpop_tha_2020_1km.tif")
OUT = os.path.join(DATA, "contested_pop.json")

RADIUS_M = 10000.0     # branch catchment radius (matches build_branch_population.py)
CONTEST_M = 2000.0     # a cell is contested when its centre is <= this from any rival
MLAT = 110540.0        # metres per degree latitude (same constant as the population builder)
MIN_POP = 25000        # top-list rank rule: only branches with >= this catchment population
TOP_N = 25             # most-contested records shipped (UI shows top 10)


def _load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def build():
    try:
        import rasterio
    except Exception:
        return None
    if not os.path.exists(RASTER):
        return None

    branches = _load(os.path.join(DATA, "branches.json"))
    census = _load(os.path.join(DATA, "competitors_census.json"))

    rivals, skipped = [], 0
    for it in census.get("items", []):
        lat, lng = it.get("lat"), it.get("lng")
        if lat is None or lng is None:
            skipped += 1
            continue
        rivals.append((float(lng), float(lat)))

    with rasterio.open(RASTER) as r:
        arr = r.read(1)
        nodata = r.nodata
        T = r.transform
        H, W = arr.shape
    # cell centre lng/lat from the affine transform (EPSG:4326, axis-aligned)
    # lng = T.c + (col+0.5)*T.a ; lat = T.f + (row+0.5)*T.e   (T.e < 0)
    x0, dx, y0, dy = T.c, T.a, T.f, T.e

    # ── pass 1: mark CONTESTED cells — centre within CONTEST_M of any rival ────────────
    contested = set()
    pad_lat = (CONTEST_M / MLAT) + abs(dy)
    for (rlng, rlat) in rivals:
        mlon = 111320.0 * math.cos(math.radians(rlat))
        pad_lng = (CONTEST_M / mlon) + abs(dx)
        c_lo = int(math.floor((rlng - pad_lng - x0) / dx))
        c_hi = int(math.ceil((rlng + pad_lng - x0) / dx))
        r_lo = int(math.floor((rlat + pad_lat - y0) / dy))   # dy<0 → +pad gives smaller row
        r_hi = int(math.ceil((rlat - pad_lat - y0) / dy))
        c0, c1 = max(0, min(c_lo, c_hi)), min(W, max(c_lo, c_hi) + 1)
        r0, r1 = max(0, min(r_lo, r_hi)), min(H, max(r_lo, r_hi) + 1)
        for row in range(r0, r1):
            clat = y0 + (row + 0.5) * dy
            dyy = (clat - rlat) * MLAT
            for col in range(c0, c1):
                if (row, col) in contested:
                    continue
                clng = x0 + (col + 0.5) * dx
                dxx = (clng - rlng) * mlon
                if dxx * dxx + dyy * dyy <= CONTEST_M * CONTEST_M:
                    contested.add((row, col))

    # ── pass 2: per branch, sum the 10km disc (pop10) + its contested subset ──────────
    # direct WorldPop raster sample; branch_population.json's shipped values instead
    # area-weight district populations (rasterio fallback), so the two do NOT match.
    deg_pad_lat = (RADIUS_M / MLAT) + abs(dy)
    rows = []
    tot_pop = tot_con = 0
    for b in branches:
        blng, blat = float(b["x"]), float(b["y"])
        mlon = 111320.0 * math.cos(math.radians(blat))
        deg_pad_lng = (RADIUS_M / mlon) + abs(dx)
        c_lo = int(math.floor((blng - deg_pad_lng - x0) / dx))
        c_hi = int(math.ceil((blng + deg_pad_lng - x0) / dx))
        r_lo = int(math.floor((blat + deg_pad_lat - y0) / dy))
        r_hi = int(math.ceil((blat - deg_pad_lat - y0) / dy))
        c0, c1 = max(0, min(c_lo, c_hi)), min(W, max(c_lo, c_hi) + 1)
        r0, r1 = max(0, min(r_lo, r_hi)), min(H, max(r_lo, r_hi) + 1)
        pop = con = 0.0
        for row in range(r0, r1):
            clat = y0 + (row + 0.5) * dy
            dyy = (clat - blat) * MLAT
            for col in range(c0, c1):
                v = arr[row, col]
                if nodata is not None and v == nodata:
                    continue
                if not (v > 0):
                    continue
                clng = x0 + (col + 0.5) * dx
                dxx = (clng - blng) * mlon
                if dxx * dxx + dyy * dyy <= RADIUS_M * RADIUS_M:
                    pop += float(v)
                    if (row, col) in contested:
                        con += float(v)
        rows.append([int(round(pop)), int(round(con))])
        tot_pop += pop
        tot_con += con

    # ── top-N most contested ground (share desc; only real catchments, pop10>=MIN_POP) ─
    cand = []
    for i, (pop, con) in enumerate(rows):
        if pop >= MIN_POP:
            cand.append((-(con / pop), -con, i))
    cand.sort()
    top = []
    for negshare, negcon, i in cand[:TOP_N]:
        pop, con = rows[i]
        b = branches[i]
        top.append({
            "i": i, "name": b.get("n"), "prov": b.get("v"),
            "district": b.get("d"), "region": b.get("r"),
            "pop": pop, "cpop": con, "pct": int(round(100.0 * con / pop)),
        })

    n_full = sum(1 for pop, con in rows if pop > 0 and con == pop)
    n_zero = sum(1 for pop, con in rows if pop > 0 and con == 0)
    meta = {
        "generated_by": "pipeline/build_contested_pop.py",
        "label": "CONTESTED POPULATION per branch — MEASURED overlay of the WorldPop 2020 1km "
                 "population raster and the merged measured competitor census: of each branch's "
                 "10km catchment population, how many people also live within %.0f km of a rival "
                 "branch. Pure geometry over two committed measured layers — no scores, no "
                 "synthesis." % (CONTEST_M / 1000.0),
        "objective": "Both objectives: #2 (a highly contested catchment is a fight for share, not "
                     "white space — weigh expansion elsewhere) and #1 (contested ground is where "
                     "rate/LTV competition bites the book first).",
        "provenance": {
            "population": "MEASURED — WorldPop 2020 gridded population (1km, UN-adjusted to the "
                          "official national total ~69.8M): source-data/worldpop_tha_2020_1km.tif. "
                          "pop10 sums every 1km cell whose centre falls within the branch's %.0f km "
                          "circle — a direct sample of the WorldPop raster. NOTE: this does NOT match "
                          "branch_population.json, whose shipped values are a district-population "
                          "AREA-WEIGHT estimate (build_branch_population.py's rasterio path was "
                          "unavailable and fell back); pop10 is the genuine raster count that the "
                          "area-weight figure only approximates." % (RADIUS_M / 1000.0),
            "rivals": "MEASURED — platform/data/competitors_census.json .items (%d usable points; "
                      "%d skipped for missing coords). Official store-locator networks for "
                      "Muangthai/Srisawad/Tidlor (measured-complete); Heng is a Google∪Overture "
                      "SAMPLE (lower bound)." % (len(rivals), skipped),
            "contested": "RULE, stated: a 1km cell is CONTESTED when its centre lies within %.0f km "
                         "of ANY census rival (equirectangular metres, same constant family as the "
                         "population builder). contested_pop sums the contested cells of the same "
                         "10km disc; share = contested_pop / pop10." % (CONTEST_M / 1000.0),
        },
        "vintage": "WorldPop 2020 (latest constrained 1km release committed to source-data); "
                   "competitor census as committed in competitors_census.json.",
        "radius_km": RADIUS_M / 1000.0,
        "contest_km": CONTEST_M / 1000.0,
        "top_rule": "top[] ranks branches by contested share desc (ties: contested people desc, "
                    "index asc), restricted to pop10 >= %d so tiny catchments cannot post "
                    "meaningless 100%%s — a stated editorial cutoff over measured values." % MIN_POP,
        "n_branches": len(rows),
        "n_rivals": len(rivals),
        "n_rivals_skipped": skipped,
        "n_cells_contested": len(contested),
        "n_fully_contested": n_full,
        "n_uncontested": n_zero,
        "national_contested_share_pct": round(100.0 * tot_con / tot_pop, 1) if tot_pop else None,
        "branches_fingerprint": branches_fingerprint(branches),
        "index_note": "rows[] is INDEX-ALIGNED to platform/data/branches.json (entry i <-> branch i), "
                      "identical to branch_population.json / rival_pressure.json.",
        "fields": {
            "rows[][0]": "pop10 — MEASURED WorldPop 2020 population inside the branch's 10km circle.",
            "rows[][1]": "contested_pop — MEASURED subset of pop10 in cells within %.0f km of any "
                         "census rival (always <= pop10). Share = rows[][1]/rows[][0]." % (CONTEST_M / 1000.0),
            "top[]": "top-%d most-contested branches (pop10 >= %d): i (branch index), name/prov/"
                     "district/region, pop, cpop, pct (rounded share)." % (TOP_N, MIN_POP),
        },
        "gaps": [
            "WorldPop models population from census + built-area + ancillary layers; it is the "
            "standard measured gridded estimate but still a model, not a headcount. Vintage 2020 — "
            "refresh when a newer year lands.",
            "The census misses Heng's full network (sample only) and ALL sub-scale local operators "
            "(the long tail facing the Q1-2026 BoT registration deadline) — contested share is a "
            "LOWER BOUND on the true contest.",
            "1km cells give ~±1-cell edge granularity on the 2km contest ring; a cell is all-in or "
            "all-out by its centre.",
        ],
        "inputs": ["branches.json (branch coordinates)",
                   "competitors_census.json (merged measured rival census)",
                   "source-data/worldpop_tha_2020_1km.tif (WorldPop 2020 1km raster)"],
    }
    return {"meta": meta, "rows": rows, "top": top}


def run(check=False):
    obj = build()
    if obj is None:
        if check:
            print("SKIP: rasterio or source-data/worldpop_tha_2020_1km.tif unavailable — "
                  "contested_pop not checkable (dependency gap, not data drift)")
            return 3
        print("missing dep/input: needs rasterio + source-data/worldpop_tha_2020_1km.tif.")
        return 1
    text = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    if check:
        if not os.path.exists(OUT) or open(OUT, encoding="utf-8").read() != text:
            print("DRIFT: %s" % os.path.relpath(OUT, REPO))
            return 1
        print("OK: contested_pop.json reproduces (%d branches, national contested share %s%%)"
              % (obj["meta"]["n_branches"], obj["meta"]["national_contested_share_pct"]))
        return 0
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(text)
    m = obj["meta"]
    print("wrote %d branches -> platform/data/contested_pop.json (%d rivals, %d contested cells, "
          "national contested share %s%%, %d fully contested / %d uncontested catchments)"
          % (m["n_branches"], m["n_rivals"], m["n_cells_contested"],
             m["national_contested_share_pct"], m["n_fully_contested"], m["n_uncontested"]))
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(
        description="contested population per branch (WorldPop 10km catchment x 2km rival rings)")
    ap.add_argument("--check", action="store_true")
    raise SystemExit(run(check=ap.parse_args().check))
