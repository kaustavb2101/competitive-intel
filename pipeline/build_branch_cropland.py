#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_branch_cropland.py — per-branch MEASURED-corrected crop land-use area.

Takes build_branch_agri's SPAM-2010 per-branch catchment crop-ha (the fine SPATIAL pattern) and
rescales each crop's MAGNITUDE to DOAE's measured 2025 province planted-area totals
(source-data/doae_planted_area.json, via ingest_doae.py). Result: precise, current per-branch cropland
hectares by crop — SPAM's within-province distribution, corrected to measured 2025 provincial magnitude
and vintage (SPAM is a 2010 ~9km model).

Factor per province per crop = DOAE_2025_ha / SPAM_province_ha (platform/data/crop_landuse.json).
Sugarcane keeps its SPAM value (DOAE has no sugarcane — it's OCSB). Factor clamps to a sane band and
falls back to 1.0 (pure SPAM) where DOAE or the SPAM denominator is absent/zero.

DETERMINISTIC + NETWORK-FREE. Carries --check; SKIP-passes (exit 3) when doae_planted_area.json is
absent (optional upstream) so the gate never breaks on a missing pull. Index-aligned to branches.json.

  python3 build_branch_cropland.py
  python3 build_branch_cropland.py --check
"""
import argparse, json, os, sys
from lib.fingerprint import branches_fingerprint
from lib.regionmap import canonical
from build_branch_agri import spam_crop_cells, cell_key, haversine_km, CROPS, RADIUS_KM

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
BRANCHES = os.path.join(ROOT, "platform", "data", "branches.json")
CROP_LANDUSE = os.path.join(ROOT, "platform", "data", "crop_landuse.json")
DOAE = os.path.join(ROOT, "source-data", "doae_planted_area.json")
OUT = os.path.join(ROOT, "platform", "data", "branch_cropland.json")

FACTOR_MIN, FACTOR_MAX = 0.1, 10.0   # clamp so a tiny SPAM denominator can't explode a branch's ha

def _load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)

def province_factors():
    """canonical prov -> {crop_key: DOAE/SPAM factor}. 1.0 where unavailable; rubber/sugarcane omitted."""
    spam = {canonical(p["province_th"]): p.get("crop_area_ha", {}) for p in _load(CROP_LANDUSE)["provinces"]}
    doae = _load(DOAE)["provinces"]   # keys already canonical (ingest_doae)
    factors = {}
    for prov, meas in doae.items():
        sp = spam.get(prov, {})
        f = {}
        for crop, meas_ha in meas.items():
            if crop == "rubber":       # SPAM has no rubber grid — can't rescale a per-branch rubber pattern
                continue
            s = sp.get(crop, 0.0)
            f[crop] = min(FACTOR_MAX, max(FACTOR_MIN, meas_ha / s)) if (s > 0 and meas_ha > 0) else 1.0
        factors[prov] = f
    return factors

def build():
    branches = _load(BRANCHES)
    branches = branches if isinstance(branches, list) else branches.get("items", branches)
    grid = {}
    for (lng, lat, ha) in spam_crop_cells():
        grid.setdefault(cell_key(lng, lat), []).append((lng, lat, ha))
    factors = province_factors()
    keys = [c["key"] for c in CROPS]
    nkey = len(keys)

    out = []
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
        pf = factors.get(canonical(b.get("v", "") or b.get("prov", "")), {})
        meas = [round(vec[k] * pf.get(keys[k], 1.0), 1) for k in range(nkey)]
        tot = round(sum(meas), 1)
        dom = max(range(nkey), key=lambda k: meas[k]) if tot > 0 else -1
        out.append({"ha": meas, "crop_ha": tot, "dom": dom,
                    "fac": [round(pf.get(keys[k], 1.0), 3) for k in range(nkey)]})

    corrected = sum(1 for b in branches
                    if canonical(b.get("v", "") or b.get("prov", "")) in factors)
    return {
        "meta": {
            "title": "Per-branch MEASURED-corrected crop land-use area (SPAM spatial x DOAE 2025 magnitude)",
            "generated_by": "pipeline/build_branch_cropland.py",
            "radius_km": RADIUS_KM,
            "crops": keys,
            "provenance": "SPAM-2010 modelled spatial pattern (ESTIMATED) rescaled per province to DOAE "
                          "farmer-registry MEASURED 2025 planted area (rai/6.25). Sugarcane uncorrected "
                          "(no DOAE, it's OCSB); rubber not spatialized here (SPAM has no rubber grid).",
            "factor_clamp": [FACTOR_MIN, FACTOR_MAX],
            "branches_fingerprint": branches_fingerprint(branches),
            "n_branches": len(branches),
            "n_province_corrected": corrected,
        },
        "branches": out,
    }

def serialize(o):
    return json.dumps(o, ensure_ascii=False, separators=(",", ":"))

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    for s in (sys.stdout, sys.stderr):
        try: s.reconfigure(encoding="utf-8")
        except Exception: pass
    if not os.path.exists(DOAE):
        if args.check:
            print("build_branch_cropland.py --check: SKIP (source-data/doae_planted_area.json absent)")
            sys.exit(3)
        sys.exit("doae_planted_area.json missing — run: python3 ingest_doae.py --pull && python3 ingest_doae.py")
    payload = serialize(build())
    if args.check:
        if not os.path.exists(OUT):
            # Not generated yet — the CI committee loop (Python 3.11) builds + commits it. SKIP so a
            # fresh PR doesn't fail before the layer is generated in the gate's own environment.
            print("build_branch_cropland.py --check: SKIP (branch_cropland.json not generated yet)")
            sys.exit(3)
        if open(OUT, encoding="utf-8").read() != payload:
            sys.exit("build_branch_cropland.py --check: branch_cropland.json drifted — run "
                     "python3 pipeline/build_branch_cropland.py")
        print("build_branch_cropland.py --check: OK (byte-exact)")
        return
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(payload)
    obj = json.loads(payload)
    m = obj["meta"]
    print(f"wrote {OUT} ({m['n_branches']} branches; {m['n_province_corrected']} joined to DOAE 2025)")

if __name__ == "__main__":
    main()
