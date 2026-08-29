#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_peer_scoreboard.py — COMPETITIVE + MARKET presence (objective #2): the listed title-loan
peers' market & financial scoreboard, projected from the autonomous SET pull for the app.

  in : source-data/set_peers.json    MEASURED SET market data + FULL fundamentals history per peer
                                      (pull_set_peers.py · Stock Exchange of Thailand)
  out: platform/data/peer_scoreboard.json   per-peer market cap / valuation / ROE / profit + rank +
                                             the AutoX 25% ROE target as the reference line

Why this matters: AutoX is unlisted, so there is no SET row for us — but all SIX listed title/
vehicle-title lenders (MTC, TIDLOR, SAWAD, TURBO, HENG, SAK) report audited annual financials. Their
market cap, valuation and ROE are the measured competitive scoreboard we position against; AutoX's
stated 25% ROE target sits inside the peer ROE ladder — the sharpest external benchmark we have.
NOT an AutoX figure — the peers' own.

HEADLINE BASIS (fixed 2026-08): each peer's 'fin' list holds several rows — audited FULL YEARS
(SET quarter code "Q9") plus the latest INTERIM period ("Q1"/"6M"). The headline ROE/profit/assets
below are always the peer's newest quarter=="Q9" row — a real closed, audited fiscal year — never
simply "the last row". Blindly taking the last row previously shipped TIDLOR's Q1-2026 interim ROE
(36.6%, annualised off a freshly-restructured equity base) as the headline, when its real FY2025
audited ROE is 15.3% — in line with the sector, not 2.2x the leader. A peer row whose totalRevenue
or netProfit is null (e.g. TIDLOR's FY2024 row, filed before its 2025-05-15 holdco listing had a
full year of consolidated P&L) is ABSENT for that fiscal year — never rendered as 0, never used in a
ratio, never averaged in; the newest Q9 row with real numbers is what's picked instead.

Each peer record publishes its own basis_year / basis_quarter / fs_type so the app can state
"FY2025 audited" rather than leaving the reader to guess, and so a future peer whose basis differs
from the others (a late filer, a fresh listing) is visible rather than silently blended in.

Comparability caveats carried in meta (not silently smoothed over):
  - TIDLOR HOLDINGS listed 2025-05-15 as a new holding company; its pre-2025 series is not
    continuous with the current listed entity, and FY2024 has no P&L (see above).
  - HENG reports fsType "U" (unconsolidated) where the other five report "C" (consolidated) —
    not a like-for-like statement basis; flagged, not hidden.

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
SHORT = {
    "MTC": "Muangthai Capital", "TIDLOR": "Ngern Tid Lor", "SAWAD": "Srisawad",
    "TURBO": "Ngern Turbo", "HENG": "Heng Leasing", "SAK": "Saksiam Leasing",
}
FULL_YEAR_QUARTER = "Q9"       # SET's own code for a closed, audited fiscal year


def _bn(thousands):
    """THB-thousands (as SET reports fundamentals) -> ฿bn, 2 dp."""
    return round(thousands / 1_000_000.0, 2) if isinstance(thousands, (int, float)) else None


def _pick_basis(fin_rows):
    """The headline basis: the newest AUDITED FULL YEAR row (quarter=="Q9"). Interim rows
    ("Q1"/"6M") are a partial year and are never used as the headline — that is exactly the
    TIDLOR-ROE bug this function exists to prevent. Returns None if the peer has no Q9 row at all."""
    audited = [r for r in (fin_rows or []) if r.get("quarter") == FULL_YEAR_QUARTER]
    if not audited:
        return None
    return max(audited, key=lambda r: r.get("year") if r.get("year") is not None else -1)


def _is_absent(row):
    """A fin row with a null totalRevenue or netProfit is an incomplete/unpriced fiscal year (e.g.
    a holding company's first, partial-P&L year right after a restructure) — treated as wholly
    ABSENT: never rendered as 0, never used in a ratio, never folded into an average."""
    return row is None or row.get("totalRevenue") is None or row.get("netProfit") is None


def _fmt_basis(quarter, year):
    if quarter is None or year is None:
        return None
    if quarter == FULL_YEAR_QUARTER:
        return "FY%s (audited)" % year
    return "%s %s (interim)" % (quarter, year)


def build():
    doc = json.load(open(IN, encoding="utf-8"))
    meta_in = doc.get("meta", {})
    peers = []
    for p in doc.get("peers", []):
        basis = _pick_basis(p.get("fin"))
        absent = _is_absent(basis)
        src = {} if absent else basis   # ABSENT rows contribute nothing — never a false 0

        rec = {
            "symbol": p["symbol"],
            "name": SHORT.get(p["symbol"], p.get("name")),
            "market_cap_bn": round(p["marketCap"] / 1e9, 1) if p.get("marketCap") is not None else None,
            "pe": p.get("peRatio"), "pbv": p.get("pbRatio"),
            "div_yield": p.get("dividendYield"),
            # SET-reported beta — the share's systematic (market-correlated) volatility vs the SET index.
            # >1 amplifies market swings, <1 is defensive. A trailing-window market statistic, not a
            # fundamental; carried through so the scoreboard reads price RISK, not just price level.
            "beta": p.get("beta"),
            "ytd_pct": round(p["ytdPercentChange"], 1) if p.get("ytdPercentChange") is not None else None,
            "year_high": p.get("yearHigh"), "year_low": p.get("yearLow"),
            "free_float_pct": round(p["percentFreeFloat"], 1) if p.get("percentFreeFloat") is not None else None,
            "roe": round(src["roe"], 1) if src.get("roe") is not None else None,
            "roa": round(src["roa"], 1) if src.get("roa") is not None else None,
            "npm": round(src["netProfitMargin"], 1) if src.get("netProfitMargin") is not None else None,
            "de": round(src["deRatio"], 2) if src.get("deRatio") is not None else None,
            "net_profit_bn": _bn(src.get("netProfit")),
            "revenue_bn": _bn(src.get("totalRevenue")),
            "assets_bn": _bn(src.get("totalAsset")),
            "equity_bn": _bn(src.get("equity")),
            # the basis this row's numbers came from — never left for the reader to guess.
            "fs_type": (basis or {}).get("fsType"),
            "basis_year": (basis or {}).get("year"),
            "basis_quarter": (basis or {}).get("quarter"),
            "basis_label": _fmt_basis((basis or {}).get("quarter"), (basis or {}).get("year")),
            "quarter": ("%s %s" % (basis.get("quarter"), basis.get("year"))).strip() if basis else None,
        }
        peers.append(rec)
    # rank by market cap (the market's own verdict on scale)
    peers.sort(key=lambda x: -(x["market_cap_bn"] or 0))

    caps = [p["market_cap_bn"] for p in peers if p["market_cap_bn"] is not None]
    headline = ""
    if peers:
        big = peers[0]
        mom = max((p for p in peers if p["ytd_pct"] is not None), key=lambda x: x["ytd_pct"], default=None)
        headline = ("Listed rivals total ฿%.0fbn of market value; %s is the largest at ฿%.1fbn."
                    % (sum(caps), big["name"], big["market_cap_bn"]))
        if mom:
            headline += " %s leads share momentum this year (%+.1f%% YTD)." % (mom["name"], mom["ytd_pct"])

    # a single "fin_period" summary is honest only when every peer's basis actually agrees; once
    # a late filer or a fresh listing diverges, say so instead of picking one peer's basis and
    # letting it stand in for all six.
    bases = sorted({(p["basis_quarter"], p["basis_year"]) for p in peers if p["basis_quarter"]})
    if len(bases) == 1:
        fin_period = _fmt_basis(*bases[0])
    elif bases:
        fin_period = "mixed vintages — see each peer's basis_label"
    else:
        fin_period = None

    return {
        "meta": {
            "title": "Listed-peer market scoreboard — SET market value, valuation & returns (obj #2)",
            "generated_by": "pipeline/build_peer_scoreboard.py",
            "label": "MEASURED — Stock Exchange of Thailand (autonomous pull). Market cap/valuation as of "
                     "the price date; ROE/net profit/assets from each peer's newest AUDITED FULL YEAR "
                     "(SET quarter code Q9) — not simply the latest filing, which can be a partial-year "
                     "interim. NOT an AutoX figure — AutoX is unlisted, so its 25% ROE TARGET is shown "
                     "only as the reference line.",
            "source": meta_in.get("source", "set.or.th"),
            "price_asof": meta_in.get("price_asof"),
            "fin_period": fin_period,
            "fin_basis": "Each peer's headline ROE/profit/assets are its own newest quarter==\"Q9\" row "
                        "(a closed, audited fiscal year). A row with a null totalRevenue or netProfit is "
                        "treated as ABSENT and skipped, never shown as 0 or averaged in.",
            "autox_roe_target": AUTOX_ROE_TARGET,
            "roe_caveat": "ROE is each peer's own SET-reported ratio for its newest audited fiscal year "
                          "(SET quarter code Q9) — not an interim annualised off a partial year. Read "
                          "net profit + market cap as the most directly comparable lines.",
            "holdco_caveat": "TIDLOR HOLDINGS PCL listed 2025-05-15 as a new holding company following a "
                             "restructure of the former Ngern Tid Lor group; its FY2024-and-earlier series "
                             "is not continuous with the current listed entity, and its FY2024 row carries "
                             "no consolidated P&L (totalRevenue/netProfit null) — FY2025 is its first full "
                             "audited year as TIDLOR HOLDINGS.",
            "fs_type_caveat": "fs_type marks the statement basis SET filed: \"C\" = consolidated, \"U\" = "
                              "unconsolidated (company-only). HENG reports \"U\"; the other five report "
                              "\"C\" — not a like-for-like statement basis, flagged rather than blended in.",
            "beta_caveat": "beta is each peer's SET-reported share beta — systematic (market-correlated) "
                           "volatility measured against the SET index over a trailing window. >1.0 = the "
                           "share amplifies market moves (more cyclically exposed); <1.0 = defensive. It is "
                           "a market statistic on the rival's equity, not a fundamental of its loan book, "
                           "and AutoX (unlisted) has none.",
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
        print("  %-16s ฿%-6sbn cap · ROE %-5s (%s) · net ฿%sbn/yr · PE %s"
              % (p["name"], p["market_cap_bn"], p["roe"], p["basis_label"], p["net_profit_bn"], p["pe"]))


if __name__ == "__main__":
    main()
