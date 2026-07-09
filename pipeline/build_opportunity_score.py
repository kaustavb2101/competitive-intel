#!/usr/bin/env python3
"""
build_opportunity_score.py — composite EXPANSION-OPPORTUNITY score per amphoe
============================================================================
Objective #2 (WHERE TO EXPAND). build_amphoe.py already scores demand /
white-space / risk per district, and crop_stress.json scores agri stress per
province, and competitors_national.json maps competitor branches nationwide.
This layer FUSES them into a single, transparent, 0-100 composite that answers
one question for the strategy team: "where do we open the next branch?"

The score is an ESTIMATED COMPOSITE. It blends MEASURED signals (white-space
from OSM footfall + AutoX saturation; competitor density by point-in-polygon)
with an ESTIMATED signal (province-inherited crop-household stress). Every
component is exposed per district in the output so the blend is auditable.

Per amphoe (keyed by the SAME shapeID build_amphoe.py uses) it combines:
  - whitespace      REQUIRED  underserved demand from platform/data/amphoe.json
                              (the `whitespace` field), normalized 0-100 across
                              all districts. Higher = more underserved. MEASURED.
  - agri_stress     REQUIRED  province crop-household stress from
                              platform/data/crop_stress.json (0..1 -> 0-100),
                              mapped to the district's province. ESTIMATED.
                              Province-inherited (NOT amphoe-measured).
  - competitor_gap  OPTIONAL  competitor scarcity. Point-in-polygon count of
                              platform/data/competitors_national.json (+ _overture
                              if present) into each amphoe polygon, normalized and
                              INVERTED (undercompeted district -> higher gap ->
                              better opportunity). MEASURED (best-effort census).
  - occupation_pull OPTIONAL  establishment density from
                              platform/data/amphoe_occupations.json if present
                              (dominant occupation + establishment total). MEASURED.
                              Skipped gracefully when the file is absent.

Composite = weighted sum of the AVAILABLE terms, with weights renormalized over
exactly the terms used (so a missing optional input does not silently deflate the
score). Weights and the list of inputs actually used are recorded in meta.

Output: platform/data/opportunity_score.json
  { meta:{weights, inputs_used, generated_with, ...},
    districts:[{id, name, province, score, components:{...}}] }  sorted score desc.

Deterministic + network-free.
    python3 build_opportunity_score.py            # write the JSON
    python3 build_opportunity_score.py --check     # verify byte-for-byte reproduce
"""
import os, json, math, argparse, sys

ROOT = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(ROOT)
DATA = os.path.join(REPO, "platform", "data")
OUT  = os.path.join(DATA, "opportunity_score.json")
sys.path.insert(0, ROOT)
from regionmap import canonical

# ── component weights (sum to 1.0 over the FULL set; renormalized per district
#    over whichever terms are actually available). Tuned for objective #2:
#    underserved demand leads, undercompeted-ness and agri stress refine it,
#    establishment pull is a light tie-breaker. ───────────────────────────────
WEIGHTS = {
    "whitespace":      0.45,   # MEASURED — underserved demand vs AutoX saturation
    "competitor_gap":  0.30,   # MEASURED — fewer competitors = more room
    "agri_stress":     0.15,   # ESTIMATED — province crop-household stress (demand for cash)
    "occupation_pull": 0.10,   # MEASURED — establishment density (commercial pull)
}

# The MERGED full census (official store-locators for Muangthai/Srisawad/Tidlor + Google/Overture
# sample for Heng — ~16,393 MEASURED rival branches), already deduped. Do NOT also list the raw
# national/overture samples — the census already contains them (would double-count).
COMPETITOR_FILES = ["competitors_census.json"]


def _load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


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


def _norm100(vals):
    """min-max to 0-100. Returns a function value->0..100 (constant 0 if flat)."""
    lo, hi = min(vals), max(vals)
    rng = (hi - lo) or 1.0
    return lambda v: (v - lo) / rng * 100.0


def build():
    amphoe = _load(os.path.join(DATA, "amphoe.json"))["amphoe"]
    cs     = _load(os.path.join(DATA, "crop_stress.json"))["provinces"]

    # province agri_stress 0..1 -> 0-100, keyed by canonical province name.
    prov_agri = {canonical(p["th"]): round((p.get("agri_stress") or 0) * 100, 1) for p in cs}

    # ── OPTIONAL competitor census: PIP every competitor point into amphoe polygons.
    # Requires the amphoe polygon geometry; rebuild the bbox/PIP index from the same
    # th_amphoe.geojson build_amphoe.py uses (keyed by the identical shapeID).
    comp_files_used = [f for f in COMPETITOR_FILES if os.path.exists(os.path.join(DATA, f))]
    comp_counts = None
    n_comp_points = 0
    if comp_files_used:
        geo = _load(os.path.join(REPO, "source-data", "th_amphoe.geojson"))["features"]
        polys = [(g["properties"]["shapeID"], g["geometry"], _bbox(g["geometry"])) for g in geo]
        comp_counts = {g["properties"]["shapeID"]: 0 for g in geo}
        for cf in comp_files_used:
            for it in _load(os.path.join(DATA, cf)).get("items", []):
                lng, lat = it.get("lng"), it.get("lat")
                if lng is None or lat is None:
                    continue
                n_comp_points += 1
                for sid, geom, (x0, y0, x1, y1) in polys:
                    if x0 <= lng <= x1 and y0 <= lat <= y1 and _contains(geom, lng, lat):
                        comp_counts[sid] += 1
                        break

    # ── OPTIONAL occupations: establishment total per amphoe (keyed by shapeID). ──
    occ_total = None
    occ_path = os.path.join(DATA, "amphoe_occupations.json")
    if os.path.exists(occ_path):
        occ = _load(occ_path)
        occ_recs = occ.get("districts") or occ.get("amphoe") or []
        tmp = {}
        def _estab(r):
            # establishment total per district; current schema uses "t", older guesses fall back.
            return (r.get("t") or r.get("establishments") or r.get("estab_total")
                    or r.get("total") or r.get("n_estab") or 0)
        if isinstance(occ_recs, dict):
            # "amphoe" is a MAP {shapeID: record} (the shipped schema).
            for sid, r in occ_recs.items():
                if isinstance(r, dict):
                    tmp[sid] = _estab(r)
        else:
            # list-of-records fallback (each record carries its own id).
            for r in occ_recs:
                if not isinstance(r, dict):
                    continue
                sid = r.get("id")
                if sid is not None:
                    tmp[sid] = _estab(r)
        if tmp:
            occ_total = tmp

    inputs_used = ["whitespace (amphoe.json, MEASURED)", "agri_stress (crop_stress.json, ESTIMATED)"]
    if comp_counts is not None:
        inputs_used.append("competitor_gap (" + " + ".join(comp_files_used) + ", MEASURED, PIP)")
    if occ_total is not None:
        inputs_used.append("occupation_pull (amphoe_occupations.json, MEASURED)")

    # ── normalizers across the district set ──────────────────────────────────────
    ws_n = _norm100([r["whitespace"] for r in amphoe])
    # competitor_gap: more competitors -> LOWER gap. Normalize count, then invert.
    if comp_counts is not None:
        cvals = [comp_counts.get(r["id"], 0) for r in amphoe]
        c_n = _norm100(cvals)
    if occ_total is not None:
        ovals = [math.log1p(occ_total.get(r["id"], 0)) for r in amphoe]
        o_n = _norm100(ovals)

    districts = []
    for r in amphoe:
        sid = r["id"]
        comps = {}
        # whitespace (REQUIRED)
        comps["whitespace"] = round(ws_n(r["whitespace"]), 1)
        # agri_stress (REQUIRED) — already 0-100, province-inherited
        comps["agri_stress"] = round(prov_agri.get(r["province_th"], r.get("agri_stress") or 0), 1)
        # competitor_gap (OPTIONAL) — inverted normalized count
        if comp_counts is not None:
            cc = comp_counts.get(sid, 0)
            comps["competitor_gap"] = round(100.0 - c_n(cc), 1)
            comps["_competitors"] = cc
        # occupation_pull (OPTIONAL)
        if occ_total is not None:
            comps["occupation_pull"] = round(o_n(math.log1p(occ_total.get(sid, 0))), 1)

        # weighted blend over AVAILABLE scored terms (renormalize weights).
        scored = {k: comps[k] for k in WEIGHTS if k in comps}
        wsum = sum(WEIGHTS[k] for k in scored) or 1.0
        score = round(sum(WEIGHTS[k] * comps[k] for k in scored) / wsum, 1)

        districts.append({
            "id": sid,
            "name": r["name"],
            "province": r["province_th"],
            "region": r["region"],
            "branches": r["branches"],
            "score": score,
            "components": comps,
        })

    districts.sort(key=lambda d: (-d["score"], d["id"]))

    # effective weights actually in play (renormalized over the available terms).
    active = [k for k in WEIGHTS if (k in ("whitespace", "agri_stress")
                                     or (k == "competitor_gap" and comp_counts is not None)
                                     or (k == "occupation_pull" and occ_total is not None))]
    wtot = sum(WEIGHTS[k] for k in active) or 1.0
    eff_weights = {k: round(WEIGHTS[k] / wtot, 3) for k in active}

    meta = {
        "generated_with": "pipeline/build_opportunity_score.py",
        "label": "ESTIMATED COMPOSITE — blends MEASURED white-space + competitor density "
                 "with ESTIMATED province crop-stress. A ranking aid for branch expansion "
                 "(objective #2), not a measured quantity. Every component is exposed per "
                 "district for honesty.",
        "objective": "Acquisition / where to expand — rank amphoe (districts) by expansion opportunity.",
        "n_districts": len(districts),
        "weights_full": WEIGHTS,
        "weights_effective": eff_weights,
        "inputs_used": inputs_used,
        "inputs_optional_absent": [f for f in COMPETITOR_FILES if f not in comp_files_used]
                                  + ([] if occ_total is not None else ["amphoe_occupations.json"]),
        "competitor_points_joined": n_comp_points,
        "id_note": "id is the th_amphoe.geojson shapeID — identical key to build_amphoe.py amphoe[].id.",
        "components_note": {
            "whitespace": "0-100 norm of amphoe.json whitespace (MEASURED demand minus AutoX saturation). higher = more underserved.",
            "agri_stress": "province crop-household stress from crop_stress.json (0..1 -> 0-100), province-inherited. ESTIMATED.",
            "competitor_gap": "100 minus 0-100 norm of competitor count (PIP). higher = fewer competitors = more room. MEASURED, best-effort census.",
            "occupation_pull": "0-100 norm of log1p(establishment total) from amphoe_occupations.json. MEASURED. present only if that file exists.",
            "_competitors": "raw competitor branch count inside the polygon (audit field).",
        },
        "score_formula": "score = sum(weight_k * component_k) / sum(weight_k) over available terms k (0-100).",
        "sorted_by": "score desc, then id asc (stable)",
    }
    return {"meta": meta, "districts": districts}


def run(check=False):
    obj = build()
    text = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    if check:
        if not os.path.exists(OUT) or open(OUT, encoding="utf-8").read() != text:
            print(f"DRIFT: {os.path.relpath(OUT, REPO)}"); return 1
        print(f"OK: opportunity_score.json reproduces ({obj['meta']['n_districts']} districts)")
        return 0
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"wrote {obj['meta']['n_districts']} districts -> platform/data/opportunity_score.json")
    print(f"  inputs used: {len(obj['meta']['inputs_used'])} ({', '.join(obj['meta']['weights_effective'].keys())})")
    top = obj["districts"][:5]
    for d in top:
        print(f"  {d['score']:5.1f}  {d['name']} ({d['province']})  comps={d['components']}")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="composite expansion-opportunity score per amphoe")
    ap.add_argument("--check", action="store_true")
    raise SystemExit(run(check=ap.parse_args().check))
