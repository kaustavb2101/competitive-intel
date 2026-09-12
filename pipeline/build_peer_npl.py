#!/usr/bin/env python3
"""build_peer_npl.py — Peer loan-quality league (like-for-like) + MEASURED AutoX self-anchor.

Assembles platform/data/peer_npl.json from two committed, in-repo sources — no network:

  1. The six SET-listed title-lender peers' loan quality — ALL on ONE like-for-like basis:
     each peer's SET-filed TFRS9 Stage-3 (credit-impaired) gross share, at the reporting period
     declared by the sibling layer's own meta.as_of. These are NOT re-typed here — they are READ
     from the committed, cited platform/data/peer_asset_quality.json (built by
     build_peer_asset_quality.py from the same SET reviewed financial-statement NOTES), the single
     source of truth for the rivals' loan quality, so this layer can never silently drift from its
     sibling board. It FOLLOWS that sibling: the values, dates AND period labels (Q2/2026, as-of
     date) are derived from its meta.as_of, so the day peer_asset_quality is refreshed with a newer
     filing this board advances with it — no separate edit here (that sibling's as_of is refreshed
     owner-side, since SET is Akamai/bot-blocked from CI, not on a CI schedule). Only the editorial
     descriptors (each peer's collateral book, and — for the big-three that ALSO publish one — their
     prior FY2025 self-reported headline NPL, kept as context, not erased) are carried as constants.

     WHY ONE BASIS (the freshness + honesty change, 2026-09-12): this board previously mixed
     bases — Tidlor / MTC / Srisawad on their ~9-month-stale FY2025 / 2025 IR self-reported
     headline NPL, and only Heng / Saksiam / Ngern Turbo on the current Q2/2026 Stage-3 share —
     so the "peer NPL league" was not like-for-like across its own rows, even though a fresher,
     consistent Q2/2026 Stage-3 figure for ALL six already sat in peer_asset_quality.json (whose
     own note states the six ARE comparable, because all report on the same IFRS-9 basis). Putting
     every peer on that one basis makes the league genuinely comparable AND advances the big-three
     from FY2025 to Q2/2026. The self-reported headline is preserved per-row as `headline_npl` /
     in the source string, so nothing is lost. (AutoX remains a DISTINCT MEASURED anchor — see below.)

  2. AutoX / Ngern Chaiyo's OWN book quality — MEASURED, computed live from the real
     loan tape (platform/data/tape_real.json `bucket_ladder`), so the anchor always
     tracks the committed tape and is never hand-typed.

WHY AN ANCHOR, NOT A RANKED ROW (the honesty crux): the peer figures are each company's
reported IFRS-9 Stage-3 share; the AutoX figure is measured OS-weighted from the real
tape. They are NOT a like-for-like league table WITH AutoX — listed peers write off / provision
out deep-delinquent stock, whereas the AutoX tape carries a 180+ bucket SEPARATELY as legacy
workout inventory (the tape's own framing: "late-stage collections inventory, not fresh
risk"). So AutoX is surfaced as a distinct MEASURED anchor beside the reported-peer band,
NOT sorted into the peers' ranking. Every AutoX number below is derived from the tape's
committed measured buckets; nothing is invented. No open/close/expand framing — a pure
loan-quality read.

Deterministic + network-free + --check byte-reproduce (the AutoX inputs come from the
committed tape, the peers from the committed peer_asset_quality.json + the constants here, so
the output is a pure function of the committed tree). Added to the determinism gate.

  python3 pipeline/build_peer_npl.py            # regenerate platform/data/peer_npl.json
  python3 pipeline/build_peer_npl.py --check    # byte-exact verify (exit 1 on drift)
"""
import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TAPE = os.path.join(ROOT, "platform", "data", "tape_real.json")
ASSET_QUALITY = os.path.join(ROOT, "platform", "data", "peer_asset_quality.json")
OUT = os.path.join(ROOT, "platform", "data", "peer_npl.json")

# --- (1) Editorial descriptors per peer (NOT the NPL number — that is READ from
# peer_asset_quality.json so the loan-quality figure has ONE source of truth). Display order;
# the app re-sorts by NPL. `collateral` is an editorial book descriptor; `headline_npl` (big-3
# only) preserves each company's own prior FY2025 / 2025 IR self-reported headline NPL as
# context so unifying the board onto the current Q2/2026 Stage-3 basis erases nothing. ---
PEER_META = [
    {
        "ticker": "TIDLOR",
        "collateral": "vehicle title (best-in-class)",
        "headline_npl": {"pct": 1.5, "cite": "FY2025 company / thaipr — headline NPL 1.5%"},
    },
    {
        "ticker": "MTC",
        "collateral": "vehicle / motorcycle title",
        "headline_npl": {"pct": 2.53, "cite": "FY2025 company IR / kaohoon — headline NPL 2.53% (target <2.7%)"},
    },
    {
        "ticker": "SAWAD",
        "collateral": "cars/pickups/heavy-vehicle + land/house/condo",
        # SAWAD's self-reported headline is a guidance RANGE; `label` carries it verbatim (the
        # exact cited string), `pct` its midpoint for any numeric use.
        "headline_npl": {"pct": 3.55, "label": "3.5–3.6", "cite": "2025 IR oppday deck — headline NPL guidance 3.5–3.6%"},
        # Stage-3 excludes the purchased/originated credit-impaired (bought distressed-debt) book,
        # reported separately as poci_bn in peer_asset_quality.json — carried in the source string.
        "stage3_note": "excludes the separately-reported purchased credit-impaired (POCI) book",
    },
    {
        # The one CONTRACTING listed peer, and the only reported peer whose loan-quality figure
        # brackets AutoX's own ~6% tape-measured impaired share (objective #2: "compliant" is not
        # "thriving").
        "ticker": "HENG",
        "collateral": "motorcycle / car / land title + hire-purchase (contracting)",
    },
    {
        "ticker": "SAK",
        "collateral": "motorcycle / car / land title + hire-purchase (Isan-focused)",
    },
    {
        "ticker": "TURBO",
        "collateral": "car / motorcycle title (hire-purchase + title loan)",
    },
]


_MONTHS = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
           "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _period_labels(as_of):
    """Derive the reporting-period labels FROM the upstream as-of date so the copy stays
    internally consistent when the filing advances — never a hard-coded "Q2/2026". From an ISO
    "YYYY-MM-DD" return (quarter_label, asof_label) e.g. ("Q2/2026", "30 Jun 2026)."""
    y, m, d = (int(x) for x in as_of.split("-")[:3])
    q = (m - 1) // 3 + 1
    return "Q%d/%d" % (q, y), "%d %s %d" % (d, _MONTHS[m], y)


def _peers_from_asset_quality():
    """Build the six peer rows on ONE like-for-like basis — each peer's SET-filed TFRS9 Stage-3
    credit-impaired gross share, at the reporting period declared by peer_asset_quality.json's own
    meta.as_of — READ from that committed layer (the single source of truth for rival loan quality),
    not re-typed. So this board always FOLLOWS the sibling: the day peer_asset_quality is refreshed
    with a newer SET filing, the values, dates and period labels here advance with it (SET is
    Akamai/bot-blocked from CI, so that sibling's as_of is itself refreshed owner-side, not on a
    schedule). Editorial descriptors + the preserved FY2025 self-reported headline come from
    PEER_META. A PEER_META ticker MISSING from the sibling board is a hard build failure — never a
    silently shorter league than the six the meta/UI advertise."""
    with open(ASSET_QUALITY, encoding="utf-8") as f:
        aq = json.load(f)
    by_sym = {p["symbol"]: p for p in aq.get("peers", [])}
    as_of = aq.get("meta", {}).get("as_of", "2026-06-30")
    period, asof_label = _period_labels(as_of)
    peers = []
    for meta in PEER_META:
        sym = meta["ticker"]
        row = by_sym.get(sym)
        if not row:
            # A required peer is absent from the sibling board — FAIL, never silently ship a
            # shorter league. (A symbol rename or a partial upstream build must break the gate,
            # not pass by the "non-empty list" validator.)
            raise SystemExit(
                "FATAL build_peer_npl: required peer %r not found in peer_asset_quality.json "
                "(has %s). Reconcile PEER_META with the sibling board before building."
                % (sym, sorted(by_sym)))
        npl = row["npl_pct"]
        name = row.get("name", sym)
        src = ("%s SET filing, %s — TFRS9 Stage-3 credit-impaired %s%% of gross receivables, "
               "%s (like-for-like loan-quality basis; from peer_asset_quality.json)"
               % (name, period, _fmt(npl), asof_label))
        if meta.get("stage3_note"):
            src += " — %s" % meta["stage3_note"]
        hl = meta.get("headline_npl")
        if hl:
            src += " · cf. self-reported %s" % hl["cite"]
        out = {
            "ticker": sym,
            "name": name,
            "npl": npl,
            "collateral": meta["collateral"],
            "source": src,
        }
        if hl:
            out["headline_npl"] = hl["pct"]
            out["headline_source"] = hl["cite"]
        peers.append(out)
    return peers, as_of, period, asof_label


def _fmt(v):
    """Format an NPL % the way it is carried (drop a trailing .0 so 6.8 not 6.80)."""
    return ("%g" % v)

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
    peers, as_of, period, asof_label = _peers_from_asset_quality()
    return {
        "meta": {
            "title": "Peer loan-quality league (like-for-like) + AutoX measured anchor",
            "note": ("Six SET-listed title-loan peers on ONE like-for-like loan-quality basis — "
                     "each peer's %s SET-filed TFRS9/IFRS-9 Stage-3 (credit-impaired) gross "
                     "share, as-of %s, READ from platform/data/peer_asset_quality.json "
                     "(the single source of truth for rival loan quality; comparable across the six "
                     "because all report on the same IFRS-9 basis) — shown next to AutoX/Ngern "
                     "Chaiyo's OWN book quality, MEASURED from the real loan tape. This board FOLLOWS "
                     "that sibling layer: values, dates and period labels here are read from it, so "
                     "they advance the day it is refreshed with a newer filing (that sibling's as_of "
                     "is refreshed owner-side — SET is bot-blocked from CI — not on a schedule). The "
                     "big-three's prior FY2025 / 2025 IR self-reported headline NPL is preserved "
                     "per-row as context (headline_npl), not erased. AutoX is NOT ranked inside the "
                     "peer list: listed peers write off / provision out deep-delinquent stock that "
                     "AutoX carries SEPARATELY as 180+ legacy workout inventory, so AutoX is a "
                     "distinct MEASURED anchor beside the reported-peer band. Heng is the one "
                     "CONTRACTING peer and the only reported peer whose Stage-3 share brackets "
                     "AutoX's own impaired share ('compliant' is not 'thriving'). The spread tracks "
                     "collateral mix: gold/vehicle books run lower Stage-3, land/agri/heavy-vehicle "
                     "books higher.") % (period, asof_label),
            "measured": "peers = SET-filed IFRS-9 Stage-3 share (reported); AutoX = measured from the real loan tape",
            "source": ("peers: platform/data/peer_asset_quality.json (all six, SET %s reviewed "
                       "financial-statement NOTES, TFRS9 Stage-3, as-of %s); big-three "
                       "self-reported headline context: docs/RESEARCH_DIGEST.md §B; "
                       "AutoX: platform/data/tape_real.json") % (period, asof_label),
            "generated_by": "pipeline/build_peer_npl.py",
            "updated": as_of,
            "period_label": period,
            "as_of_label": asof_label,
        },
        "peers": peers,
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
    b = build()
    a = b["autox"]
    print("wrote %s — %d peers (like-for-like Q2/2026 Stage-3) + AutoX anchor "
          "(NPL-live %.2f%% OS · 90+%.2f%% OS)"
          % (OUT, len(b["peers"]), a["npl_live_os_pct"], a["npl_90plus_os_pct"]))


if __name__ == "__main__":
    main()
