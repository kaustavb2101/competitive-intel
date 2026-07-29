#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_province_cropland.py — per-province MEASURED planted area by crop.

Distils the committed MEASURED DOAE farmer-registry planted area
(source-data/doae_planted_area.json, via ingest_doae.py) into a clean per-province
layer keyed on the province SLUG, so the 77-province deep-dive (province.html) can
show the authoritative MEASURED crop magnitude beside its ESTIMATED SPAM-2010 crop
lens — the province-level analogue of the per-branch SPAM x DOAE pairing already on
the branch popup (build_branch_cropland.py).

Why this exists (objective #1, crop / collateral portfolio risk): the province crop
lens only ever showed SPAM-2010's model-allocated SPATIAL pattern (ESTIMATED). The
measured MAGNITUDE — how many hectares of each crop are actually registered — was
carried only inside the per-branch catchment rescale, never surfaced per province.
Summing the per-branch 10km catchments would double-count overlaps, so the honest
per-province figure is DOAE's own province total, used here directly (no modelling).

Join: DOAE provinces are keyed on canonical Thai names; provinces/index.json gives
the canonical-Thai -> slug map. Output keyed by slug for a trivial browser lookup.

DETERMINISTIC + NETWORK-FREE. Carries --check; SKIP-passes (exit 3) when the DOAE
input is absent (optional upstream Thai-IP pull) so the gate never breaks on it.

  python3 build_province_cropland.py
  python3 build_province_cropland.py --check
"""
import argparse, json, os, sys
from lib.regionmap import canonical

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DOAE = os.path.join(ROOT, "source-data", "doae_planted_area.json")
INDEX = os.path.join(ROOT, "platform", "data", "provinces", "index.json")
OUT = os.path.join(ROOT, "platform", "data", "province_cropland.json")


def _load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def slug_map():
    """canonical province_th -> {slug, en} from the committed province index."""
    idx = _load(INDEX)
    items = idx if isinstance(idx, list) else (idx.get("provinces") or idx.get("items") or [])
    m = {}
    for it in items:
        th = it.get("th") or it.get("province_th")
        if not th:
            continue
        m[canonical(th)] = {"slug": it.get("slug"), "en": it.get("en") or it.get("province_en") or ""}
    return m


def build():
    doae = _load(DOAE)
    crops = doae["meta"].get("crops", ["rice", "cassava", "maize", "oilpalm", "rubber"])
    smap = slug_map()

    provinces = {}
    joined = 0
    for prov_th, meas in doae["provinces"].items():
        info = smap.get(canonical(prov_th))
        if not info or not info.get("slug"):
            continue  # a DOAE province with no matching slug (should be 0 — index covers all 77)
        joined += 1
        ha = {k: round(float(meas.get(k, 0.0)), 1) for k in crops}
        total = round(sum(ha.values()), 1)
        # dominant crop = largest measured planted area (only among crops with area)
        dom, dom_ha = "", 0.0
        for k in crops:
            if ha[k] > dom_ha:
                dom, dom_ha = k, ha[k]
        provinces[info["slug"]] = {
            "th": prov_th, "en": info["en"],
            "crops": ha, "total_ha": total,
            "dominant": dom, "dominant_ha": dom_ha,
        }

    # sort by slug for byte-deterministic output
    provinces = {s: provinces[s] for s in sorted(provinces)}
    return {
        "meta": {
            "title": "Per-province MEASURED planted area by crop (DOAE farmer registry 2568/2025)",
            "generated_by": "pipeline/build_province_cropland.py",
            "source": "DOAE farmer_all webservice (farmer.doae.go.th), via ingest_doae.py; no key",
            "provenance": "MEASURED — DOAE farmer-registration planted area, hectares (rai/6.25), "
                          "crop year 2568/2025. Sugarcane absent (registered with OCSB, not DOAE); "
                          "rubber included (DOAE carries it, unlike the SPAM spatial lens).",
            "unit": "hectares",
            "year_be": "2568",
            "vintage": "2568 (2025)",
            "crops": crops,
            "n_provinces": len(provinces),
        },
        "provinces": provinces,
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
            print("build_province_cropland.py --check: SKIP (source-data/doae_planted_area.json absent)")
            sys.exit(3)
        sys.exit("doae_planted_area.json missing — run: python3 ingest_doae.py --pull && python3 ingest_doae.py")
    payload = serialize(build())
    if args.check:
        if not os.path.exists(OUT):
            print("build_province_cropland.py --check: SKIP (province_cropland.json not generated yet)")
            sys.exit(3)
        if open(OUT, encoding="utf-8").read() != payload:
            sys.exit("build_province_cropland.py --check: province_cropland.json drifted — run "
                     "python3 pipeline/build_province_cropland.py")
        print("build_province_cropland.py --check: OK (byte-exact)")
        return
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(payload)
    m = json.loads(payload)["meta"]
    print(f"wrote {OUT} ({m['n_provinces']} provinces, MEASURED DOAE 2568/2025)")


if __name__ == "__main__":
    main()
