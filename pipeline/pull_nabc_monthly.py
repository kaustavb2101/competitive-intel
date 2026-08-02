#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pull_nabc_monthly.py — the OTHER NABC endpoint: /api/monthly-prices, never wired before 2026-08-02.

THE MISS: pull_nabc_prices.py and pull_nabc_history.py both read agriapi.nabc.go.th's
/api/daily-prices family — 13 categories. NABC ALSO publishes a completely separate
/api/monthly-prices family — 17 categories, including the orchard fruits (durian, rambutan,
longan) that /api/daily-prices does not carry at all. It went unnoticed because the monthly family
400s ("Year is required") on every call unless BOTH `year_th` (Buddhist-era year, e.g. 2569 =
2026 CE) and, for the /product endpoint, an EXACT `product_name` taken from /product-names are
supplied — there is no way to browse it blind, so it read as absent rather than gated. Verified
reachable and working 2026-08-02:
  /api/monthly-prices/categories?year_th=<BE>
  /api/monthly-prices/product-names?year_th=<BE>
  /api/monthly-prices/product?product_name=<exact>&year_th=<BE>&page=&limit=

WHAT IT PRODUCES: source-data/nabc_monthly.json — the full monthly history (see WINDOW below) for
four series that carry no other Thai price source anywhere in this repo:
  · durian   — ทุเรียนหมอนทอง คละ (Monthong mixed grade), commod ทุเรียน
  · rambutan — เงาะโรงเรียน คละ (Rong Rean mixed grade), commod เงาะ
  · longan   — ลำไย, TWO grades both carried (เกรด A, เกรด AA) — build_commodities.py picks ONE
  · beef     — โคพันธุ์ลูกผสม ขนาดกลาง (medium crossbred cattle), commod โคเนื้อ. Added 2026-08-02
               and NOT a fruit: the board's Beef row had no Thai price at all, so it ran on the
               World Bank index (+11.8%) while Thai cattle were in a four-year slide. Quoted in
               บาท/ตัว — per HEAD, not per kg like the fruits. See PRODUCT_FILTERS.
mangosteen (มังคุด) / longkong (ลองกอง) / lychee (ลิ้นจี่) were checked against BOTH endpoint
families across every BE year 2563-2569 and are absent from all of them — do not re-add without
new evidence; there is nothing to pull for those three.

PRODUCT NAMES ARE NEVER HARDCODED-AND-TRUSTED: every name used below is re-resolved at pull time
from /product-names against a narrow Thai-substring filter (see PRODUCT_FILTERS), and the pull FAILS
LOUDLY if a filter doesn't resolve to exactly its expected count (1 for durian/rambutan, 2 for
longan) — an upstream rename breaks the pull instead of silently mismatching a stale string.

WINDOW: the most recent YEARS_BACK Buddhist-era years, current year inclusive (e.g. 2565-2569 for
a pull made in CE 2026) — NOT the full archive. Older years DO exist in this same endpoint (durian
answers back to at least BE 2561 / CE 2018) but are deliberately excluded: a currency-bounded
window keeps the call count small (mirrors pull_nabc_prices.py's own MAX_PAGES reasoning) and keeps
every series inside the same recent regime the rest of the board's YoY comparisons live in. Widen
YEARS_BACK to pull further back — nothing else in the script assumes 5.

YoY IS SAME-MONTH, NOT A ROLLING WINDOW. pull_nabc_prices.py's YoY (recent-30d vs the window around
-365d) is right for a year-round daily market. These are seasonal HARVEST fruits — durian and
rambutan only quote during their harvest months, NABC simply has no record the rest of the year —
so a rolling-window YoY would compare a real harvest-month price against an empty off-season gap
and produce nonsense (or silently nothing). Same calendar month, one year back, is the only
comparison that means anything for a seasonal crop; see yoy_same_month().

NO FABRICATION: only real NABC records. Month keys fold the record's own Buddhist-era year_th with
an explicit guard (_ce_year) that refuses to ever land on a CE year later than today — the bare-BE-
year trap this repo has hit before (a year_th read as a raw int lands 543 years in the future).

  python3 pull_nabc_monthly.py             # pull + write source-data/nabc_monthly.json
  python3 pull_nabc_monthly.py --stamp 2026-08-02
  python3 pull_nabc_monthly.py --selftest  # offline: prove month-fold + same-month YoY, no network
"""
import argparse, json, os, sys, time, urllib.request, urllib.parse
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "source-data", "nabc_monthly.json")
BASE = "https://agriapi.nabc.go.th/api/monthly-prices"
UA = {"User-Agent": "Mozilla/5.0 (compatible; autox-credit-intel/1.0)"}
BE_OFFSET = 543
YEARS_BACK = 5     # current BE year + this many prior years — see WINDOW in the module docstring

# product key -> (Thai-substring predicate, expected /product-names match count). Longan matches 2
# (both grades); everything else matches exactly 1. No product_name string is ever hand-typed into
# a lookup — every one used below is the literal string this predicate found.
PRODUCT_FILTERS = {
    "durian":   (lambda n: "ทุเรียนหมอนทอง" in n, 1),
    "rambutan": (lambda n: "เงาะโรงเรียน" in n, 1),
    "longan":   (lambda n: "ลำไย" in n and "เกรด" in n, 2),   # split into longan_a / longan_aa
    # BEEF CATTLE, added 2026-08-02 — the reason this file stopped being fruit-only.
    # The board's Beef row was running on the World Bank Pink Sheet beef index alone (+11.8%) with
    # no Thai series, so its belt drill showed 24 provinces and 136,293 book accounts against two
    # empty income columns: the income engine will not pass a WORLD price through to a Thai
    # household, and correctly so. NABC's monthly family does carry a Thai one — commod โคเนื้อ,
    # product โคพันธุ์ลูกผสม ขนาดกลาง (medium crossbred cattle), a national average in บาท/ตัว
    # (per HEAD, not per kg like every other series here — build_commodities.py must not assume kg).
    # It reverses the row's sign: Thai cattle have fallen from ฿34,688/head (2022-12) to
    # ฿20,719 (2026-06), −40% off peak and −6.1% same-month YoY, while the world index rose.
    # กระบือ (buffalo) is on the same feed and deliberately NOT pulled — no board row needs it.
    "beef":     (lambda n: "โคพันธุ์ลูกผสม" in n, 1),
}

# VERIFIED 2026-08-02 (see the discovery notes this script was written from) — do not adjust the
# code to force these; if a real pull disagrees, something upstream changed and it should fail loud.
ACCEPTANCE = {
    "durian":   {"n_months": 31, "first_month": "2022-03", "latest_date": "2026-06",
                 "price": 87.03, "yoy": 7.0},
    "rambutan": {"n_months": 26, "first_month": "2022-05", "latest_date": "2026-06",
                 "price": 20.19, "yoy": -13.5},
    "longan_a":  {"n_months": 51, "first_month": "2022-01", "latest_date": "2026-06",
                  "price": 26.27, "yoy": 60.2},
    "longan_aa": {"n_months": 54, "first_month": "2022-01", "latest_date": "2026-06",
                  "price": 34.71, "yoy": 12.4},
    # Unlike the fruits, cattle quote EVERY month — 54 of 54 in the window, no seasonal gaps.
    "beef":      {"n_months": 54, "first_month": "2022-01", "latest_date": "2026-06",
                  "price": 20718.51, "yoy": -6.1},
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


def product_names(year_th):
    d = _get(BASE + "/product-names?" + urllib.parse.urlencode({"year_th": year_th}))
    return d.get("data", []) if d.get("success") else []


def resolve_products(year_th):
    """Fruit key(s) -> exact product_name string(s), resolved from /product-names — never guessed.

    Falls back one year earlier if the requested year's /product-names comes back empty (e.g. a
    pull made before the current year's first monthly record has posted) — resolution only needs
    the CATALOG of names, which is stable year to year; the actual price pull still spans the full
    WINDOW regardless of which year the names were resolved against.
    """
    names = product_names(year_th)
    if not names:
        names = product_names(year_th - 1)
    if not names:
        raise RuntimeError("resolve_products: /product-names empty for year_th=%s and %s"
                           % (year_th, year_th - 1))
    out = {}
    for key, (pred, expect_n) in PRODUCT_FILTERS.items():
        hits = sorted(n for n in names if pred(n))
        if len(hits) != expect_n:
            raise RuntimeError("resolve_products: %s expected %d product-names match(es), got %d: %s"
                               % (key, expect_n, len(hits), hits))
        if key == "longan":
            grades = {}
            for n in hits:
                grade = n.rsplit("เกรด", 1)[-1].strip()
                grades[grade] = n
            if sorted(grades) != ["A", "AA"]:
                raise RuntimeError("resolve_products: longan grades not exactly {A, AA}: %s" % hits)
            out["longan_a"] = grades["A"]
            out["longan_aa"] = grades["AA"]
        else:
            out[key] = hits[0]
    return out


def product_records(product_name, year_th, tries=4):
    q = urllib.parse.urlencode({"product_name": product_name, "year_th": year_th,
                                "page": 1, "limit": 100})
    d = _get(BASE + "/product?" + q, tries=tries)
    rows = d.get("data") or []
    total = (d.get("pagination") or {}).get("total")
    # One BE year is at most 12 months, well under limit=100 — a total bigger than page 1 returned
    # would mean the API started paginating a single year, which none of the target products need
    # today. Fail loudly rather than silently dropping months if that ever changes.
    if total is not None and total > len(rows):
        raise RuntimeError("product_records: %s year_th=%s paginates (%d of %d) — this puller has "
                           "no page-2+ loop because no target product has ever needed one"
                           % (product_name, year_th, len(rows), total))
    return rows


def _ce_year(year_th):
    """Fold a Buddhist-era year to Common Era, and refuse a result in the future.

    NABC's own year_th is always BE (2569 = 2026), so the >2400 branch always fires here — but
    every BE fold in this repo carries this exact guard after the bare-BE-year trap (a stamp read
    as a raw int lands 543 years in the future). Kept even though the else-branch is dead today.
    """
    yt = int(year_th)
    ce = yt - BE_OFFSET if yt > 2400 else yt
    assert ce <= date.today().year, (
        "pull_nabc_monthly._ce_year: year_th=%s folded to CE %d, which is in the future — "
        "refusing to write it" % (year_th, ce))
    return ce


def build_series(product_name, years_th):
    """{month 'YYYY-MM' (CE) : price} across the given BE years, for one exact product_name."""
    series, unit = {}, None
    for yr in years_th:
        for r in product_records(product_name, yr):
            m = r.get("month")
            try:
                m = int(m)
            except (TypeError, ValueError):
                continue
            if not (1 <= m <= 12):
                continue
            ce = _ce_year(r.get("year_th"))
            try:
                price = float(r.get("value"))
            except (TypeError, ValueError):
                continue
            series["%04d-%02d" % (ce, m)] = price
            unit = r.get("unit") or unit
    return series, unit


def yoy_same_month(series):
    """(latest_month, latest_price, prior_month, yoy_pct|None) — same calendar month, one year back.

    NOT a rolling 30-day window (see the module docstring): these fruits only quote in-season, so a
    window comparison would race a real harvest-month price against an empty off-season gap.
    """
    if not series:
        return None, None, None, None
    months = sorted(series)
    latest = months[-1]
    y, m = latest.split("-")
    prior = "%04d-%s" % (int(y) - 1, m)
    if prior not in series or not series[prior]:
        return latest, series[latest], prior, None
    yoy = round((series[latest] - series[prior]) / series[prior] * 100, 1)
    return latest, series[latest], prior, yoy


def build():
    be_now = date.today().year + BE_OFFSET
    years_th = list(range(be_now - YEARS_BACK + 1, be_now + 1))
    names = resolve_products(years_th[-1])
    products = {}
    for fruit in sorted(names):
        pname = names[fruit]
        series, unit = build_series(pname, years_th)
        latest, latest_price, prior, yoy = yoy_same_month(series)
        months_sorted = sorted(series)
        products[fruit] = {
            "product": pname,
            "price": latest_price,
            "unit": unit,
            "latest_date": latest,          # 'YYYY-MM' — monthly series, no finer date exists
            "yoy": yoy,
            "yoy_basis": ("%s vs %s (same-month YoY)" % (latest, prior)) if latest else None,
            "n_markets": None,               # national monthly average, not a per-market quote
            "n_months": len(months_sorted),
            "first_month": months_sorted[0] if months_sorted else None,
            "monthly": [{"month": mth, "price": series[mth]} for mth in months_sorted],
        }
    return products, years_th


def assert_acceptance(products):
    """The VERIFIED FACTS this script was written from (checked 2026-08-02) — a hard regression pin,
    not a derivation. If NABC revises its own published history this will need a fresh verification
    pass, not a code tweak to make it pass."""
    for fruit, want in ACCEPTANCE.items():
        got = products.get(fruit)
        if not got:
            raise AssertionError("assert_acceptance: %s missing from the pull" % fruit)
        for k, v in want.items():
            if got.get(k) != v:
                raise AssertionError("assert_acceptance: %s.%s = %r, expected %r"
                                     % (fruit, k, got.get(k), v))
    print("acceptance check: OK (%s match the verified 2026-08-02 facts)"
          % "/".join(sorted(ACCEPTANCE)), file=sys.stderr)


def payload(products, years_th, stamp):
    be_span = "%d-%d" % (years_th[0], years_th[-1])
    ce_span = "%d-%d" % (years_th[0] - BE_OFFSET, years_th[-1] - BE_OFFSET)
    return {
        "meta": {
            "source": "NABC Agricultural Data Service (agriapi.nabc.go.th) — the "
                      "/api/monthly-prices endpoint family, DISTINCT from /api/daily-prices "
                      "(pull_nabc_prices.py / pull_nabc_history.py). Monthly-prices 400s without "
                      "BOTH year_th and (for /product) an exact product_name, which is why it read "
                      "as absent rather than gated and was never pulled before 2026-08-02.",
            "label": "MEASURED — live Thai monthly national-average farm-gate/market prices "
                     "(durian, rambutan, longan two grades, beef cattle). No other Thai price "
                     "source in this repo carries any of them.",
            "units_differ": "Not every series is บาท/กก. — beef quotes in บาท/ตัว (per HEAD). Read "
                            "each product's own 'unit' field; never assume a common unit here.",
            "generated_by": "pipeline/pull_nabc_monthly.py",
            "pulled": stamp,
            "window_be": be_span,
            "window_ce": ce_span,
            "window_note": "Most recent %d Buddhist-era years, current year inclusive — NOT the "
                           "full archive (durian alone answers back to at least BE 2561 / CE "
                           "2018 on this same endpoint). Bounded on purpose; see WINDOW in the "
                           "module docstring." % YEARS_BACK,
            "yoy_method": "Same-month year-on-year (this month vs the same calendar month one "
                          "year back), NOT pull_nabc_prices.py's rolling 30-day-window method. "
                          "The fruits are seasonal harvests with no off-season quote at all, so a "
                          "rolling window would compare a harvest-month price against an empty "
                          "gap. Beef quotes year-round and would survive either method; it uses "
                          "the same one so every series on this feed is compared alike.",
            "products_covered": sorted(products),
            "longan_grades": "Both เกรด A and เกรด AA are carried here; build_commodities.py picks "
                             "ONE grade for the board row and states which and why.",
            "absent_confirmed": "มังคุด (mangosteen) / ลองกอง (longkong) / ลิ้นจี่ (lychee) are "
                                "absent from BOTH NABC endpoint families in every BE year "
                                "2563-2569 — checked, not missed. Do not re-add without new "
                                "evidence.",
        },
        "products": {k: products[k] for k in sorted(products)},
    }


SELFTEST_RECORDS = [
    {"year_th": 2569, "month": "06", "value": "110.5", "unit": "บาท/กก."},
    {"year_th": 2568, "month": "06", "value": "100.0", "unit": "บาท/กก."},
    {"year_th": 2569, "month": "05", "value": "999", "unit": "บาท/กก."},   # different month, ignored
]


def selftest():
    series = {}
    for r in SELFTEST_RECORDS:
        ce = _ce_year(r["year_th"])
        series["%04d-%02d" % (ce, int(r["month"]))] = float(r["value"])
    latest, price, prior, yoy = yoy_same_month(series)
    assert latest == "2026-06" and price == 110.5, (latest, price)
    assert prior == "2025-06" and yoy == 10.5, (prior, yoy)   # (110.5-100)/100*100 = 10.5
    # BE-fold guard: a year_th that would land in the future must raise, never silently wrap.
    try:
        _ce_year(date.today().year + BE_OFFSET + 1)
        raise SystemExit("selftest FAILED: _ce_year accepted a future year_th")
    except AssertionError:
        pass
    print("selftest OK: same-month YoY %s -> %s = %+g%% vs %s; future-year guard fires"
          % (prior, latest, yoy, prior))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stamp", default="", help="pull date (YYYY-MM-DD) recorded in meta.pulled")
    ap.add_argument("--selftest", action="store_true", help="offline parse/aggregate check; no network")
    a = ap.parse_args()
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass

    if a.selftest:
        selftest()
        return

    products, years_th = build()
    assert_acceptance(products)
    doc = payload(products, years_th, a.stamp)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(json.dumps(doc, ensure_ascii=False, separators=(",", ":")))
    print("wrote %s" % OUT)
    for k, v in doc["products"].items():
        print("  %-10s %-28s %8s %-10s YoY %s%%  (%d months, %s..%s)"
              % (k, v["product"], v["price"], v["unit"], v["yoy"],
                 v["n_months"], v["first_month"], v["latest_date"]))


if __name__ == "__main__":
    main()
