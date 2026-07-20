#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_region_debt.py — REGIONAL household-debt backdrop (objective #1): Bank of Thailand's own
regional household-debt analysis, projected for the app.

  in : source-data/staging/bot_hhdebt.json       BoT Regional Letters (ingest 2026-07-20)
  out: platform/data/region_debt.json            numeric series grouped national / region / province

Provenance: MEASURED — Bank of Thailand publications over NSO SES survey data (vintages carried
per series; the nationwide 4-region cut is SES 2019, the Northern deep-dive SES 2023). BoT
publishes NO routine province-level household-debt table — the few province points here are the
only ones BoT printed, and qualitative map-flags from the ingest are EXCLUDED (numeric only).

Deterministic + network-free; `--check` byte-compares; SKIPs (exit 3) if staging absent.
"""
import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IN = os.path.join(ROOT, "source-data", "staging", "bot_hhdebt.json")
OUT = os.path.join(ROOT, "platform", "data", "region_debt.json")


def build():
    doc = json.load(open(IN, encoding="utf-8"))
    groups = {"national": [], "region": [], "province": []}
    for s in doc.get("series", []):
        if not isinstance(s.get("value"), (int, float)):
            continue                                   # numeric only — drop qualitative map-flags
        lvl = s.get("geo_level")
        if lvl in groups:
            groups[lvl].append({
                "indicator": s.get("indicator"), "indicator_th": s.get("indicator_th"),
                "geo": s.get("geo"), "value": s["value"], "unit": s.get("unit"),
                "vintage": s.get("vintage"), "confidence": s.get("confidence"),
            })
    for g in groups.values():
        g.sort(key=lambda x: (x["indicator"] or "", x["geo"] or ""))

    headline = ("BoT's regional household-debt read carried into the console: %d national, %d "
                "regional and %d province-level measured series. BoT publishes no routine "
                "province table — region is the honest grain."
                % (len(groups["national"]), len(groups["region"]), len(groups["province"])))

    return {
        "meta": {
            "title": "Regional household debt — Bank of Thailand backdrop (obj #1)",
            "generated_by": "pipeline/build_region_debt.py",
            "label": "MEASURED — BoT Regional Letters over NSO SES data (per-series vintages "
                     "carried; 4-region cut = SES 2019, Northern deep-dive = SES 2023). "
                     "Qualitative choropleth flags from the ingest are excluded. "
                     "medium-confidence rows were reconstructed from infographics — noted per row.",
            "source": doc.get("meta", {}).get("label"),
            "retrieved": doc.get("meta", {}).get("retrieved"),
        },
        "headline": headline,
        "series": groups,
    }


def serialize(o):
    return json.dumps(o, ensure_ascii=False, separators=(",", ":"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    if not os.path.exists(IN):
        if args.check:
            print("build_region_debt.py --check: SKIP (staging/bot_hhdebt.json absent)")
            sys.exit(3)
        sys.exit("build_region_debt.py: staging/bot_hhdebt.json missing")
    payload = serialize(build())
    if args.check:
        if not os.path.exists(OUT):
            sys.exit("build_region_debt.py --check: output missing")
        if open(OUT, encoding="utf-8").read() != payload:
            sys.exit("build_region_debt.py --check: drifted — re-run the builder.")
        print("build_region_debt.py --check: OK (byte-exact)")
        return
    open(OUT, "w", encoding="utf-8").write(payload)
    obj = json.loads(payload)
    print("wrote %s" % OUT)
    print("headline:", obj["headline"])


if __name__ == "__main__":
    main()
