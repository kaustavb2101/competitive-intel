#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_amphoe_crops.py — DISTRICT-level crop exposure × drought (objective #1): the granularity
upgrade. OAE's nationwide satellite planted-area-by-amphoe surveys + OAE Zone 6's rich Eastern
ข้อมูลเอกภาพ tables, joined to OAE's district SPEI drought index.

  in : source-data/staging/amphoe_crops_national.json  OAE HQ satellite surveys (rice นาปี/นาปรัง,
                                                        rubber, cassava — amphoe grain, cited PDFs)
       source-data/staging/doae_amphoe_crops.json      OAE Zone 6 East detail (16 crops incl.
                                                        durian/mangosteen, 9 provinces)
       source-data/staging/drought_district.json       OAE SPEI per amphoe (2026-06 snapshot)
  out: platform/data/amphoe_crops.json                 per-district crop rows + drought join +
                                                        district crop-drought hotspot ranking

Provenance: planted areas MEASURED (OAE remote-sensing surveys / Zone-6 unified data, each row
carries its source PDF); drought MODELLED (OAE SPEI, ERA5-Land). The join is by normalized Thai
names (the source PDFs' font scrambles some vowel clusters — normalization collapses spacing
artifacts; unmatched rows are counted in meta, never guessed).

Known coverage limits (carried in meta, from the sources' own structure): cassava has no South
section; oil palm's source PDF is corrupted at origin; rubber covers 42/77. Zone-6 rows overlap
the national files for the East — kept as separate rows with distinct source tags (different
survey vintages; do NOT sum across sources).

Deterministic + network-free; `--check` byte-compares; SKIPs (exit 3) if staging absent.
"""
import argparse
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IN_NAT = os.path.join(ROOT, "source-data", "staging", "amphoe_crops_national.json")
IN_Z6 = os.path.join(ROOT, "source-data", "staging", "doae_amphoe_crops.json")
IN_DR = os.path.join(ROOT, "source-data", "staging", "drought_district.json")
OUT = os.path.join(ROOT, "platform", "data", "amphoe_crops.json")

_WS = re.compile(r"[\s​ ]+")


def norm(s):
    return _WS.sub("", s or "")


def build():
    nat = json.load(open(IN_NAT, encoding="utf-8"))
    z6 = json.load(open(IN_Z6, encoding="utf-8")) if os.path.exists(IN_Z6) else {"rows": []}
    dr = json.load(open(IN_DR, encoding="utf-8")) if os.path.exists(IN_DR) else {"districts": []}

    dmap = {}
    for d in dr.get("districts", []):
        dmap[(d.get("province_th"), norm(d.get("name_th")))] = d

    rows, unmatched = [], 0
    for src, doc in (("oae_satellite", nat), ("oae_zone6", z6)):
        for r in doc.get("rows", []):
            key = (r.get("province_th"), norm(r.get("amphoe_th")))
            d = dmap.get(key)
            if d is None:
                unmatched += 1
            rows.append({
                "province_th": r.get("province_th"),
                "amphoe_th": norm(r.get("amphoe_th")),
                "crop": r.get("crop"), "crop_th": r.get("crop_th"),
                "year": r.get("crop_year") or r.get("year"),
                "planted_rai": r.get("planted_rai"),
                "harvested_rai": r.get("harvested_rai"),
                "production_tons": r.get("production_tons"),
                "yield_kg_per_rai": r.get("yield_kg_per_rai"),
                "src": src, "source_file": r.get("source_file"),
                "spei": (d or {}).get("spei_2026_06"),
                "drought": None,
            })
    # classify drought like build_drought_district (keep the two consistent)
    for r in rows:
        s = r["spei"]
        if s is None or s == 0.0:
            continue
        r["drought"] = ("extreme" if s <= -2.0 else "severe" if s <= -1.5 else
                        "moderate" if s <= -1.0 else "normal" if s < 1.0 else "wet")
        r["spei"] = round(s, 3)
    rows.sort(key=lambda r: (r["province_th"] or "", r["amphoe_th"] or "", r["crop"] or "", r["src"]))

    # hotspots: districts ranked by planted rai sitting at severe+ drought (per crop, national src
    # preferred; Zone-6 rows add the East's tree crops)
    hot = {}
    for r in rows:
        if r["drought"] in ("severe", "extreme") and (r["planted_rai"] or 0) > 0:
            k = (r["province_th"], r["amphoe_th"], r["crop"])
            if k not in hot or (r["planted_rai"] or 0) > (hot[k]["planted_rai"] or 0):
                hot[k] = r
    hotspots = sorted(hot.values(), key=lambda r: -(r["planted_rai"] or 0))[:60]
    hotspots = [{"province_th": h["province_th"], "amphoe_th": h["amphoe_th"], "crop": h["crop"],
                 "crop_th": h["crop_th"], "planted_rai": h["planted_rai"], "spei": h["spei"],
                 "drought": h["drought"]} for h in hotspots]

    cov = {}
    for r in rows:
        if r["src"] == "oae_satellite":
            cov.setdefault(r["crop"], set()).add(r["province_th"])
    coverage = {c: len(v) for c, v in sorted(cov.items())}

    n_sev = len(hot)
    top = hotspots[0] if hotspots else None
    headline = ("District-grain crop exposure is live: %d measured amphoe crop rows joined to the "
                "OAE drought index; %d district-crop cells sit at severe-or-worse drought."
                % (len(rows), n_sev))
    if top:
        headline += (" Largest single exposure: %s in %s·%s — %s rai at SPEI %.2f."
                     % (top["crop"], top["province_th"], top["amphoe_th"],
                        format(int(top["planted_rai"]), ","), top["spei"]))

    return {
        "meta": {
            "title": "District crop exposure × drought — OAE amphoe surveys × OAE SPEI (obj #1)",
            "generated_by": "pipeline/build_amphoe_crops.py",
            "label": "MEASURED planted areas (OAE remote-sensing amphoe surveys + OAE Zone-6 "
                     "unified data; every row cites its source PDF) × MODELLED drought (OAE SPEI, "
                     "ERA5-Land, 2026-06). Name-joined; unmatched rows counted below, never "
                     "guessed. Do NOT sum across the two sources — different survey vintages.",
            "sources": {"national": nat.get("meta", {}).get("label") or "OAE satellite surveys",
                        "zone6": z6.get("meta", {}).get("label") or "OAE Zone 6",
                        "drought": dr.get("meta", {}).get("label") or "OAE SPEI"},
            "coverage_provinces_by_crop": coverage,
            "coverage_note": "cassava: no South section in the source PDF (structural); oil palm "
                             "source corrupted at origin (not recoverable); Zone-6 adds 16 Eastern "
                             "crops incl. durian/mangosteen.",
            "drought_unjoined_rows": unmatched,
            "retrieved": nat.get("meta", {}).get("retrieved"),
        },
        "headline": headline,
        "hotspots": hotspots,
        "rows": rows,
    }


def serialize(o):
    return json.dumps(o, ensure_ascii=False, separators=(",", ":"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    if not os.path.exists(IN_NAT):
        if args.check:
            print("build_amphoe_crops.py --check: SKIP (staging/amphoe_crops_national.json absent)")
            sys.exit(3)
        sys.exit("build_amphoe_crops.py: staging/amphoe_crops_national.json missing")
    payload = serialize(build())
    if args.check:
        if not os.path.exists(OUT):
            sys.exit("build_amphoe_crops.py --check: output missing")
        if open(OUT, encoding="utf-8").read() != payload:
            sys.exit("build_amphoe_crops.py --check: drifted — re-run the builder.")
        print("build_amphoe_crops.py --check: OK (byte-exact)")
        return
    open(OUT, "w", encoding="utf-8").write(payload)
    obj = json.loads(payload)
    print("wrote %s — %d rows, %d hotspots" % (OUT, len(obj["rows"]), len(obj["hotspots"])))
    print("coverage:", obj["meta"]["coverage_provinces_by_crop"])
    print("headline:", obj["headline"])


if __name__ == "__main__":
    main()
