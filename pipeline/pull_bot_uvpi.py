#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pull_bot_uvpi.py — MEASURED Bank of Thailand Used Vehicle Price Index (UVPI, EC_EI_040), the
collateral-recovery anchor for objective #1 (portfolio risk). This is the price a lender actually
gets back when it repossesses and auctions a vehicle — the nearest MEASURED read on how much
title-loan collateral value has eroded.

SOURCE
  ดัชนีราคารถยนต์มือสอง (Used Vehicle Price Index), report EC_EI_040, Bank of Thailand:
  https://app.bot.or.th/BTWS_STAT/statistics/BOTWEBSTAT.aspx?reportID=919&language=TH
  Monthly, national, base 2015 (พ.ศ. 2558) = 100, published back to Jan 2011. Three series:
  overall, รถยนต์นั่ง (passenger car), รถยนต์บรรทุก (the "truck" sub-index — see DEFINITION below).
  Built by BoT from Union Auction Public Company Limited's (AUCT's, "บริษัท สหการประมูล จำกัด
  (มหาชน)") own hammer prices — AUCT being the largest used-vehicle auction house in Thailand, 13
  auction centres nationwide, ~50% of its volume from the Bangkok HQ centre alone. BoT's own stated
  purpose (Stat-Horizon paper, ยัง below) is assessing hire-purchase and title-lender risk: "ราคา
  รถยนต์มือสองที่ใช้ในการจัดทำดัชนีฯ จึงควรเป็นราคาที่สะท้อนมูลค่าที่เจ้าหนี้ได้รับเงินคืนหากมีการยึด
  รถและขายทอดตลาด" ("the used-vehicle price used to build the index should reflect the value a
  creditor recovers if it repossesses and auctions the vehicle") — i.e. this IS the collateral-
  recovery scale AutoX's own repossession economics sit on.

DEFINITION — does the "truck" sub-index (รถยนต์บรรทุก) cover PICKUPS or heavy commercial trucks?
  CONFIRMED: it is รถกระบะ — PICKUP TRUCKS, not heavy/commercial trucks. BoT's own 2019 Stat-
  Horizon methodology paper ("ดัชนีราคารถยนต์มือสอง (Used Vehicle Price Index)", ชาครีย์ อักษรถึง +
  จารุพรรณ วานิชธนันกูล, สิงหาคม 2562 — the paper the CURRENT metadata PDF still points to via its
  "ดูรายละเอียดเพิ่มเติม" link) states plainly, captioning its car-vs-truck chart (Figure 4, p.13):
    "เมื่อจำแนกดัชนีราคารถยนต์มือสองออกเป็นประเภทรถยนต์นั่ง (Car) และรถกระบะ (Truck) (ภาพที่ 4)
     พบว่า ดัชนีราคารถยนต์ทั้งสองประเภทส่วนใหญ่มีทิศทางการเปลี่ยนแปลงของราคาไปในทิศทางเดียวกัน"
    ("When the used-vehicle price index is split into passenger-car [Car] and pickup-truck [Truck]
     types [Figure 4], both types' price indices mostly move in the same direction...")
  — i.e. BoT's own paper uses "รถกระบะ" (pickup) and "Truck" as the SAME label for this series. The
  regression appendix (p.16) reuses the identical pairing: "ประเภทรถ (รถนั่ง และรถกระบะ)" ("vehicle
  type: car and pickup"), with a `truck` dummy defined as "1 เมื่อเป็นประเภทรถบรรทุก" — the two Thai
  terms (รถบรรทุก / รถกระบะ) are used interchangeably by the authors throughout. The 11 brands the
  index is built from (Toyota, Isuzu, Honda, Mitsubishi, Nissan, Mazda, Ford, Chevrolet, BMW,
  Mercedes-Benz, Volvo) are passenger-car and pickup marques (Hilux/D-Max/Ranger/Colorado
  territory) — no heavy-truck-only OEM (Hino, Scania, UD Trucks, Fuso) appears, consistent with a
  hire-purchase repossession auction book, not a commercial-fleet one.
  Source: metadata PDF https://app.bot.or.th/BTWS_STAT/statistics/DownloadFile.aspx?file=EC_EI_040_TH.PDF
  ("สามารถดูรายละเอียดเพิ่มเติมได้ที่" links to the paper below) +
  https://www.bot.or.th/content/dam/bot/documents/th/research-and-publications/research/
  stat-horizon-and-stat-in-focus/stat-horizon/UVPI.pdf
  Caveat: the linked methodology paper is dated Aug 2019; BoT's live metadata page still cites it
  as the definitive "more detail" reference as of this pull, with no note of a later revision, but
  a silent post-2019 basket change cannot be fully ruled out. Labelled "pickup trucks (รถกระบะ)"
  on the strength of this citation, not "truck-plated vehicles; pickup coverage unconfirmed".

PULL METHOD
  No clean CSV/JSON endpoint exists behind the ดาวน์โหลด button. The page IS a classic ASP.NET
  WebForms grid (__VIEWSTATE/__EVENTVALIDATION) that renders its data server-side as a plain HTML
  table (id="dgExcel") — no XHR/JSON call, no Playwright needed. Method:
    1. GET reportID=919 fresh -> read __VIEWSTATE / __VIEWSTATEGENERATOR / __EVENTVALIDATION,
       the session cookie, and the currently valid period range from #lblValidPeriodRange
       (e.g. "( ม.ค. 2554 - พ.ค. 2569 )" — BE, converted -543).
    2. POST the same URL as a real form submit (drpFromMonth/drpFromYear/drpToMonth/drpToYear set
       to that FULL valid range, btnSubmit=Submit) — this re-renders #dgExcel with EVERY published
       month as columns (185 as of this pull: 2011-01 .. 2026-05), not just the default 6-month view.
    3. Parse #dgExcel: row 0 = period headers (Thai BE month-year, latest column flagged " p" =
       preliminary/still-revisable); the 3 data rows are matched by LABEL substring, not position
       ("นั่ง" -> car, "บรรทุก" -> truck, neither -> overall), so a future column-reorder can't
       silently swap two series.
  DETERMINISM: the live pull's full POST response is cached (gitignored) at
  source-data/.bot_uvpi_raw/EC_EI_040_full.html; source-data/bot_uvpi.json is the committed,
  distilled artifact. `--check` re-parses the cached raw OFFLINE and byte-compares; exit 3 SKIP if
  either the committed JSON or the gitignored raw cache is absent (network-pulled input, not drift).
  No wall clock in the data — `pulled` comes only from --stamp.

ACCEPTANCE TEST — six spot-verified months (base 2015=100), hard-fails (not silently adjusts) if
the source no longer reproduces them:
  Dec 2025  overall 70.41 / car 84.46 / truck 61.85
  Jan 2026  overall 77.04 / car 96.60 / truck 65.12
  Feb 2026  overall 79.02 / car 99.62 / truck 66.26
  Mar 2026  overall 80.51 / car 99.38 / truck 68.49
  Apr 2026  overall 72.75 / car 86.68 / truck 63.81
  May 2026  overall 75.15 / car 87.78 / truck 66.81   (preliminary, flagged "p" by BoT)

Run:
  python3 pull_bot_uvpi.py --stamp 2026-08-02   # download + parse + write
  python3 pull_bot_uvpi.py                       # default --stamp = today
  python3 pull_bot_uvpi.py --check               # offline byte-reproduce from cached raw
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

OUT = os.path.join(ROOT, "source-data", "bot_uvpi.json")
RAW_DIR = os.path.join(ROOT, "source-data", ".bot_uvpi_raw")
RAW_HTML = os.path.join(RAW_DIR, "EC_EI_040_full.html")

REPORT_URL = "https://app.bot.or.th/BTWS_STAT/statistics/BOTWEBSTAT.aspx?reportID=919&language=TH"
METADATA_PDF_URL = "https://app.bot.or.th/BTWS_STAT/statistics/DownloadFile.aspx?file=EC_EI_040_TH.PDF"
STATHORIZON_URL = ("https://www.bot.or.th/content/dam/bot/documents/th/research-and-publications/"
                    "research/stat-horizon-and-stat-in-focus/stat-horizon/UVPI.pdf")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

TH_MON = {"ม.ค.": 1, "ก.พ.": 2, "มี.ค.": 3, "เม.ย.": 4, "พ.ค.": 5, "มิ.ย.": 6,
          "ก.ค.": 7, "ส.ค.": 8, "ก.ย.": 9, "ต.ค.": 10, "พ.ย.": 11, "ธ.ค.": 12}
TH_MON_RE = "|".join(re.escape(m) for m in TH_MON)

# Spot-verification anchors (base 2015=100) — a re-publish that moves any of these fails loudly,
# forcing re-verification rather than silently landing changed history.
ANCHORS = {
    "2025-12": {"overall": 70.41, "car": 84.46, "truck": 61.85},
    "2026-01": {"overall": 77.04, "car": 96.60, "truck": 65.12},
    "2026-02": {"overall": 79.02, "car": 99.62, "truck": 66.26},
    "2026-03": {"overall": 80.51, "car": 99.38, "truck": 68.49},
    "2026-04": {"overall": 72.75, "car": 86.68, "truck": 63.81},
    "2026-05": {"overall": 75.15, "car": 87.78, "truck": 66.81},
}


def _be_month_year_to_iso(text):
    """'ม.ค. 2554' / 'พ.ค. 2569 p' -> ('2011-01', preliminary_bool). None if unparseable."""
    prelim = bool(re.search(r"\bp\b", text))
    m = re.search(r"(%s)\s*(\d{4})" % TH_MON_RE, text)
    if not m:
        return None, False
    mon_th, y_be = m.group(1), int(m.group(2))
    y_be = y_be - 543 if y_be > 2400 else y_be  # BE guard — bare BE years read 543y in the future
    return "%04d-%02d" % (y_be, TH_MON[mon_th]), prelim


def _fetch(opener, url, data=None, extra_headers=None, timeout=60):
    headers = {"User-Agent": UA}
    if extra_headers:
        headers.update(extra_headers)
    req = urllib.request.Request(url, data=data, headers=headers)
    with opener.open(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace"), dict(r.getheaders())


def _hidden_field(html, name):
    m = re.search(r'id="%s"[^>]*value="([^"]*)"' % re.escape(name), html)
    return m.group(1) if m else ""


def _fetch_full_history_html():
    """GET the report, read its currently valid period range + ASP.NET postback state, POST the
    date-range form to expand the grid to that FULL range, and return the response HTML."""
    cj = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))

    get_html, _ = _fetch(opener, REPORT_URL)
    m = re.search(r'id="lblValidPeriodRange"[^>]*>([^<]*)<', get_html)
    if not m:
        sys.exit("pull_bot_uvpi.py: lblValidPeriodRange not found on the GET page — page layout changed.")
    range_text = m.group(1)
    m = re.search(r"(%s)\s*(\d{4})\s*-\s*(%s)\s*(\d{4})" % (TH_MON_RE, TH_MON_RE), range_text)
    if not m:
        sys.exit("pull_bot_uvpi.py: could not parse valid period range %r" % range_text)
    from_mon, from_y_be, to_mon, to_y_be = m.groups()
    from_y_ad, to_y_ad = int(from_y_be) - 543, int(to_y_be) - 543

    form = {
        "__EVENTTARGET": "",
        "__EVENTARGUMENT": "",
        "__LASTFOCUS": "",
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
    post_html, _ = _fetch(opener, REPORT_URL, data=body, extra_headers={
        "Content-Type": "application/x-www-form-urlencoded",
        "Referer": REPORT_URL,
        "Origin": "https://app.bot.or.th",
    })
    return post_html


def _parse_dgexcel(html):
    """Parse the #dgExcel grid -> {"overall"|"car"|"truck": {"YYYY-MM": value}}, preliminary set."""
    m = re.search(r'<table[^>]*id="dgExcel"[^>]*>', html)
    if not m:
        sys.exit("pull_bot_uvpi.py: #dgExcel table not found in the response — page layout changed.")
    start = m.start()
    end = html.find("</table>", start)
    if end == -1:
        sys.exit("pull_bot_uvpi.py: #dgExcel table not closed — truncated response?")
    trs = re.findall(r"<tr[^>]*>(.*?)</tr>", html[start:end + 8], re.S)
    if len(trs) != 4:
        sys.exit("pull_bot_uvpi.py: expected 4 rows (header + overall/car/truck) in #dgExcel, got %d"
                  % len(trs))

    def cells(tr):
        return [re.sub(r"&nbsp;", " ", c).strip()
                for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S)]

    header = cells(trs[0])[2:]
    periods, preliminary = [], []
    for h in header:
        iso, p = _be_month_year_to_iso(h)
        if iso is None:
            sys.exit("pull_bot_uvpi.py: unparseable period header %r" % h)
        periods.append(iso)
        if p:
            preliminary.append(iso)

    VAL = re.compile(r"^-?\d+(?:\.\d+)?$")
    series = {}
    missing = {}
    for tr in trs[1:]:
        cs = cells(tr)
        label, vals = cs[1], cs[2:]
        if "นั่ง" in label:
            key = "car"
        elif "บรรทุก" in label:
            key = "truck"
        else:
            key = "overall"
        if len(vals) != len(periods):
            sys.exit("pull_bot_uvpi.py: row %r has %d values for %d periods" % (label, len(vals), len(periods)))
        d = {}
        miss = []
        for period, v in zip(periods, vals):
            if VAL.match(v):
                d[period] = float(v)
            else:
                miss.append(period)  # honestly absent — never fabricated
        series[key] = d
        if miss:
            missing[key] = sorted(miss)

    if set(series.keys()) != {"overall", "car", "truck"}:
        sys.exit("pull_bot_uvpi.py: expected overall/car/truck rows, got %r" % sorted(series.keys()))
    return series, sorted(set(preliminary)), missing


def _verify_anchors(series):
    bad = []
    for period, want in ANCHORS.items():
        for name, want_v in want.items():
            got_v = series.get(name, {}).get(period)
            if got_v is None or abs(got_v - want_v) > 0.005:
                bad.append("%s/%s: got %s, expected %s" % (period, name, got_v, want_v))
    if bad:
        sys.exit("pull_bot_uvpi.py: ANCHOR FAIL — the source no longer reproduces the verified "
                  "sample; STOP and re-verify rather than adjusting:\n  " + "\n  ".join(bad))


def build_from_html(html, stamp):
    series, preliminary, missing = _parse_dgexcel(html)
    _verify_anchors(series)

    n_months = {k: len(v) for k, v in series.items()}
    all_periods = sorted(set().union(*[set(v) for v in series.values()]))

    return {
        "meta": {
            "title": "Used Vehicle Price Index (UVPI, EC_EI_040) — the collateral-recovery anchor "
                     "for AutoX's title-loan book (portfolio risk, objective #1)",
            "generated_by": "pipeline/pull_bot_uvpi.py",
            "label": "MEASURED — Bank of Thailand (ธปท.), report EC_EI_040 ดัชนีราคารถยนต์มือสอง. "
                     "Built by BoT from Union Auction Public Company Limited's (AUCT, บริษัท "
                     "สหการประมูล จำกัด (มหาชน)) own auction hammer prices — AUCT is Thailand's "
                     "largest used-vehicle auction house (13 auction centres nationwide). BoT's own "
                     "stated purpose is assessing hire-purchase / title-lender collateral risk: the "
                     "used price this index tracks is the price a lender recovers when it "
                     "repossesses and auctions a vehicle.",
            "source_url": REPORT_URL,
            "metadata_pdf_url": METADATA_PDF_URL,
            "methodology_paper_url": STATHORIZON_URL,
            "base": "2015 (พ.ศ. 2558) = 100",
            "frequency": "monthly",
            "definition_truck_series": (
                "CONFIRMED PICKUP TRUCKS (รถกระบะ), not heavy/commercial trucks. BoT's own 2019 "
                "Stat-Horizon methodology paper (still the live 'ดูรายละเอียดเพิ่มเติม' link from the "
                "current metadata PDF) captions its car-vs-truck comparison chart: 'เมื่อจำแนกดัชนี"
                "ราคารถยนต์มือสองออกเป็นประเภทรถยนต์นั่ง (Car) และรถกระบะ (Truck)' — i.e. BoT itself "
                "uses รถกระบะ (pickup) and 'Truck' interchangeably for this series; the regression "
                "appendix repeats the same pairing ('ประเภทรถ (รถนั่ง และรถกระบะ)'). The 11 "
                "constituent brands (Toyota, Isuzu, Honda, Mitsubishi, Nissan, Mazda, Ford, "
                "Chevrolet, BMW, Mercedes-Benz, Volvo) are passenger-car/pickup marques — no "
                "heavy-truck-only OEM (Hino, Scania, UD Trucks, Fuso) appears. Caveat: that "
                "methodology paper is dated Aug 2019; a silent post-2019 basket change cannot be "
                "fully ruled out, but the live metadata page still cites it as the current "
                "definitive reference with no note of revision."
            ),
            "pull_method": "No CSV/JSON endpoint exists behind the download button. The report page "
                           "is an ASP.NET WebForms grid (__VIEWSTATE/__EVENTVALIDATION) that renders "
                           "its data server-side as a plain HTML table (id=dgExcel); pulled by GET "
                           "(read postback state + the live valid period range) then a real form "
                           "POST re-requesting that full range — no Playwright needed.",
            "pulled": stamp,
            "n_months": n_months,
            "period_range": {"min": all_periods[0], "max": all_periods[-1]} if all_periods else None,
            "preliminary_periods": preliminary,
            "preliminary_note": "BoT marks its most recent published month 'p' (ข้อมูลเบื้องต้น, "
                                "preliminary) — subject to revision on the next release.",
            "missing_periods": missing,
            "acceptance_test": "6 spot-verified months (2025-12..2026-05) checked against fixed "
                               "anchors on every pull; a mismatch hard-fails rather than silently "
                               "landing changed history — see ANCHORS in pull_bot_uvpi.py.",
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
                         "source-data/bot_uvpi.json; exit 1 on drift, exit 3 SKIP if the committed "
                         "JSON or the gitignored raw cache is absent (network-pulled input).")
    args = ap.parse_args()

    if args.check:
        if not os.path.exists(OUT) or not os.path.exists(RAW_HTML):
            print("pull_bot_uvpi.py --check: SKIP (committed bot_uvpi.json or gitignored raw "
                  "source-data/.bot_uvpi_raw/ absent — network-pulled input, not drift)")
            sys.exit(3)
        prev = json.load(open(OUT, encoding="utf-8"))
        html = open(RAW_HTML, encoding="utf-8", errors="ignore").read()
        data = build_from_html(html, prev["meta"]["pulled"])
        if _dumps(data) != open(OUT, encoding="utf-8").read():
            sys.exit("pull_bot_uvpi.py --check: bot_uvpi.json drifted from a fresh parse of the "
                     "cached raw — re-run python3 pipeline/pull_bot_uvpi.py")
        print("pull_bot_uvpi.py --check: OK (byte-exact from cached raw, %d months)"
              % data["meta"]["n_months"]["overall"])
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
    n = data["meta"]["n_months"]
    rng = data["meta"]["period_range"]
    print("  months: overall=%d car=%d truck=%d  range %s..%s" %
          (n["overall"], n["car"], n["truck"], rng["min"], rng["max"]))
    print("  preliminary: %s" % data["meta"]["preliminary_periods"])
    print("  acceptance test: PASSED (6/6 anchor months matched)")


if __name__ == "__main__":
    main()
