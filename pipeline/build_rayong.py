#!/usr/bin/env python3
"""
build_rayong.py — regenerate the Rayong province pilot from the master
=====================================================================
The Rayong deep-dive (platform/data/rayong_province.json) was a static, hand-built
file with no builder in the repo, so it drifted from the master: after the
province-key normalization it showed 57 branches / stale district rollups while
the master has 59. This rebuilds the data-driven parts deterministically so the
pilot can't drift again — the template for the eventual by-province generator.

    python3 build_rayong.py            # rebuild platform/data/rayong_province.json
    python3 build_rayong.py --check    # report drift vs committed (exit 1), don't write

Recomputed from source-data:  branch list (with nearest-POI / nearest-competitor
distances) and per-district rollups (counts + rounded-mean features).
Carried from the current file (curated/editorial, not master-derived):  poi,
estates, facts, and each district's geometry + shapeName + centroid + estate count.
Competitors come from source-data/rayong_competitors.json.
"""
import os, json, math, argparse, statistics as st

ROOT = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(ROOT)
SRC  = os.path.join(REPO, "source-data")
OUT  = os.path.join(REPO, "platform", "data", "rayong_province.json")
PROV = "ระยอง"


def _load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def hav(la1, lo1, la2, lo2):
    R = 6371.0; p = math.pi / 180
    a = (0.5 - math.cos((la2 - la1) * p) / 2
         + math.cos(la1 * p) * math.cos(la2 * p) * (1 - math.cos((lo2 - lo1) * p)) / 2)
    return 2 * R * math.asin(math.sqrt(a))


# full within-10km POI counts per branch (short key -> master field) — sourced the
# same way derive.py / build_province.py build k10. Measured (OSM, within 10km).
K10 = {"ind": "ind10", "bank": "bank10", "atm": "atm10", "cvs": "cvs10", "hotel": "hotel10",
       "civic": "civic10", "fmkt": "fmkt10", "rest": "rest10", "super": "super10",
       "pharm": "pharm10", "gold": "gold10", "veh": "veh10", "sch": "sch10", "est": "n_estate10"}


def short(name):
    """Strip the chain prefix to the branch's distinguishing label."""
    s = name
    if s.startswith("เงินไชโย"):
        s = s[len("เงินไชโย"):]
    s = s.lstrip()
    if s.startswith("สาขา"):
        s = s[len("สาขา"):]
    return s.strip()


def build():
    master = _load(os.path.join(SRC, "branches_final.json"))
    prev = _load(OUT)                       # carry curated/editorial blocks from current file
    comps = _load(os.path.join(SRC, "rayong_competitors.json"))
    fbd = _load(os.path.join(SRC, "factories_by_district.json"))   # real DIW factory/worker counts
    govp = fbd["provinces"].get(PROV, {"fac": 0, "workers": 0})
    veh = _load(os.path.join(SRC, "vehicles_by_province.json"))["provinces"].get(PROV, {})
    emp = _load(os.path.join(SRC, "employment_by_province.json"))["provinces"].get(PROV, {})
    ray = [b for b in master if b["prov"] == PROV]

    poi = prev["poi"]                        # OSM points — unaffected by the master fix
    ind = [tuple(p) for p in poi["industrial"]]      # [lat, lng]
    mkt = [tuple(p) for p in poi["fresh_market"]]
    cpts = [(c["lat"], c["lng"], c["brand"]) for c in comps]

    def nearest(lat, lng, pts):
        return round(min(hav(lat, lng, a, b) for a, b in pts), 1) if pts else None

    branches = []
    for b in ray:
        nc = min(((hav(b["lat"], b["lng"], a, o), br) for a, o, br in cpts), default=(None, None))
        branches.append({
            "x": round(b["lng"], 3), "y": round(b["lat"], 4), "n": short(b["name"]),
            "d": b["district"], "ind": b["ind10"], "veh": b["veh10"], "gold": b["gold10"],
            "fmkt": b["fmkt10"], "own": b["own10"], "wa": b.get("dist_workingage"),
            "nfac": nearest(b["lat"], b["lng"], ind), "nmkt": nearest(b["lat"], b["lng"], mkt),
            "nest": b.get("nearest_km"), "ncomp": round(nc[0], 1) if nc[0] is not None else None,
            "ncompn": nc[1],
            "k10": {sk: b.get(mk, 0) for sk, mk in K10.items()},
        })

    # per-district rollups: recompute numbers, carry geometry/labels/centroid/estate count
    bd = {}
    for b in ray:
        bd.setdefault(b["district"], []).append(b)
    carry = {f["properties"]["district"]: f for f in prev["districts"]["features"]}
    feats = []
    for d, f in carry.items():
        rows = bd.get(d, [])
        pr = dict(f["properties"])
        if rows:
            pr["branches"] = len(rows)
            pr["workingage"] = rows[0].get("dist_workingage")
            pr["factories_avg"] = round(st.mean(r["ind10"] for r in rows))
            pr["vehicle_avg"] = round(st.mean(r["veh10"] for r in rows))
            pr["gold_avg"] = round(st.mean(r["gold10"] for r in rows))
            pr["market_avg"] = round(st.mean(r["fmkt10"] for r in rows))
            pr["own"] = len(rows)
        gd = fbd["districts"].get(f"{PROV}|{d}", {"fac": 0, "workers": 0})   # real DIW counts
        pr["real_fac"] = gd["fac"]
        pr["real_workers"] = gd["workers"]
        feats.append({**f, "properties": pr})
    districts = {**prev["districts"], "features": feats}

    return {"districts": districts, "branches": branches,
            "competitors": [{"brand": c["brand"], "name": c["name"], "lat": c["lat"], "lng": c["lng"]} for c in comps],
            "poi": prev["poi"], "estates": prev["estates"], "facts": prev["facts"],
            "gov": {"factories": govp["fac"], "workers": govp["workers"],
                    "vehicles": veh, "employment": emp,
                    "src": "DIW factories · DLT vehicles · NSO labour (data.go.th) — measured"}}


def run(check=False):
    obj = build()
    text = json.dumps(obj, ensure_ascii=False)
    if check:
        if _load(OUT) != obj:
            print(f"DRIFT: {os.path.relpath(OUT, REPO)} differs from a fresh build "
                  f"({len(obj['branches'])} branches vs {len(_load(OUT)['branches'])} committed)")
            return 1
        print("OK: rayong_province.json matches a fresh build")
        return 0
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(text)
    nd = sum(len(v["branches"]) > 0 for v in [obj])  # noqa
    print(f"built rayong_province.json — {len(obj['branches'])} branches, "
          f"{len(obj['districts']['features'])} districts, {len(obj['competitors'])} competitors")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="regenerate the Rayong province pilot from the master")
    ap.add_argument("--check", action="store_true", help="report drift vs committed; exit 1; don't write")
    raise SystemExit(run(check=ap.parse_args().check))
