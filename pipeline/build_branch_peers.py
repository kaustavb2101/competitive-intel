#!/usr/bin/env python3
"""
build_branch_peers.py — statistical-twin peer benchmark per branch (objective #1)
=================================================================================
branch_risk.json ranks branches by an absolute composite. But an absolute rank
can't separate "risky branch in a risky market" (expected, priced) from "risky
branch whose comparable markets are all calm" (a SIGNAL — something local is
off: collections, fraud, competition, staffing). This layer finds, for every
branch, its k statistical TWINS — the branches with the most similar MEASURED
market fingerprint anywhere else in the country — and flags the branches whose
estimated composite risk sits far above their twins'.

Twin matching (MEASURED features only, no estimated composites, so the match
cannot inherit the risk model's own assumptions):
  - log1p of the 14 k10 POI counts (industry, banks, ATMs, convenience, hotels,
    civic, fresh markets, restaurants, supermarkets, pharmacies, gold shops,
    vehicle shops, schools, establishments) — the 10km catchment fingerprint
  - log1p district factory count (DIW) and district workers
  - rainfall index, own-AutoX density (w = branches <=10km)
  - province household debt-to-income (NSO SES, MEASURED), weighted DTI_W x, so
    twins share the same household-leverage BACKDROP. Without this the deviation
    mostly re-discovers province-level DTI differences (composite_risk carries a
    province household component); with it, the deviation isolates what is
    BRANCH-LOCAL: occupation mix, segment tilt, local market anomalies.
  All z-standardized; twins = k nearest by Euclidean distance, EXCLUDING any
  branch within GEO_EXCL_KM (twins must be similar markets ELSEWHERE, so the
  comparison is market-vs-market, not neighborhood-vs-itself).

Outlier score (ESTIMATED — it compares the estimated composite_risk from
branch_risk.json against the twin group):
  dev = composite_risk - median(twin composite_risk)   (points, 0-100 scale)
  rz  = dev / (1.4826 * MAD(twin risks) + 1)     (robust z; +1 damps tiny-MAD blowups)
Outliers are ranked by dev (interpretable: "N points above its twins") and
gated on rz >= RZ_MIN so a wide twin spread can't fake a signal.

Deterministic + network-free (numpy, fixed inputs, no wall clock); --check
reproduces byte-for-byte. Published values rounded to 2dp.

Output: platform/data/branch_peers.json
  { meta:{...},
    branches:[{dev, rz, pm} x 2015]  INDEX-ALIGNED to branches.json,
    outliers:[top OUT_N by rz with names + 3 named twins for explainability] }
"""
import argparse
import json
import math
import os
import sys

try:
    import numpy as np
except ImportError:
    print("SKIP: numpy not installed (pip install --break-system-packages numpy) — "
          "cannot run build_branch_peers.py; this is a missing dependency, NOT data drift.",
          file=sys.stderr)
    raise SystemExit(3)

from lib.fingerprint import branches_fingerprint

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BRANCHES = os.path.join(REPO, "platform", "data", "branches.json")
BRISK = os.path.join(REPO, "platform", "data", "branch_risk.json")
HHRISK = os.path.join(REPO, "platform", "data", "household_risk_by_province.json")
OUT = os.path.join(REPO, "platform", "data", "branch_peers.json")

K = 15             # twins per branch
GEO_EXCL_KM = 25.0 # twins must be at least this far away (market-vs-market, not neighborhood)
OUT_N = 20         # published outlier rows
RZ_MIN = 2.0       # only publish outliers at least this many robust-sigmas above their twins
DTI_W = 3.0        # weight on the province-DTI feature: twins must share the leverage backdrop

K10_KEYS = ["ind", "bank", "atm", "cvs", "hotel", "civic", "fmkt", "rest",
            "super", "pharm", "gold", "veh", "sch", "est"]


def build():
    br = json.load(open(BRANCHES, encoding="utf-8"))
    riskj = json.load(open(BRISK, encoding="utf-8"))
    risks = np.array([r.get("composite_risk", 0.0) for r in riskj["branches"]], dtype=np.float64)
    n = len(br)
    assert len(risks) == n, "branch_risk.json not aligned to branches.json"
    hh = json.load(open(HHRISK, encoding="utf-8"))
    dti = {p["province"]: float(p.get("debt_to_income") or 0.0) for p in hh.get("provinces", [])}
    dti_med = float(np.median(list(dti.values()))) if dti else 0.0

    feats = []
    for b in br:
        k10 = b.get("k10") or {}
        row = [math.log1p(float(k10.get(k) or 0)) for k in K10_KEYS]
        row.append(math.log1p(float(b.get("dfac") or 0)))
        row.append(math.log1p(float(b.get("dwork") or 0)))
        row.append(float(b.get("rain") or 0.0))
        row.append(float(b.get("w") or 0))
        row.append(dti.get(b.get("v"), dti_med))  # province household DTI backdrop (NSO, measured)
        feats.append(row)
    X = np.array(feats, dtype=np.float64)
    mu = X.mean(axis=0)
    sd = X.std(axis=0)
    sd[sd == 0] = 1.0
    Z = (X - mu) / sd
    Z[:, -1] *= DTI_W  # leverage backdrop must match harder than any single POI count

    # feature distance (squared euclidean) + geographic exclusion, computed row-by-row with
    # elementwise ops only — NO matmul/BLAS, whose SIMD reduction order varies across CPUs and
    # would break the byte-exact --check gate between machines.
    lat = np.radians(np.array([b["y"] for b in br], dtype=np.float64))
    lng = np.radians(np.array([b["x"] for b in br], dtype=np.float64))
    clat = np.cos(lat)
    order = np.empty((n, K), dtype=np.int64)
    for i in range(n):
        d = ((Z - Z[i]) ** 2).sum(axis=1)
        geo_km = 6371.0 * np.sqrt((lat - lat[i]) ** 2 + (clat[i] * (lng - lng[i])) ** 2)  # equirect
        d[geo_km < GEO_EXCL_KM] = np.inf  # excludes self (distance 0) too
        order[i] = np.argsort(d, kind="stable")[:K]

    rows, cand = [], []
    for i in range(n):
        tw = order[i]
        tr = risks[tw]
        pm = float(np.median(tr))
        mad = float(np.median(np.abs(tr - pm)))
        dev = float(risks[i]) - pm
        rz = dev / (1.4826 * mad + 1.0)
        rows.append({"dev": round(dev, 2), "rz": round(rz, 2), "pm": round(pm, 2)})
        if rz >= RZ_MIN:
            cand.append((dev, rz, i, tw, pm, mad))

    cand.sort(key=lambda t: (-t[0], t[2]))
    outliers = []
    for dev, rz, i, tw, pm, mad in cand[:OUT_N]:
        b = br[i]
        outliers.append({
            "i": i, "name": b.get("n"), "prov": b.get("v"), "region": b.get("r"),
            "district": b.get("d"), "risk": round(float(risks[i]), 1),
            "peer_median": round(pm, 1), "dev": round(float(risks[i]) - pm, 1),
            "rz": round(rz, 2),
            "top_driver": (riskj["branches"][i] or {}).get("top_driver"),
            "twins": [{"name": br[j].get("n"), "prov": br[j].get("v"),
                       "risk": round(float(risks[j]), 1)} for j in tw[:3].tolist()],
        })

    meta = {
        "generated_by": "pipeline/build_branch_peers.py",
        "label": ("ESTIMATED PEER BENCHMARK — twins are matched on MEASURED market features only "
                  "(OSM 10km POI fingerprint, DIW factories, district workers, rainfall, own density); "
                  "the deviation compares the ESTIMATED composite_risk (branch_risk.json) against the twin group. "
                  "NOT a measured default rate; use as an audit-first triage list."),
        "method": (f"k={K} nearest branches by z-scored feature distance (province DTI weighted {DTI_W:g}x so twins "
                   f"share the leverage backdrop), excluding any branch within {GEO_EXCL_KM:.0f} km (twins are "
                   "similar markets ELSEWHERE). dev = risk - median(twin risks); rz = dev / (1.4826*MAD + 1). "
                   "Outliers ranked by dev, published at rz >= %.1f." % RZ_MIN),
        "features": K10_KEYS + ["dfac(log1p)", "dwork(log1p)", "rain", "w", "prov_dti(NSO,x%g)" % DTI_W],
        "params": {"k": K, "geo_excl_km": GEO_EXCL_KM, "out_n": OUT_N, "rz_min": RZ_MIN, "dti_w": DTI_W},
        "n_branches": n,
        "branches_fingerprint": branches_fingerprint(br),
        "n_outliers": len(outliers),
        "index_note": "branches[] is INDEX-ALIGNED to platform/data/branches.json (entry i <-> branch i). "
                      "dev = composite_risk minus twin median; rz = robust z vs twins; pm = twin median risk.",
        "sorted_by": "outliers: rz desc",
    }
    return {"meta": meta, "branches": rows, "outliers": outliers}


def run(check=False):
    obj = build()
    text = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    if check:
        if not os.path.exists(OUT) or open(OUT, encoding="utf-8").read() != text:
            print(f"DRIFT: {os.path.relpath(OUT, REPO)}")
            return 1
        print(f"OK: branch_peers.json reproduces ({obj['meta']['n_branches']} branches, "
              f"{obj['meta']['n_outliers']} outliers)")
        return 0
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(text)
    m = obj["meta"]
    print(f"wrote {m['n_branches']} peer rows, {m['n_outliers']} outliers -> platform/data/branch_peers.json")
    for o in obj["outliers"][:6]:
        tw = ", ".join(f"{t['name']}({t['risk']})" for t in o["twins"])
        print(f"  rz={o['rz']:>5}  {o['name']} ({o['prov']}) risk {o['risk']} vs twin median {o['peer_median']}"
              f" — twins: {tw}")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="statistical-twin peer benchmark per branch")
    ap.add_argument("--check", action="store_true")
    raise SystemExit(run(check=ap.parse_args().check))
