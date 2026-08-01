#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""pull_nabc_history.py — the Thai price TIME SERIES and PROVINCE spread NABC was already giving us.

pull_nabc_prices.py pages ~2,200 daily records per category out of agriapi.nabc.go.th and keeps six
numbers from each: latest price, unit, date, YoY, market count, product. Everything else is thrown
away on the floor — and "everything else" is two whole dimensions:

  · TIME. Each record is one market's quote on one day. The app has no Thai price history anywhere;
    the only sparklines it draws are World Bank Pink Sheet series, which are WORLD prices. So the
    commodities board could show a 60-month trend for the world sugar price and nothing at all for
    the Thai farm-gate price a borrower actually receives.
  · PLACE. Every record carries `province` and `market_name`. A national average across quoting
    markets hides the spread, and the spread is the point when you are deciding which branch's
    borrowers are affected.

This pulls the same endpoint and keeps both, as monthly national means plus a per-province recent
mean. It writes its OWN file rather than extending nabc_prices.json, deliberately: that file's
numbers are inputs to a dozen derived layers, and re-pulling it would churn all of them for no
reason. Nothing here feeds price_stress or the branch layers; it is a display layer.

  python3 pull_nabc_history.py             # pull -> source-data/nabc_history.json
  python3 pull_nabc_history.py --stamp 2026-08-01
  python3 pull_nabc_history.py --selftest  # offline: prove the aggregation, no network

NO WALL CLOCK. "Recent" is anchored on the newest date IN THE DATA, never on today, so a re-run on
unchanged upstream data reproduces byte-for-byte. Months are the record's own year_th/month fields
folded from the Buddhist era (year_th 2569 -> 2026), not parsed from a locale-dependent string.
"""
import argparse, json, os, sys, time, urllib.parse, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "source-data", "nabc_history.json")
BASE = "https://agriapi.nabc.go.th/api/daily-prices"
UA = {"User-Agent": "Mozilla/5.0 (compatible; autox-credit-intel/1.0)"}
MAX_PAGES = 30
PAGE_LIMIT = 100
BE_OFFSET = 543
RECENT_DAYS = 90        # province means use the last quarter of quotes, anchored on the data's own end
MIN_MONTH_QUOTES = 3    # a month quoted fewer times than this is too thin to plot as a mean

# Same 13 categories the price puller covers, same bucket tags — kept as its own copy so a change
# to one file cannot silently reshape the other.
CATEGORY_BUCKET = {
    "ข้าวหอมมะลิ": "crop", "ข้าวโพดเลี้ยงสัตว์": "crop", "มันสำปะหลัง": "crop",
    "ปาล์มน้ำมัน": "crop", "ยางพารา": "crop", "สับปะรดโรงงาน": "crop",
    "มะพร้าว": "crop", "ลำไย": "crop", "มะนาว": "crop",
    "ไก่": "livestock", "ไข่ไก่": "livestock", "สุกร": "livestock",
    "กุ้งขาว": "fishery",
}


def _get(url, tries=4):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=45) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            last = e
            time.sleep(1.5 * (i + 1))
    raise RuntimeError("NABC GET failed after %d tries: %s\n  %s" % (tries, last, url))


def category_records(cat):
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


def _ord(iso):
    """Day ordinal for date-window arithmetic. Proleptic and approximate — only ever used to ask
    'is this quote within N days of that one', never to render a date."""
    y, m, d = (int(x) for x in iso.split("-"))
    return (y * 365) + (m * 31) + d


def _month(r):
    """'YYYY-MM' in the Common Era, from the record's own Buddhist-era year field.

    year_th arrives as 2569 for 2026. Folding by 543 here rather than parsing data_date means a
    malformed date string cannot silently place a quote 543 years in the future — the trap this
    repo has hit before with bare BE stamps.
    """
    try:
        y, m = int(r.get("year_th")), int(r.get("month"))
    except (TypeError, ValueError):
        return None
    if y > 2400:
        y -= BE_OFFSET
    return "%04d-%02d" % (y, m) if 1 <= m <= 12 else None


def aggregate(records):
    """One category's records -> {product, monthly[], provinces[], span}. Pure; no network, no clock."""
    if not records:
        return None
    counts = {}
    for r in records:
        counts[r.get("product_name")] = counts.get(r.get("product_name"), 0) + 1
    # Most-quoted product, ties broken by name so the choice cannot ride on dict order.
    product = max(sorted(counts), key=lambda p: (counts[p], p))
    rows = [r for r in records
            if r.get("product_name") == product and isinstance(r.get("day_price"), (int, float))]
    if not rows:
        return None

    by_month, by_day = {}, {}
    for r in rows:
        mk = _month(r)
        if mk:
            by_month.setdefault(mk, []).append(r["day_price"])
        d = r.get("data_date")
        if d:
            by_day.setdefault(d, []).append(r["day_price"])

    monthly = [{"month": m, "mean": round(sum(v) / len(v), 2), "n": len(v)}
               for m, v in sorted(by_month.items()) if len(v) >= MIN_MONTH_QUOTES]

    dates = sorted(by_day)
    latest = dates[-1] if dates else None
    cutoff = _ord(latest) - RECENT_DAYS if latest else None
    prov = {}
    for r in rows:
        d, p = r.get("data_date"), (r.get("province") or "").strip()
        if not d or not p or _ord(d) < cutoff:
            continue
        prov.setdefault(p, []).append(r["day_price"])
    provinces = [{"province": p, "mean": round(sum(v) / len(v), 2), "n": len(v)}
                 for p, v in sorted(prov.items())]
    provinces.sort(key=lambda x: (-x["mean"], x["province"]))

    return {
        "product": product,
        "unit": next((r.get("unit") for r in rows if r.get("unit")), ""),
        "first_month": monthly[0]["month"] if monthly else None,
        "last_month": monthly[-1]["month"] if monthly else None,
        "n_months": len(monthly),
        "n_quotes": len(rows),
        "latest_date": latest,
        "monthly": monthly,
        "provinces": provinces,
        "n_provinces": len(provinces),
    }


def payload(by_cat, stamp):
    cats = {c: a for c, a in by_cat.items() if a}
    return {
        "meta": {
            "title": "MEASURED Thai daily price history + province spread (NABC)",
            "generated_by": "pipeline/pull_nabc_history.py",
            "source": "NABC Agricultural Data Service (agriapi.nabc.go.th) — the same daily-price "
                      "endpoint pull_nabc_prices.py reads; this keeps the time and province "
                      "dimensions that one discards.",
            "label": "MEASURED — no modelling, no interpolation. Monthly values are the plain mean "
                     "of that month's quotes for the category's most-quoted product; months with "
                     "fewer than %d quotes are omitted rather than drawn from a thin sample."
                     % MIN_MONTH_QUOTES,
            "pulled": stamp,
            "recent_window_days": RECENT_DAYS,
            "province_note": "Province means cover the last %d days of quotes, anchored on each "
                             "category's own newest quote date — NOT on the wall clock, so the "
                             "output is byte-reproducible. A province appears only where a market "
                             "in it actually quotes the product; absence is silence, not zero."
                             % RECENT_DAYS,
            "coverage_note": "History depth is bounded by how far back the API pages (~%d records "
                             "per category), so a heavily-quoted commodity reaches back fewer "
                             "months than a thinly-quoted one. n_months and first_month state the "
                             "real span per category instead of implying a uniform window."
                             % (MAX_PAGES * PAGE_LIMIT),
            "categories_covered": sorted(cats),
        },
        "categories": {c: dict(cats[c], bucket=CATEGORY_BUCKET.get(c, "crop")) for c in sorted(cats)},
    }


SELFTEST = [
    {"data_date": "2026-07-20", "year_th": "2569", "month": "7", "product_name": "X",
     "market_name": "M1", "province": "ร้อยเอ็ด", "day_price": 100, "unit": "u"},
    {"data_date": "2026-07-21", "year_th": "2569", "month": "7", "product_name": "X",
     "market_name": "M2", "province": "สุรินทร์", "day_price": 120, "unit": "u"},
    {"data_date": "2026-07-22", "year_th": "2569", "month": "7", "product_name": "X",
     "market_name": "M1", "province": "ร้อยเอ็ด", "day_price": 110, "unit": "u"},
    {"data_date": "2025-01-05", "year_th": "2568", "month": "1", "product_name": "X",
     "market_name": "M1", "province": "ร้อยเอ็ด", "day_price": 90, "unit": "u"},
    {"data_date": "2026-07-22", "year_th": "2569", "month": "7", "product_name": "Y",
     "market_name": "M9", "province": "ตาก", "day_price": 999, "unit": "u"},
]


def selftest():
    a = aggregate(SELFTEST)
    assert a["product"] == "X", a["product"]
    assert a["n_months"] == 1, a["n_months"]           # 2025-01 has 1 quote, below the floor
    assert a["monthly"][0] == {"month": "2026-07", "mean": 110.0, "n": 3}, a["monthly"]
    # the 2025 quote is outside the 90d window anchored on 2026-07-22, so it cannot reach a province
    assert [p["province"] for p in a["provinces"]] == ["สุรินทร์", "ร้อยเอ็ด"], a["provinces"]
    assert a["provinces"][1]["n"] == 2, a["provinces"]
    print("pull_nabc_history.py --selftest: OK (aggregation, BE fold, recency window, tie-break)")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stamp", help="pull date recorded in meta.pulled (YYYY-MM-DD)")
    ap.add_argument("--selftest", action="store_true", help="offline aggregation test, no network")
    args = ap.parse_args()
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass
    if args.selftest:
        selftest()
        return

    by_cat = {}
    for cat in sorted(CATEGORY_BUCKET):
        try:
            recs = category_records(cat)
        except RuntimeError as e:
            print("WARNING: %s — skipped (%s)" % (cat, e), file=sys.stderr)
            continue
        by_cat[cat] = aggregate(recs)
        a = by_cat[cat]
        print("  %-18s %5d quotes  %2d months %s..%s  %2d provinces"
              % (cat, a["n_quotes"] if a else 0, a["n_months"] if a else 0,
                 (a or {}).get("first_month") or "-", (a or {}).get("last_month") or "-",
                 a["n_provinces"] if a else 0))

    doc = payload(by_cat, args.stamp)
    if not doc["categories"]:
        sys.exit("NABC returned nothing for any category — refusing to write an empty history file")
    # newline="\n": the Windows default would write CRLF and diverge from the LF blob CI reads.
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(doc, ensure_ascii=False, indent=1))
    print("wrote %s (%d categories)" % (OUT, len(doc["categories"])))


if __name__ == "__main__":
    main()
