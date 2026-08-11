#!/usr/bin/env python3
"""check_peer_constants.py — tripwire: peer scoreboard constants ⇄ RESEARCH_DIGEST.md §B.

WHY THIS EXISTS
    The listed title-lender peers' branch counts, loan books, NPL ratios and MTC's
    branch-add pace are the backbone of the objective-#2 competitive read. They are
    hand-carried as CITED constants in two builders:
        pipeline/build_peer_npl.py            — PEERS[].npl  (the reported NPL ladder)
        pipeline/build_competitor_coverage.py — EXPECTED[] branch counts + PEER_FINANCIALS[]
                                                books / net-adds / growth target / YoY
    Their single source of truth is docs/RESEARCH_DIGEST.md §B ("Competitors — listed
    peers' 2025 scoreboard"). Only the tape→book link is gate-checked today (see the
    2026-08-11 PROGRESS_LOG entry); these IR figures are NOT. So a future IR refresh could
    update the digest and leave a builder stale — or edit a builder and leave the digest
    stale — and the peer board would silently diverge from the cited research with a green
    gate. That is exactly the provenance defect this repo's determinism gate exists to catch.

WHAT IT DOES
    For each cited figure it DERIVES the expected digest substring FROM the live builder
    constant (imported, not re-typed here) and asserts that substring is present in that
    brand's own §B FINDING bullet. Scoping to the per-brand FINDING line (not the whole
    section) means a figure that is repeated in the INTERPRETATION line cannot launder a
    single-occurrence edit, so BOTH drift directions are caught:
      - edit a builder constant  → its derived substring no longer matches the digit in the
                                    brand's FINDING bullet
      - edit a FINDING figure     → the builder's derived substring is no longer in the bullet
    Nothing is written — this is a pure cross-consistency assertion, so it needs no
    platform/data output and no provenance regen. Both `check_peer_constants.py` and the
    `--check` alias run the same verification (there is nothing to "build"), exiting 1 on
    any mismatch so it is a clean tripwire for tests/run.sh and rederive_drift.py alike.

    python3 pipeline/check_peer_constants.py            # report each figure, exit 1 on drift
    python3 pipeline/check_peer_constants.py --check     # identical (gate-convention alias)
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DIGEST = os.path.join(ROOT, "docs", "RESEARCH_DIGEST.md")

# Import the two builders' constants live, so a builder edit is what changes the expected
# substring (never a second hand-typed copy here). Both import only stdlib at module level.
sys.path.insert(0, HERE)
import build_peer_npl            # noqa: E402
import build_competitor_coverage as bcc  # noqa: E402

# Canonical brand key → the exact marker that opens that brand's §B FINDING bullet. Every
# cited figure for a brand lives on this bullet (the following "  - http…" lines are its
# source URLs). Both builders' brand spellings map onto these three keys.
FINDING_MARKERS = {
    "MTC": "**FINDING — Muangthai Capital (MTC):**",
    "SAWAD": "**FINDING — Srisawad (SAWAD):**",
    "TIDLOR": "**FINDING — Ngern Tid Lor (TIDLOR):**",
}


def _section_b(text):
    """Return §B ('### B.' up to the next '### ' heading)."""
    lines = text.splitlines()
    start = next((i for i, ln in enumerate(lines) if ln.startswith("### B.")), None)
    if start is None:
        sys.exit("FATAL: '### B.' scoreboard section not found in docs/RESEARCH_DIGEST.md")
    end = next((j for j in range(start + 1, len(lines)) if lines[j].startswith("### ")),
               len(lines))
    return lines[start:end]


def _finding_bullets(section_lines):
    """Map each canonical brand key → the text of its FINDING bullet (the '- **FINDING…'
    line plus any wrapped continuation up to the next top-level '- ' bullet, but NOT the
    indented '  - http' source lines)."""
    bullets = {}
    for key, marker in FINDING_MARKERS.items():
        idx = next((i for i, ln in enumerate(section_lines) if marker in ln), None)
        if idx is None:
            sys.exit("FATAL: §B FINDING bullet for %s not found (marker %r)" % (key, marker))
        buf = [section_lines[idx]]
        for ln in section_lines[idx + 1:]:
            if ln.startswith("- ") or ln.startswith("### "):
                break
            if ln.strip().startswith("- http"):   # source-URL sub-bullets — not figures
                continue
            buf.append(ln)
        bullets[key] = "\n".join(buf)
    return bullets


def _thousands(n):
    """Render a figure the way the digest prints it (comma thousands, no decimals)."""
    return format(int(round(n)), ",")


def _checks():
    """(brand_key, label, expected-substring) triples, each DERIVED from a live builder
    constant. Only figures cited verbatim in a FINDING bullet are asserted (arithmetic-only
    fields such as prior_year_branches are excluded — they are back-computed, not cited)."""
    exp = bcc.EXPECTED
    fin = bcc.PEER_FINANCIALS
    peers = {p["ticker"]: p for p in build_peer_npl.PEERS}
    return [
        # build_competitor_coverage.EXPECTED — nationwide branch counts
        ("MTC", "EXPECTED[Muangthai] branches", _thousands(exp["Muangthai"])),
        ("TIDLOR", "EXPECTED[Tidlor] branches", _thousands(exp["Tidlor"])),
        ("SAWAD", "EXPECTED[Srisawad] branches", _thousands(exp["Srisawad"])),
        # build_competitor_coverage.PEER_FINANCIALS — books (฿bn → ฿m), pace, target, YoY
        ("MTC", "PEER_FINANCIALS[Muangthai] loan book ฿m", _thousands(fin["Muangthai"]["loan_book_bn"] * 1000)),
        ("TIDLOR", "PEER_FINANCIALS[Tidlor] loan book ฿m", _thousands(fin["Tidlor"]["loan_book_bn"] * 1000)),
        ("SAWAD", "PEER_FINANCIALS[Srisawad] loan book ฿m", _thousands(fin["Srisawad"]["loan_book_bn"] * 1000)),
        ("MTC", "PEER_FINANCIALS[Muangthai] net branch adds", str(fin["Muangthai"]["net_adds_yr"])),
        ("MTC", "PEER_FINANCIALS[Muangthai] growth target %", str(fin["Muangthai"]["growth_target_pct"])),
        ("TIDLOR", "PEER_FINANCIALS[Tidlor] book YoY %", f'{fin["Tidlor"]["book_yoy_pct"]}%'),
        # build_peer_npl.PEERS — the reported NPL ladder
        ("TIDLOR", "PEERS[TIDLOR] NPL %", f'{peers["TIDLOR"]["npl"]}%'),
        ("MTC", "PEERS[MTC] NPL %", f'{peers["MTC"]["npl"]}%'),
        # SAWAD carries a range label ("3.5–3.6"); assert the label the app shows, not the midpoint.
        ("SAWAD", "PEERS[SAWAD] NPL range label", str(peers["SAWAD"]["npl_label"])),
    ]


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true",
                    help="gate-convention alias; identical behaviour (nothing is written)")
    ap.parse_args()

    with open(DIGEST, encoding="utf-8") as f:
        bullets = _finding_bullets(_section_b(f.read()))

    checks = _checks()
    missing = []
    for brand, label, needle in checks:
        present = needle in bullets[brand]
        print(f"  [{'OK ' if present else 'MISS'}] {label:44s} → {needle!r}  (§B {brand} bullet)")
        if not present:
            missing.append((brand, label, needle))

    if missing:
        print("\nFAIL check_peer_constants: %d peer figure(s) not found in their §B FINDING "
              "bullet in docs/RESEARCH_DIGEST.md —" % len(missing))
        for brand, label, needle in missing:
            print(f"    {label}: expected {needle!r} in the {brand} FINDING bullet")
        print("  The builder constant and the cited research have diverged. Reconcile "
              "build_peer_npl.py / build_competitor_coverage.py with RESEARCH_DIGEST.md §B "
              "(update whichever is stale after an IR refresh).")
        sys.exit(1)

    print("\nOK check_peer_constants: all %d peer scoreboard constants match their §B "
          "FINDING bullet in docs/RESEARCH_DIGEST.md." % len(checks))


if __name__ == "__main__":
    main()
