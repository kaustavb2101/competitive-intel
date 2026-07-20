#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_crop_margin.py — FARMER MARGIN per crop (objective #1): OAE production cost vs measured
farm-gate price — the missing half of the crop-stress read.

  in : source-data/staging/oae_crop_costs.json   OAE cost/rai + cost/kg per crop (ingest 2026-07-20)
       source-data/farmgate_prices.json          measured NABC farm-gate prices (฿/ton)
  out: platform/data/crop_margin.json            per-crop: price/kg, cost/kg, margin/kg, margin/rai

Provenance: costs MEASURED (OAE cost reports; some rows derived from cost/ton × OAE yield — the
per-row `method` field says which), prices MEASURED (NABC farm-gate). The MARGIN itself is DERIVED
arithmetic over the two, with a stated vintage mismatch (costs = crop year 2567/68; prices = live).

Deterministic + network-free; `--check` byte-compares; SKIPs (exit 3) if the staging file is absent.
"""
import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IN_COSTS = os.path.join(ROOT, "source-data", "staging", "oae_crop_costs.json")
IN_PRICES = os.path.join(ROOT, "source-data", "farmgate_prices.json")
OUT = os.path.join(ROOT, "platform", "data", "crop_margin.json")


def build():
    costs = json.load(open(IN_COSTS, encoding="utf-8"))
    prices = json.load(open(IN_PRICES, encoding="utf-8"))
    comm = prices.get("commodities", {})

    rows = []
    for c in costs.get("crops", []):
        key = c.get("crop_key") or ""
        # crop rows carry keys like rice/cassava/maize/oilpalm/rubber via crop_en; resolve loosely
        if not key:
            en = (c.get("crop_en") or "").lower()
            for k in comm:
                if k in en.replace("-", "").replace(" ", ""):
                    key = k
                    break
            if not key and "rice" in en:
                key = "rice"
        p = comm.get(key)
        if not p or c.get("cost_per_kg_baht") is None:
            continue
        # farmgate units are MIXED per commodity ("บาท/ตัน" vs "บาท/กก.") — convert only tons
        unit = p.get("unit") or ""
        price_kg = round(p["price"] / 1000.0, 2) if "ตัน" in unit else round(p["price"], 2)
        cost_kg = round(c["cost_per_kg_baht"], 2)
        margin_kg = round(price_kg - cost_kg, 2)
        y = c.get("yield_kg_per_rai")
        rows.append({
            "crop": key, "crop_th": c.get("crop_th"), "crop_en": c.get("crop_en"),
            "practice": c.get("region", "national"),
            "cost_year": c.get("year"),
            "cost_method": c.get("method", "measured_cost_per_rai"),
            "price_kg": price_kg, "price_asof": p.get("latest_date"),
            "price_yoy_pct": p.get("yoy"),
            "cost_kg": cost_kg,
            "cost_per_rai": c.get("cost_per_rai_baht"),
            "yield_kg_per_rai": y,
            "margin_kg": margin_kg,
            "margin_per_rai": round(margin_kg * y, 0) if y is not None else None,
            "margin_pct_of_price": round(margin_kg * 100.0 / price_kg, 1) if price_kg else None,
        })
    rows.sort(key=lambda r: (r["crop"], r["crop_th"] or ""))

    pos = [r for r in rows if (r["margin_kg"] or 0) > 0]
    neg = [r for r in rows if (r["margin_kg"] or 0) <= 0]
    headline = ("Farm-gate price covers OAE production cost on %d of %d crop rows"
                % (len(pos), len(rows)))
    if neg:
        headline += "; under water: " + ", ".join(sorted(set(r["crop"] for r in neg))) + "."
    else:
        headline += " — every joined crop currently clears its cost."

    return {
        "meta": {
            "title": "Farmer margin — OAE production cost vs measured farm-gate price (obj #1)",
            "generated_by": "pipeline/build_crop_margin.py",
            "label": "MEASURED inputs (OAE cost reports crop year 2567/68 · NABC farm-gate prices, "
                     "live) — the margin arithmetic is DERIVED, and the two vintages differ; read "
                     "direction, not decimals. Rows whose cost came from cost/ton × OAE yield are "
                     "marked in cost_method.",
            "sources": [costs.get("meta", {}).get("label"), prices.get("meta", {}).get("label")],
            "cost_ingested": costs.get("meta", {}).get("retrieved"),
            "omitted_crops": [o.get("crop_en") for o in costs.get("omitted", [])],
        },
        "headline": headline,
        "crops": rows,
    }


def serialize(o):
    return json.dumps(o, ensure_ascii=False, separators=(",", ":"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    if not os.path.exists(IN_COSTS):
        if args.check:
            print("build_crop_margin.py --check: SKIP (staging/oae_crop_costs.json absent)")
            sys.exit(3)
        sys.exit("build_crop_margin.py: staging/oae_crop_costs.json missing")
    payload = serialize(build())
    if args.check:
        if not os.path.exists(OUT):
            sys.exit("build_crop_margin.py --check: output missing")
        if open(OUT, encoding="utf-8").read() != payload:
            sys.exit("build_crop_margin.py --check: drifted — re-run the builder.")
        print("build_crop_margin.py --check: OK (byte-exact)")
        return
    open(OUT, "w", encoding="utf-8").write(payload)
    obj = json.loads(payload)
    print("wrote %s — %d crop rows" % (OUT, len(obj["crops"])))
    print("headline:", obj["headline"])


if __name__ == "__main__":
    main()
