#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_peer_scoreboard.py — COMPETITIVE + MARKET presence (objective #2): the listed title-loan
peers' market & financial scoreboard, projected from the autonomous SET pull for the app.

  in : source-data/set_peers.json    MEASURED SET market data + latest-quarter fundamentals
                                      (pull_set_peers.py · Stock Exchange of Thailand)
  out: platform/data/peer_scoreboard.json   per-peer market cap / valuation / ROE / profit + rank +
                                             the AutoX 25% ROE target as the reference line

Why this matters: AutoX is unlisted, so there is no SET row for us — but our three biggest rivals
ARE listed and report audited quarterly financials. Their market cap, valuation and ROE are the
measured competitive scoreboard we position against; AutoX's stated 25% ROE target sits inside the
peer ROE ladder, which is the sharpest IPO benchmark we have. NOT an AutoX figure — the peers' own.

Note on ROE comparability: SET reports each peer's ratio as filed; TIDLOR's holding-company
restructure inflates its reported ROE vs the others, so read the ladder with that caveat (carried in
meta), and lead with net profit + market cap which are directly comparable.

Deterministic + network-free; money rolled to ฿bn and ratios to 1 dp so the output is byte-stable
across Python builds. `--check` byte-compares; SKIPs (exit 3) if set_peers.json is absent.

  python3 build_peer_scoreboard.py
  python3 build_peer_scoreboard.py --check
"""
import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IN = os.path.join(ROOT, "source-data", "set_peers.json")
OUT = os.path.join(ROOT, "platform", "data", "peer_scoreboard.json")

AUTOX_ROE_TARGET = 25.0        # AutoX's stated ROE target (CLAUDE.md) — the reference line
SHORT = {"MTC": "Muangthai Capital", "TIDLOR": "Ngern Tid Lor", "SAWAD": "Srisawad"}


def _bn(thousands):
    """THB-thousands (as SET reports fundamentals) -> ฿bn, 2 dp."""
    return round(thousands / 1_000_000.0, 2) if isinstance(thousands, (int, float)) else None


def build():
    doc = json.load(open(IN, encoding="utf-8"))
    meta_in = doc.get("meta", {})
    peers = []
    for p in doc.get("peers", []):
        peers.append({
            "symbol": p["symbol"],
            "name": SHORT.get(p["symbol"], p.get("name")),
            "market_cap_bn": round(p["marketCap"] / 1e9, 1) if p.get("marketCap") is not None else None,
            "pe": p.get("peRatio"), "pbv": p.get("pbRatio"),
            "div_yield": p.get("dividendYield"),
            "ytd_pct": round(p["ytdPercentChange"], 1) if p.get("ytdPercentChange") is not None else None,
            "year_high": p.get("yearHigh"), "year_low": p.get("yearLow"),
            "free_float_pct": round(p["percentFreeFloat"], 1) if p.get("percentFreeFloat") is not None else None,
            "roe": round(p["roe"], 1) if p.get("roe") is not None else None,
            "roa": round(p["roa"], 1) if p.get("roa") is not None else None,
            "npm": round(p["netProfitMargin"], 1) if p.get("netProfitMargin") is not None else None,
            "de": round(p["deRatio"], 2) if p.get("deRatio") is not None else None,
            "net_profit_q_bn": _bn(p.get("netProfit")),
            "revenue_q_bn": _bn(p.get("totalRevenue")),
            "assets_bn": _bn(p.get("totalAsset")),
            "equity_bn": _bn(p.get("equity")),
            "quarter": ("%s %s" % (p.get("quarter"), p.get("year"))).strip(),
        })
    # rank by market cap (the market's own verdict on scale)
    peers.sort(key=lambda x: -(x["market_cap_bn"] or 0))

    caps = [p["market_cap_bn"] for p in peers if p["market_cap_bn"] is not None]
    roes = [(p["symbol"], p["roe"]) for p in peers if p["roe"] is not None]
    headline = ""
    if peers:
        big = peers[0]
        mom = max((p for p in peers if p["ytd_pct"] is not None), key=lambda x: x["ytd_pct"], default=None)
        headline = ("Listed rivals total ฿%.0fbn of market value; %s is the largest at ฿%.1fbn."
                    % (sum(caps), big["name"], big["market_cap_bn"]))
        if mom:
            headline += " %s leads share momentum this year (%+.1f%% YTD)." % (mom["name"], mom["ytd_pct"])

    return {
        "meta": {
            "title": "Listed-peer market scoreboard — SET market value, valuation & returns (obj #2)",
            "generated_by": "pipeline/build_peer_scoreboard.py",
            "label": "MEASURED — Stock Exchange of Thailand (autonomous pull). Market cap/valuation as of "
                     "the price date; ROE/net profit/assets from the latest quarterly filing. NOT an AutoX "
                     "figure — AutoX is unlisted, so its 25% ROE TARGET is shown only as the reference line.",
            "source": meta_in.get("source", "set.or.th"),
            "price_asof": meta_in.get("price_asof"),
            "fin_period": meta_in.get("fin_period"),
            "autox_roe_target": AUTOX_ROE_TARGET,
            "roe_caveat": "ROE is each peer's own SET-reported ratio; TIDLOR's holding-company structure "
                          "inflates its reported ROE relative to MTC/SAWAD, so read the ladder with that "
                          "caveat and compare net profit + market cap directly.",
            "units": "market_cap/assets/profit/revenue/equity in ฿bn; ratios in %",
        },
        "headline": headline,
        "autox_roe_target": AUTOX_ROE_TARGET,
        "peers": peers,
    }


def serialize(o):
    return json.dumps(o, ensure_ascii=False, separators=(",", ":"))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    if not os.path.exists(IN):
        if args.check:
            print("build_peer_scoreboard.py --check: SKIP (set_peers.json absent — SET pull, not committed)")
            sys.exit(3)
        sys.exit("build_peer_scoreboard.py: source-data/set_peers.json missing — run pull_set_peers.py")
    payload = serialize(build())
    if args.check:
        if not os.path.exists(OUT):
            sys.exit("build_peer_scoreboard.py --check: output missing — run the builder.")
        if open(OUT, encoding="utf-8").read() != payload:
            sys.exit("build_peer_scoreboard.py --check: drifted — re-run the builder.")
        print("build_peer_scoreboard.py --check: OK (byte-exact)")
        return
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(payload)
    obj = json.loads(payload)
    print("wrote %s — %d peers · AutoX ROE ref %.0f%%" % (OUT, len(obj["peers"]), obj["autox_roe_target"]))
    for p in obj["peers"]:
        print("  %-16s ฿%-6sbn cap · ROE %-5s · net ฿%sbn/q · PE %s"
              % (p["name"], p["market_cap_bn"], p["roe"], p["net_profit_q_bn"], p["pe"]))


if __name__ == "__main__":
    main()
