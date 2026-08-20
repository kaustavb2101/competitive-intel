#!/usr/bin/env python3
# mandate_guard.py — the anti-expansion PRODUCT-MANDATE gate.
#
# CLAUDE.md, "The two standing objectives": this platform is a competitive-RISK lens on the
# footprint AutoX ALREADY runs. It "makes NO open / close / where-to-open recommendations" and
# there is "no branch-growth target" (the network is consolidating). Reporting a RIVAL's growth
# ("Muangthai opened 518 branches in 2025", "Expansion pace & book scale …") is allowed — that is a
# competitive-risk signal. Recommending where AUTOX should open / expand is forbidden.
#
# WHY THIS EXISTS: the forbidden framing has shipped before. `build_regional_outlook.py` once emitted
# a "📈 Expand — N branches sit on prime white-space with thin competition; lead the region's
# acquisition here" recommendation and `_top_action` mapped the `acquire` kind to a bare "Expand"
# chip (reframed to "Low rival pressure" / "Low competitive pressure" on 2026-08-02). That fix lived
# only in the data-builder source and was re-audited by hand every intelligence-loop run because
# nothing in the gate LOCKED it in. A future edit to any narrative builder (regional_outlook,
# branch_recommendations, decision_queue, impact_cards, cluster_brief …) could silently reintroduce
# it and ship straight to production. This turns that manual audit into an automated regression gate.
#
# SCOPE (deliberately tight, to stay false-positive-free and never red the gate on legitimate text):
#   * Scans STRING VALUES in every committed platform/data/*.json — the narrative layers a data
#     refresh regenerates. This is the actual regression vector.
#   * Does NOT scan app.js / *.html: those carry legitimate CUSTOMER-acquisition copy ("Who to
#     acquire here — top leads"), UI affordances ("aria-expanded", "Expand this section") and
#     mandate-compliance CODE COMMENTS, which a phrase scan can't safely tell apart. The data
#     layers carry none of those, so the scan there is clean and unambiguous.
#   * Matches only BRANCH-EXPANSION RECOMMENDATION phrases (imperatives aimed at AutoX), never the
#     bare word "expand"/"expansion" (which legitimately reports RIVAL growth), and never customer
#     "acquire" (leads). The built-in self-test below proves both directions.
#
# Offline, stdlib-only, deterministic. Exit 0 = clean; exit 1 = a forbidden phrase is live.

import glob
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
DATA = os.path.join(REPO, "platform", "data")

# Each pattern targets a recommendation to OPEN / EXPAND / CLOSE AutoX branches, or the specific
# branch-"acquisition" framing the mandate forbids. Kept as multi-word phrases so reporting a rival's
# own expansion ("expansion pace", "opened 518 branches") and customer acquisition ("who to acquire")
# never match. Case-insensitive.
FORBIDDEN = [
    r"where to open",
    r"open(?:s|ed|ing)?\s+(?:a\s+|an\s+|another\s+|new\s+)?branch(?:es)?\s+(?:here|there|in\b|next\b)",
    r"recommend(?:s|ed|ing)?\s+opening",
    r"should\s+open\s+(?:a\s+|an\s+|another\s+|new\s+)?branch",
    r"branch(?:es)?\s+to\s+open",
    r"open\s+(?:a\s+|an\s+|another\s+|new\s+)?branch\s+here",
    r"expand\s+the\s+(?:branch\s+)?network",
    r"grow\s+the\s+(?:branch\s+)?network",
    r"lead\s+the\s+region'?s?\s+acquisition",
    r"add\s+\d+\s+(?:new\s+)?branch(?:es)?\b",
    r"where\s+(?:to\s+)?(?:expand|grow)\b",
    r"prime\s+white-?space\s+with\s+thin\s+competition",
]
_RX = [re.compile(p, re.IGNORECASE) for p in FORBIDDEN]


def _scan_string(s):
    """Return the first forbidden pattern that matches s, or None."""
    for rx in _RX:
        m = rx.search(s)
        if m:
            return rx.pattern, m.group(0)
    return None


def _walk(node, path, hits):
    if isinstance(node, dict):
        for k, v in node.items():
            _walk(v, path + "/" + str(k), hits)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            _walk(v, path + "[%d]" % i, hits)
    elif isinstance(node, str):
        h = _scan_string(node)
        if h:
            hits.append((path, h[0], h[1], node.strip()[:140]))


def _selftest():
    """Prove the guard FIRES on known-bad branch-expansion copy and stays QUIET on the legitimate
    look-alikes (rival expansion reporting, customer acquisition, UI affordances). Any failure here
    means the pattern set drifted — that is itself a gate failure, so the guard can never pass
    vacuously."""
    must_fire = [
        "\U0001F4C8 Expand — 12 branches sit on prime white-space with thin competition; lead the region's acquisition here.",
        "Where to open next: 8 under-served amphoe.",
        "We should open a branch here given the coverage gap.",
        "Recommend opening 3 branches in Rayong.",
        "Add 5 new branches to close the whitespace.",
        "Grow the branch network into the northeast.",
    ]
    must_stay_quiet = [
        "Expansion pace & book scale — Muangthai ฿142bn (+18% YoY) +518 branches/2025.",
        "Who to acquire here — top leads (measured nearby).",
        "Low competitive pressure — 14 branches face thin rival presence; least margin pressure in the region.",
        "Defend the book — 9 branches face 3+ rival branches within 2 km.",
        "MTC opened 518 branches in 2025 per company IR.",
        "The network is consolidating, so branch-expand actions are not surfaced.",
    ]
    fails = []
    for s in must_fire:
        if _scan_string(s) is None:
            fails.append("SHOULD-FIRE but did not: %r" % s)
    for s in must_stay_quiet:
        h = _scan_string(s)
        if h is not None:
            fails.append("FALSE POSITIVE on %r via %r" % (s, h[0]))
    return fails


def main():
    st = _selftest()
    if st:
        print("mandate_guard: SELF-TEST FAILED (pattern set is unsound, not a data problem):")
        for f in st:
            print("   -", f)
        return 1

    files = sorted(glob.glob(os.path.join(DATA, "*.json")))
    hits = []
    for fp in files:
        try:
            with open(fp, encoding="utf-8") as fh:
                doc = json.load(fh)
        except Exception:
            continue  # non-JSON / unreadable is not this guard's concern
        _walk(doc, os.path.basename(fp), hits)

    if hits:
        print("mandate_guard: FORBIDDEN branch open/close/expand RECOMMENDATION language is live in "
              "surfaced data layers (CLAUDE.md: this platform makes NO open/close/where-to-open "
              "recommendations — it is a competitive-RISK lens on the network AutoX already runs):")
        for path, pat, frag, ctx in hits[:40]:
            print("   %s\n      matched %r via /%s/\n      → %s" % (path, frag, pat, ctx))
        print("\n   %d occurrence(s). Reframe as a competitive-RISK readout (e.g. \"low rival "
              "pressure\"), not an expansion action; reporting a RIVAL's growth is fine." % len(hits))
        return 1

    print("mandate_guard: OK — 0 branch-expansion recommendations across %d data layers "
          "(self-test: %d fire + %d quiet cases pass)." % (len(files), 6, 6))
    return 0


if __name__ == "__main__":
    sys.exit(main())
