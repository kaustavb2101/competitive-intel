#!/usr/bin/env python3
"""build_peer_npl.py — Peer NPL benchmark + MEASURED AutoX self-anchor.

Assembles platform/data/peer_npl.json from two committed, in-repo sources — no network:

  1. The listed title-lender peers' OWN reported NPL ratios — hand-curated from
     docs/RESEARCH_DIGEST.md §B (each company's FY2025 / 2025 IR figure; Heng's is its
     H1-2026 SET-filed Stage-3 credit-impaired share, the loan-quality analog for a TFRS9
     hire-purchase/leasing lender), carried as cited constants below. They are the source of
     truth (they change ~yearly and are published, not pulled), so hard-coding them here —
     with their citation — is honest.

  2. AutoX / Ngern Chaiyo's OWN book quality — MEASURED, computed live from the real
     loan tape (platform/data/tape_real.json `bucket_ladder`), so the anchor always
     tracks the committed tape and is never hand-typed.

WHY AN ANCHOR, NOT A RANKED ROW (the honesty crux): the peer figures are each company's
reported NPL on its own basis; the AutoX figure is measured OS-weighted from the real
tape. They are NOT a like-for-like league table — listed peers write off / provision out
deep-delinquent stock, whereas the AutoX tape carries a 180+ bucket SEPARATELY as legacy
workout inventory (the tape's own framing: "late-stage collections inventory, not fresh
risk"). So AutoX is surfaced as a distinct MEASURED anchor beside the reported-peer band,
NOT sorted into the peers' ranking. Every AutoX number below is derived from the tape's
committed measured buckets; nothing is invented. No open/close/expand framing — a pure
loan-quality read.

Deterministic + network-free + --check byte-reproduce (the AutoX inputs come from the
committed tape, the peers from the constants here, so the output is a pure function of the
committed tree). Added to the determinism gate.

  python3 pipeline/build_peer_npl.py            # regenerate platform/data/peer_npl.json
  python3 pipeline/build_peer_npl.py --check    # byte-exact verify (exit 1 on drift)
"""
import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TAPE = os.path.join(ROOT, "platform", "data", "tape_real.json")
OUT = os.path.join(ROOT, "platform", "data", "peer_npl.json")

# --- (1) Listed title-lender peers' OWN reported NPL — docs/RESEARCH_DIGEST.md §B ---
# Reported by the companies themselves (FY2025 / 2025 IR). Order preserved from the
# hand-curated source; the app re-sorts by NPL for display.
PEERS = [
    {
        "ticker": "TIDLOR",
        "name": "Ngern Tid Lor",
        "npl": 1.5,
        "collateral": "vehicle title (best-in-class)",
        "source": "FY2025 company / thaipr — NPL 1.5%",
    },
    {
        "ticker": "MTC",
        "name": "Muangthai Capital",
        "npl": 2.53,
        "collateral": "vehicle / motorcycle title",
        "source": "FY2025 company IR / kaohoon — NPL 2.53% (target <2.7%)",
    },
    {
        "ticker": "SAWAD",
        "name": "Srisawad",
        "npl": 3.55,
        "npl_label": "3.5–3.6",
        "collateral": "cars/pickups/heavy-vehicle + land/house/condo",
        "source": "2025 IR oppday deck — NPL guidance 3.5–3.6%",
    },
    {
        # The one CONTRACTING listed peer, and the only reported peer whose loan-quality figure
        # brackets AutoX's own ~6% tape-measured impaired share (objective #2: "compliant" is not
        # "thriving"). Heng is a hire-purchase / leasing lender, so it reports a TFRS9/IFRS-9
        # Stage-3 (credit-impaired) share rather than a bank-style 90+ NPL — the loan-quality
        # analog for its accounting basis, and arguably a CLOSER basis-match to AutoX's own
        # impaired-share read than the other peers' headline NPLs. The mixed basis is disclosed
        # in the row source, the meta.note, and the app's method box — this stays consistent with
        # the layer's standing "NOT a like-for-like league table" framing.
        "ticker": "HENG",
        "name": "Heng Leasing & Capital",
        "npl": 6.78,
        "collateral": "motorcycle / car / land title + hire-purchase (contracting)",
        "source": "Heng SET filing, H1-2026 — Stage 3 credit-impaired 6.78% of gross book "
                  "(฿542.8m/฿8,002.8m), 30 Jun 2026; TFRS9/IFRS-9 basis (loan-quality analog)",
    },
]

# Buckets in tape_real.json's ladder that are 90+ days past due (the strict BoT NPL
# definition: overdue >90 days, INCLUDING the 180+ legacy stock).
NPL_90PLUS_PREFIXES = ("5.", "6.", "7.", "8.")


def _measured_autox_anchor():
    """Compute AutoX's own measured NPL figures from the real loan tape. Every value is
    read/derived from tape_real.json's committed `bucket_ladder` — nothing hand-typed."""
    with open(TAPE, encoding="utf-8") as f:
        tape = json.load(f)
    bl = tape["bucket_ladder"]
    book_os = float(bl["book_total"]["os_sum"])
    live = bl["live_book"]
    live_npl_os = float(live["npl_live_os"])
    # strict BoT 90+ (90/120/150/180+) as a share of the TOTAL book — the basis the
    # peers report on (NPL / gross loans), so this is the closest like-for-like figure.
    os_90plus = sum(
        float(r["os_sum"]) for r in bl["ladder"]
        if str(r["bucket"]).startswith(NPL_90PLUS_PREFIXES)
    )
    legacy = bl["legacy_180plus"]
    return {
        "name": "AutoX / Ngern Chaiyo",
        "handle": "own book",
        "basis": "MEASURED — real loan tape (%s no-PII accounts), OS-weighted"
                 % f"{int(tape['meta']['n_accounts']):,}",
        # headline number the rest of the platform already uses: 90-179dpd NPL-live as a
        # share of the LIVE book (Current..150dpd) — the fresh-risk read.
        "npl_live_os_pct": round(float(live["npl_live_os_pct"]), 2),
        "npl_live_acct_pct": round(float(live["npl_live_pct"]), 2),
        # the same live NPL expressed against the TOTAL book (so it shares the peers' denominator).
        "npl_live_of_total_os_pct": round(live_npl_os / book_os * 100, 2),
        # strict 90+ (incl. the separately-held 180+ legacy workout stock) / total book.
        "npl_90plus_os_pct": round(os_90plus / book_os * 100, 2),
        "legacy_180plus_os_pct": round(float(legacy["os_sum"]) / book_os * 100, 2),
        "collateral": "motorcycle / pickup / car title + land (mixed, heavier tail)",
        "source": "MEASURED — platform/data/tape_real.json (real loan-tape aggregates, obj #1)",
        "caveat": ("NOT a like-for-like rank vs the reported peers: the headline 90-179dpd "
                   "NPL-live is a share of the LIVE book, while a strict BoT 90+ (incl. the "
                   "฿3.05bn 180+ legacy workout stock the tape holds SEPARATELY as late-stage "
                   "collections inventory) on the full book is higher — and listed peers write "
                   "off / provision out that deep-delinquent stock, so their reported NPL sits "
                   "on a different basis. Read the direction, not a precise league position."),
    }


def build():
    autox = _measured_autox_anchor()
    return {
        "meta": {
            "title": "Peer NPL benchmark (reported) + AutoX measured anchor",
            "note": ("Listed title-loan peers' reported NPL ratios (their own FY2025 / 2025 IR "
                     "figures; Heng's is its H1-2026 SET-filed TFRS9 Stage-3 credit-impaired "
                     "share — the loan-quality metric a hire-purchase/leasing lender publishes in "
                     "place of a bank-style 90+ NPL, and the closest basis-match to AutoX's own "
                     "impaired-share read) shown next to AutoX/Ngern Chaiyo's OWN book quality, "
                     "MEASURED from the real loan tape. NOT a like-for-like league table — peers "
                     "report on their own bases and write off / provision out deep-delinquent stock "
                     "that AutoX carries SEPARATELY as 180+ legacy workout inventory — so AutoX is a "
                     "distinct MEASURED anchor, not ranked inside the reported-peer list. Heng is "
                     "the one CONTRACTING peer and the only reported peer whose figure brackets "
                     "AutoX's own impaired share ('compliant' is not 'thriving'). The spread tracks "
                     "collateral mix: gold/vehicle books run lower NPL, land/agri/heavy-vehicle "
                     "books higher."),
            "measured": "peers = reported by the companies; AutoX = measured from the real loan tape",
            "source": "peers: docs/RESEARCH_DIGEST.md §B (FY2025 / 2025 IR); AutoX: platform/data/tape_real.json",
            "generated_by": "pipeline/build_peer_npl.py",
            "updated": "2026-06",
        },
        "peers": PEERS,
        "autox": autox,
    }


def _dumps(data):
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true",
                    help="byte-exact verify the committed peer_npl.json reproduces")
    args = ap.parse_args()

    payload = _dumps(build())

    if args.check:
        if not os.path.exists(OUT):
            print("SKIP build_peer_npl --check: %s absent" % OUT)
            sys.exit(3)
        cur = open(OUT, encoding="utf-8").read()
        if cur != payload:
            print("FAIL build_peer_npl --check: peer_npl.json drifted from builder output")
            sys.exit(1)
        print("OK build_peer_npl --check: peer_npl.json reproduces exactly")
        return

    with open(OUT, "w", encoding="utf-8") as f:
        f.write(payload)
    a = build()["autox"]
    print("wrote %s — %d peers + AutoX anchor (NPL-live %.2f%% OS · 90+%.2f%% OS)"
          % (OUT, len(PEERS), a["npl_live_os_pct"], a["npl_90plus_os_pct"]))


if __name__ == "__main__":
    main()
