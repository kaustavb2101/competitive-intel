#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pull_google_trends.py — Google Trends demand + brand share-of-search snapshot (NETWORK pull).

Two payloads, each one Trends request batch (pytrends, unofficial but stable):
  1. DEMAND: category search interest by Thai province (geo=TH, 12 months) for title-loan terms.
  2. BRANDS: the 5 title-lender brands in ONE payload — Trends scales multi-keyword payloads on a
     shared 0-100 axis, so per-province values are comparable ACROSS brands -> share-of-search.

Output: source-data/google_trends.json (committed SNAPSHOT with pull vintage in meta; the
deterministic builder build_search_demand.py derives platform/data/search_demand.json from it).

PROVENANCE / HONESTY: Google Trends is a RELATIVE index (0-100 within the payload), not absolute
search volume; low-volume provinces are noisy. Everything derived from this is labelled
ESTIMATED (search-interest proxy). No values are invented; provinces Google omits stay absent.

Run:  python3 pull_google_trends.py          (needs network; ~4 requests with polite sleeps)
"""
import json, os, time, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "source-data", "google_trends.json")

DEMAND_TERMS = ["จำนำทะเบียนรถ", "สินเชื่อรถแลกเงิน"]   # title-pawn + car-for-cash loan
BRANDS = {  # brand -> the consumer search term
    "AutoX":    "เงินไชโย",
    "Srisawad": "ศรีสวัสดิ์ เงินสดทันใจ",
    "Tidlor":   "เงินติดล้อ",
    "Muangthai":"เมืองไทยแคปปิตอล",
    "Heng":     "เฮงลิสซิ่ง",
}
TIMEFRAME = "today 12-m"

def pull():
    from pytrends.request import TrendReq
    # NOTE: no retries= kwarg — pytrends' internal Retry uses the removed urllib3
    # 'method_whitelist' argument and crashes; we retry manually below instead.
    pt = TrendReq(hl="th-TH", tz=420, timeout=(10, 30))
    out = {"demand": {}, "brands": {}, "brand_terms": BRANDS, "demand_terms": DEMAND_TERMS}

    # ---- demand terms: one payload each so each term keeps its own full 0-100 spread ----
    def region_df(terms):
        for attempt in range(3):
            try:
                pt.build_payload(terms, timeframe=TIMEFRAME, geo="TH")
                return pt.interest_by_region(resolution="REGION", inc_low_vol=True)
            except Exception as e:
                if attempt == 2:
                    raise
                print(f"  retry {attempt+1} after {type(e).__name__}"); time.sleep(8 * (attempt + 1))

    for term in DEMAND_TERMS:
        df = region_df([term])
        out["demand"][term] = {prov: int(row[term]) for prov, row in df.iterrows()}
        print(f"demand '{term}': {len(df)} provinces, top={df[term].idxmax()}")
        time.sleep(4)

    # ---- brands: ONE payload (shared axis -> cross-brand comparable) ----
    terms = list(BRANDS.values())
    df = region_df(terms)
    for brand, term in BRANDS.items():
        out["brands"][brand] = {prov: int(row[term]) for prov, row in df.iterrows()}
    print(f"brands (shared axis): {len(df)} provinces x {len(terms)} brands")

    # national time series for the primary demand term (12-mo trajectory, for the vintage digest)
    time.sleep(4)
    pt.build_payload([DEMAND_TERMS[0]], timeframe=TIMEFRAME, geo="TH")
    ts = pt.interest_over_time()
    if ts is not None and len(ts):
        col = DEMAND_TERMS[0]
        out["national_ts"] = [[str(ix.date()), int(row[col])] for ix, row in ts.iterrows()
                              if not row.get("isPartial", False)]

    out["meta"] = {
        "source": "Google Trends (geo=TH, REGION resolution, timeframe " + TIMEFRAME + ")",
        "label": "ESTIMATED — relative search-interest index (0-100), NOT absolute volume",
        "provenance": "Pulled via pytrends. Brand values share one payload axis so per-province "
                      "share-of-search across brands is meaningful; low-volume provinces are noisy. "
                      "Provinces Google omits are absent, not zero-filled.",
        "generated_by": "pipeline/pull_google_trends.py",
        "pulled_at_utc": time.strftime("%Y-%m-%dT%H:%MZ", time.gmtime()),
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1, sort_keys=True)
    n = sum(len(v) for v in out["demand"].values())
    print(f"wrote {OUT} ({n} demand rows, {len(out['brands'])} brands)")

if __name__ == "__main__":
    pull()
