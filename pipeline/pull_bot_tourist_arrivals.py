#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pull_bot_tourist_arrivals.py — MEASURED monthly foreign tourist arrivals (owner escalation
2026-08-02: the "TOURISTS" chip on the live macro strip showed "32.9M / 2025", an annual figure,
while the owner pointed out monthly 2026 arrivals are published and asked to find them).

SOURCE
  เครื่องชี้ภาวะการท่องเที่ยว (Tourism Indicator), report EC_EI_028_S2, Bank of Thailand:
  https://app.bot.or.th/BTWS_STAT/statistics/BOTWEBSTAT.aspx?reportID=875&language=TH
  Row 1 of that report: "จำนวนนักท่องเที่ยวต่างประเทศที่เดินทางเข้าประเทศไทย (พันคน)" — number of
  foreign tourists arriving in Thailand, thousand persons, MONTHLY. Same BOTWEBSTAT ASP.NET grid
  idiom as pull_bot_uvpi.py (reportID=919) / pull_bot_current_account.py (reportID=953): GET the
  report to read the live valid-period-range + postback state, POST the same form re-requesting
  that full range to expand #dgExcel to full history.

  BOT compiles this series from Immigration Bureau arrival records (its statistical release notes
  attribute it to the Immigration Bureau / Ministry of Tourism and Sports feed) — it is BOT's own
  carried copy of the same headline number MOTS and the Department of Tourism report in their own
  monthly releases, not a BOT-original survey.

VERIFIED 2026-08-02 (live pull): valid period range Jan 2015 - Jun 2026. Latest three months (all
flagged "p", preliminary): Apr 2026 2,368.90k, May 2026 2,346.85k (cross-checks against the
2,346,845 May-2026 figure widely reported by MOTS/press same week), Jun 2026 1,841.55k (a partial/
early preliminary read — BOT's own "p" flag, not a parsing artifact). These three are the anchors
below; a mismatch means the parser broke, not that BOT revised published history.

DETERMINISM: the live pull's full POST response is cached (gitignored) at
source-data/.bot_tourist_arrivals_raw/EC_EI_028_full.html; source-data/bot_tourist_arrivals.json is
the committed, distilled artifact. `--check` re-parses the cached raw OFFLINE and byte-compares. No
wall clock in the data — `pulled` comes only from --stamp.

Run:
  python3 pull_bot_tourist_arrivals.py --stamp 2026-08-02   # download + parse + write
  python3 pull_bot_tourist_arrivals.py                       # default --stamp = today
  python3 pull_bot_tourist_arrivals.py --check               # offline byte-reproduce from cached raw
"""
import argparse
import datetime
import http.cookiejar
import json
import os
import re
import sys
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

OUT = os.path.join(ROOT, "source-data", "bot_tourist_arrivals.json")
RAW_DIR = os.path.join(ROOT, "source-data", ".bot_tourist_arrivals_raw")
RAW_HTML = os.path.join(RAW_DIR, "EC_EI_028_full.html")

REPORT_URL = "https://app.bot.or.th/BTWS_STAT/statistics/BOTWEBSTAT.aspx?reportID=875&language=TH"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

TH_MON = {"ม.ค.": 1, "ก.พ.": 2, "มี.ค.": 3, "เม.ย.": 4, "พ.ค.": 5, "มิ.ย.": 6,
          "ก.ค.": 7, "ส.ค.": 8, "ก.ย.": 9, "ต.ค.": 10, "พ.ย.": 11, "ธ.ค.": 12}
TH_MON_RE = "|".join(re.escape(m) for m in TH_MON)

# label substring -> output key (matched by substring, never row position).
ROW_KEYS = [
    ("จำนวนนักท่องเที่ยวต่างประเทศที่เดินทางเข้าประเทศไทย", "foreign_arrivals_thousand"),
]

# Spot-verification anchors (thousand persons) — a mismatch means the parser broke, not that BOT
# revised published history (these three months are all still flagged "p" at pull time).
ANCHORS = {
    "2026-03": 2775.20,
    "2026-04": 2368.90,
    "2026-05": 2346.85,
    "2026-06": 1841.55,
}


def _be_month_year_to_iso(text):
    prelim = bool(re.search(r"\bp\b", text))
    m = re.search(r"(%s)\s*(\d{4})" % TH_MON_RE, text)
    if not m:
        return None, False
    mon_th, y_be = m.group(1), int(m.group(2))
    y_be = y_be - 543 if y_be > 2400 else y_be
    return "%04d-%02d" % (y_be, TH_MON[mon_th]), prelim


def _fetch(opener, url, data=None, extra_headers=None, timeout=60):
    headers = {"User-Agent": UA}
    if extra_headers:
        headers.update(extra_headers)
    req = urllib.request.Request(url, data=data, headers=headers)
    with opener.open(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def _hidden_field(html, name):
    m = re.search(r'id="%s"[^>]*value="([^"]*)"' % re.escape(name), html)
    return m.group(1) if m else ""


def _fetch_full_history_html():
    cj = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))

    get_html = _fetch(opener, REPORT_URL)
    m = re.search(r'id="lblValidPeriodRange"[^>]*>([^<]*)<', get_html)
    if not m:
        sys.exit("pull_bot_tourist_arrivals.py: lblValidPeriodRange not found on the GET page — "
                 "page layout changed.")
    range_text = m.group(1)
    m = re.search(r"(%s)\s*(\d{4})\s*-\s*(%s)\s*(\d{4})" % (TH_MON_RE, TH_MON_RE), range_text)
    if not m:
        sys.exit("pull_bot_tourist_arrivals.py: could not parse valid period range %r" % range_text)
    from_mon, from_y_be, to_mon, to_y_be = m.groups()
    from_y_ad, to_y_ad = int(from_y_be) - 543, int(to_y_be) - 543

    form = {
        "__EVENTTARGET": "", "__EVENTARGUMENT": "", "__LASTFOCUS": "",
        "__VIEWSTATE": _hidden_field(get_html, "__VIEWSTATE"),
        "__VIEWSTATEGENERATOR": _hidden_field(get_html, "__VIEWSTATEGENERATOR"),
        "__EVENTVALIDATION": _hidden_field(get_html, "__EVENTVALIDATION"),
        "drpPeriod": "MTH",
        "drpFromMonth": "xxxx%02dxx" % TH_MON[from_mon],
        "drpFromYear": "%04dxxxx" % from_y_ad,
        "drpToMonth": "xxxx%02dxx" % TH_MON[to_mon],
        "drpToYear": "%04dxxxx" % to_y_ad,
        "btnSubmit": "Submit",
    }
    body = urllib.parse.urlencode(form).encode("utf-8")
    return _fetch(opener, REPORT_URL, data=body, extra_headers={
        "Content-Type": "application/x-www-form-urlencoded",
        "Referer": REPORT_URL, "Origin": "https://app.bot.or.th",
    })


def _parse_dgexcel(html):
    m = re.search(r'<table[^>]*id="dgExcel"[^>]*>', html)
    if not m:
        sys.exit("pull_bot_tourist_arrivals.py: #dgExcel table not found — page layout changed.")
    start = m.start()
    end = html.find("</table>", start)
    if end == -1:
        sys.exit("pull_bot_tourist_arrivals.py: #dgExcel table not closed — truncated response?")
    trs = re.findall(r"<tr[^>]*>(.*?)</tr>", html[start:end + 8], re.S)

    def cells(tr):
        return [re.sub(r"&nbsp;", " ", c).strip()
                for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S)]

    header = cells(trs[0])[2:]
    periods, preliminary = [], []
    for h in header:
        iso, p = _be_month_year_to_iso(h)
        if iso is None:
            sys.exit("pull_bot_tourist_arrivals.py: unparseable period header %r" % h)
        periods.append(iso)
        if p:
            preliminary.append(iso)

    VAL = re.compile(r"^-?[\d,]+(?:\.\d+)?$")
    series = {}
    for tr in trs[1:]:
        cs = cells(tr)
        if len(cs) < 2:
            continue
        label = cs[1]
        key = next((k for sub, k in ROW_KEYS if sub in label), None)
        if key is None:
            continue
        vals = cs[2:]
        d = {}
        for period, v in zip(periods, vals):
            if VAL.match(v):
                d[period] = float(v.replace(",", ""))
        series[key] = d
    missing = [k for _, k in ROW_KEYS if k not in series]
    if missing:
        sys.exit("pull_bot_tourist_arrivals.py: expected rows not found: %r (labels may have "
                 "changed)" % missing)
    return series, sorted(set(preliminary))


def _verify_anchors(series):
    bad = []
    arr = series.get("foreign_arrivals_thousand", {})
    for period, want_v in ANCHORS.items():
        got_v = arr.get(period)
        if got_v is None or abs(got_v - want_v) > 0.5:
            bad.append("%s: got %s, expected %s" % (period, got_v, want_v))
    if bad:
        sys.exit("pull_bot_tourist_arrivals.py: ANCHOR FAIL — re-verify before landing:\n  " + "\n  ".join(bad))


def build_from_html(html, stamp):
    series, preliminary = _parse_dgexcel(html)
    _verify_anchors(series)
    arr = series["foreign_arrivals_thousand"]
    periods = sorted(arr)
    latest_p = periods[-1] if periods else None
    # trailing-12-month sum for a rolling annual comparator against the old annual "32.9M" chip
    ttm_periods = periods[-12:]
    ttm_sum_thousand = sum(arr[p] for p in ttm_periods) if len(ttm_periods) == 12 else None
    return {
        "meta": {
            "title": "Foreign tourist arrivals to Thailand — the MEASURED monthly BOT series behind "
                     "the 'Tourists' chip on the macro strip",
            "generated_by": "pipeline/pull_bot_tourist_arrivals.py",
            "label": "MEASURED — Bank of Thailand (ธปท.), report EC_EI_028_S2 เครื่องชี้ภาวะการท่องเที่ยว, "
                     "row 1 (จำนวนนักท่องเที่ยวต่างประเทศที่เดินทางเข้าประเทศไทย). Thousand persons, monthly. "
                     "BOT's own carried copy of the Immigration-Bureau-sourced arrivals count also "
                     "released monthly by the Ministry of Tourism and Sports.",
            "source_url": REPORT_URL,
            "unit": "thousand persons",
            "frequency": "monthly",
            "pulled": stamp,
            "period_range": {"min": periods[0], "max": periods[-1]} if periods else None,
            "preliminary_periods": preliminary,
            "preliminary_note": "BoT marks recent months in the default window 'p' (ข้อมูลเบื้องต้น, "
                                "preliminary) — subject to revision on the next release.",
            "latest": {"period": latest_p, "foreign_arrivals_thousand": arr.get(latest_p)} if latest_p else None,
            "trailing_12m": {"periods": ttm_periods, "sum_thousand": ttm_sum_thousand} if ttm_sum_thousand else None,
            "acceptance_test": "4 spot-verified months (2026-03..2026-06, all flagged preliminary at "
                               "pull time) checked against fixed anchors on every pull; a mismatch "
                               "hard-fails rather than silently landing changed history — see "
                               "ANCHORS in pull_bot_tourist_arrivals.py.",
        },
        "series": series,
    }


def _dumps(data):
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def main():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:
            pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stamp", default=datetime.date.today().isoformat(),
                    help="YYYY-MM-DD pull date embedded in meta.pulled (default: today)")
    ap.add_argument("--check", action="store_true",
                    help="OFFLINE: re-parse the cached raw HTML and byte-compare against "
                         "source-data/bot_tourist_arrivals.json; exit 1 on drift, exit 3 SKIP if the "
                         "committed JSON or the gitignored raw cache is absent (network-pulled "
                         "input).")
    args = ap.parse_args()

    if args.check:
        if not os.path.exists(OUT) or not os.path.exists(RAW_HTML):
            print("pull_bot_tourist_arrivals.py --check: SKIP (committed bot_tourist_arrivals.json or "
                  "gitignored raw source-data/.bot_tourist_arrivals_raw/ absent — network-pulled "
                  "input, not drift)")
            sys.exit(3)
        prev = json.load(open(OUT, encoding="utf-8"))
        html = open(RAW_HTML, encoding="utf-8", errors="ignore").read()
        data = build_from_html(html, prev["meta"]["pulled"])
        if _dumps(data) != open(OUT, encoding="utf-8").read():
            sys.exit("pull_bot_tourist_arrivals.py --check: bot_tourist_arrivals.json drifted from a "
                     "fresh parse of the cached raw — re-run python3 pipeline/pull_bot_tourist_arrivals.py")
        print("pull_bot_tourist_arrivals.py --check: OK (byte-exact from cached raw, latest %s)"
              % data["meta"]["latest"])
        return

    os.makedirs(RAW_DIR, exist_ok=True)
    print("fetching %s ..." % REPORT_URL)
    html = _fetch_full_history_html()
    with open(RAW_HTML, "w", encoding="utf-8", newline="\n") as f:
        f.write(html)
    data = build_from_html(html, args.stamp)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write(_dumps(data))
    print("wrote %s" % OUT)
    print("  latest: %s" % data["meta"]["latest"])
    print("  preliminary periods: %s" % data["meta"]["preliminary_periods"])
    print("  acceptance test: PASSED (4/4 anchor months matched)")


if __name__ == "__main__":
    main()
