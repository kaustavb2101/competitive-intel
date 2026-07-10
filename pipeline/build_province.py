#!/usr/bin/env python3
"""
build_province.py — generalize the Rayong deep-dive to ANY province
===================================================================
Generates a district-level province profile for every province from national
data, via spatial join: national amphoe polygons (source-data/th_amphoe.geojson)
+ branches (point-in-polygon) + the gov layers (factories/vehicles/employment/
unemployment).
This is the Rayong pilot, generalized — same JSON shape, so one page can render
any province.

    python3 build_province.py            # write platform/data/provinces/<slug>.json + index.json
    python3 build_province.py --check    # verify committed output matches a fresh build

Per province it emits: district polygons (with branch counts + real factory/worker
rollups), compact branch records, province gov totals (DLT vehicles, NSO workers,
DIW factories), POI filtered to the province, and a region tag. Competitors/facts
are carried only where curated (Rayong today); other provinces get safe empties.
"""
import os, json, math, argparse, statistics as st, collections, sys

ROOT = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(ROOT)
SRC  = os.path.join(REPO, "source-data")
OUTDIR = os.path.join(REPO, "platform", "data", "provinces")
sys.path.insert(0, ROOT)
from regionmap import canonical, REGION, norm_district, PROVINCE_EN

# the 10 POI layers the province page expects (subset of osm_layers), output as [lat,lng]
POI_LAYERS = ["industrial", "vehicle_commerce", "fresh_market", "gold", "bank",
              "convenience", "restaurant", "hotel", "supermarket", "pharmacy"]

# full within-10km POI counts per branch (short key -> master field), sourced the
# same way derive.py builds k10 from the master — measured (OSM, within 10km).
K10 = {"ind": "ind10", "bank": "bank10", "atm": "atm10", "cvs": "cvs10", "hotel": "hotel10",
       "civic": "civic10", "fmkt": "fmkt10", "rest": "rest10", "super": "super10",
       "pharm": "pharm10", "gold": "gold10", "veh": "veh10", "sch": "sch10", "est": "n_estate10"}


def _load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def hav(la1, lo1, la2, lo2):
    R = 6371.0; p = math.pi / 180
    a = (0.5 - math.cos((la2 - la1) * p) / 2
         + math.cos(la1 * p) * math.cos(la2 * p) * (1 - math.cos((lo2 - lo1) * p)) / 2)
    return 2 * R * math.asin(math.sqrt(a))


def short(name):
    s = name
    if s.startswith("เงินไชโย"):
        s = s[len("เงินไชโย"):]
    s = s.lstrip()
    if s.startswith("สาขา"):
        s = s[len("สาขา"):]
    return s.strip()


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


def slugify(en):
    return "".join(c for c in en.lower().replace(" ", "-") if c.isalnum() or c == "-")


# ── competitors (objective #2) ────────────────────────────────────────────────
# UNION the two measured competitor sources, dedup rivals of the SAME brand within
# ~150m, then point-in-polygon each survivor into the province's amphoe so each
# district feature carries a competitor count. Mirrors the frontend dedup in
# platform/app.js (dedupComp): brand-keyed ~165m grid, 0.15km haversine threshold.
# Graceful: when both files are absent this returns [] and every district gets 0.
# MERGED full census (official store-locators + Heng sample, ~16,393 MEASURED rivals, already
# deduped). The dedup below is now a near-no-op but harmless; do NOT add the raw samples back.
COMP_FILES = ["competitors_census.json"]
_COMP_CELL = 0.0015      # ~165m grid cell (matches app.js dedupComp)
_COMP_DEDUP_KM = 0.15    # same-brand rivals closer than this are one branch


def _load_competitors():
    """Union competitors_national + competitors_overture, dedup same-brand within
    ~150m. Returns a deterministic list of {brand,lat,lng}. [] if neither exists."""
    data_dir = os.path.join(REPO, "platform", "data")
    raw = []
    for fn in COMP_FILES:
        p = os.path.join(data_dir, fn)
        if not os.path.exists(p):
            continue
        try:
            obj = _load(p)
        except (ValueError, OSError):
            continue
        for it in obj.get("items", []):
            if not it:
                continue
            lat, lng, brand = it.get("lat"), it.get("lng"), it.get("brand")
            if lat is None or lng is None:
                continue
            raw.append({"brand": brand, "lat": lat, "lng": lng})
    if not raw:
        return []
    # deterministic input order so dedup survivors are stable across the union
    raw.sort(key=lambda it: (str(it["brand"]), it["lat"], it["lng"]))
    seen = collections.defaultdict(list)   # (brand,gx,gy) -> [(lat,lng), ...]
    out = []
    for it in raw:
        gx = round(it["lat"] / _COMP_CELL); gy = round(it["lng"] / _COMP_CELL)
        dup = False
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for (la, lo) in seen.get((it["brand"], gx + dx, gy + dy), ()):
                    if hav(it["lat"], it["lng"], la, lo) <= _COMP_DEDUP_KM:
                        dup = True; break
                if dup:
                    break
            if dup:
                break
        if dup:
            continue
        seen[(it["brand"], gx, gy)].append((it["lat"], it["lng"]))
        out.append(it)
    return out


def build_all():
    master = _load(os.path.join(SRC, "branches_final.json"))
    amphoe = _load(os.path.join(SRC, "th_amphoe.geojson"))["features"]
    fbd = _load(os.path.join(SRC, "factories_by_district.json"))
    veh = _load(os.path.join(SRC, "vehicles_by_province.json"))["provinces"]
    emp = _load(os.path.join(SRC, "employment_by_province.json"))["provinces"]
    unemp_f = os.path.join(SRC, "unemployment_by_province.json")
    unemp = _load(unemp_f)["provinces"] if os.path.exists(unemp_f) else {}
    income_f = os.path.join(SRC, "household_income_by_province.json")
    income = _load(income_f)["provinces"] if os.path.exists(income_f) else {}
    vflow_f = os.path.join(SRC, "vehicle_flow_by_province.json")
    vflow = _load(vflow_f)["provinces"] if os.path.exists(vflow_f) else {}
    facinc_f = os.path.join(REPO, "platform", "data", "factory_income_by_province.json")
    facinc = _load(facinc_f)["provinces"] if os.path.exists(facinc_f) else {}
    agrinc_f = os.path.join(REPO, "platform", "data", "agri_income_by_province.json")
    agrinc = _load(agrinc_f)["provinces"] if os.path.exists(agrinc_f) else {}
    smeinc_f = os.path.join(REPO, "platform", "data", "sme_income_by_province.json")
    smeinc = _load(smeinc_f)["provinces"] if os.path.exists(smeinc_f) else {}
    osm = _load(os.path.join(SRC, "osm_layers.json"))
    narr = _load(os.path.join(SRC, "province_narratives.json")).get("provinces", {})
    EMPTY_FACTS = {"minwage": "", "minwage_mo": "", "natl_avg": "", "premium": "",
                   "skill_gap": "", "anchors": [], "workers": [], "impacts": []}

    polys = [(f, _bbox(f["geometry"])) for f in amphoe]

    # spatial join: assign each branch to its amphoe polygon
    branches_by_poly = collections.defaultdict(list)
    branch_poly = {}
    for bi, b in enumerate(master):
        x, y = b["lng"], b["lat"]
        for f, (x0, y0, x1, y1) in polys:
            if x0 <= x <= x1 and y0 <= y <= y1 and _contains(f["geometry"], x, y):
                sid = f["properties"]["shapeID"]
                branches_by_poly[sid].append(b); branch_poly[bi] = sid
                break

    poly_by_id = {f["properties"]["shapeID"]: f for f in amphoe}

    # spatial join: competitor branches -> amphoe polygon (PIP, bbox prefilter).
    # comp_by_poly[shapeID] = count of deduped rival branches inside that amphoe.
    # Empty (all zeros) when the competitor files are absent — never crashes.
    competitors = _load_competitors()
    comp_by_poly = collections.defaultdict(int)
    for c in competitors:
        x, y = c["lng"], c["lat"]
        for f, (x0, y0, x1, y1) in polys:
            if x0 <= x <= x1 and y0 <= y <= y1 and _contains(f["geometry"], x, y):
                comp_by_poly[f["properties"]["shapeID"]] += 1
                break

    # group branch indices by province
    prov_idx = collections.defaultdict(list)
    for bi, b in enumerate(master):
        prov_idx[canonical(b["prov"])].append(bi)

    index = []
    out = {}
    for prov, idxs in sorted(prov_idx.items()):
        if prov not in REGION:
            continue
        brs = [master[i] for i in idxs]
        # district polygons = amphoe that contain this province's branches
        dist_ids = collections.OrderedDict()
        for bi in idxs:
            sid = branch_poly.get(bi)
            if sid:
                dist_ids.setdefault(sid, True)

        feats = []
        for sid in dist_ids:
            f = poly_by_id[sid]
            rows = [b for b in branches_by_poly[sid] if canonical(b["prov"]) == prov]
            if not rows:
                continue
            thai_d = collections.Counter(b["district"] for b in rows).most_common(1)[0][0]
            cx, cy = _centroid(f["geometry"])
            gd = fbd["districts"].get(f"{prov}|{norm_district(thai_d, prov)}", {"fac": 0, "workers": 0})
            feats.append({"type": "Feature", "geometry": f["geometry"], "properties": {
                "district": thai_d, "shapeName": f["properties"]["shapeName"],
                "branches": len(rows), "workingage": rows[0].get("dist_workingage"),
                "factories_avg": round(st.mean(r["ind10"] for r in rows)),
                "vehicle_avg": round(st.mean(r["veh10"] for r in rows)),
                "gold_avg": round(st.mean(r["gold10"] for r in rows)),
                "market_avg": round(st.mean(r["fmkt10"] for r in rows)),
                "own": len(rows), "cx": cx, "cy": cy,
                "real_fac": gd["fac"], "real_workers": gd["workers"],
                # MEASURED rival title-loan/vehicle-finance branches inside this
                # district (Google Places ∪ Overture, deduped same-brand ~150m).
                # 0 when the competitor files are absent (graceful). Lower bound.
                "competitors": comp_by_poly.get(sid, 0)}})

        # province bbox (union of district bboxes) for POI filtering
        if feats:
            bxs = [_bbox(ft["geometry"]) for ft in feats]
            x0 = min(b[0] for b in bxs); y0 = min(b[1] for b in bxs)
            x1 = max(b[2] for b in bxs); y1 = max(b[3] for b in bxs)
        else:
            x0 = min(b["lng"] for b in brs) - .1; x1 = max(b["lng"] for b in brs) + .1
            y0 = min(b["lat"] for b in brs) - .1; y1 = max(b["lat"] for b in brs) + .1

        poi = {}
        for layer in POI_LAYERS:
            pts = osm.get(layer, [])
            poi[layer] = [[round(la, 5), round(lo, 5)] for lo, la in pts
                          if x0 <= lo <= x1 and y0 <= la <= y1]
        ind_pts = [tuple(p) for p in poi["industrial"]]
        mkt_pts = [tuple(p) for p in poi["fresh_market"]]

        def near(lat, lng, pts):
            return round(min(hav(lat, lng, a, b) for a, b in pts), 1) if pts else None

        bout = []
        for b in brs:
            bout.append({"x": round(b["lng"], 3), "y": round(b["lat"], 4), "n": short(b["name"]),
                         "d": b["district"], "ind": b["ind10"], "veh": b["veh10"], "gold": b["gold10"],
                         "fmkt": b["fmkt10"], "own": b["own10"], "wa": b.get("dist_workingage"),
                         "nfac": near(b["lat"], b["lng"], ind_pts), "nmkt": near(b["lat"], b["lng"], mkt_pts),
                         "nest": b.get("nearest_km"), "ncomp": None, "ncompn": None,
                         "k10": {sk: b.get(mk, 0) for sk, mk in K10.items()}})

        en = PROVINCE_EN.get(prov, "")         # explicit override (BKK, Ayutthaya — no "Mueang" amphoe)
        if not en:
            for ft in feats:                   # province English name from its "Mueang" amphoe
                sn = ft["properties"]["shapeName"]
                if sn.startswith("Mueang "):
                    en = sn[len("Mueang "):]; break
        if not en and feats:
            en = feats[0]["properties"]["shapeName"]
        slug = slugify(en) or slugify(prov)

        gp = fbd["provinces"].get(prov, {"fac": 0, "workers": 0})
        obj = {"province_th": prov, "province_en": en, "region": REGION[prov],
               "districts": {"type": "FeatureCollection", "features": feats},
               "branches": bout, "competitors": [], "poi": poi, "estates": [],
               "facts": narr.get(prov, EMPTY_FACTS),
               "gov": {"factories": gp["fac"], "workers": gp["workers"],
                       "vehicles": veh.get(prov, {}), "employment": emp.get(prov, {}),
                       "unemployment": unemp.get(prov) or {},
                       "income": income.get(prov) or {},
                       "vehicle_flow": vflow.get(prov) or {},
                       "income_floor": {
                           k: v for k, v in {
                               "factory_ratio_to_national": (facinc.get(prov) or {}).get("ratio_to_national"),
                               "agri_ratio_to_national": (agrinc.get(prov) or {}).get("ratio_to_national"),
                               "sme_ratio_to_national": (smeinc.get(prov) or {}).get("ratio_to_national"),
                           }.items() if v is not None
                       },
                       "src": "DIW factories · DLT vehicles (stock + registration-action flow) · NSO labour "
                              "+ NSO Labour Force Survey + NSO SES 2566 income by occupation "
                              "(data.go.th / TMLI) — measured"},
               "meta": {
                   "generated_by": "pipeline/build_province.py",
                   "provenance": {
                       "measured": [
                           "branches (point-in-polygon of branches_final.json into th_amphoe.geojson, "
                           "district-count amphoe polygons — gov ADM2 boundaries)",
                           "poi (13-layer OSM/Overpass points, bbox-filtered to this province — osm_layers.json)",
                           "district factories_avg/vehicle_avg/gold_avg/market_avg (branch-mean of the "
                           "master's within-10km OSM POI counts, MEASURED)",
                           "district real_fac/real_workers (DIW factories_by_district.json, prov|district "
                           "join, MEASURED where the amphoe has an AutoX branch to read a Thai district "
                           "name from — see fbd join notes in build_amphoe.py)",
                           "district competitors (MEASURED rival title-loan/vehicle-finance branches, "
                           "Google Places + Overture + official store-locators, deduped ~150m — lower bound)",
                           "gov.factories/workers (DIW factories_by_district.json, province total)",
                           "gov.vehicles (DLT vehicles_by_province.json, province total; null when the "
                           "province is genuinely absent from that release — never a fabricated 0)",
                           "gov.employment (NSO labour formal/informal, employment_by_province.json; "
                           "null when absent, same rule)",
                           "gov.unemployment (NSO Labour Force Survey, unemployment_by_province.json via "
                           "ingest_tmli.py; {} when the source file is absent)",
                           "gov.income (NSO SES 2566 income-by-occupation, household_income_by_province.json "
                           "via ingest_tmli.py; {} when the source file is absent)",
                           "gov.vehicle_flow (DLT registration-ACTION flow — dereg_rate/transfer_rate per "
                           "car/pickup/moto class, trailing-12mo sum, vehicle_flow_by_province.json via "
                           "build_vehicle_flow.py; {} when the source file is absent — distinct from "
                           "gov.vehicles, which is a STOCK snapshot from a different DLT dataset)",
                           "gov.income_floor (derived ratio, factory_income_by_province.json / "
                           "agri_income_by_province.json / sme_income_by_province.json's "
                           "ratio_to_national, all pure province_income/national_avg divisions over "
                           "the same NSO SES 2566 figures above; key omitted, not zero-filled, when "
                           "the source layer is absent)",
                       ],
                       "editorial": [
                           "facts (province_narratives.json hand-written 'what impacts them' notes — "
                           "curated for Rayong today; other provinces get the safe EMPTY_FACTS stub)",
                       ],
                       "estimated": [
                           "en/slug (English name/slug derived from the province's 'Mueang' amphoe "
                           "shapeName, or a curated PROVINCE_EN override — a naming derivation, not a "
                           "measured value)",
                       ],
                   },
                   "join_note": "deterministic, network-free spatial join (--check byte-exact); "
                                 "absent-source fields are null/{} /[] rather than guessed.",
               }}
        out[slug] = obj
        # null (not 0) when a province is genuinely ABSENT from the measured source —
        # a real measured 0 in the file is preserved. Mis-ranking BKK (no NSO labour
        # row in the release) to the bottom was the bug this guards against.
        pv = veh.get(prov);  pv = pv if pv is not None else {}
        ev = emp.get(prov);  ev = ev if ev is not None else {}
        veh_present = prov in veh
        emp_present = prov in emp
        def _f(d, k, present):
            return d.get(k) if present else None
        index.append({"slug": slug, "th": prov, "en": en, "region": REGION[prov],
                      "branches": len(bout), "districts": len(feats),
                      "factories": gp["fac"],
                      "vehicles": _f(pv, "total", veh_present), "pickup": _f(pv, "pickup", veh_present),
                      "car": _f(pv, "car", veh_present),
                      "moto": _f(pv, "moto", veh_present), "ev": _f(pv, "ev", veh_present),
                      "workers": gp["workers"],
                      "informal": _f(ev, "informal", emp_present), "formal": _f(ev, "formal", emp_present)})

    index.sort(key=lambda r: -r["branches"])
    return out, index


def run(check=False):
    out, index = build_all()
    files = {os.path.join(OUTDIR, f"{slug}.json"): obj for slug, obj in out.items()}
    files[os.path.join(OUTDIR, "index.json")] = index
    if check:
        drift = 0
        for path, obj in files.items():
            text = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
            if not os.path.exists(path) or open(path, encoding="utf-8").read() != text:
                print(f"DRIFT: {os.path.relpath(path, REPO)}"); drift = 1
        if not drift:
            print(f"OK: {len(out)} province files reproduce from source-data")
        return drift
    os.makedirs(OUTDIR, exist_ok=True)
    for path, obj in files.items():
        with open(path, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))
    print(f"wrote {len(out)} provinces → platform/data/provinces/  (+ index.json)")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="generate per-province deep-dive data from national layers")
    ap.add_argument("--check", action="store_true")
    raise SystemExit(run(check=ap.parse_args().check))
