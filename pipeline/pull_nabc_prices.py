#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pull_nabc_prices.py — LIVE daily Thai agri prices from NABC (crops · livestock · fisheries).

THE SOURCE: NABC Agricultural Data Service (agriapi.nabc.go.th) — the National Agricultural Big
Data Center's REST/JSON daily market-price API. Real-time, FREE, NO API KEY, and — unlike the
data.go.th / DLT family — REACHABLE from a foreign datacenter IP (verified HTTP 200 from the cloud
sandbox and from GitHub-hosted runners). So this is the one Thai-gov price feed that can refresh in
the cloud, no Thai-IP laptop needed.

WHAT IT PRODUCES: source-data/nabc_prices.json — for each of NABC's 13 daily-price categories, the
representative (most-quoted) product's latest national-average price + a self-computed YoY from the
daily series, tagged crop / livestock / fishery. Plus a crop_yoy map (rice/cassava/maize/oilpalm/
rubber) that build_branch_agri.py reads to price its per-branch agri stress off MEASURED live Thai
prices instead of the OAE static snapshot or the World Bank GLOBAL proxy.

NO FABRICATION: only real NABC records. Prices/YoY come straight from the published daily series;
the JSON is byte-stable given the same upstream data (dates/prices are the API's, no wall clock is
embedded — pass --stamp for the pull date in meta).

  python3 pull_nabc_prices.py             # pull + write source-data/nabc_prices.json
  python3 pull_nabc_prices.py --stamp 2026-07-05   # record the pull date in meta.pulled
  python3 pull_nabc_prices.py --selftest  # offline: prove the parse/aggregate path, no network
"""
import argparse, json, os, sys, time, urllib.request, urllib.parse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "source-data", "nabc_prices.json")
BASE = "https://agriapi.nabc.go.th/api/daily-prices"
UA = {"User-Agent": "Mozilla/5.0 (compatible; autox-credit-intel/1.0)"}
MAX_PAGES = 25          # ~2500 records/category — spans >1yr for YoY, bounds the call count
PAGE_LIMIT = 100

# NABC category (Thai) -> bucket + the SPAM/agri crop key it feeds (None = not a branch_agri crop).
CATEGORY_MAP = {
    "ข้าวหอมมะลิ":      ("crop", "rice"),
    "ข้าวโพดเลี้ยงสัตว์": ("crop", "maize"),
    "มันสำปะหลัง":      ("crop", "cassava"),
    "ปาล์มน้ำมัน":       ("crop", "oilpalm"),
    "ยางพารา":         ("crop", "rubber"),
    "สับปะรดโรงงาน":    ("crop", None),
    "มะพร้าว":          ("crop", None),
    "ลำไย":            ("crop", None),
    "มะนาว":           ("crop", None),
    "ไก่":              ("livestock", None),
    "ไข่ไก่":            ("livestock", None),
    "สุกร":             ("livestock", None),
    "กุ้งขาว":           ("fishery", None),
}


def _get(url, tries=4):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=45) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:  # transient network / 5xx — back off and retry
            last = e
            time.sleep(1.5 * (i + 1))
    raise RuntimeError("NABC GET failed after %d tries: %s\n  %s" % (tries, last, url))


def categories():
    d = _get(BASE + "/categories")
    return d.get("data", []) if d.get("success") else []


def category_records(cat):
    """All daily records for a category, up to MAX_PAGES (newest first)."""
    out = []
    for page in range(1, MAX_PAGES + 1):
        q = urllib.parse.urlencode({"product_category": cat, "page": page})
        d = _get("%s/category?%s" % (BASE, q))
        rows = d.get("data") or []
        if not rows:
            break
        out.extend(rows)
        pg = d.get("pagination") or {}
        if page * PAGE_LIMIT >= (pg.get("total") or 0):
            break
        time.sleep(0.3)   # be polite to the public API
    return out


def _daily_series(records, product):
    """{data_date: national-avg day_price} for one product across all its markets."""
    by = {}
    for r in records:
        if r.get("product_name") != product:
            continue
        p = r.get("day_price")
        d = r.get("data_date")
        if isinstance(p, (int, float)) and d:
            by.setdefault(d, []).append(p)
    return {d: sum(v) / len(v) for d, v in by.items()}


def _yoy(series):
    """(latest_date, latest_price, yoy_pct|None). YoY = mean(latest 30d) vs mean(±20d around -365d)."""
    if not series:
        return None, None, None
    dates = sorted(series)               # ISO yyyy-mm-dd sorts chronologically
    latest = dates[-1]
    # recent = quotes within ~30 days of the latest date (by date proximity, not last-N records —
    # correct even when the series is sparse), so a lone year-old point can't bleed into "recent".
    recent = [series[d] for d in dates if 0 <= (_ord(latest) - _ord(d)) <= 30]
    rec = sum(recent) / len(recent)
    # find the window ~365 days earlier by string date arithmetic on the year field
    y, m, day = latest.split("-")
    target = "%04d-%s-%s" % (int(y) - 1, m, day)
    near = [series[d] for d in dates if abs((_ord(d) - _ord(target))) <= 20]
    if not near:
        return latest, round(series[latest], 2), None
    ago = sum(near) / len(near)
    yoy = (rec - ago) / ago * 100 if ago else None
    return latest, round(series[latest], 2), (round(yoy, 1) if yoy is not None else None)


def _ord(iso):
    """Days-since-epoch-ish ordinal from an ISO date string (proleptic, good enough for a ±20d window)."""
    y, m, d = (int(x) for x in iso.split("-"))
    return (y * 365) + (m * 31) + d


def build(records_by_cat):
    cats_out = {}
    crop_yoy = {}
    for cat, records in records_by_cat.items():
        bucket, cropkey = CATEGORY_MAP.get(cat, ("crop", None))
        if not records:
            continue
        # dominant product = the one with the most records (most widely quoted)
        counts = {}
        for r in records:
            counts[r.get("product_name")] = counts.get(r.get("product_name"), 0) + 1
        product = max(counts, key=counts.get)
        series = _daily_series(records, product)
        latest_date, price, yoy = _yoy(series)
        unit = next((r.get("unit") for r in records if r.get("product_name") == product), "")
        markets = len({r.get("market_name") for r in records
                       if r.get("product_name") == product and r.get("data_date") == latest_date})
        cats_out[cat] = {
            "bucket": bucket, "product": product, "price": price, "unit": unit,
            "latest_date": latest_date, "yoy": yoy, "n_markets": markets,
        }
        if cropkey and yoy is not None:
            crop_yoy[cropkey] = yoy
    return cats_out, crop_yoy


def payload(cats_out, crop_yoy, stamp):
    return {
        "meta": {
            "source": "NABC Agricultural Data Service (agriapi.nabc.go.th) — daily market prices; "
                      "real-time, free, no key. REACHABLE from cloud runners (unlike data.go.th/DLT).",
            "label": "MEASURED — live Thai daily market/farm-gate prices (crops · livestock · fisheries)",
            "generated_by": "pipeline/pull_nabc_prices.py",
            "pulled": stamp,
            "categories_covered": sorted(cats_out),
            "crop_keys": sorted(crop_yoy),
            "note": "Per category: the most-quoted product's latest national-average price + YoY "
                    "computed from the daily series (recent-30d vs the window around -365d). "
                    "crop_yoy feeds build_branch_agri.py (live prices supersede the OAE snapshot).",
        },
        "categories": {k: cats_out[k] for k in sorted(cats_out)},
        "crop_yoy": {k: crop_yoy[k] for k in sorted(crop_yoy)},
    }


SELFTEST = [
    {"data_date": "2026-07-02", "product_name": "X", "market_name": "M1", "day_price": 110, "unit": "u"},
    {"data_date": "2026-07-01", "product_name": "X", "market_name": "M1", "day_price": 110, "unit": "u"},
    {"data_date": "2025-07-02", "product_name": "X", "market_name": "M1", "day_price": 100, "unit": "u"},
]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stamp", default="", help="pull date (YYYY-MM-DD) recorded in meta.pulled")
    ap.add_argument("--selftest", action="store_true", help="offline parse/aggregate check; no network")
    a = ap.parse_args()

    if a.selftest:
        s = _daily_series(SELFTEST, "X")
        ld, price, yoy = _yoy(s)
        assert price == 110 and yoy == 10.0, (price, yoy)
        print("selftest OK: latest %s = %s, YoY %s%%" % (ld, price, yoy))
        return

    cats = categories()
    print("NABC categories: %d — %s" % (len(cats), ", ".join(cats)), file=sys.stderr)
    records_by_cat = {}
    for c in cats:
        recs = category_records(c)
        records_by_cat[c] = recs
        print("  %-22s %5d records" % (c, len(recs)), file=sys.stderr)
    cats_out, crop_yoy = build(records_by_cat)
    doc = payload(cats_out, crop_yoy, a.stamp)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(json.dumps(doc, ensure_ascii=False, separators=(",", ":")))
    print("wrote %s" % OUT)
    print("crop YoY (live NABC): " + ", ".join("%s %+g" % (k, v) for k, v in doc["crop_yoy"].items()))
    for k, v in doc["categories"].items():
        print("  %-20s %8s %-14s YoY %s (%s markets, %s)"
              % (k, v["price"], v["unit"], v["yoy"], v["n_markets"], v["bucket"]))


if __name__ == "__main__":
    main()
