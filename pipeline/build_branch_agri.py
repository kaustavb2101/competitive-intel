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

from lib.fingerprint import branches_fingerprint
from lib.regionmap import canonical

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
BRANCHES = os.path.join(ROOT, "platform", "data", "branches.json")
MASTER = os.path.join(ROOT, "source-data", "branches_final.json")
SPAM = os.path.join(ROOT, "source-data", "spam2010_th_cropgrid.json")
CROP_PRICES = os.path.join(ROOT, "source-data", "crop_prices.json")
NABC_PRICES = os.path.join(ROOT, "source-data", "nabc_prices.json")   # LIVE prices (preferred)
# The consolidated Thai farm-gate layer: NABC's live dailies PLUS sugarcane's announced OCSB price,
# which no market quotes. Top preference — see crop_price_yoy().
FARMGATE_PRICES = os.path.join(ROOT, "source-data", "farmgate_prices.json")
NABC_AGRI = os.path.join(ROOT, "source-data", "nabc_agri.json")       # per-province households + land use
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
    """{crop_key: YoY %} + {crop_key: source}. PREFERS LIVE NABC daily prices (nabc_prices.json,
    agriapi.nabc.go.th — cloud-refreshable) per crop; falls back to the OAE farm-gate snapshot
    (crop_prices.json) for crops NABC doesn't carry (e.g. sugarcane). None where neither has it."""
    # OAE snapshot (median YoY per crop) — the fallback.
    cp = _load(CROP_PRICES).get("commodities", {})
    out, src = {}, {}
    for c in CROPS:
        rows = [v for k, v in cp.items()
                if c["oae"] in k and isinstance(v.get("yoy"), (int, float))]
        ys = [v["yoy"] for v in rows]
        if ys:
            out[c["key"]] = round(statistics.median(ys), 1)
            # STATE THE VINTAGE. crop_prices.json is an OAE snapshot stamped in Buddhist-era years
            # (2561/2562 = 2018/2019 CE) — seven years old. Labelling it only "snapshot" read as
            # recent, so sugarcane's +26.1% was sitting beside live NABC dailies as if it were a
            # current move. Fold BE->CE here (subtract 543) and say the year out loud.
            yrs = sorted({int(v["year_be"]) - 543 for v in rows
                          if str(v.get("year_be", "")).isdigit()})
            when = ("%d" % yrs[-1]) if len(yrs) == 1 else (
                "%d-%d" % (yrs[0], yrs[-1]) if yrs else "undated")
            src[c["key"]] = "OAE farm-gate snapshot (%s)" % when
        else:
            out[c["key"]] = None
            src[c["key"]] = None
    # NABC live overlay (wins where present).
    if os.path.exists(NABC_PRICES):
        nabc = _load(NABC_PRICES).get("crop_yoy", {})
        for c in CROPS:
            v = nabc.get(c["key"])
            if isinstance(v, (int, float)):
                out[c["key"]] = round(v, 1)
                src[c["key"]] = "NABC live daily"
    # Farm-gate layer overlay — wins over both, because it IS the NABC feed plus the crops NABC
    # cannot quote. This is what finally reaches SUGARCANE. Until 2026-08-01 cane was the one crop
    # here with no live source, so it kept the OAE snapshot's +26.1% — a 2019 number, of the WRONG
    # SIGN: the announced cane price is -17.9%. Every cane-dominant branch was carrying price
    # support that had reversed six years ago, which pushed its price_stress the wrong way.
    if os.path.exists(FARMGATE_PRICES):
        fg = _load(FARMGATE_PRICES)
        yoys = fg.get("crop_yoy", {})
        comm = fg.get("commodities", {})
        for c in CROPS:
            v = yoys.get(c["key"])
            if isinstance(v, (int, float)):
                out[c["key"]] = round(v, 1)
                src[c["key"]] = (comm.get(c["key"]) or {}).get("source") or "Thai farm-gate layer"
    return out, src


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

    yoy, yoy_src = crop_price_yoy()
    nkey = len(CROPS)

    # RUBBER overlay — SPAM has NO rubber, but it's Thailand's #2 farm crop (10.2M households). Bring
    # it in per-province from NABC farmer-family (household share) + NABC live rubber price YoY, so the
    # South/East rubber belt stops reading as low-agri. Province rubber-household share → a rubber
    # "cropland-equivalent" per branch that folds into price stress, intensity and income.
    prov_of = [canonical(b.get("v", "") or b.get("prov", "")) for b in branches]
    rubber_share = {}
    if os.path.exists(NABC_AGRI):
        ff = _load(NABC_AGRI).get("farmer_family", {})
        for prov, crops in ff.items():
            tot_hh = sum(crops.values()) or 1
            rubber_share[prov] = crops.get("ยางพารา", 0) / tot_hh
    rubber_yoy = None
    if os.path.exists(NABC_PRICES):
        v = _load(NABC_PRICES).get("crop_yoy", {}).get("rubber")
        rubber_yoy = round(v, 1) if isinstance(v, (int, float)) else None
    RUBBER_INCOME_RAI = 14000   # ฿/rai/yr gross (yield×farm-gate; documented, ESTIMATED)

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
        # rubber "cropland-equivalent" for this perimeter = province rubber-household share × the
        # 90th-pctile SPAM cropland (so a fully-rubber province branch weighs rubber like dense cropland).
        rshare = rubber_share.get(prov_of[i], 0.0)
        rubber_ha = rshare * p90
        # crop-mix-weighted farm-gate YoY over the 5 SPAM crops + rubber (skip crops with no price)
        num = sum(vec[k] * yoy[CROPS[k]["key"]] for k in range(nkey) if yoy[CROPS[k]["key"]] is not None)
        den = sum(vec[k] for k in range(nkey) if yoy[CROPS[k]["key"]] is not None)
        if rubber_yoy is not None and rubber_ha > 0:
            num += rubber_ha * rubber_yoy
            den += rubber_ha
        pyoy = round(num / den, 1) if den > 0 else None
        price_stress = max(0.0, min(100.0, round(-(pyoy or 0.0) * 3.0, 1)))
        # drought: branch 3-month rainfall anomaly (% of normal); below 100 = dry
        ra = rain[i]
        rain_anom = round(ra, 1) if isinstance(ra, (int, float)) else None
        drought_stress = (max(0.0, min(100.0, round((100.0 - rain_anom) * 2.0, 1)))
                          if rain_anom is not None else None)
        # how agricultural is this perimeter (0-1), now INCLUDING the rubber-equivalent so the rubber
        # belt reads as farming even where SPAM cropland is thin — dilutes the pressure for city branches
        intensity = min(1.0, (tot + rubber_ha) / p90) if p90 else 0.0
        d_term = drought_stress if drought_stress is not None else 0.0
        agri_pressure = round((0.6 * price_stress + 0.4 * d_term) * intensity, 1)
        # gross farm income proxy (฿/yr) = Σ crop ha × rai/ha × income per rai (+ rubber-equivalent)
        income = int(round(sum(vec[k] * RAI_PER_HA * CROPS[k]["income_rai"] for k in range(nkey))
                           + rubber_ha * RAI_PER_HA * RUBBER_INCOME_RAI))
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
            "rubber_share": round(rshare, 3),
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
            "crop_price_yoy_source": yoy_src,
            "crop_price_source": "PREFERS NABC live daily prices (agriapi.nabc.go.th, cloud-refreshable "
                                 "MEASURED market prices); falls back to the OAE farm-gate snapshot "
                                 "(crop_prices.json) per crop. Per-crop source in crop_price_yoy_source.",
            "provenance": {
                "crop_mix": "ESTIMATED — SPAM 2010 modelled 5-arcmin cropland, summed in the 10km perimeter.",
                "price_yoy": "MEASURED — NABC live daily / OAE farm-gate price YoY, crop-mix-weighted per branch.",
                "rubber": "MEASURED overlay — NABC farmer-family per-province rubber-household share × "
                          "NABC live rubber price YoY, added to price/intensity/income (SPAM has no rubber).",
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

    # newline="\n": the Windows default translates every \n to \r\n, which inflates the byte sizes
    # build_provenance.py censuses and diverges the local tree from the LF blob CI actually reads.
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
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
