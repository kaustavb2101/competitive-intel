#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_thai_price_history.py — the Thai price trend and province spread, keyed by board label.

  in : source-data/nabc_history.json   MEASURED — monthly means + province spread (13 categories)
       source-data/ocsb_cane.json      MEASURED — the announced cane price, annual
  out: platform/data/thai_price_history.json    (--check: byte-exact reproduce)

WHY THIS EXISTS. The commodities board draws a 60-month sparkline per row, and every one of those
sparklines is a WORLD price (World Bank Pink Sheet, via commodity_history.json). The Thai farm-gate
number beside it — the move a borrower actually feels, and the number the board sorts on — had no
history at all: one value, no trend, no sense of whether -17.9% is a cliff or the tail of a slide.
This keys the measured Thai series to the same board labels so a row can show both.

It also carries the PROVINCE SPREAD, which is the part a national average destroys. Thai paddy in
July 2026 means ~17,700 baht/tonne nationally and ranges from ~15,400 in Yasothon to ~18,800 in
Amnat Charoen — a 22% spread across provinces this book actually lends into. A borrower's province
matters more than the headline for that crop.

Deterministic + network-free. Every number is a plain mean of measured quotes; nothing is smoothed,
interpolated or extrapolated, and a gap in the upstream series stays a gap.
"""
import json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "source-data")
OUT = os.path.join(ROOT, "platform", "data", "thai_price_history.json")

# NABC category -> commodities-board label. The board is the consumer, so its labels are the key.
# ลำไย (longan) has no board row and is carried anyway: it is measured, it is a real upcountry
# borrower crop, and dropping it here would make it unrecoverable downstream.
CAT_TO_LABEL = {
    "ข้าวหอมมะลิ": "Rice", "ข้าวโพดเลี้ยงสัตว์": "Maize", "มันสำปะหลัง": "Cassava",
    "ปาล์มน้ำมัน": "Palm oil", "ยางพารา": "Rubber", "สับปะรดโรงงาน": "Pineapple",
    "มะพร้าว": "Coconut", "มะนาว": "Lime", "ลำไย": "Longan",
    "ไก่": "Chicken", "ไข่ไก่": "Eggs", "สุกร": "Pork", "กุ้งขาว": "White shrimp",
}


def load(name):
    p = os.path.join(SRC, name)
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def build():
    hist = load("nabc_history.json")
    if not hist:
        return None
    series = {}
    for cat, rec in (hist.get("categories") or {}).items():
        lab = CAT_TO_LABEL.get(cat)
        months = rec.get("monthly") or []
        if not lab or len(months) < 2:
            continue
        vals = [m["mean"] for m in months]
        first, last = vals[0], vals[-1]
        provs = rec.get("provinces") or []
        # Spread across quoting provinces, as a % of the cheapest. Only meaningful with 2+
        # provinces; with one quoting market it is not a spread, it is a single price.
        spread = None
        if len(provs) >= 2:
            lo = min(p["mean"] for p in provs)
            hi = max(p["mean"] for p in provs)
            spread = round((hi / lo - 1) * 100, 1) if lo else None
        series[lab] = {
            "cadence": "monthly",
            "category_th": cat,
            "product": rec.get("product"),
            "unit": rec.get("unit"),
            "bucket": rec.get("bucket"),
            "months": [m["month"] for m in months],
            "values": vals,
            "n_quotes": [m["n"] for m in months],
            "first_month": months[0]["month"],
            "last_month": months[-1]["month"],
            "n_months": len(months),
            "change_pct": round((last / first - 1) * 100, 1) if first else None,
            "min": min(vals), "max": max(vals),
            "provinces": provs,
            "n_provinces": len(provs),
            "spread_pct": spread,
        }

    # Sugarcane is ANNUAL and administered — a different cadence entirely, flagged as such so the
    # UI cannot draw it as if it were a monthly market series.
    cane = load("ocsb_cane.json") or {}
    cp = cane.get("price") or {}
    pts = cp.get("series") or []
    if len(pts) >= 2:
        vals = [p["price"] for p in pts]
        series["Sugar"] = {
            "cadence": "annual",
            "category_th": None,
            "product": "อ้อยโรงงาน — announced cane price (~10 CCS)",
            "unit": cp.get("unit"),
            "bucket": "crop",
            "months": [str(p["year_ce"]) for p in pts],
            "values": vals,
            "n_quotes": [1] * len(pts),
            "first_month": str(pts[0]["year_ce"]),
            "last_month": str(pts[-1]["year_ce"]),
            "n_months": len(pts),
            "change_pct": round((vals[-1] / vals[0] - 1) * 100, 1) if vals[0] else None,
            "min": min(vals), "max": max(vals),
            # An administered national price has no province spread by construction — the whole
            # country is paid the same announced rate. Empty here means "cannot vary", not "unknown".
            "provinces": [],
            "n_provinces": 0,
            "spread_pct": None,
        }

    if not series:
        return None
    return {
        "meta": {
            "title": "MEASURED Thai price history + province spread, by commodities-board label",
            "generated_by": "pipeline/build_thai_price_history.py",
            "label": "MEASURED. Monthly points are the plain mean of that month's quotes for the "
                     "category's most-quoted product (NABC daily market feed); the annual sugarcane "
                     "series is OCSB's announced price. Nothing smoothed or interpolated — a month "
                     "with too few quotes is omitted, so a gap in the line is a gap in the data.",
            "sources": ["source-data/nabc_history.json (pipeline/pull_nabc_history.py)",
                        "source-data/ocsb_cane.json (pipeline/ingest_ocsb_cane.py)"],
            "cadence_note": "Every series states its own cadence. Sugar is ANNUAL and ADMINISTERED "
                            "(one announced national price per season) — it is not a market series "
                            "and must not be drawn or compared as one.",
            "spread_note": "spread_pct is the gap between the dearest and cheapest quoting province "
                           "over the feed's recent window, as a %% of the cheapest. It exists only "
                           "where 2+ provinces quote; a national average hides it entirely, and it "
                           "is routinely wider than the YoY move the board leads with.",
            "vintage": (hist.get("meta") or {}).get("pulled"),
            "n_series": len(series),
            "labels": sorted(series),
        },
        "series": {k: series[k] for k in sorted(series)},
    }


def main():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass
    doc = build()
    if doc is None:
        print("build_thai_price_history.py: SKIP (source-data/nabc_history.json absent)")
        sys.exit(3)
    payload = json.dumps(doc, ensure_ascii=False, separators=(",", ":"))
    if "--check" in sys.argv[1:]:
        if not os.path.exists(OUT) or open(OUT, encoding="utf-8").read() != payload:
            sys.exit("build_thai_price_history.py --check: drifted — re-run the builder.")
        print("build_thai_price_history.py --check: OK (byte-exact)")
        return
    # newline="\n": the Windows default writes CRLF, inflating the byte size provenance censuses.
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write(payload)
    print("wrote %s (%d series)" % (OUT, doc["meta"]["n_series"]))
    for lab in doc["meta"]["labels"]:
        s = doc["series"][lab]
        print("  %-13s %2d %-7s %s..%s  %+6.1f%%  spread %s"
              % (lab, s["n_months"], s["cadence"], s["first_month"], s["last_month"],
                 s["change_pct"] or 0,
                 ("%.1f%% across %d prov" % (s["spread_pct"], s["n_provinces"]))
                 if s["spread_pct"] is not None else "—"))


if __name__ == "__main__":
    main()
