#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_farmgate_prices.py — the MEASURED Thai FARM-GATE price layer (objective #1, di-farmgate).

Consolidates the measured Thai crop prices already landed by pipeline/pull_nabc_prices.py
(source-data/nabc_prices.json — NABC daily national-average prices, agriapi.nabc.go.th) into a
single, explicitly-named farm-gate price layer: source-data/farmgate_prices.json. This is the file
pipeline/build_crop_stress.py prefers over the World Bank Pink Sheet GLOBAL proxy for price_stress.

WHY A DEDICATED LAYER (di-farmgate): the roadmap item is "replace the GLOBAL price proxy with Thai
farm-gate prices". OAE's ราคาที่เกษตรกรขายได้ (price-farmers-received) series is NOT exposed as a
machine-readable price-by-commodity resource on catalog.oae.go.th (verified 2026-07-12: only
value-of-production PDF/JSON datasets remain there; the price series moved to the geo-blocked
data.go.th aggregator). The REACHABLE measured Thai price source is NABC. Its quoted products are
the RAW farm commodities farmers sell — ข้าวเปลือก (paddy), หัวมันสำปะหลังสด (fresh cassava),
ผลปาล์มน้ำมันทั้งทะลาย (whole palm bunches), ยางพาราแผ่นดิบ (raw rubber sheet) — i.e. farm-gate
product forms, aggregated as daily national averages. Confirmed live-reachable from the Thai IP on
2026-07-12 (rice +10.7, rubber +35.0, oil palm +41.7 — within noise of the committed vintage).

NO FABRICATION: every number is copied straight from the measured NABC landing file; nothing is
modelled. Deterministic + network-free: byte-stable given the same nabc_prices.json.

  python3 build_farmgate_prices.py            # write source-data/farmgate_prices.json
  python3 build_farmgate_prices.py --check    # re-run, byte-compare against the committed file
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, "source-data")
NABC = os.path.join(SRC, "nabc_prices.json")
OUT = os.path.join(SRC, "farmgate_prices.json")

# NABC category (Thai) -> canonical crop key + English label. Only the crops NABC quotes as raw
# farm commodities. (rice = paddy hom mali; the same keys build_crop_stress.py area-weights.)
CAT_TO_CROP = {
    "ข้าวหอมมะลิ":       ("rice",    "Rice (paddy)"),
    "ยางพารา":          ("rubber",  "Rubber (raw sheet)"),
    "ปาล์มน้ำมัน":       ("oilpalm", "Oil palm (fresh bunch)"),
    "มันสำปะหลัง":       ("cassava", "Cassava (fresh root)"),
    "ข้าวโพดเลี้ยงสัตว์": ("maize",   "Maize"),
}


def build():
    with open(NABC, encoding="utf-8") as f:
        nabc = json.load(f)
    cats = nabc.get("categories") or {}
    nmeta = nabc.get("meta") or {}

    commodities = {}
    latest = None
    for cat, (crop, en) in CAT_TO_CROP.items():
        row = cats.get(cat)
        if not row:
            continue
        commodities[crop] = {
            "crop_en": en,
            "product_th": row.get("product"),
            "category_th": cat,
            "price": row.get("price"),
            "unit": row.get("unit"),
            "latest_date": row.get("latest_date"),
            "yoy": row.get("yoy"),
            "n_markets": row.get("n_markets"),
        }
        d = row.get("latest_date")
        if d and (latest is None or d > latest):
            latest = d

    # crop_yoy: the map build_crop_stress.py consumes (only crops with a usable YoY)
    crop_yoy = {c: e["yoy"] for c, e in sorted(commodities.items())
                if isinstance(e.get("yoy"), (int, float))}

    doc = {
        "meta": {
            "title": "Measured Thai farm-gate crop prices (portfolio risk, objective #1)",
            "generated_by": "pipeline/build_farmgate_prices.py",
            "label": "MEASURED — Thai daily national-average prices for RAW farm commodities "
                     "(farm-gate product forms: paddy, fresh cassava root, whole palm bunch, raw "
                     "rubber sheet, maize). Nothing modelled.",
            "source": "NABC Agricultural Data Service (agriapi.nabc.go.th) — daily market prices, "
                      "national average across quoting markets, pulled by pipeline/pull_nabc_prices.py "
                      "(REACHABLE from a Thai IP and from cloud runners; verified live 2026-07-12).",
            "farmgate_note": "OAE's ราคาที่เกษตรกรขายได้ (price-farmers-received) series is not "
                             "exposed as a machine-readable price resource on catalog.oae.go.th "
                             "(only value-of-production datasets remain; the price series moved to the "
                             "geo-blocked data.go.th aggregator). NABC's quoted products ARE the raw "
                             "farm commodities farmers sell, so this stands in for farm-gate as the "
                             "reachable measured Thai price layer — replacing the World Bank Pink "
                             "Sheet GLOBAL proxy for price_stress. It is a national daily average, "
                             "not a per-province farm-gate census.",
            "vintage": latest,
            "pulled": nmeta.get("pulled"),
            "upstream": "source-data/nabc_prices.json",
            "crops_covered": sorted(crop_yoy),
            "consumer": "pipeline/build_crop_stress.py prefers these measured Thai YoY values over "
                        "the World Bank GLOBAL Pink Sheet proxy for matching crops; the GLOBAL proxy "
                        "remains the graceful fallback when this layer is absent.",
        },
        "commodities": {c: commodities[c] for c in sorted(commodities)},
        "crop_yoy": {c: crop_yoy[c] for c in sorted(crop_yoy)},
    }
    return doc


def dumps(obj):
    return json.dumps(obj, ensure_ascii=False, indent=2) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true",
                    help="re-run and byte-compare against the committed JSON; exit 1 on drift")
    args = ap.parse_args()
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:
            pass

    if not os.path.exists(NABC):
        sys.exit("build_farmgate_prices.py: source-data/nabc_prices.json missing — run "
                 "pipeline/pull_nabc_prices.py first (NABC is reachable from a Thai IP / cloud).")

    text = dumps(build())

    if args.check:
        if not os.path.exists(OUT):
            print("CHECK FAIL: %s does not exist" % OUT)
            sys.exit(1)
        with open(OUT, encoding="utf-8") as f:
            existing = f.read()
        if existing == text:
            print("CHECK OK: %s reproduces byte-for-byte" % OUT)
            sys.exit(0)
        print("CHECK FAIL: %s differs from a fresh build" % OUT)
        sys.exit(1)

    with open(OUT, "w", encoding="utf-8") as f:
        f.write(text)
    doc = json.loads(text)
    print("wrote %s (vintage %s, crops: %s)" % (
        OUT, doc["meta"]["vintage"], ", ".join(doc["meta"]["crops_covered"])))
    for c, y in doc["crop_yoy"].items():
        print("  %-9s YoY %+g%%" % (c, y))


if __name__ == "__main__":
    main()
