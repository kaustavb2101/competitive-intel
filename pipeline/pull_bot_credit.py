#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pull_bot_credit.py — MEASURED Bank of Thailand credit-quality anchor (portfolio risk, objective #1).

WHY THIS EXISTS
  The platform's per-branch risk score is an ESTIMATED 0-100 composite (build_branch_risk.py) with
  no real default anchor — it is a TRIAGE RANK, not a predicted NPL. To read it honestly you need the
  real-world scale it sits against: the MEASURED non-performing-loan (NPL) level BoT publishes for the
  banking system and the household-debt backdrop. This puller extracts those measured figures so the
  app can show the true NPL scale ALONGSIDE (never inside) the estimated composite.

WHAT IS MEASURED (every figure here is read from a BoT source and spot-verified against an anchor):
  From the Financial Stability Report 2024 (รายงานการประเมินเสถียรภาพระบบการเงินไทย 2567) — a real
  TEXT-LAYER PDF (verified: 28/29 pages text), so these are deterministic text extractions:
    - system_npl_pct              commercial-bank (ธพ.) gross NPL / total loans, r้อยละ 2.8, end-2567 (p.20)
    - household_debt_to_gdp_pct   Thai household debt / GDP, ร้อยละ 88.4, end-2567 (p.6)
  From BoT statistics report 984 (เงินให้กู้ยืมแก่ภาคครัวเรือนจำแนกตามวัตถุประสงค์, "Loans to
  households classified by purpose", app.bot.or.th) — a plain GET renders the data table server-side,
  so the cached HTML re-parses byte-deterministically like a CSV pull:
    - household_debt_thb          total household debt, latest quarter (Q2/2568) — the ~16.3tn scale
    - auto_hp_household_debt_thb  the "ซื้อหรือเช่าซื้อรถยนต์และรถจักรยานยนต์" (auto + motorcycle
                                  purchase / hire-purchase) line — the vehicle-collateral loan book
                                  nearest AutoX's title-loan collateral, and its share of household debt.

WHAT IS HONESTLY ABSENT (never fabricated):
    - auto_hp_npl_pct is left null. BoT's finest NPL-by-consumer-loan-PURPOSE split (which carries the
      auto hire-purchase NPL, ~2.1%) lives only behind BoT's documented data API (apiportal.bot.or.th),
      which is geoblocked from this environment (HTTP 502 via the proxy). The public BOTWEBSTAT report
      pages expose household loans by purpose (report 984, used above) and system NPL (FSR), but not the
      per-purpose NPL split. Rather than invent a number, this field stays null with a stated reason; the
      app surfaces the nearest MEASURED vehicle-collateral NPL scale from peer_npl.json (vehicle-title
      peers' own reported NPL) instead.

DETERMINISM / PROVENANCE (mirrors pull_oae_farm_economics.py):
  - Raw sources are cached (gitignored) in source-data/.bot_credit_raw/ (FSR2024.pdf, report984.html);
    the distilled source-data/bot_credit.json is committed.
  - `pulled` comes only from --stamp; no wall clock in the data, so a re-parse of the same cached raw
    with the same --stamp is byte-identical.
  - --check re-parses the cached raw OFFLINE and byte-compares; exit 3 SKIP if the committed JSON or the
    gitignored raw is absent (a network-pulled input, not drift).

Run:
  python3 pull_bot_credit.py --stamp 2026-07-18   # download + parse + write
  python3 pull_bot_credit.py                       # default --stamp = today
  python3 pull_bot_credit.py --check               # offline byte-reproduce from cached raw
"""
import argparse
import datetime
import html
import json
import os
import re
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from ingest_pdf import extract_pdf

OUT = os.path.join(ROOT, "source-data", "bot_credit.json")
RAW_DIR = os.path.join(ROOT, "source-data", ".bot_credit_raw")
RAW_FSR = os.path.join(RAW_DIR, "FSR2024.pdf")
RAW_HH = os.path.join(RAW_DIR, "report984.html")

FSR_URL = ("https://www.bot.or.th/content/dam/bot/documents/th/research-and-publications/reports/"
           "financial-stability-report/FSR2024.pdf")
HH_URL = "https://app.bot.or.th/BTWS_STAT/statistics/BOTWEBSTAT.aspx?reportID=984&language=TH"
CA = "/root/.ccr/ca-bundle.crt"
UA = {"User-Agent": "Mozilla/5.0"}

# Spot-verification anchors — a re-publish that moves any of these fails loudly, forcing
# re-verification rather than silently landing changed data.
ANCHOR_SYSTEM_NPL = 2.8
ANCHOR_HH_GDP = 88.4
ANCHOR_HH_TOTAL_MIL = 16308809          # total household debt, latest column (Q2/2568), ล้านบาท
ANCHOR_AUTO_HP_MIL = 1557477            # auto + motorcycle purchase/hire-purchase, ล้านบาท


def _fetch(url, timeout=180):
    import ssl
    ctx = ssl.create_default_context(cafile=CA) if os.path.exists(CA) else None
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
        return r.read()


# ---- FSR2024 text-layer extraction --------------------------------------------
def _parse_fsr(pdf_path):
    doc = extract_pdf(pdf_path, pages=(1, 29), want_tables=False)
    pages = {p["page"]: re.sub(r"\s+", " ", p["text"]) for p in doc["pages"]}
    p6, p20 = pages.get(6, ""), pages.get(20, "")
    m_npl = re.search(r"NPL ratio อยู่ที่ ?ร้อยละ (\d+(?:\.\d+)?)", p20)
    m_gdp = re.search(r"GDP\).{0,40}?ร้อยละ (\d+(?:\.\d+)?) ?ณ สิ้นปี", p6)
    if not m_npl:
        sys.exit("pull_bot_credit.py: system NPL not found on FSR2024 p.20 — check label.")
    if not m_gdp:
        sys.exit("pull_bot_credit.py: household-debt/GDP not found on FSR2024 p.6 — check label.")
    return float(m_npl.group(1)), float(m_gdp.group(1))


# ---- BoT report 984 (household loans by purpose) HTML extraction ---------------
_VAL = re.compile(r"^-?\d[\d,]*(?:\.\d+)?$")


def _rows(html_text):
    out = []
    for r in re.findall(r"<tr[^>]*>(.*?)</tr>", html_text, re.S):
        cells = [html.unescape(re.sub(r"<[^>]+>", " ", c)).strip()
                 for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", r, re.S)]
        cells = [re.sub(r"\s+", " ", c) for c in cells if c.strip() != ""]
        if cells:
            out.append(cells)
    return out


def _latest_value_mil(rows, label_sub):
    """First (latest) numeric value on the row whose text contains label_sub, as an int of ล้านบาท."""
    for cs in rows:
        if label_sub in " ".join(cs):
            vals = [c for c in cs if _VAL.match(c)]
            vals = [v for v in vals if "," in v] or vals   # drop the leading row-index cell
            if vals:
                return int(vals[0].replace(",", ""))
    return None


def _parse_household(html_text):
    rows = _rows(html_text)
    period = None
    for cs in rows:
        for c in cs:
            m = re.match(r"(Q[1-4]/\d{4})", c)
            if m:
                period = m.group(1)
                break
        if period:
            break
    total = _latest_value_mil(rows, "รวม")
    auto = _latest_value_mil(rows, "รถยนต์และรถจักรยานยนต์")
    if not period or total is None or auto is None:
        sys.exit("pull_bot_credit.py: report 984 parse failed (period=%s total=%s auto=%s) — "
                 "check the table layout." % (period, total, auto))
    return period, total, auto


def _verify(system_npl, hh_gdp, hh_total_mil, auto_hp_mil):
    checks = [("system_npl", system_npl, ANCHOR_SYSTEM_NPL, 0.05),
              ("household_debt_to_gdp", hh_gdp, ANCHOR_HH_GDP, 0.05),
              ("household_debt_total", hh_total_mil, ANCHOR_HH_TOTAL_MIL, 0.5),
              ("auto_hp_debt", auto_hp_mil, ANCHOR_AUTO_HP_MIL, 0.5)]
    for name, got, want, tol in checks:
        if abs(got - want) > tol:
            sys.exit("pull_bot_credit.py: ANCHOR FAIL %s = %s, expected %s — the source changed; "
                     "re-verify before landing." % (name, got, want))


def build_from_raw(stamp):
    system_npl, hh_gdp = _parse_fsr(RAW_FSR)
    with open(RAW_HH, encoding="utf-8", errors="ignore") as f:
        period, hh_total_mil, auto_hp_mil = _parse_household(f.read())
    _verify(system_npl, hh_gdp, hh_total_mil, auto_hp_mil)
    auto_share = round(auto_hp_mil / hh_total_mil * 100, 2)
    return {
        "meta": {
            "title": "Bank of Thailand credit-quality anchor (portfolio risk, objective #1)",
            "generated_by": "pipeline/pull_bot_credit.py",
            "label": "MEASURED — Bank of Thailand. System non-performing-loan (NPL) level and "
                     "household-debt backdrop: the real-world scale the ESTIMATED 0-100 branch-risk "
                     "triage score sits against. System NPL + household-debt/GDP from the Financial "
                     "Stability Report 2024 text layer (not OCR); total household debt and the "
                     "vehicle hire-purchase share from BoT statistics report 984.",
            "source": "ธนาคารแห่งประเทศไทย (ธปท.) — Financial Stability Report 2024 (รายงานการ"
                      "ประเมินเสถียรภาพระบบการเงินไทย 2567) + BoT statistics report 984",
            "provenance": "MEASURED. Every figure read directly from a BoT source and spot-verified "
                          "against a fixed anchor. Nothing modelled.",
            "pulled": stamp,
            "sources": {
                "fsr": {"url": FSR_URL,
                        "name_th": "รายงานการประเมินเสถียรภาพระบบการเงินไทย 2567 (FSR 2024)",
                        "method": "text-layer PDF (not OCR)"},
                "household_by_purpose": {"url": HH_URL,
                        "name_th": "เงินให้กู้ยืมแก่ภาคครัวเรือนจำแนกตามวัตถุประสงค์ (report 984)",
                        "method": "server-rendered HTML table (plain GET)"},
            },
        },
        "figures": {
            "system_npl_pct": {
                "value": system_npl, "unit": "%",
                "scope": "commercial banks (ธพ.), gross NPL / total loans",
                "vintage": "end-2567 (Dec 2024)",
                "source": "FSR 2024, p.20",
                "source_url": FSR_URL,
                "source_th": "อัตราส่วน NPL ต่อสินเชื่อรวม (NPL ratio) ณ สิ้นปี 2567 ร้อยละ 2.8",
            },
            "household_debt_to_gdp_pct": {
                "value": hh_gdp, "unit": "% of GDP",
                "scope": "Thailand household debt / GDP",
                "vintage": "end-2567 (Dec 2024)",
                "source": "FSR 2024, p.6",
                "source_url": FSR_URL,
                "source_th": "หนี้ครัวเรือนต่อ GDP ร้อยละ 88.4 ณ สิ้นปี 2567",
            },
            "household_debt_thb": {
                "value_mil_thb": hh_total_mil,
                "value_thb": hh_total_mil * 1_000_000,
                "value_tn_thb": round(hh_total_mil / 1_000_000, 2),
                "unit": "THB",
                "scope": "total loans to households (all purposes)",
                "vintage": period,
                "source": "BoT statistics report 984 (household loans by purpose), row 'รวม'",
                "source_url": HH_URL,
            },
            "auto_hp_household_debt_thb": {
                "value_mil_thb": auto_hp_mil,
                "value_thb": auto_hp_mil * 1_000_000,
                "value_tn_thb": round(auto_hp_mil / 1_000_000, 3),
                "share_of_hh_debt_pct": auto_share,
                "unit": "THB",
                "scope": "auto + motorcycle purchase / hire-purchase (the vehicle-collateral loan "
                         "book nearest AutoX's title-loan collateral)",
                "vintage": period,
                "source": "BoT statistics report 984, row 'ซื้อหรือเช่าซื้อรถยนต์และรถจักรยานยนต์'",
                "source_url": HH_URL,
            },
            "auto_hp_npl_pct": {
                "value": None,
                "unit": "%",
                "scope": "auto hire-purchase NPL",
                "reason_absent": "BoT's finest NPL-by-consumer-loan-PURPOSE split (which carries the "
                                 "auto hire-purchase NPL, ~2.1%) is published only via BoT's data API "
                                 "(apiportal.bot.or.th), geoblocked from this environment (HTTP 502). "
                                 "Not fabricated. Nearest MEASURED vehicle-collateral NPL scale is the "
                                 "vehicle-title peer band in peer_npl.json (TIDLOR ~1.5%, MTC ~2.53%).",
            },
        },
        "notes": [
            "The per-branch 0-100 branch-risk score (build_branch_risk.py) is an ESTIMATED triage "
            "rank, NOT a predicted NPL. These BoT figures are the measured real-world scale it sits "
            "against — shown alongside the score, never inside it.",
            "system_npl_pct is the whole commercial-banking system (all collateral classes); the "
            "auto hire-purchase sub-class runs near it but is not separately sourceable here.",
            "auto_hp_household_debt_thb is the vehicle-collateral loan EXPOSURE (nearest AutoX), not "
            "its NPL — a scale reference, not a default rate.",
        ],
    }


def _dumps(data):
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def main():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:
            pass
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stamp", default=datetime.date.today().isoformat(),
                    help="YYYY-MM-DD pull date embedded in meta.pulled (default: today)")
    ap.add_argument("--check", action="store_true",
                    help="OFFLINE: re-parse the cached raw + committed --stamp and byte-compare "
                         "against source-data/bot_credit.json; exit 1 on drift, exit 3 SKIP if the "
                         "committed JSON or the gitignored raw is absent (network-pulled input).")
    args = ap.parse_args()

    if args.check:
        if not os.path.exists(OUT) or not os.path.exists(RAW_FSR) or not os.path.exists(RAW_HH):
            print("pull_bot_credit.py --check: SKIP (committed bot_credit.json or gitignored raw "
                  "source-data/.bot_credit_raw/ absent — network-pulled input, not drift)")
            sys.exit(3)
        prev = json.load(open(OUT, encoding="utf-8"))
        data = build_from_raw(prev["meta"]["pulled"])
        if _dumps(data) != open(OUT, encoding="utf-8").read():
            sys.exit("pull_bot_credit.py --check: bot_credit.json drifted from a fresh parse of the "
                     "cached raw — re-run python3 pipeline/pull_bot_credit.py")
        print("pull_bot_credit.py --check: OK (byte-exact from cached raw)")
        return

    os.makedirs(RAW_DIR, exist_ok=True)
    if not os.path.exists(RAW_FSR):
        print("downloading %s ..." % FSR_URL)
        with open(RAW_FSR, "wb") as f:
            f.write(_fetch(FSR_URL))
    if not os.path.exists(RAW_HH):
        print("downloading %s ..." % HH_URL)
        with open(RAW_HH, "wb") as f:
            f.write(_fetch(HH_URL))
    data = build_from_raw(args.stamp)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(_dumps(data))
    print("wrote %s" % OUT)
    fg = data["figures"]
    print("  system NPL           %.2f%%  (%s)" % (fg["system_npl_pct"]["value"], fg["system_npl_pct"]["vintage"]))
    print("  household debt/GDP   %.1f%%  (%s)" % (fg["household_debt_to_gdp_pct"]["value"], fg["household_debt_to_gdp_pct"]["vintage"]))
    print("  household debt       %.2f tn THB  (%s)" % (fg["household_debt_thb"]["value_tn_thb"], fg["household_debt_thb"]["vintage"]))
    print("  auto hire-purchase   %.3f tn THB  (%.2f%% of hh debt, %s)" % (
        fg["auto_hp_household_debt_thb"]["value_tn_thb"],
        fg["auto_hp_household_debt_thb"]["share_of_hh_debt_pct"],
        fg["auto_hp_household_debt_thb"]["vintage"]))


if __name__ == "__main__":
    main()
