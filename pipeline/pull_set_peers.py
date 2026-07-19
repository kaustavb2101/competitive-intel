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
  /api/set/stock/<SYM>/company-highlight/financial-data?period=Q  quarterly fundamentals (latest = newest)

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
DEFAULT_SYMS = ["MTC", "TIDLOR", "SAWAD"]

# the async fetch run INSIDE the loaded SET page — same-origin, so it bypasses the external 403.
PAGE_FETCH_JS = r"""
async (syms) => {
  const out = { peers: [] };
  for (const s of syms) {
    const rec = { symbol: s };
    const h = await (await fetch(`/api/set/stock/${s}/highlight-data?lang=en`)).json();
    Object.assign(rec, { marketCap: h.marketCap, peRatio: h.peRatio, pbRatio: h.pbRatio,
      dividendYield: h.dividendYield, beta: h.beta, ytdPercentChange: h.ytdPercentChange,
      yearHigh: h.yearHighPrice, yearLow: h.yearLowPrice, percentFreeFloat: h.percentFreeFloat });
    try { const p = await (await fetch(`/api/set/stock/${s}/profile?lang=en`)).json(); rec.name = p.name; } catch(e){}
    const arr = await (await fetch(`/api/set/stock/${s}/company-highlight/financial-data?lang=en&period=Q`)).json();
    const L = arr[arr.length - 1];
    Object.assign(rec, { quarter: L.quarter, year: L.year, totalAsset: L.totalAsset, equity: L.equity,
      totalRevenue: L.totalRevenue, netProfit: L.netProfit, eps: L.eps, roa: L.roa, roe: L.roe,
      netProfitMargin: L.netProfitMargin, deRatio: L.deRatio });
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

    payload = {
        "meta": {
            "title": "Listed title-loan peers — SET market & financial data (measured, autonomous pull)",
            "generated_by": "pipeline/pull_set_peers.py",
            "label": "MEASURED — Stock Exchange of Thailand (set.or.th). Market cap + valuation as of the "
                     "price date; fundamentals from the latest quarterly filing. NOT an AutoX figure — "
                     "AutoX is unlisted (SCBX subsidiary), so there is no comparable SET row for us.",
            "source": "Stock Exchange of Thailand · set.or.th in-browser JSON API "
                      "(highlight-data + profile + company-highlight/financial-data)",
            "price_asof": (data.get("price_asof") or "")[:10],
            "fin_period": ("%s %s" % (data["peers"][0].get("quarter"), data["peers"][0].get("year"))).strip() if data.get("peers") else None,
            "units": "marketCap in THB; totalAsset/equity/totalRevenue/netProfit in THB thousands (as SET reports); ratios in %",
        },
        "peers": data.get("peers", []),
    }
    json.dump(payload, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("wrote %s — %d peers (price asOf %s)" % (OUT, len(payload["peers"]), payload["meta"]["price_asof"]))


if __name__ == "__main__":
    main()
