#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ingest_doae.py — MEASURED 2025 planted area by province (DOAE farmer registry).

DOAE's farmer_all webservice publishes per-province planted area (rai) by crop for the current year
(2568/2025), no key needed, reachable from any IP. This normalizes it into the canonical 77-province
layer the pipeline uses, mapping DOAE's crop columns to the pipeline's crop keys and converting rai->ha.
It supersedes the SPAM-2010 (~9km modelled, 15-year-old) MAGNITUDE with a measured current total, per
province — build_branch_cropland.py rescales each branch's SPAM spatial pattern to these totals.

    python3 ingest_doae.py --pull      # fetch DOAE live (Thai IP or any IP; no key) -> source-data/doae_raw.json
    python3 ingest_doae.py             # normalize source-data/doae_raw.json -> source-data/doae_planted_area.json
    python3 ingest_doae.py --check     # verify the normalized layer reproduces byte-exact

Provenance: MEASURED (DOAE farmer registration, YEAR 2568). Sugarcane is NOT in DOAE (it's OCSB) — that
crop stays on the SPAM baseline downstream.
"""
import argparse, json, os, sys, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from lib.regionmap import canonical

RAW = os.path.join(ROOT, "source-data", "doae_raw.json")
OUT = os.path.join(ROOT, "source-data", "doae_planted_area.json")
URL = "https://farmer.doae.go.th/webservice/farmer_all/get_data2dit"
RAI_PER_HA = 6.25

# pipeline crop key -> DOAE S_*_RAI area columns (summed). Sugarcane intentionally absent (OCSB, not DOAE).
CROP_COLS = {
    "rice":    ["S_RICE_1_RAI", "S_RICE_2_RAI"],
    "cassava": ["S_CASSAVA_RAI"],
    "maize":   ["S_CORN_RAI"],
    "oilpalm": ["S_PALM_RAI"],
    "rubber":  ["S_RUBBER_RAI"],
}

def _num(v):
    try: return float(v)
    except (TypeError, ValueError): return 0.0

def pull():
    with urllib.request.urlopen(URL, timeout=90) as r:
        data = r.read()
    with open(RAW, "wb") as f:
        f.write(data)
    print(f"pulled DOAE -> {RAW} ({len(data):,} B)")

def normalize():
    rows = json.load(open(RAW, encoding="utf-8"))["dataResult"]
    provinces, year = {}, None
    for row in rows:
        year = year or row.get("YEAR")
        prov = canonical(row.get("PLANT_PROVINCE_NAME", ""))
        if not prov:
            continue
        rec = provinces.setdefault(prov, {})
        for key, cols in CROP_COLS.items():
            ha = sum(_num(row.get(c)) for c in cols) / RAI_PER_HA
            rec[key] = round(rec.get(key, 0.0) + ha, 1)
    return {
        "meta": {
            "title": "MEASURED planted area by province (DOAE farmer registry)",
            "generated_by": "pipeline/ingest_doae.py",
            "source": "DOAE farmer_all webservice (farmer.doae.go.th), no key",
            "year_be": year, "unit": "hectares (converted from rai / 6.25)",
            "provenance": "MEASURED — DOAE farmer registration. Sugarcane absent (OCSB, not DOAE).",
            "crops": list(CROP_COLS),
            "n_provinces": len(provinces),
        },
        "provinces": dict(sorted(provinces.items())),
    }

def serialize(o): return json.dumps(o, ensure_ascii=False, indent=1)

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pull", action="store_true", help="fetch DOAE live -> source-data/doae_raw.json")
    ap.add_argument("--check", action="store_true", help="verify normalized layer reproduces byte-exact")
    args = ap.parse_args()
    for stream in (sys.stdout, sys.stderr):
        try: stream.reconfigure(encoding="utf-8")
        except Exception: pass

    if args.pull:
        pull()
        if not args.check:
            return
    if not os.path.exists(RAW):
        if args.check:
            print("ingest_doae.py --check: SKIP (source-data/doae_raw.json absent)"); sys.exit(3)
        sys.exit("source-data/doae_raw.json missing — run: python3 ingest_doae.py --pull")

    payload = serialize(normalize())
    if args.check:
        if not os.path.exists(OUT) or open(OUT, encoding="utf-8").read() != payload:
            sys.exit("ingest_doae.py --check: doae_planted_area.json drifted — run python3 pipeline/ingest_doae.py")
        print("ingest_doae.py --check: OK (byte-exact)")
        return
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(payload)
    obj = json.loads(payload)
    print(f"wrote {OUT} ({obj['meta']['n_provinces']} provinces, year BE {obj['meta']['year_be']})")
    nat = {}
    for rec in obj["provinces"].values():
        for k, v in rec.items():
            nat[k] = nat.get(k, 0) + v
    print("  national measured ha:", ", ".join(f"{k} {v:,.0f}" for k, v in sorted(nat.items(), key=lambda x: -x[1])))

if __name__ == "__main__":
    main()
