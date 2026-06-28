#!/usr/bin/env python3
"""
derive.py — project the master into the deployable platform data
================================================================
Regenerates `platform/data/branches.json` + `platform/data/meta.json` from the
master inputs in `source-data/`, so "refresh the data" is one deterministic,
network-free command. This is the projection half of the recursive loop:
`autox_enrich_loop.py` recomputes the master (live sources), then calls this to
push the result to the app. See docs/NEXT_STEPS.md #6.

    python3 derive.py            # rebuild platform/data from source-data
    python3 derive.py --check    # build in memory, diff vs committed, exit 1 on drift

What is DERIVED here (mechanical, from source-data alone, verified byte-exact):
  branches.json            every field, all 2,015 records
  meta.board               passthrough of source-data/commodity_board.json
  meta.region n/agri/md/col branch count + rounded mean per region
  meta.estates own         AutoX branches within 10 km of each estate

What is CARRIED FORWARD unchanged (needs the enrich loop or is editorial — not
recoverable from source-data alone, so we never silently overwrite it):
  meta.region hi, meta.n_agri   "agri branch" counts embed the regional
                                livestock-income buffer (see PROGRESS_LOG)
  meta.mws, meta.cws            merchant / collateral white-space rankings
  meta.macro, meta.updated      editorial macro board + freshness stamp
"""
import os, sys, json, math, argparse

ROOT = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(ROOT)
SRC  = os.path.join(REPO, "source-data")
OUT  = os.path.join(REPO, "platform", "data")
sys.path.insert(0, ROOT)
from regionmap import norm_district   # shared district normalizer (Thai SARA-AM safe)

# fields carried straight from the master record into the compact branch record
DIRECT = {"v": "prov", "r": "region", "a": "agri_pd", "m": "merchant_demand",
          "c": "collateral_density", "w": "own10", "t": "tourism_score",
          "dem": "demand", "fmkt": "fmkt10", "veh": "veh10", "rain": "rain_3mo_anom"}
# meta fields that are not derivable from source-data alone (kept from current meta)
CARRY = ("mws", "cws", "macro", "n_agri", "updated")


def _load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def hav(la1, lo1, la2, lo2):
    """Great-circle distance in km."""
    R = 6371.0; p = math.pi / 180
    a = (0.5 - math.cos((la2 - la1) * p) / 2
         + math.cos(la1 * p) * math.cos(la2 * p) * (1 - math.cos((lo2 - lo1) * p)) / 2)
    return 2 * R * math.asin(math.sqrt(a))


# within-10km POI counts (master field -> short key) for the per-branch radar
POI10 = {"ind": "ind10", "bank": "bank10", "atm": "atm10", "cvs": "cvs10", "hotel": "hotel10",
         "civic": "civic10", "fmkt": "fmkt10", "rest": "rest10", "super": "super10",
         "pharm": "pharm10", "gold": "gold10", "veh": "veh10", "sch": "sch10", "est": "n_estate10"}


def build_branches(master):
    """Compact per-branch record the app loads (platform/data/branches.json)."""
    fbd = _load(os.path.join(SRC, "factories_by_district.json"))["districts"]
    out = []
    misses = {}
    for b in master:
        k10 = {sk: b.get(mk, 0) for sk, mk in POI10.items()}   # what's within 10km (OSM)
        key = f"{b['prov']}|{norm_district(b.get('district'), b['prov'])}"
        if key not in fbd:
            misses[key] = misses.get(key, 0) + 1
        gd = fbd.get(key, {"fac": 0, "workers": 0})
        # insertion order must match the committed file: x,y,n,v,r,o,a,m,c,w,t,dem,fmkt,veh,rain
        rec = {"x": round(b["lng"], 4), "y": round(b["lat"], 4), "n": b["name"][:34],
               "v": b["prov"], "r": b["region"], "o": round(b["opportunity"], 1),
               "a": b["agri_pd"], "m": b["merchant_demand"], "c": b["collateral_density"],
               "w": b["own10"], "t": b["tourism_score"], "dem": b["demand"],
               "fmkt": b["fmkt10"], "veh": b["veh10"], "rain": b["rain_3mo_anom"],
               "k10": k10, "dfac": gd["fac"], "dwork": gd["workers"], "d": b.get("district", "")}
        out.append(rec)
    if misses:
        n = sum(misses.values())
        print(f"  ⚠ {n} branches have no DIW factory-district match ({len(misses)} distinct keys); "
              f"dfac/dwork=0 for them: {', '.join(list(misses)[:6])}{' …' if len(misses) > 6 else ''}")
    return out


def build_meta(master, prev):
    """meta.json: derive what we can from source-data, carry the rest from `prev`."""
    board = _load(os.path.join(SRC, "commodity_board.json"))

    # region rollups — preserve the region order from the current meta, derive
    # count + rounded means, carry the `hi` agri-branch count (livestock-buffered).
    by_region = {}
    for b in master:
        by_region.setdefault(b["region"], []).append(b)

    def rmean(rows, field):
        return round(sum(r[field] for r in rows) / len(rows))

    region = []
    for r in prev["region"]:
        rows = by_region[r["r"]]
        region.append({"r": r["r"], "n": len(rows),
                       "agri": rmean(rows, "agri_pd"),
                       "md": rmean(rows, "merchant_demand"),
                       "col": rmean(rows, "collateral_density"),
                       "hi": r["hi"]})  # carried — needs the enrich-loop buffer logic

    # industrial estates — own = AutoX branches within 10 km; keep source order,
    # then stable-sort by own ascending (white-space first), as in the committed file.
    estates_src = _load(os.path.join(SRC, "estates.json"))   # [name, lat, lng, _]
    pts = [(b["lat"], b["lng"]) for b in master]
    estates = []
    for name, lat, lng, _ in estates_src:
        own = sum(1 for la, lo in pts if hav(lat, lng, la, lo) <= 10)
        estates.append({"name": name, "lat": lat, "lng": lng, "own": own})
    estates.sort(key=lambda e: e["own"])  # stable → preserves source order within ties

    meta = {"board": board, "region": region, "estates": estates}
    for k in CARRY:
        meta[k] = prev[k]
    # key order in the committed file: board, region, estates, mws, cws, macro, n_agri, updated
    return {"board": meta["board"], "region": meta["region"], "estates": meta["estates"],
            "mws": meta["mws"], "cws": meta["cws"], "macro": meta["macro"],
            "n_agri": meta["n_agri"], "updated": meta["updated"]}


def run(check=False):
    master = _load(os.path.join(SRC, "branches_final.json"))
    prev_meta = _load(os.path.join(OUT, "meta.json"))

    branches = build_branches(master)
    meta = build_meta(master, prev_meta)

    # branches.json is stored compact (no whitespace); meta.json uses default spacing
    targets = [(os.path.join(OUT, "branches.json"),
                json.dumps(branches, ensure_ascii=False, separators=(",", ":"))),
               (os.path.join(OUT, "meta.json"),
                json.dumps(meta, ensure_ascii=False))]

    if check:
        drift = False
        for path, text in targets:
            with open(path, encoding="utf-8") as f:
                if f.read() != text:
                    drift = True
                    print(f"DRIFT: {os.path.relpath(path, REPO)} differs from a fresh derive")
        if drift:
            return 1
        print("OK: platform/data/{branches,meta}.json reproduce exactly from source-data")
        return 0

    for path, text in targets:
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
    print(f"derived {len(branches)} branches + meta → platform/data/  "
          f"(carried forward: {', '.join(CARRY)} + region.hi)")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="project source-data → platform/data")
    ap.add_argument("--check", action="store_true",
                    help="verify the committed platform/data matches a fresh derive; exit 1 on drift")
    raise SystemExit(run(check=ap.parse_args().check))
