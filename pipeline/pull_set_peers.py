#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pull_set_peers.py — MEASURED listed-peer market & financial data from the Stock Exchange of
Thailand (set.or.th), pulled AUTONOMOUSLY. Writes source-data/set_peers.json.

WHY A BROWSER: SET's JSON API (www.set.or.th/api/set/...) 403s every external request (Akamai bot
protection) even with full browser headers, and the quote pages are client-rendered (no clean
__NEXT_DATA__). The one reliable path is a real browser: load a SET quote page, then call the API
with a SAME-ORIGIN fetch from inside the page — which carries the tokens/cookies the 403 was
missing and returns 200. This script drives a headless Chromium (Playwright) to do exactly that.

Endpoints (same-origin, from a loaded set.or.th page):
  /api/set/stock/<SYM>/highlight-data?lang=en                     market cap, PE, PBV, div yield, YTD, 52wk
  /api/set/stock/<SYM>/profile?lang=en                            company name / sector
  /api/set/stock/<SYM>/company-highlight/financial-data?period=Q  the FULL fundamentals history — 4
                                                                   audited full years (quarter:"Q9") +
                                                                   the latest interim (quarter:"Q1"/"6M").
                                                                   period=Q and period=Y are IDENTICAL —
                                                                   there is no separate annual endpoint.

NETWORK + BROWSER. Not in the offline determinism gate (the committed set_peers.json is the artifact;
build_peer_scoreboard.py derives the app layer deterministically from it). Requires:
  pip install playwright && python -m playwright install chromium

  python3 pull_set_peers.py                    # refresh all peers -> source-data/set_peers.json
  python3 pull_set_peers.py --symbols MTC,TIDLOR,SAWAD
"""
import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "source-data", "set_peers.json")
# The SIX SET-listed Thai title/vehicle-title lenders. TURBO listed 2025; HENG (Heng Leasing and
# Capital) and SAK (Saksiam Leasing) were missing entirely — only 4 of 6 were ever covered.
DEFAULT_SYMS = ["MTC", "TIDLOR", "SAWAD", "TURBO", "HENG", "SAK"]

# the async fetch run INSIDE the loaded SET page — same-origin, so it bypasses the external 403.
PAGE_FETCH_JS = r"""
async (syms) => {
  const out = { peers: [] };
  for (const s of syms) {
    const rec = { symbol: s };
    const h = await (await fetch(`/api/set/stock/${s}/highlight-data?lang=en`)).json();
    // SOURCE vs OUTPUT names differ here, and confusing the two silently nulls four fields forever.
    // highlight-data's OWN keys — dumped live 2026-08-08, do not "correct" these from memory:
    //   symbol asOfDate marketCap peRatio pbRatio dividendYield beta ytdPercentChange xdDate
    //   xdSession dividend dividendRatio freeFloatAsOfDate percentFreeFloat yearHighPrice
    //   yearLowPrice listedShare par currency nvdr* outstanding* dividendYield12M turnoverRatio
    // There is NO h.ytd, h.freeFloat, h.yearHigh or h.yearLow on the response. The OUTPUT names we
    // write (yearHigh/yearLow) are OUR OWN shorter aliases, which build_peer_scoreboard.py expects —
    // so a fixture of this script's output is NOT evidence of what the endpoint returns. Verify a
    // key change against a live `Object.keys(h)` dump, never against a committed set_peers.json.
    Object.assign(rec, { marketCap: h.marketCap, peRatio: h.peRatio, pbRatio: h.pbRatio,
      dividendYield: h.dividendYield, beta: h.beta, ytdPercentChange: h.ytdPercentChange,
      yearHigh: h.yearHighPrice, yearLow: h.yearLowPrice, percentFreeFloat: h.percentFreeFloat,
      listedShare: h.listedShare });
    try { const p = await (await fetch(`/api/set/stock/${s}/profile?lang=en`)).json(); rec.name = p.name; } catch(e){}
    // financial-data returns 5 rows, NOT one: 4 audited FULL YEARS (quarter:"Q9", years 2022-2025)
    // plus the latest interim period (quarter:"Q1" or "6M"). CRITICAL TRAP: quarter:"Q9" means FULL
    // YEAR; "Q1"/"6M" means a single interim period — mixing them silently compares a full year
    // against one quarter. Also: period=Q and period=Y return IDENTICAL data on this endpoint, so
    // there is no separate annual call to make. Keep the WHOLE array — collapsing to the last row
    // (the old behavior) threw away 4 years of audited history and can even present an interim
    // period's numbers as if they were a full year's.
    const arr = await (await fetch(`/api/set/stock/${s}/company-highlight/financial-data?lang=en&period=Q`)).json();
    rec.fin = arr.map(r => ({ quarter: r.quarter, year: r.year, fsType: r.fsType, begin: r.begin, end: r.end,
      totalAsset: r.totalAsset, equity: r.equity, totalRevenue: r.totalRevenue, netProfit: r.netProfit,
      eps: r.eps, roa: r.roa, roe: r.roe, netProfitMargin: r.netProfitMargin, deRatio: r.deRatio,
      paidupCapital: r.paidupCapital }));
    out.peers.push(rec);
  }
  out.price_asof = (await (await fetch(`/api/set/stock/${syms[0]}/highlight-data?lang=en`)).json()).asOfDate;
  return out;
}
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", default=",".join(DEFAULT_SYMS))
    args = ap.parse_args()
    syms = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sys.exit("pull_set_peers.py: needs Playwright — pip install playwright && python -m playwright "
                 "install chromium. (The committed source-data/set_peers.json is the artifact; this "
                 "script only refreshes it.)")

    with sync_playwright() as pw:
        br = pw.chromium.launch(headless=True)
        pg = br.new_page(user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                                     "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"))
        pg.goto("https://www.set.or.th/en/market/product/stock/quote/%s/price" % syms[0],
                wait_until="domcontentloaded", timeout=45000)
        data = pg.evaluate(PAGE_FETCH_JS, syms)
        br.close()

    peer0_fin = (data.get("peers") or [{}])[0].get("fin") or []
    latest_fin = peer0_fin[-1] if peer0_fin else {}
    payload = {
        "meta": {
            "title": "Listed title-loan peers — SET market & financial data (measured, autonomous pull)",
            "generated_by": "pipeline/pull_set_peers.py",
            "label": "MEASURED — Stock Exchange of Thailand (set.or.th). Market cap + valuation as of the "
                     "price date; fundamentals carry the FULL financial-data history per peer (audited "
                     "full years + the latest interim). NOT an AutoX figure — AutoX is unlisted (SCBX "
                     "subsidiary), so there is no comparable SET row for us.",
            "source": "Stock Exchange of Thailand · set.or.th in-browser JSON API "
                      "(highlight-data + profile + company-highlight/financial-data)",
            "price_asof": (data.get("price_asof") or "")[:10],
            # informational only — the freshest row pulled (often the interim). Each peer's own
            # audited-year basis for the headline scoreboard is picked downstream by
            # build_peer_scoreboard.py (newest quarter=="Q9" row), not by this field.
            "fin_period": ("%s %s" % (latest_fin.get("quarter"), latest_fin.get("year"))).strip() if latest_fin else None,
            "fin_note": "Each peer's 'fin' list carries every row the endpoint returns for period=Q — "
                        "normally 4 audited FULL YEARS (quarter:\"Q9\", years 2022-2025) plus the latest "
                        "interim period (quarter:\"Q1\" or \"6M\"). Q9 = a closed, audited fiscal year; "
                        "Q1/6M = a partial-year interim — never compare them as like-for-like. "
                        "period=Q and period=Y return IDENTICAL data on this endpoint.",
            "units": "marketCap in THB; totalAsset/equity/totalRevenue/netProfit in THB thousands (as SET reports); ratios in %",
        },
        "peers": data.get("peers", []),
    }
    json.dump(payload, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    n_fin = sum(len(p.get("fin") or []) for p in payload["peers"])
    print("wrote %s — %d peers, %d fin rows total (price asOf %s)"
          % (OUT, len(payload["peers"]), n_fin, payload["meta"]["price_asof"]))


if __name__ == "__main__":
    main()
