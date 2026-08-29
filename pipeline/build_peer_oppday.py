#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_peer_oppday.py — surface each SET-listed peer's LATEST earnings-call disclosure.

THE GAP THIS CLOSES. pipeline/pull_investor_docs.py pulls the six SET-listed title-loan peers'
own investor documents into source-data/investor_docs/ — ~40 SET Opportunity Day quarterly
earnings-call decks (kind=oppday) plus the 56-1 One Reports (kind=annual), all committed with a
structured source-data/investor_docs/index.json. Until now nothing but the CI log read that corpus:
`grep -rln investor_docs` returned only build_competitor_coverage.py, and only as a citation anchor
for Heng's branch count. So the freshest peer disclosure in the repo — every rival's own quarterly
earnings call — was distilled by nothing, and the app's peer boards (peer_scoreboard,
peer_asset_quality) gave the exec no read on WHEN each rival last reported or a link to the primary
source.

WHAT THIS MAKES. platform/data/peer_oppday.json: a compact, app-ready CALENDAR/RECENCY projection of
the corpus — per peer, its most recent Opportunity Day call (round, meeting date, video + SET-snapshot
links, page count), the number of calls the corpus holds and the earliest one, newest-first. Plus a
deterministic headline: when every peer's latest disclosure is the same quarter, that shared round and
its date span. The app renders a "Peer earnings watch" strip beside the peer asset-quality board so the
exec sees, at a glance, how current the peer boards are and can open each rival's own call.

DELIBERATELY CALENDAR-ONLY. This reads the STRUCTURED index (symbol / round / meeting_date / links /
page count / status) — it does NOT parse figures out of the call transcripts. No NPL, growth or
guidance number is extracted here; the transcripts are ASR/OCR text and a figure lifted from them
would be an unverifiable claim. Every field in this layer is a company-published SET filing fact.

PROVENANCE. MEASURED — the companies' own SET Opportunity Day filings (api.lcp.setgroup.or.th),
pulled by pipeline/pull_investor_docs.py. This build only projects the committed index; it invents
nothing.

Deterministic and network-free: every field (as_of, spans, headline) derives from the input index's
own meeting_date stamps, never the wall clock. `--check` byte-compares; exits 3 (SKIP) when
source-data/investor_docs/index.json is absent (the puller is a network pull, not in the gate).

  python3 build_peer_oppday.py
  python3 build_peer_oppday.py --check
"""
import argparse
import io
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IN = os.path.join(ROOT, "source-data", "investor_docs", "index.json")
OUT = os.path.join(ROOT, "platform", "data", "peer_oppday.json")

# Canonical display names, matched to peer_asset_quality.json so the two peer boards agree. The index
# carries only SET symbols; this map is the stable naming convention (like the other peer builders').
NAMES = {
    "HENG": "Heng Leasing & Capital",
    "MTC": "Muangthai Capital",
    "SAK": "Saksiam Leasing",
    "SAWAD": "Srisawad",
    "TIDLOR": "Ngern Tid Lor (Tidlor Holdings)",
    "TURBO": "Ngern Turbo (NTL)",
}


def build():
    if not os.path.exists(IN):
        return None
    with io.open(IN, encoding="utf-8") as f:
        src = json.load(f)
    sm = src.get("meta", {}) or {}
    docs = src.get("documents", []) or []

    # Group the successfully-pulled Opportunity Day calls by peer.
    by_sym = {}
    for d in docs:
        if d.get("kind") != "oppday" or d.get("status") != "ok":
            continue
        md = d.get("meeting_date")
        if not md:
            continue
        by_sym.setdefault(d.get("symbol"), []).append(d)

    peers = []
    for sym, calls in by_sym.items():
        # Sort by meeting_date (ISO strings sort chronologically); latest is the newest call.
        calls.sort(key=lambda z: z.get("meeting_date") or "")
        latest = calls[-1]
        peers.append({
            "symbol": sym,
            "name": NAMES.get(sym, sym),
            "latest_round": latest.get("round_name"),
            "latest_date": latest.get("meeting_date"),
            "video_link": latest.get("video_link"),
            "snapshot_link": latest.get("snapshot_link"),
            "n_pages": latest.get("n_pages"),
            "has_summary": bool(latest.get("has_summary")),
            "n_calls": len(calls),
            "first_round": calls[0].get("round_name"),
            "first_date": calls[0].get("meeting_date"),
        })

    # Newest disclosure first, then a stable symbol order for ties.
    peers.sort(key=lambda p: (p["latest_date"] or "", p["symbol"]), reverse=True)

    dates = [p["latest_date"] for p in peers if p["latest_date"]]
    as_of = max(dates) if dates else None
    span_lo = min(dates) if dates else None
    rounds = {p["latest_round"] for p in peers if p["latest_round"]}
    n_peers = len(peers)

    if n_peers and len(rounds) == 1:
        shared = next(iter(rounds))
        headline = ("All %d SET-listed peers' latest disclosure is the %s earnings call (%s–%s) — the "
                    "peer boards above read the newest public quarter." % (n_peers, shared, span_lo, as_of))
    elif n_peers:
        newest = peers[0]
        headline = ("%d SET-listed peers tracked; the newest call is %s's %s (%s)."
                    % (n_peers, newest["symbol"], newest["latest_round"], newest["latest_date"]))
    else:
        headline = "No Opportunity Day calls in the corpus yet."

    out = {
        "meta": {
            "title": "Peer earnings watch — each SET-listed peer's latest Opportunity Day call",
            "label": ("MEASURED — the six SET-listed title-loan peers' own SET Opportunity Day quarterly "
                      "earnings-call filings (round, meeting date, video + snapshot links, page count). "
                      "CALENDAR / RECENCY ONLY: no figure is parsed out of the call transcripts — the "
                      "boards above carry the measured peer financials."),
            "provenance": ("MEASURED · SET Opportunity Day (api.lcp.setgroup.or.th), pulled by "
                           "pipeline/pull_investor_docs.py into source-data/investor_docs/. This build "
                           "projects the committed structured index; it parses no transcript text."),
            "generated_by": "pipeline/build_peer_oppday.py",
            "source": "source-data/investor_docs/index.json (pipeline/pull_investor_docs.py)",
            "objective": ("Competitive risk (#2) — primary-source access to each rival's latest earnings "
                          "disclosure and a freshness read on how current the peer boards are."),
            "corpus_generated": sm.get("generated_date"),
            "as_of": as_of,
            "latest_span": [span_lo, as_of] if dates else None,
            "n_peers": n_peers,
            "n_calls": sum(p["n_calls"] for p in peers),
            "shared_latest_round": (next(iter(rounds)) if (n_peers and len(rounds) == 1) else None),
            "headline": headline,
        },
        "peers": peers,
    }
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    out = build()
    if out is None:
        print("SKIP: source-data/investor_docs/index.json absent")
        return 3
    txt = json.dumps(out, ensure_ascii=False, indent=1, sort_keys=True) + "\n"
    if a.check:
        if not os.path.exists(OUT):
            print("SKIP: %s not built yet" % OUT)
            return 3
        with io.open(OUT, encoding="utf-8") as f:
            cur = f.read()
        if cur != txt:
            print("DRIFT: %s differs from a fresh build" % OUT)
            return 1
        print("OK: %s reproduces byte-for-byte" % OUT)
        return 0
    with io.open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write(txt)
    m = out["meta"]
    print("wrote %s — %d peers, %d calls, latest %s"
          % (OUT, m["n_peers"], m["n_calls"], m["as_of"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
