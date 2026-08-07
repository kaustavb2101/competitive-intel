#!/usr/bin/env python3
"""
build_exit_whitespace.py — "competitor-exit white-space" cue per amphoe (district)
=================================================================================
Objective #2 (WHERE TO EXPAND). A REGULATORY-TAILWIND lens.

THE THESIS (regulatory tailwind, cited)
---------------------------------------
Thailand's BoT responsible-lending framework (notification 25680030) puts auto
title-loan operators under a personal-loan licence: >=THB 50m registered capital,
interest capped at 28%. The registration window closes **Q1 2026**; non-compliant,
sub-scale / informal lenders risk **forced exit**. Tighter supervision favours
scaled, compliant incumbents (MTC, SAWAD, Tidlor, Heng, and AutoX) and squeezes
small operators out — so **white-space may open as sub-scale rivals retreat**.
(docs/RESEARCH_DIGEST.md, section A; https://www.bot.or.th/.../25680030.pdf)

⛔ HONESTY — WHY THIS IS AN ESTIMATED PROXY, NOT A MEASUREMENT
-------------------------------------------------------------
The firms that will EXIT are exactly the sub-scale / informal operators we do
**not** census. platform/data/competitors_national.json is a best-effort Google
Places census of the FOUR BIG, COMPLIANT brands only (Heng, Muangthai, Tidlor,
Srisawad) — i.e. the incumbents who will *survive*, not the marginal players who
will leave. We therefore CANNOT directly measure where sub-scale rivals will exit;
inventing such a count would be fabrication.

What we CAN do honestly is INFER the opportunity surface: districts where AutoX
demand/white-space exists but the big-4 are ABSENT or SPARSE. In such districts the
implied incumbent serving local title-loan demand is, by elimination, a smaller /
local operator — exactly the kind of player most exposed to the Q1-2026 capital &
registration bar. So the cue answers:

  "Where could AutoX capture share if marginal operators exit?" — computed from
  (big-4 competitor scarcity) x (our white-space / demand). ESTIMATED proxy.

The exit-capture SCORE stays ESTIMATED: whether a marginal operator will actually
exit is not something we can measure. What we CAN now measure — and surface beside
the inferred proxy as a reality-check — is sub-scale rival PRESENCE: pico_operators
is a straight per-district tally of LICENSED PICO-finance (พิโกไฟแนนซ์) operators from
the FPO registry (pico_district.json). It grounds the "is a real sub-scale field
here?" question in data (high = the inference is corroborated; 0 = the residual
rests on big-4 absence alone). It does NOT feed the score, and because licensed PICO
operators are compliant it is presence, NOT a count of who will exit under Q1-2026.

METHOD (deterministic, network-free)
------------------------------------
Per amphoe (keyed by the SAME th_amphoe.geojson shapeID build_amphoe.py uses):
  - big4_competitors   MEASURED  point-in-polygon count of competitors_national.json
                                 (+ _overture if present) into the polygon. The
                                 big-4 footprint = the *surviving* incumbents.
  - demand             MEASURED  amphoe.json demand (OSM footfall + workers), 0-100.
  - whitespace         MEASURED  amphoe.json whitespace (demand minus AutoX
                                 saturation), 0-100.
  - sub_scale_proxy    ESTIMATED 0-100. HIGH where demand exists but the big-4 are
                                 thin -> the residual market is likely served by
                                 sub-scale operators (the exit candidates).
                                 = demand_norm * (1 - big4_share), where big4_share
                                 is the polygon's big-4 count normalised 0..1 across
                                 districts (so 0 big-4 -> full residual).
  - exit_capture_score ESTIMATED 0-100. The headline cue:
                                 0.5*sub_scale_proxy + 0.5*whitespace_norm.
                                 HIGH = real underserved demand AND a thin big-4
                                 footprint = best place to capture share if the
                                 marginal local operator exits under Q1-2026.
  - pico_operators      MEASURED  per-district tally of LICENSED PICO-finance
                                 operators (pico_district.json, FPO registry) — a
                                 real sub-scale non-bank lender class, joined by
                                 "province_th|amphoe". A CROSS-CHECK on the inferred
                                 sub_scale_proxy (high = a real sub-scale field backs
                                 the inference; 0 = the residual rests on big-4
                                 absence alone). Does NOT feed the score; licensed
                                 operators are compliant, so it is rival PRESENCE,
                                 not a count of who will exit.

Every component is exposed per district so the blend is auditable. We DELIBERATELY
exclude districts with zero measured demand (nothing to capture) from the ranked
head, but keep all 928 in the output for completeness.

Output: platform/data/exit_whitespace.json
  { meta:{label, regulatory_citation, provenance, formulas, ...},
    districts:[{id, name, province, region, branches,
                exit_capture_score, components:{...}}] }  sorted score desc.

    python3 build_exit_whitespace.py            # write the JSON
    python3 build_exit_whitespace.py --check     # verify byte-for-byte reproduce
"""
import os, json, math, argparse, sys

ROOT = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(ROOT)
DATA = os.path.join(REPO, "platform", "data")
OUT  = os.path.join(DATA, "exit_whitespace.json")

# The MERGED full census (official store-locators for Muangthai/Srisawad/Tidlor + Google/Overture
# sample for Heng — ~16,393 MEASURED rival branches), already deduped. Do NOT also list the raw
# national/overture samples — the census already contains them (would double-count).
COMPETITOR_FILES = ["competitors_census.json"]

# MEASURED cross-check for the ESTIMATED sub_scale_proxy: pico_district.json is a per-district tally
# of LICENSED PICO-finance (พิโกไฟแนนซ์) operators — a real sub-scale non-bank lender class — from the
# FPO registry. Keyed "province_th|amphoe", exactly the (province_th, name) pair amphoe.json carries,
# so the join is byte-exact. It does NOT feed the score (the exit+capture leap stays inferred); it is
# surfaced beside the proxy so a reader can see where the inferred residual is backed by a real
# sub-scale field vs where it rests on big-4 absence alone. Licensed PICO operators are compliant, so
# this measures sub-scale rival PRESENCE, not which operators will exit. Committed + deterministic.
PICO_DISTRICT_FILE = "pico_district.json"


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


def _norm01(vals):
    """min-max to 0..1. Returns a function value->0..1 (constant 0 if flat)."""
    lo, hi = min(vals), max(vals)
    rng = (hi - lo) or 1.0
    return lambda v: (v - lo) / rng


def build():
    amphoe = _load(os.path.join(DATA, "amphoe.json"))["amphoe"]

    # ── MEASURED sub-scale-rival cross-check: licensed PICO-finance operators per district. ──
    #    Keyed "province_th|amphoe" == amphoe.json (province_th, name); a district absent from the
    #    tally has 0 RESOLVED operators. We carry the layer's resolution_pct into meta so the 0s are
    #    honest (a small share of operators do not resolve to a district and are not double-guessed).
    pico_by_key, pico_meta = {}, {}
    pico_path = os.path.join(DATA, PICO_DISTRICT_FILE)
    if os.path.exists(pico_path):
        pj = _load(pico_path)
        pico_meta = pj.get("meta", {})
        for k, v in (pj.get("by_district") or {}).items():
            pico_by_key[k] = int(v.get("total", 0))

    # ── big-4 competitor census: PIP every point into amphoe polygons (same key
    #    build_amphoe.py / build_opportunity_score.py use). MEASURED, best-effort. ──
    comp_files_used = [f for f in COMPETITOR_FILES if os.path.exists(os.path.join(DATA, f))]
    comp_counts = {}
    n_comp_points = 0
    brands_seen = set()
    if comp_files_used:
        geo = _load(os.path.join(REPO, "source-data", "th_amphoe.geojson"))["features"]
        polys = [(g["properties"]["shapeID"], g["geometry"], _bbox(g["geometry"])) for g in geo]
        comp_counts = {g["properties"]["shapeID"]: 0 for g in geo}
        for cf in comp_files_used:
            obj = _load(os.path.join(DATA, cf))
            for it in obj.get("items", []):
                if it.get("brand"):
                    brands_seen.add(it["brand"])
                lng, lat = it.get("lng"), it.get("lat")
                if lng is None or lat is None:
                    continue
                n_comp_points += 1
                for sid, geom, (x0, y0, x1, y1) in polys:
                    if x0 <= lng <= x1 and y0 <= lat <= y1 and _contains(geom, lng, lat):
                        comp_counts[sid] += 1
                        break

    # ── normalizers across the district set ──────────────────────────────────────
    dem_n = _norm01([a["demand"] for a in amphoe])
    ws_n  = _norm01([a["whitespace"] for a in amphoe])
    big4_n = _norm01([comp_counts.get(a["id"], 0) for a in amphoe]) if comp_counts else (lambda v: 0.0)

    districts = []
    n_pico_corroborated = 0   # districts where proxy>0 AND a measured PICO field is present
    for a in amphoe:
        sid = a["id"]
        big4 = comp_counts.get(sid, 0)
        d01 = dem_n(a["demand"])           # 0..1 demand
        w01 = ws_n(a["whitespace"])        # 0..1 whitespace
        b01 = big4_n(big4)                 # 0..1 big-4 footprint share

        # sub-scale residual proxy: demand that the big-4 do NOT cover.
        sub_scale = round(100.0 * d01 * (1.0 - b01), 1)
        # headline exit-capture cue: residual sub-scale demand + our white-space.
        score = round(0.5 * sub_scale + 0.5 * (100.0 * w01), 1)

        # MEASURED cross-check (does NOT feed the score): licensed PICO operators resolved here.
        pico_ops = pico_by_key.get("%s|%s" % (a["province_th"], a["name"]), 0)
        if sub_scale > 0 and pico_ops > 0:
            n_pico_corroborated += 1

        districts.append({
            "id": sid,
            "name": a["name"],
            "province": a["province_th"],
            "region": a["region"],
            "branches": a["branches"],
            "exit_capture_score": score,
            "components": {
                "sub_scale_proxy": sub_scale,
                "whitespace": round(a["whitespace"], 1),
                "demand": round(a["demand"], 1),
                "big4_competitors": big4,
                "pico_operators": pico_ops,
            },
        })

    districts.sort(key=lambda d: (-d["exit_capture_score"], d["id"]))

    meta = {
        "generated_with": "pipeline/build_exit_whitespace.py",
        "label": "ESTIMATED PROXY — competitor-exit white-space cue. Where AutoX could "
                 "CAPTURE SHARE if marginal sub-scale operators exit under the Q1-2026 "
                 "registration deadline. NOT a measurement of sub-scale operators (we do "
                 "not census them); inferred from big-4 scarcity x our demand/white-space.",
        "objective": "Acquisition / where to expand (objective #2) — a regulatory-tailwind lens.",
        "regulatory_citation": {
            "summary": "BoT responsible-lending framework (notification 25680030): auto "
                       "title-loan operators need a personal-loan licence (>=THB 50m capital, "
                       "28% interest cap). Registration window closes Q1 2026; non-compliant, "
                       "sub-scale / informal lenders risk forced exit. Tighter supervision "
                       "favours scaled compliant incumbents and squeezes small operators out, "
                       "so white-space may open as sub-scale rivals retreat.",
            "deadline": "Q1 2026",
            "confidence": "High",
            "sources": [
                "https://www.bot.or.th/content/dam/bot/fipcs/documents/FPG/2568/EngPDF/25680030.pdf",
                "https://netsoltech.com/blog/decoding-the-bot-mandate",
            ],
            "from": "docs/RESEARCH_DIGEST.md, section A (Conf: High)",
        },
        "honesty_caveat": "The operators that will EXIT are the sub-scale / informal lenders. "
                          "competitors_national.json is a best-effort census of the FOUR BIG, COMPLIANT "
                          "brands (Heng, Muangthai, Tidlor, Srisawad) — the incumbents who will SURVIVE "
                          "— so the exit-capture SCORE is still inferred from big-4 absence x demand and "
                          "stays ESTIMATED. What we CAN now measure is sub-scale rival PRESENCE: the "
                          "pico_operators component is a straight tally of LICENSED PICO-finance operators "
                          "in the district (pico_district.json, FPO registry), surfaced beside the "
                          "inferred sub_scale_proxy as a reality-check — high where a real sub-scale field "
                          "backs the inference, 0 where the residual rests on big-4 absence alone. It does "
                          "NOT feed the score, and because licensed PICO operators are compliant it "
                          "measures presence, not which operators will exit. Treat exit_capture_score as "
                          "ESTIMATED; treat pico_operators as MEASURED.",
        "n_districts": len(districts),
        "pico_crosscheck": {
            "component": "components.pico_operators",
            "provenance": "MEASURED",
            "source_file": PICO_DISTRICT_FILE,
            "source": pico_meta.get("source", "FPO licensed PICO-finance operator registry (per-district tally)"),
            "vintage": pico_meta.get("vintage"),
            "resolution_pct": pico_meta.get("resolution_pct"),
            "n_districts_proxy_corroborated": n_pico_corroborated,
            "note": "Licensed PICO operators are a sub-scale non-bank lender class and are compliant, so "
                    "this measures sub-scale rival PRESENCE, not exit. 0 = zero operators RESOLVED to the "
                    "district (the registry resolves ~resolution_pct of operators to a district; the rest "
                    "are counted in pico_district.json, not guessed here). Does NOT feed exit_capture_score.",
        },
        "competitor_census": {
            "files_used": comp_files_used,
            "brands_censused": sorted(brands_seen),
            "points_joined": n_comp_points,
            "note": "big-4 only; a lower bound (Places caps ~60/query/province), not a registry.",
        },
        "formulas": {
            "sub_scale_proxy": "100 * demand_norm * (1 - big4_share_norm); HIGH where demand "
                               "exists but big-4 footprint is thin -> residual market likely "
                               "served by sub-scale (exit-prone) operators. ESTIMATED.",
            "exit_capture_score": "0.5*sub_scale_proxy + 0.5*(100*whitespace_norm); HIGH = real "
                                  "underserved demand AND a thin big-4 footprint = best capture "
                                  "if a marginal local operator exits. ESTIMATED.",
            "norm": "min-max 0..1 across all 928 districts (demand, whitespace, big-4 count).",
        },
        "provenance": {
            "measured": [
                "big4_competitors (PIP of competitors_national.json into th_amphoe.geojson, MEASURED best-effort)",
                "demand, whitespace (platform/data/amphoe.json, MEASURED — OSM footfall + AutoX saturation)",
                "pico_operators (per-district tally of licensed PICO-finance operators, pico_district.json / "
                "FPO registry — MEASURED sub-scale rival presence; a cross-check, does NOT feed the score)",
            ],
            "estimated": [
                "sub_scale_proxy, exit_capture_score (inferred — see honesty_caveat)",
            ],
        },
        "id_note": "id is the th_amphoe.geojson shapeID — identical key to build_amphoe.py amphoe[].id.",
        "sorted_by": "exit_capture_score desc, then id asc (stable)",
    }
    return {"meta": meta, "districts": districts}


def run(check=False):
    obj = build()
    text = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    if check:
        if not os.path.exists(OUT) or open(OUT, encoding="utf-8").read() != text:
            print(f"DRIFT: {os.path.relpath(OUT, REPO)}"); return 1
        print(f"OK: exit_whitespace.json reproduces ({obj['meta']['n_districts']} districts)")
        return 0
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(text)
    m = obj["meta"]
    print(f"wrote {m['n_districts']} districts -> platform/data/exit_whitespace.json")
    print(f"  competitor census: {m['competitor_census']['points_joined']} pts, "
          f"brands={m['competitor_census']['brands_censused']}")
    for d in obj["districts"][:5]:
        c = d["components"]
        print(f"  {d['exit_capture_score']:5.1f}  {d['name']} ({d['province']})  "
              f"sub_scale={c['sub_scale_proxy']} ws={c['whitespace']} big4={c['big4_competitors']}")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="competitor-exit white-space cue per amphoe (ESTIMATED)")
    ap.add_argument("--check", action="store_true")
    raise SystemExit(run(check=ap.parse_args().check))
