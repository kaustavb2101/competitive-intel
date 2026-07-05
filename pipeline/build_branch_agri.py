#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_branch_agri.py — per-branch AGRICULTURAL profile (crop exposure · price stress · drought ·
farm income), the granular deepening of the province-level crop_stress.json.

WHY
---
crop_stress.json is PROVINCE-level and prices its risk off a GLOBAL commodity proxy. This layer
makes agriculture BRANCH-granular (each branch's 10km catchment) and prices it off REAL Thai
OAE farm-gate prices — so "which farmers are getting squeezed" is answered per branch, with the
crops that are actually around that branch. Serves objective #1 (portfolio/PD risk) and #2 (farm
income → borrowing capacity → where to expand).

WHAT EACH BRANCH GETS (10km perimeter)
--------------------------------------
  * crops        — cropland hectares by crop from the SPAM grid (rice/cassava/maize/oilpalm/
                   sugarcane) + shares + dominant crop. Spatial, MEASURED-modeled (SPAM 2010).
  * price_yoy    — the branch's crop-mix-weighted farm-gate price YoY, from OAE ราคาที่เกษตรกรขายได้
                   (crop_prices.json — REAL Thai farm-gate, MEASURED), NOT the global proxy.
  * price_stress — 0-100, higher when the branch's crops are the ones with FALLING prices.
  * rain_anom / drought_stress — the branch's own 3-month rainfall anomaly (% of normal, HDX,
                   MEASURED); drought_stress rises as rain falls below normal.
  * income_est   — gross farm income proxy (Σ crop ha × yield × price), ESTIMATED from documented
                   Thai per-rai yield×price constants; a borrowing-capacity signal for acquisition.
  * agri_pressure — combined price+drought risk, DILUTED by how agricultural the perimeter is
                   (a city branch with no cropland reads ~0). The objective-#1 headline.

HONEST PROVENANCE — mixed, all labelled: crop mix ESTIMATED (SPAM model); price YoY MEASURED (OAE
farm-gate); rainfall MEASURED (HDX); income ESTIMATED (yield×price constants). No number is a
census; every number traces to a real source. Prices refresh when crop_prices.json is re-pulled.

DETERMINISTIC + NETWORK-FREE. All inputs committed (branches.json, branches_final.json,
spam2010_th_cropgrid.json, crop_prices.json). Carries --check; the gate runs it. INDEX-ALIGNED to
branches.json with a branches_fingerprint stamp.

  python3 build_branch_agri.py          # build/refresh platform/data/branch_agri.json
  python3 build_branch_agri.py --check  # byte-exact reproduce gate
"""
import argparse, json, math, os, sys, statistics

from fingerprint import branches_fingerprint
from regionmap import canonical

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
BRANCHES = os.path.join(ROOT, "platform", "data", "branches.json")
MASTER = os.path.join(ROOT, "source-data", "branches_final.json")
SPAM = os.path.join(ROOT, "source-data", "spam2010_th_cropgrid.json")
CROP_PRICES = os.path.join(ROOT, "source-data", "crop_prices.json")
OUT = os.path.join(ROOT, "platform", "data", "branch_agri.json")

RADIUS_KM = 10.0
CELL_DEG = 0.1
EARTH_KM = 6371.0
D2R = math.pi / 180.0

# SPAM crop columns (cells[2:7]) in order, with the label + the OAE crop_prices name-substring used
# to pull that crop's real farm-gate YoY, and a documented gross income per rai (฿/yr) for the
# income proxy (Thai national-average yield × farm-gate price; ESTIMATED, stated not fitted).
CROPS = [
    {"key": "rice",      "label": "Rice",       "oae": "ข้าวเปลือก",   "income_rai": 4050},
    {"key": "cassava",   "label": "Cassava",    "oae": "มันสำปะหลัง",  "income_rai": 8750},
    {"key": "maize",     "label": "Maize",      "oae": "ข้าวโพด",      "income_rai": 5600},
    {"key": "oilpalm",   "label": "Oil palm",   "oae": "ปาล์ม",        "income_rai": 14000},
    {"key": "sugarcane", "label": "Sugarcane",  "oae": "อ้อย",         "income_rai": 13200},
]
RAI_PER_HA = 6.25


def haversine_km(lng1, lat1, lng2, lat2):
    dlat = (lat2 - lat1) * D2R
    dlng = (lng2 - lng1) * D2R
    a = (math.sin(dlat / 2) ** 2
         + math.cos(lat1 * D2R) * math.cos(lat2 * D2R) * math.sin(dlng / 2) ** 2)
    return 2 * EARTH_KM * math.asin(min(1.0, math.sqrt(a)))


def cell_key(lng, lat):
    return (math.floor(lng / CELL_DEG), math.floor(lat / CELL_DEG))


def _load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def crop_price_yoy():
    """{crop_key: median OAE farm-gate YoY %} from crop_prices.json — REAL Thai farm-gate, refreshes
    when the pull refreshes. None for a crop with no priced series."""
    cp = _load(CROP_PRICES).get("commodities", {})
    out = {}
    for c in CROPS:
        ys = [v.get("yoy") for k, v in cp.items()
              if c["oae"] in k and isinstance(v.get("yoy"), (int, float))]
        out[c["key"]] = round(statistics.median(ys), 1) if ys else None
    return out


def spam_crop_cells():
    """[(lng, lat, [ha per CROPS])] for SPAM cells with any cropland."""
    s = _load(SPAM)
    g = s["meta"]["grid"]
    x0, y0, res = g["x0"], g["y0"], g["res_deg"]
    out = []
    for c in s["cells"]:
        ha = c[2:2 + len(CROPS)]
        if sum(ha) > 0:
            out.append((x0 + (c[0] + 0.5) * res, y0 - (c[1] + 0.5) * res, ha))
    return out


def build():
    branches = _load(BRANCHES)
    branches = branches if isinstance(branches, list) else branches.get("items", branches)
    master = _load(MASTER)
    rain = [b.get("rain_3mo_anom") for b in master] if len(master) == len(branches) else [None] * len(branches)

    cells = spam_crop_cells()
    grid = {}
    for (lng, lat, ha) in cells:
        grid.setdefault(cell_key(lng, lat), []).append((lng, lat, ha))

    yoy = crop_price_yoy()
    nkey = len(CROPS)

    # first pass: per-branch cropland ha vector, to set the intensity normaliser (P90 total ha)
    ha_vecs, totals = [], []
    for b in branches:
        lng, lat = b.get("x"), b.get("y")
        vec = [0.0] * nkey
        if lng is not None and lat is not None:
            cx, cy = cell_key(lng, lat)
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for (cl, ca, ha) in grid.get((cx + dx, cy + dy), ()):
                        if haversine_km(lng, lat, cl, ca) <= RADIUS_KM:
                            for k in range(nkey):
                                vec[k] += ha[k]
        ha_vecs.append(vec)
        totals.append(sum(vec))
    pos = sorted(t for t in totals if t > 0)
    p90 = pos[int(0.9 * (len(pos) - 1))] if pos else 1.0

    out_branches = []
    for i, b in enumerate(branches):
        vec = ha_vecs[i]
        tot = totals[i]
        shares = [round(v / tot, 3) if tot else 0.0 for v in vec]
        dom = max(range(nkey), key=lambda k: vec[k]) if tot else -1
        # crop-mix-weighted farm-gate YoY (skip crops with no price series; renormalise weights)
        wsum = sum(vec[k] for k in range(nkey) if yoy[CROPS[k]["key"]] is not None) or 0.0
        pyoy = (round(sum(vec[k] * yoy[CROPS[k]["key"]] for k in range(nkey)
                          if yoy[CROPS[k]["key"]] is not None) / wsum, 1)
                if wsum > 0 else None)
        price_stress = max(0.0, min(100.0, round(-(pyoy or 0.0) * 3.0, 1)))
        # drought: branch 3-month rainfall anomaly (% of normal); below 100 = dry
        ra = rain[i]
        rain_anom = round(ra, 1) if isinstance(ra, (int, float)) else None
        drought_stress = (max(0.0, min(100.0, round((100.0 - rain_anom) * 2.0, 1)))
                          if rain_anom is not None else None)
        # how agricultural is this perimeter (0-1) — dilutes the pressure for city branches
        intensity = min(1.0, tot / p90) if p90 else 0.0
        d_term = drought_stress if drought_stress is not None else 0.0
        agri_pressure = round((0.6 * price_stress + 0.4 * d_term) * intensity, 1)
        # gross farm income proxy (฿/yr) = Σ crop ha × rai/ha × income per rai
        income = int(round(sum(vec[k] * RAI_PER_HA * CROPS[k]["income_rai"] for k in range(nkey))))
        out_branches.append({
            "ha": [round(v) for v in vec],
            "sh": shares,
            "dom": dom,
            "crop_ha": round(tot),
            "price_yoy": pyoy,
            "price_stress": price_stress,
            "rain_anom": rain_anom,
            "drought_stress": drought_stress,
            "intensity": round(intensity, 3),
            "agri_pressure": agri_pressure,
            "income_est": income,
        })

    # national context for the meta
    stressed = sum(1 for x in out_branches if x["agri_pressure"] >= 25)
    return {
        "meta": {
            "title": "Per-branch agricultural profile (crop exposure · farm-gate price stress · "
                     "drought · farm income) — objective #1 + #2",
            "generated_by": "pipeline/build_branch_agri.py",
            "radius_km": RADIUS_KM,
            "crops": [{"key": c["key"], "label": c["label"]} for c in CROPS],
            "crop_price_yoy": yoy,
            "crop_price_source": "OAE ราคาที่เกษตรกรขายได้ (crop_prices.json) — REAL Thai farm-gate "
                                 "price YoY, median per crop. MEASURED (Thai), not the global proxy.",
            "provenance": {
                "crop_mix": "ESTIMATED — SPAM 2010 modelled 5-arcmin cropland, summed in the 10km perimeter.",
                "price_yoy": "MEASURED — OAE farm-gate price YoY, crop-mix-weighted per branch.",
                "rain_anom": "MEASURED — HDX 3-month rainfall anomaly (% of normal), per branch.",
                "income_est": "ESTIMATED — Σ crop ha × Thai national-average yield×price per rai (stated constants).",
                "agri_pressure": "ESTIMATED composite — 0.6·price_stress + 0.4·drought, diluted by cropland intensity.",
            },
            "income_constants_baht_per_rai": {c["key"]: c["income_rai"] for c in CROPS},
            "branches_fingerprint": branches_fingerprint(branches),
            "n_branches": len(branches),
            "n_agri_stressed": stressed,
            "label": "ESTIMATED composite over MEASURED price/rain inputs; a triage read, not a "
                     "measured default rate.",
        },
        "branches": out_branches,
    }


def serialize(obj):
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true",
                    help="verify the committed output reproduces byte-exact (no write)")
    args = ap.parse_args()

    payload = serialize(build())
    if args.check:
        if not os.path.exists(OUT):
            sys.exit("build_branch_agri.py --check: branch_agri.json missing — run build_branch_agri.py.")
        if open(OUT, encoding="utf-8").read() != payload:
            sys.exit("build_branch_agri.py --check: branch_agri.json drifted — re-run "
                     "python3 pipeline/build_branch_agri.py.")
        print("build_branch_agri.py --check: OK (byte-exact)")
        return

    with open(OUT, "w", encoding="utf-8") as f:
        f.write(payload)
    obj = json.loads(payload)
    m = obj["meta"]
    from collections import Counter
    dom = Counter(CROPS[b["dom"]]["label"] for b in obj["branches"] if b["dom"] >= 0)
    kb = os.path.getsize(OUT) / 1024.0
    print(f"wrote {OUT}  ({kb:.1f} KB)")
    print("  real farm-gate YoY:", ", ".join(f"{k} {v:+}" if v is not None else f"{k} n/a"
                                              for k, v in m["crop_price_yoy"].items()))
    print(f"  {m['n_agri_stressed']} branches at agri_pressure ≥ 25")
    print("  dominant crop across branches:")
    for lab, c in dom.most_common():
        print(f"    {lab:<12} {c:>4} branches")


if __name__ == "__main__":
    main()
