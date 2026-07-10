#!/usr/bin/env python3
"""
build_amphoe.py — DISTRICT (amphoe) intelligence engine
=======================================================
Province granularity masks ~10x within-province differences. This builds a
district-level layer for EVERY one of the 928 amphoe polygons in
source-data/th_amphoe.geojson — including amphoe where AutoX has ZERO branches
(the white-space targets) — by spatial join over national point layers.

Reuses build_province.py's point-in-polygon + bbox prefilter exactly.

For each amphoe polygon it computes, deterministically and network-free:
  - province_th, region, amphoe name (Thai if derivable from the branches that
    fall inside the polygon, else the English shapeName)
  - AutoX branch count (PIP of branches_final.json)
  - POI counts by type inside the polygon (PIP over osm_layers national points)
  - DIW factories + workers (prov|norm_district join — MEASURED at amphoe, but
    only resolvable for amphoe whose Thai district name we can read off branches)
  - province-inherited vehicles{car,pickup,moto,ev}, informal/formal employment,
    unemployment_rate (NSO Labour Force Survey), and an agri_stress proxy (clearly
    tagged province-inherited, NOT amphoe-measured)
Then two scores:
  - whitespace : demand proxy (POI footfall + DIW workers, log-normalized) MINUS
    AutoX saturation (branch count). Higher = more underserved. Works for 0-branch amphoe.
  - risk_proxy : province agri_stress + province unemployment + local collateral/merchant
    mix (ESTIMATED weighting over MEASURED unemployment_rate + agri_stress inputs).

Output: platform/data/amphoe.json, sorted by whitespace desc.

    python3 build_amphoe.py            # write platform/data/amphoe.json
    python3 build_amphoe.py --check    # verify committed output byte-reproduces
"""
import os, json, math, argparse, collections, sys

ROOT = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(ROOT)
SRC  = os.path.join(REPO, "source-data")
OUT  = os.path.join(REPO, "platform", "data", "amphoe.json")
sys.path.insert(0, ROOT)
from regionmap import canonical, REGION, norm_district

# POI layers in osm_layers.json -> short key used in output. Items are [lng, lat].
POI = {"ind": "industrial", "veh": "vehicle_commerce", "gold": "gold", "fmkt": "fresh_market",
       "bank": "bank", "cvs": "convenience", "rest": "restaurant", "super": "supermarket",
       "school": "school", "atm": "atm", "hotel": "hotel", "pharm": "pharmacy", "civic": "civic"}

# weights for the demand proxy (footfall): which POI types signal title-loan demand.
# merchant/retail footfall + vehicle commerce (collateral) + gold (pawn-adjacent) dominate.
DEMAND_W = {"ind": 1.0, "veh": 1.2, "gold": 1.5, "fmkt": 1.0, "bank": 0.6, "cvs": 0.4,
            "rest": 0.3, "super": 0.7, "school": 0.3}


def _load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def hav(la1, lo1, la2, lo2):
    R = 6371.0; p = math.pi / 180
    a = (0.5 - math.cos((la2 - la1) * p) / 2
         + math.cos(la1 * p) * math.cos(la2 * p) * (1 - math.cos((lo2 - lo1) * p)) / 2)
    return 2 * R * math.asin(math.sqrt(a))


def _rings(geom):
    return geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]


def _bbox(geom):
    xs, ys = [], []
    for poly in _rings(geom):
        for x, y in poly[0]:
            xs.append(x); ys.append(y)
    return min(xs), min(ys), max(xs), max(ys)


def _pip(x, y, ring):
    inside = False; n = len(ring); j = n - 1
    for i in range(n):
        xi, yi = ring[i]; xj, yj = ring[j]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-12) + xi):
            inside = not inside
        j = i
    return inside


def _contains(geom, x, y):
    for poly in _rings(geom):
        if _pip(x, y, poly[0]) and not any(_pip(x, y, h) for h in poly[1:]):
            return True
    return False


def _centroid(geom):
    xs, ys = [], []
    for poly in _rings(geom):
        for x, y in poly[0]:
            xs.append(x); ys.append(y)
    return round(sum(xs) / len(xs), 4), round(sum(ys) / len(ys), 4)


def build():
    master = _load(os.path.join(SRC, "branches_final.json"))
    amphoe = _load(os.path.join(SRC, "th_amphoe.geojson"))["features"]
    fbd    = _load(os.path.join(SRC, "factories_by_district.json"))["districts"]
    veh    = _load(os.path.join(SRC, "vehicles_by_province.json"))["provinces"]
    emp    = _load(os.path.join(SRC, "employment_by_province.json"))["provinces"]
    unemp_f = os.path.join(SRC, "unemployment_by_province.json")
    unemp  = _load(unemp_f)["provinces"] if os.path.exists(unemp_f) else {}
    osm    = _load(os.path.join(SRC, "osm_layers.json"))

    polys = [(f, _bbox(f["geometry"])) for f in amphoe]

    # ── province agri_stress (province-inherited proxy) ──────────────────────────
    # Primary source: platform/data/crop_stress.json — the richer per-province crop-
    # household stress index (price proxy × drought, scaled by crop_dependence, with
    # measured components). It ships agri_stress on a 0..1 scale; we rescale to 0-100
    # to keep the amphoe.json contract (the frontend reads amphoe agri_stress / risk_proxy
    # as 0-100). Inherited by every amphoe in the province — explicitly NOT amphoe-measured.
    # Fallback (only for provinces ABSENT from crop_stress.json, e.g. บึงกาฬ): the old
    # branch-level agri_pd province mean from the master (also 0-100).
    cs = _load(os.path.join(REPO, "platform", "data", "crop_stress.json"))["provinces"]
    prov_agri = {canonical(p["th"]): round((p.get("agri_stress") or 0) * 100, 1) for p in cs}
    # ── province household DTI (MEASURED NSO SES 2566, province-inherited) ────────
    # The one measured variable that best separates Isan (DTI 1.0-1.15) from the Central
    # belt (0.47-0.68) was absent from the district risk score — a Khon Kaen district and
    # a Suphanburi district with the same footprint scored the same despite a 2x leverage
    # difference (committee gap finding, 2026-07-10). Inherited per province, NOT
    # amphoe-measured; scaled DTI 0 -> 0, 1.2x -> 100 (Isan max observed 1.15).
    hr_f = os.path.join(REPO, "platform", "data", "household_risk_by_province.json")
    prov_dti = {}
    if os.path.exists(hr_f):
        for p in _load(hr_f)["provinces"]:
            if p.get("debt_to_income") is not None:
                prov_dti[canonical(p["province"])] = float(p["debt_to_income"])
    n_cropstress = len(prov_agri)
    prov_branch_mean = collections.defaultdict(list)
    for b in master:
        prov_branch_mean[canonical(b["prov"], b.get("district"))].append(b.get("agri_pd", 0))
    n_fallback_prov = 0
    for p, v in prov_branch_mean.items():
        if p and p not in prov_agri and v:
            prov_agri[p] = round(sum(v) / len(v), 1)
            n_fallback_prov += 1

    # ── spatial join: branches -> amphoe polygon (PIP, bbox prefilter) ───────────
    # branch_sid[i] = shapeID of the amphoe branch i (master order) falls inside.
    # A few branches sit just off a polygon (coast/border geometry) — those get a
    # nearest-centroid fallback below so EVERY branch maps to an amphoe (the client
    # district lens needs a total join). branch_pip flags true PIP vs fallback.
    poly_centroids = [(_centroid(f["geometry"]), f["properties"]["shapeID"]) for f in amphoe]
    branches_by_poly = collections.defaultdict(list)
    branch_sid = [None] * len(master)
    branch_pip = [False] * len(master)
    branch_join = 0
    for i, b in enumerate(master):
        x, y = b["lng"], b["lat"]
        for f, (x0, y0, x1, y1) in polys:
            if x0 <= x <= x1 and y0 <= y <= y1 and _contains(f["geometry"], x, y):
                branches_by_poly[f["properties"]["shapeID"]].append(b)
                branch_sid[i] = f["properties"]["shapeID"]
                branch_pip[i] = True
                branch_join += 1
                break
        if branch_sid[i] is None:
            # fallback: nearest amphoe centroid (geometric, ESTIMATED)
            (cxx0, cyy0), sid0 = min(
                poly_centroids, key=lambda c: hav(y, x, c[0][1], c[0][0]))
            branch_sid[i] = sid0

    # branch centroids per province for assigning province to ZERO-branch amphoe
    # (nearest branch's province). Branch amphoe get province from their branches.
    bpts = [(b["lat"], b["lng"], canonical(b["prov"], b.get("district"))) for b in master]

    # ── POI -> amphoe polygon (PIP, bbox prefilter). One pass per layer. ─────────
    # poi_counts[shapeID][shortkey] = count of that POI type inside the polygon.
    poi_counts = collections.defaultdict(lambda: collections.defaultdict(int))
    for sk, layer in POI.items():
        for lng, lat in osm.get(layer, []):
            for f, (x0, y0, x1, y1) in polys:
                if x0 <= lng <= x1 and y0 <= lat <= y1 and _contains(f["geometry"], lng, lat):
                    poi_counts[f["properties"]["shapeID"]][sk] += 1
                    break

    # ── assemble per-amphoe records ──────────────────────────────────────────────
    recs = []
    fac_attempt = 0; fac_join = 0
    for f in amphoe:
        sid = f["properties"]["shapeID"]
        en  = f["properties"]["shapeName"]
        geom = f["geometry"]
        rows = branches_by_poly.get(sid, [])
        cy, cx = None, None
        cxx, cyy = _centroid(geom)  # (lng, lat)

        # province + Thai amphoe name
        if rows:
            prov = collections.Counter(canonical(b["prov"], b.get("district")) for b in rows).most_common(1)[0][0]
            thai = collections.Counter(b["district"] for b in rows).most_common(1)[0][0]
            name = thai
            measured_name = True
        else:
            # zero-branch amphoe: province = nearest branch's province; name = English shapeName
            best = min(bpts, key=lambda t: hav(cyy, cxx, t[0], t[1]))
            prov = best[2]
            name = en
            measured_name = False
        region = REGION.get(prov, "Other")

        # DIW factories+workers — MEASURED at amphoe, joinable only when we have a
        # Thai district name (i.e. the amphoe has >=1 branch).
        fac = work = 0
        fac_measured = False
        if measured_name:
            fac_attempt += 1
            gd = fbd.get(f"{prov}|{norm_district(name, prov)}")
            if gd:
                fac, work = gd["fac"], gd["workers"]
                fac_measured = True
                fac_join += 1

        pc = poi_counts.get(sid, {})
        poi = {sk: pc.get(sk, 0) for sk in POI}

        pv = veh.get(prov) or {}
        ev = emp.get(prov) or {}

        recs.append({
            "id": sid, "name": name, "name_en": en, "province_th": prov, "region": region,
            "cx": cxx, "cy": cyy, "branches": len(rows),
            "poi": poi,
            "fac": fac, "workers": work,
            "fac_measured": fac_measured, "name_measured": measured_name,
            "veh": {"car": pv.get("car"), "pickup": pv.get("pickup"),
                    "moto": pv.get("moto"), "ev": pv.get("ev")},
            "informal": ev.get("informal"), "formal": ev.get("formal"),
            "unemployment_rate": (unemp.get(prov) or {}).get("unemployment_rate"),
            "debt_to_income": prov_dti.get(prov),
            "agri_stress": prov_agri.get(prov),
            # local merchant/collateral mix (mean of branch features in this amphoe,
            # if any) — used by risk_proxy. None when no branch sits here.
            "_coll": round(sum(b.get("collateral_density", 0) for b in rows) / len(rows), 1) if rows else None,
            "_merch": round(sum(b.get("merchant_pd", 0) for b in rows) / len(rows), 1) if rows else None,
        })

    # ── scores ───────────────────────────────────────────────────────────────────
    # demand proxy: weighted POI footfall + DIW workers, log-compressed so a few
    # giant amphoe don't swamp the scale, then 0-100 normalized.
    def demand_raw(r):
        foot = sum(DEMAND_W[sk] * r["poi"][sk] for sk in DEMAND_W)
        return math.log1p(foot) + 0.5 * math.log1p(r["workers"])

    draw = [demand_raw(r) for r in recs]
    dmin, dmax = min(draw), max(draw)
    drange = (dmax - dmin) or 1.0
    # saturation: branches per unit demand. whitespace = demand(0-100) minus a
    # saturation penalty scaled by branch count. 0-branch amphoe keep full demand.
    for r, dr in zip(recs, draw):
        demand100 = round((dr - dmin) / drange * 100, 1)
        # penalty grows with branch count but saturates (an amphoe already covered
        # by AutoX is low whitespace). log so 1->4 branches matters more than 10->13.
        sat = round(min(100, 28 * math.log1p(r["branches"])), 1)
        r["demand"] = demand100
        r["whitespace"] = round(max(0.0, demand100 - sat), 1)
        # risk_proxy (ESTIMATED weighting): province agri_stress + province unemployment
        # stress (NSO LFS unemployment_rate, capped at 3.0% -> 100 and scaled linearly —
        # 3.0% is above the observed national max of 3.59% is clipped, not extrapolated)
        # + local collateral/merchant mix. When no branch sits in the amphoe, fall back
        # to agri_stress + unemployment alone (same 2:1 ratio as the branch case's 0.4:0.2).
        ag = r["agri_stress"] or 0
        un = round(min(100.0, (r["unemployment_rate"] or 0) / 3.0 * 100), 1)
        dti = prov_dti.get(prov)
        dt = round(min(100.0, (dti or 0) / 1.2 * 100), 1)
        if r["_coll"] is not None:
            r["risk_proxy"] = round(0.3 * ag + 0.25 * dt + 0.2 * r["_coll"] + 0.1 * r["_merch"] + 0.15 * un, 1)
        else:
            r["risk_proxy"] = round(0.45 * ag + 0.3 * dt + 0.25 * un, 1)
        del r["_coll"]; del r["_merch"]

    recs.sort(key=lambda r: -r["whitespace"])

    # ── branch -> amphoe index (master order) ────────────────────────────────────
    # platform/data/branches.json is derived 1:1 from branches_final.json in the
    # same order (derive.py iterates the master and appends one record per branch),
    # so branch_amphoe[i] is the index into this (sorted) amphoe[] list for the
    # i-th branch. Lets the National map color each branch by its district scores
    # with a guaranteed total join — no fuzzy client-side name matching.
    sid_to_idx = {r["id"]: k for k, r in enumerate(recs)}
    branch_amphoe = [sid_to_idx[sid] for sid in branch_sid]
    n_fallback = sum(1 for p in branch_pip if not p)

    meta = {
        "generated_by": "pipeline/build_amphoe.py",
        "n_amphoe": len(recs),
        "n_amphoe_with_branch": sum(1 for r in recs if r["branches"] > 0),
        "n_amphoe_zero_branch": sum(1 for r in recs if r["branches"] == 0),
        "provenance": {
            "measured_at_amphoe": [
                "branches (point-in-polygon of branches_final.json into th_amphoe.geojson)",
                "poi counts by type (point-in-polygon of osm_layers.json — OSM, measured)",
                "fac/workers (DIW factories_by_district, prov|district join — MEASURED, "
                "only where the amphoe has a branch so a Thai district name is readable; "
                "see fac_measured flag per amphoe)",
            ],
            "province_inherited": [
                "veh{car,pickup,moto,ev} (DLT vehicles_by_province — every amphoe inherits its province total)",
                "informal/formal (NSO employment_by_province — province-inherited)",
                "unemployment_rate (NSO Labour Force Survey unemployment_by_province.json, percent, "
                "province-inherited, MEASURED; null when the source file is absent — graceful)",
                "agri_stress (platform/data/crop_stress.json per-province crop-household stress index — "
                "price proxy x drought scaled by crop_dependence, rescaled 0..1 -> 0-100; province-inherited, "
                "ESTIMATED. Provinces absent from crop_stress.json fall back to the province mean of branch "
                "agri_pd from the master.)",
            ],
            "name_note": "amphoe name is Thai (from branches inside it) where name_measured=true; "
                         "otherwise the English shapeName from th_amphoe.geojson.",
            "province_note": "zero-branch amphoe inherit province from the nearest AutoX branch "
                             "(geometric, ESTIMATED); branch amphoe take the majority province of their branches.",
        },
        "formulas": {
            "demand": "0-100 norm of log1p(sum(w*poi)) + 0.5*log1p(workers); "
                      "w = " + json.dumps(DEMAND_W, ensure_ascii=False),
            "whitespace": "max(0, demand - 28*log1p(branches)); higher = more underserved opportunity",
            "risk_proxy": "ESTIMATED weighting. 0.3*agri_stress + 0.25*dti_stress (MEASURED NSO SES 2566 "
                          "debt_to_income, province-inherited, scaled 0-1.2x -> 0-100, clipped) + "
                          "0.2*collateral_density + 0.1*merchant_pd "
                          "(branch-mean in amphoe) + 0.15*unemployment_stress (MEASURED NSO unemployment_rate, "
                          "linearly scaled 0-3.0% -> 0-100, clipped); falls back to 0.45*agri_stress + 0.3*dti_stress + "
                          "0.25*unemployment_stress for zero-branch amphoe (no collateral/merchant signal)",
        },
        "join_rates": {
            "branch_to_amphoe": f"{branch_join}/{len(master)}",
            "branch_amphoe_fallback": f"{n_fallback}/{len(master)} branches off any polygon, assigned nearest amphoe centroid (ESTIMATED)",
            "factories_to_amphoe": f"{fac_join}/{fac_attempt} (attempted only on branch amphoe with a Thai district name)",
            "agri_stress_from_crop_stress": f"{n_cropstress} provinces from crop_stress.json, "
                                            f"{n_fallback_prov} provinces fell back to branch agri_pd mean",
            "unemployment_to_province": f"{sum(1 for r in recs if r['unemployment_rate'] is not None)}/{len(recs)} "
                                        "amphoe with a province unemployment_rate (0 when unemployment_by_province.json is absent)",
        },
        "branch_amphoe_note": "branch_amphoe[i] = index into amphoe[] for the i-th branch in "
                              "platform/data/branches.json (same order as branches_final.json). "
                              "PIP join; coast/border misses use nearest amphoe centroid.",
        "sorted_by": "whitespace desc",
    }
    return {"meta": meta, "amphoe": recs, "branch_amphoe": branch_amphoe}, branch_join, len(master), fac_join, fac_attempt


def run(check=False):
    obj, bj, bn, fj, fa = build()
    text = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    if check:
        if not os.path.exists(OUT) or open(OUT, encoding="utf-8").read() != text:
            print(f"DRIFT: {os.path.relpath(OUT, REPO)}"); return 1
        print(f"OK: amphoe.json reproduces ({obj['meta']['n_amphoe']} amphoe)")
        return 0
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"wrote {obj['meta']['n_amphoe']} amphoe -> platform/data/amphoe.json")
    print(f"  branch->amphoe join: {bj}/{bn}")
    print(f"  factories->amphoe join: {fj}/{fa} (branch amphoe only)")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="district (amphoe) intelligence engine")
    ap.add_argument("--check", action="store_true")
    raise SystemExit(run(check=ap.parse_args().check))
