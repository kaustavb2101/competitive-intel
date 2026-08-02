#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pull_nesdc_gdp.py — MEASURED Thai real GDP growth, quarterly actual (owner review 2026-08-02, item
(c): "real GDP growth, most recent actual").

WHO ACTUALLY PUBLISHES THAI GDP — NOT the Bank of Thailand
  BOT's own real-sector statistics page (bot.or.th/th/statistics/real-sector.html) links OUT to the
  Office of the National Economic and Social Development Council (สำนักงานสภาพัฒนาการเศรษฐกิจและ
  สังคมแห่งชาติ, NESDC/"สภาพัฒน์") for GDP — BOT does not compile or publish it itself (verified
  2026-08-02, same finding as pull_tpso_cpi.py for CPI). NESDC releases the Quarterly GDP (QGDP) press
  statistic about 6-7 weeks after each quarter ends.

PULL METHOD
  www.nesdc.go.th sits behind a bot-mitigation redirect that a plain urllib GET cannot pass (infinite
  self-redirect without a browser User-Agent + a cookie jar to carry the challenge cookie the first
  redirect sets — verified 2026-08-02). This puller opens the homepage with a browser UA and a
  cookiejar, finds the "ผลิตภัณฑ์มวลรวมในประเทศ ไตรมาสที่ N/YYYY" link (NESDC's own most-recent-QGDP
  link, refreshed by them every quarter), and downloads whatever it points to. NOTE: despite living at
  a query-string URL with no file extension, that link serves the press-release PDF directly (verified
  by magic bytes, not by content-type) — this puller saves it as .pdf regardless of what the URL looks
  like and lets ingest_pdf's extractor confirm it opens as one.

  The headline growth rate is read straight off the first page of the press release via a tolerant
  regex (BE Thai PDF text extraction can drop diacritics/reorder combining marks quarter to quarter —
  e.g. "ร้อยละ" sometimes extracts as "รอยละ" — so the pattern makes the ้ mark optional). If a future
  release's phrasing or layout shifts far enough that this regex no longer matches, the puller hard-
  exits rather than guessing.

VERIFIED 2026-08-02 (live pull): latest released quarter is Q1/2026 (Jan-Mar), published 18 May 2026.
Real GDP grew 2.8% YoY (accelerating from 2.5% in Q4/2025); agriculture +1.2%, non-agriculture +3.0%.
Seasonally-adjusted QoQ: +0.7%. Q2/2026 has not yet been released as of this pull (typically due
~mid-August). This is well above BOT's own June-2026 MPC forecast for full-year 2026 (2.3%) and the
IMF WEO's 2026 projection already on the Macro tab (1.5%) — all three are legitimate but DIFFERENT
things (a realized quarter vs. two different full-year forecasts); do not conflate them on the card.

DETERMINISM: the live pull's PDF is cached (gitignored) at source-data/.nesdc_gdp_raw/; the distilled
source-data/nesdc_gdp.json is committed. `--check` re-parses the cached raw OFFLINE and byte-compares.
No wall clock in the data — `pulled` comes only from --stamp.

Run:
  python3 pull_nesdc_gdp.py --stamp 2026-08-02   # discover + download + parse + write
  python3 pull_nesdc_gdp.py                       # default --stamp = today
  python3 pull_nesdc_gdp.py --check               # offline byte-reproduce from cached raw
"""
import argparse
import datetime
import html
import http.cookiejar
import json
import os
import re
import sys
import unicodedata
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from ingest_pdf import extract_pdf

OUT = os.path.join(ROOT, "source-data", "nesdc_gdp.json")
RAW_DIR = os.path.join(ROOT, "source-data", ".nesdc_gdp_raw")
RAW_PDF = os.path.join(RAW_DIR, "qgdp_release.pdf")
RAW_SRC_URL = os.path.join(RAW_DIR, "source_url.txt")

HOME_URL = "https://www.nesdc.go.th/"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

# NESDC's PDF embeds a subsetted Thai font whose ToUnicode CMap maps several presentation-form
# glyphs (tone marks / thanthakhat in different vertical positions depending on the preceding
# consonant's ascender height) to Private-Use-Area codepoints instead of the real Unicode combining
# marks (verified 2026-08-02: mai tho ้ U+0E49 comes back as U+F706 or U+F70B depending on context,
# thanthakhat ์ U+0E4C as U+F70E, mai ek ่ U+0E48 as U+F70A — not a fixed 1:1 map). _norm() strips the
# whole PUA range rather than trying to enumerate every variant, so "ร้อยละ" reliably normalizes to
# "รอยละ" regardless of which glyph variant the font picked.
RE_ROI_LA = "รอยละ"

# Spot-verification anchor — the Q1/2026 release is permanent public record and will not revise on a
# later run of THIS script (a genuine NESDC revision would be a real news event, not parser drift).
ANCHOR_QUARTER = "Q1/2569"
ANCHOR_YOY = 2.8
ANCHOR_QOQ_SA = 0.7


def _opener():
    cj = http.cookiejar.CookieJar()
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))


def _fetch(opener, url, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with opener.open(req, timeout=timeout) as r:
        return r.read()


def _discover_release_url(opener):
    home = _fetch(opener, HOME_URL).decode("utf-8", "replace")
    m = re.search(r'href="([^"]*)"[^>]*>ผลิตภัณฑ์มวลรวมในประเทศ ไตรมาสที่\s*(\d)/(\d{4})', home)
    if not m:
        sys.exit("pull_nesdc_gdp.py: could not find the latest QGDP release link on the NESDC "
                 "homepage — page layout changed.")
    url, q, y_be = html.unescape(m.group(1)), m.group(2), m.group(3)
    quarter = "Q%s/%s" % (q, y_be)
    return url, quarter


def _norm(text):
    text = unicodedata.normalize("NFC", text)
    text = re.sub(r"[-]", "", text)   # strip misencoded PUA presentation-form glyphs
    return re.sub(r"\s+", " ", text)


def _parse_pdf(pdf_path):
    doc = extract_pdf(pdf_path, pages=(1, 6), want_tables=False)
    pages = {p["page"]: _norm(p["text"]) for p in doc["pages"]}
    p1 = pages.get(1, "")
    m = re.search(r"ไตรมาสที่\s*(\d)/(\d{4}).{0,20}?ขยายตัว%s\s*([\d.]+)" % RE_ROI_LA, p1)
    if not m:
        sys.exit("pull_nesdc_gdp.py: headline growth figure not found on page 1 — release wording "
                 "or layout changed; re-check regex in pull_nesdc_gdp.py.")
    quarter = "Q%s/%s" % (m.group(1), m.group(2))
    yoy = float(m.group(3))

    m_prior = re.search(r"เร่?งขึ้นจาก(?:การขยายตัว|ขยายตัว)%s\s*([\d.]+)\s*ในไตรมาส\s*(\d)/(\d{4})" % RE_ROI_LA, p1)
    prior = None
    if m_prior:
        prior = {"quarter": "Q%s/%s" % (m_prior.group(2), m_prior.group(3)), "yoy": float(m_prior.group(1))}

    m_agri = re.search(r"ภาคเกษตรขยายตัว%s\s*([\d.]+)" % RE_ROI_LA, p1)
    m_nonagri = re.search(r"ภาคนอกเกษตรขยายตัว%s\s*([\d.]+)" % RE_ROI_LA, p1)

    # QoQ-SA: anchor on the "(QoQ SA)" marker itself and take the number right before it, rather
    # than matching the preceding Thai phrase. Verified 2026-08-02: this release's PDF text
    # extraction reorders combining vowels within some Thai words unpredictably (e.g. "khayaay
    # tua" comes back with its vowel and consonant swapped in one spot but not another), so a
    # literal Thai-word match is not reliable here; "(QoQ SA)" is plain ASCII and never reordered.
    qoq_sa = None
    for pg in pages.values():
        m_val = re.search(r"([\d.]+)\s*\(QoQ SA\)", pg)
        if m_val:
            qoq_sa = float(m_val.group(1))
            break

    return {
        "quarter": quarter, "yoy_pct": yoy, "prior_quarter": prior,
        "agriculture_yoy_pct": float(m_agri.group(1)) if m_agri else None,
        "non_agriculture_yoy_pct": float(m_nonagri.group(1)) if m_nonagri else None,
        "qoq_sa_pct": qoq_sa,
    }


def _verify_anchor(fig):
    if fig["quarter"] != ANCHOR_QUARTER:
        return  # a genuinely newer quarter has been released since this puller was last updated
    bad = []
    if abs(fig["yoy_pct"] - ANCHOR_YOY) > 0.05:
        bad.append("yoy_pct: got %s, expected %s" % (fig["yoy_pct"], ANCHOR_YOY))
    if fig["qoq_sa_pct"] is not None and abs(fig["qoq_sa_pct"] - ANCHOR_QOQ_SA) > 0.05:
        bad.append("qoq_sa_pct: got %s, expected %s" % (fig["qoq_sa_pct"], ANCHOR_QOQ_SA))
    if bad:
        sys.exit("pull_nesdc_gdp.py: ANCHOR FAIL (%s) — re-verify before landing:\n  %s"
                 % (ANCHOR_QUARTER, "\n  ".join(bad)))


def build_from_pdf(pdf_path, stamp, source_url):
    fig = _parse_pdf(pdf_path)
    _verify_anchor(fig)
    return {
        "meta": {
            "title": "Thailand real GDP growth — latest actual quarter (Quarterly GDP, QGDP)",
            "generated_by": "pipeline/pull_nesdc_gdp.py",
            "label": "MEASURED — Office of the National Economic and Social Development Council "
                     "(NESDC / สภาพัฒน์), the actual government compiler of Thai GDP. NOT a Bank of "
                     "Thailand series — BOT's own real-sector statistics page links out to NESDC "
                     "rather than hosting it (verified 2026-08-02).",
            "source": "สำนักงานสภาพัฒนาการเศรษฐกิจและสังคมแห่งชาติ (NESDC) — ผลิตภัณฑ์มวลรวมในประเทศ "
                      "รายไตรมาส (Quarterly Gross Domestic Product)",
            "source_page_url": HOME_URL,
            "source_file_url": source_url,
            "unit": "% YoY (real, chain-volume measure) unless noted",
            "pulled": stamp,
        },
        "latest": fig,
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
                    help="OFFLINE: re-parse the cached raw PDF and byte-compare against "
                         "source-data/nesdc_gdp.json; exit 1 on drift, exit 3 SKIP if the committed "
                         "JSON or the gitignored raw cache is absent (network-pulled input).")
    args = ap.parse_args()

    if args.check:
        if not os.path.exists(OUT) or not os.path.exists(RAW_PDF):
            print("pull_nesdc_gdp.py --check: SKIP (committed nesdc_gdp.json or gitignored raw "
                  "source-data/.nesdc_gdp_raw/ absent — network-pulled input, not drift)")
            sys.exit(3)
        prev = json.load(open(OUT, encoding="utf-8"))
        src_url = open(RAW_SRC_URL, encoding="utf-8").read().strip() if os.path.exists(RAW_SRC_URL) else prev["meta"]["source_file_url"]
        data = build_from_pdf(RAW_PDF, prev["meta"]["pulled"], src_url)
        if _dumps(data) != open(OUT, encoding="utf-8").read():
            sys.exit("pull_nesdc_gdp.py --check: nesdc_gdp.json drifted from a fresh parse of the "
                     "cached raw — re-run python3 pipeline/pull_nesdc_gdp.py")
        print("pull_nesdc_gdp.py --check: OK (byte-exact from cached raw, %s = %+.1f%% YoY)"
              % (data["latest"]["quarter"], data["latest"]["yoy_pct"]))
        return

    os.makedirs(RAW_DIR, exist_ok=True)
    opener = _opener()
    print("fetching %s ..." % HOME_URL)
    release_url, quarter_hint = _discover_release_url(opener)
    print("  discovered %s release: %s" % (quarter_hint, release_url))
    pdf_bytes = _fetch(opener, release_url)
    with open(RAW_PDF, "wb") as f:
        f.write(pdf_bytes)
    with open(RAW_SRC_URL, "w", encoding="utf-8", newline="\n") as f:
        f.write(release_url + "\n")
    data = build_from_pdf(RAW_PDF, args.stamp, release_url)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write(_dumps(data))
    print("wrote %s" % OUT)
    lt = data["latest"]
    print("  %s real GDP: %+.1f%% YoY (QoQ SA %s)" % (lt["quarter"], lt["yoy_pct"], lt["qoq_sa_pct"]))


if __name__ == "__main__":
    main()
