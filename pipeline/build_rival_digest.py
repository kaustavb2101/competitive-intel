#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_rival_digest.py — the daily rival-pulse email: what moved in the competitive field.

WHY. Every rival feed in this repo already refreshes daily (pull_swarm.py: google_ads,
app_reviews, apple_reviews, rival_youtube, rival_promos), lands as an auto-merged PR and is
rendered on the Competition tab. None of it is PUSHED anywhere, so seeing it requires
remembering to go and look — which is the one step a daily cadence cannot rely on. This
renders the day's movement as an email.

IT DETECTS NOTHING ITSELF. rival_watch.json is already the diff layer, and it is careful in
ways worth not re-implementing badly: it never claims a promo "disappeared" without a measured
last_seen to prove it stopped, never reads a trend off a single snapshot, and never uses the
wall clock — every date is copied from a field the source data stamped. This script renders
that, plus the rate board and the sentiment ladder. If the digest and the site ever disagree,
the site is right and this is broken.

NO WALL CLOCK, same as everything upstream: the digest is stamped with the sources' own as_of
dates. Re-running on a different day with unchanged inputs produces an identical email, which
is what makes "nothing new today" a trustworthy statement rather than an absence of evidence.

SENDING. --send posts it over SMTP using env vars and nothing else — no third-party action, no
vendor SDK, stdlib smtplib only. Absent credentials it exits 3 (SKIP) and still writes the
HTML, so the workflow stays green and says why, matching how the repo handles YOUTUBE_API_KEY.

  python3 build_rival_digest.py --out digest.html          # render only
  python3 build_rival_digest.py --out digest.html --send    # render + email
  python3 build_rival_digest.py --stdout                    # print the text version
"""
import argparse
import io
import json
import os
import smtplib
import sys
from email.message import EmailMessage
from email.utils import formataddr

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = os.path.join(ROOT, "platform", "data")
# Our OWN policy ceilings, so the email can name a lever instead of only a rival. Deliberately in
# pipeline/ and not platform/data — platform/ is the deployed folder and this is internal policy.
# Written by build_policy_levers.py from the owner-side workbook. See that script's docstring.
LEVERS = os.path.join(ROOT, "pipeline", "policy_levers.json")

# LIGHT palette, on the owner's instruction — the dark console theme belongs to the dashboard,
# where it is read on a big screen; in an inbox at 08:30 on a phone it is just hard to read.
# Accent/gold/merch are the app's hues DARKENED to hold contrast on white (the dashboard values
# are tuned against #0F1216 and go illegible on a light ground).
#
# INK is the one dark surface, and it is a MASTHEAD BAND, not a reading ground. The instruction
# that produced this palette was that black body text on black is unreadable in a mail client,
# which is true and is not an argument against a header carrying six words in 34px type. Every
# line of actual content stays on white or on the near-white wash.
BG, CARD, FG, DIM = "#F4F5F7", "#FFFFFF", "#1B1F27", "#5C6572"
WASH, LINE, INK = "#F4F5F7", "#E3E6EB", "#0B0E14"
ACC, GOLD, MERCH, PD = "#3B5BD9", "#8A6206", "#12695C", "#A6332C"
# Two tints that only ever appear ON the dark masthead (ACCLT, MUTED) or as a card ground
# behind the undercut rows (PDWASH). Kept separate so nothing reaches for a lightened accent
# on a white ground, where it would fail contrast.
ACCLT, MUTED, PDWASH = "#8FA6FF", "#8B93A1", "#FDF4F3"


def load(name):
    p = os.path.join(D, name + ".json")
    if not os.path.exists(p):
        return {}
    try:
        with io.open(p, encoding="utf-8") as f:
            return json.load(f)
    except (ValueError, OSError):
        return {}


def esc(s):
    return (str(s if s is not None else "").replace("&", "&amp;")
            .replace("<", "&lt;").replace(">", "&gt;"))


def fmt(v):
    """A rate, printed without inventing precision or a decimal point it never had."""
    if v is None:
        return "—"
    return ("%.2f" % v).rstrip("0").rstrip(".")


def thai_names():
    """key -> Thai brand name, from the operator universe.

    Every layer carries the same operator `key`, but each renders its own label: the watch
    layer prints the English "Srisawad", the Play ladder prints an app name. The owner reads
    these brands in Thai, so one canonical map is applied at render time rather than trusting
    whatever string each layer happened to store.
    """
    p = os.path.join(ROOT, "source-data", "rival_universe.json")
    try:
        with io.open(p, encoding="utf-8") as f:
            u = json.load(f)
    except (ValueError, OSError):
        return {}
    ops = u.get("operators") if isinstance(u, dict) else u
    return {o.get("key"): o.get("name_th") for o in (ops or []) if o.get("key")}


def th(names, key, fallback=None):
    """Thai name for an operator key, falling back to whatever the layer stored.

    Never invents a name: an operator absent from the universe keeps its own label rather
    than being silently dropped or rendered as a bare key.
    """
    return names.get(key) or fallback or key or "—"


def collect():
    """Everything the digest says, as plain data — so the HTML and text stay in step."""
    watch, pulse = load("rival_watch"), load("rival_pulse")
    board, ads = load("rate_board"), load("rival_ads")
    fb = load("rival_facebook")
    w_ads = watch.get("ads") or {}
    w_promo = watch.get("promos") or {}
    w_search = watch.get("search_demand") or {}

    # The as_of the whole digest is stamped with: the newest date the SOURCES claim, never today.
    stamps = [w_ads.get("as_of"), w_promo.get("as_of"),
              (ads.get("meta") or {}).get("pulled"),
              (board.get("meta") or {}).get("asof_ads")]
    asof = max([s for s in stamps if s] or ["unknown"])

    # NEW PRICING ADS — the slice a pricing decision is actually made from. Recency comes from
    # the creative's own first-shown date against the pull stamp, so this cannot drift with
    # when the job happens to run.
    pulled = (ads.get("meta") or {}).get("pulled") or ""
    fresh = [a for a in (ads.get("ads") or [])
             if a.get("pricing") and a.get("first") and pulled and a["first"] >= pulled[:8] + "01"]
    fresh.sort(key=lambda a: (a.get("first") or "", a.get("key") or ""), reverse=True)

    ops = board.get("operators") or []
    ltv = sorted([o for o in ops if o.get("ltv_pct") is not None],
                 key=lambda o: -o["ltv_pct"])
    comp = ((board.get("meta") or {}).get("comparable_effective")) or {}

    sent = pulse.get("sentiment") or []
    us = next((s for s in sent if s.get("is_us")), None)

    # SENTIMENT ACROSS ALL FOUR LISTENING POSTS, not just Google Play. Play and Apple only see
    # brands that ship an app, which is why เงินให้ใจ never appeared in this email despite
    # LEADING Pantip discussion — the loudest brand in the field was invisible because it has
    # no app. Union the keys so presence in ANY source puts a brand on the board.
    names = thai_names()
    # The app-review pullers key by APP identity, the universe/Pantip/YouTube by OPERATOR.
    # Unaliased, เงินเทอร์โบ showed "no app presence" on this board while actually rating
    # 4.08★ on Play — the same brand under two names, silently split. KRUNGSRI_GO is
    # deliberately NOT folded into CAR4CASH: GO is Krungsri Auto's super-app and Car4Cash is
    # the loan product, and Pantip tracks them apart too.
    ALIAS = {"NGERNTURBO": "TURBO", "SAKSIAM": "SAK"}
    def op(k):
        return ALIAS.get(k, k)

    # Apple's catalogue reaches well past vehicle refinance; a 4.84★ digital cash-advance app
    # is not a peer of ours and must not sit in a title-loan board. Keep the title cohort.
    ios = [r for r in (pulse.get("ios") or [])
           if (r.get("cohort") or "title") == "title"]
    pantip = [b for b in (load("pantip_panel").get("brands") or [])
              if b.get("key") and b.get("key") != "_CATEGORY"]
    tube = load("rival_youtube").get("channels") or []

    play_by = {op(r["brand"]): r for r in sent if r.get("brand")}
    ios_by = {op(r["brand"]): r for r in ios if r.get("brand")}
    pan_by = {op(b["key"]): b for b in pantip}
    tube_by = {op(c["key"]): c for c in tube if c.get("key")}

    # EVERY OPERATOR IN THE UNIVERSE, on the owner's instruction: "if there are 23 players in
    # this universe, you need to find information on all of them." A board built only from
    # brands that happen to HAVE data silently drops the ones we cover worst — อะมานะฮ์
    # ลิสซิ่ง has nothing in any source and so was invisible, which reads as "no such
    # competitor" rather than "we are not watching this competitor". Listing all 23 with the
    # blanks showing turns a hidden coverage gap into a visible one.
    rate_by = {}
    for o in ops:
        if o.get("key"):
            rate_by[o["key"]] = o
    universe_keys = [k for k in names] or sorted(
        set(play_by) | set(ios_by) | set(pan_by) | set(tube_by))

    board_rows = []
    for key in universe_keys:
        pl, ap = play_by.get(key) or {}, ios_by.get(key) or {}
        pa, yt = pan_by.get(key) or {}, tube_by.get(key) or {}
        rb = rate_by.get(key) or {}
        row = {
            "key": key,
            "name": th(names, key, pa.get("label") or yt.get("name_th") or pl.get("name")),
            "is_us": bool(pl.get("own") or pa.get("is_us") or yt.get("is_us") or key == "AUTOX"),
            "eff": rb.get("effective_lo"),
            "eff_src": rb.get("effective_source"),
            "play": pl.get("score"),
            "apple": ap.get("score"),
            "pantip": pa.get("est_threads"),
            "subs": yt.get("subscribers"),
            # Whose channel: a PARENT corporate channel is not the product's own audience.
            "subs_parent": bool(yt.get("is_parent_channel")),
        }
        row["n_sources"] = sum(row[f] is not None
                               for f in ("eff", "play", "apple", "pantip", "subs"))
        board_rows.append(row)
    # Ordered by Pantip volume — who the market is actually talking about. Brands with no
    # Pantip figure sort last rather than being read as "quiet", and the ones we hold nothing
    # at all on sort last of those, which puts our own blind spots at the bottom in plain view.
    board_rows.sort(key=lambda r: (r["pantip"] is None, -(r["pantip"] or 0), -r["n_sources"]))
    blind = [r["name"] for r in board_rows if r["n_sources"] == 0]

    # THE FACEBOOK FEED LEADS THE EMAIL. Kaustav: "facebook is always the promo." The rate card
    # is the BoT-mandated disclosure — the legal ceiling — while the post is what the rival is
    # actually winning customers with this week. KTC พี่เบิ้ม posted 0.60%/month the same day its
    # published card said 12.99–24%/yr; that teaser appears nowhere in the disclosure. So the
    # post goes above the rate board, and the two are never averaged.
    fb_promos = [p for p in (fb.get("promos") or []) if p.get("post")]

    # WHERE THE CARD UNDERSTATES THE RIVAL. build_promo_gap.py compares each operator's live
    # promo against its own published disclosure and reports only the ones that survive the
    # conservative reading (unstated monthly rates scored as FLAT, at the operator's own maximum
    # tenor). This layer existed, was gated and was even listed in the workflow's pre-flight, but
    # nothing read it — so the finding that started this whole thread (เงินติดล้อ selling at 10%
    # against a 24% card) reached the site and never reached the person who asked for it.
    gap = load("promo_gap")
    gap_hits = [r for r in (gap.get("operators") or []) if r.get("undercuts_own_card")]
    gap_hits.sort(key=lambda r: -(r.get("gap_pp") or 0))

    out = {
        "asof": asof,
        "names": names,
        "fb_promos": fb_promos,
        "fb_meta": fb.get("meta") or {},
        "gap_hits": gap_hits,
        "gap_meta": gap.get("meta") or {},
        "sentiment_board": board_rows,
        "blind": blind,
        "n_universe": len(board_rows),
        "pantip_headline": (load("pantip_panel").get("headline") or None),
        "n_pantip_brands": len(pantip),
        "headline": pulse.get("headline"),
        "ads_appeared": w_ads.get("appeared") or [],
        "ads_disappeared": w_ads.get("disappeared") or [],
        "promos_new": w_promo.get("new") or [],
        "promos_gone": w_promo.get("disappeared") or [],
        "search_moved": w_search.get("movement") or [],
        "fresh_pricing": fresh[:8],
        "n_fresh_pricing": len(fresh),
        "operators": ops,
        "ltv_top": ltv[:3],
        "comparable": comp,
        "cheapest_flat": (board.get("meta") or {}).get("cheapest_flat"),
        "sentiment": sent[:6],
        "us": us,
        "n_creatives": (ads.get("meta") or {}).get("n_creatives"),
        "n_pricing": (ads.get("meta") or {}).get("n_ads_pricing"),
        "basis_stated": (board.get("meta") or {}).get("n_creatives_basis_stated"),
        "basis_scanned": (board.get("meta") or {}).get("n_creatives_scanned"),
    }
    # Derived LAST, because each of these reads the observations above.
    lv = levers()
    out["levers_meta"] = lv.get("meta") or {}
    # THE RATE WE GO TO MARKET AT. Owner's instruction: the LTVX C-code floor is "what we are vying
    # to win in the market for", so it — not the published card floor — is what every part of this
    # email uses to say where we sit on price. Falls back to the board figure if the projection is
    # absent, so an unavailable levers file degrades the framing rather than blanking the rank.
    out["gtm_rate"] = ((lv.get("ltvx") or {}).get("title_best_rate_pct")
                       or ((next((o for o in ops if o.get("is_us")), None) or {}).get("effective_lo")))
    out["ltv_standing"] = ltv_standing(ops, lv)
    out["beat_matrix"] = beat_matrix(ops, board.get("rows") or [], lv)
    out["agri"] = agri()
    out["actions"] = actions(out, lv)
    return out


def ltv_standing(ops, lv):
    """Where our LIVE campaign ceiling sits against every rival that publishes an LTV.

    The owner's question, verbatim: "which players are we better or on par with based on our new
    LTVX campaign". So the comparator is the CAMPAIGN ceiling (ประกาศ 097/047/107 uplift), never
    the base ระเบียบ grid — a rival's headline LTV is its campaign too, and netting their promo
    against our base would understate us by the whole uplift.

    ON PAR is a band, not an equality: ±5pp. Two lenders at 100% and 98% are the same offer to a
    borrower, and reporting that as "behind" would be false precision on numbers that are rounded
    in the advertising anyway.

    THE CAVEAT IS NOT OPTIONAL. Their percentage may be quoted on a different base than our
    appraised-value basis, so `basis_confirmed` stays False until someone gets one in writing.
    The verdict is still worth stating — it is the best available read — but it is stated as
    resting on that assumption rather than as settled fact.
    """
    x = (lv or {}).get("ltvx") or {}
    ours = x.get("title_cap_pct")            # the title-loan cap — our core book
    pub = sorted([o for o in ops if o.get("ltv_pct") is not None],
                 key=lambda o: -o["ltv_pct"])
    if ours is None or not pub:
        return {}
    BAND = 5.0
    behind = [o for o in pub if o["ltv_pct"] > ours + BAND]
    on_par = [o for o in pub if abs(o["ltv_pct"] - ours) <= BAND]
    better = [o for o in pub if o["ltv_pct"] < ours - BAND]
    us = next((o for o in ops if o.get("is_us")), None)
    return {
        "ours": ours,
        "standard": x.get("standard_cap_pct"),
        "rate_at_cap": x.get("title_rate_at_cap"),
        "best_rate": x.get("title_best_rate_pct"),
        "card_rate": (us or {}).get("effective_lo"),
        "codes": [c for c in (x.get("codes") or []) if c.get("loan_kind") == "title"],
        "gate": x.get("low_risk_gate"),
        "vtypes": x.get("eligible_vehicle_types") or [],
        "v46": x.get("v46_change"),
        "source": x.get("source"),
        "source_note": x.get("source_note"),
        "band_pp": BAND,
        "behind": behind, "on_par": on_par, "better": better,
        "n_published": len(pub),
        "basis_confirmed": False,
    }


# The heatmap's bands. Each is "how far apart before a borrower would notice", not a tolerance.
BEAT_BAND_LTV = 5.0     # pp — two lenders at 100% and 98% are the same offer
BEAT_BAND_RATE = 0.5    # pp/yr on a nominal reducing-balance basis
BEAT_BAND_TENOR = 6     # months — 60 vs 63 is not a competitive difference


def beat_matrix(ops, board_rows, lv):
    """WHO WE CAN BEAT NOW — the owner's question, as a scored grid instead of prose.

    Three dimensions, because three are what the rate board actually measures for enough operators
    to be worth colouring: LTV ceiling, rate, and maximum tenor. Each cell says who wins, and
    carries both numbers so the colour can be audited rather than trusted.

    EVERY RIVAL IS RESTATED ONTO OUR OWN PRODUCT FIRST, and this is the whole difference between
    a useful heatmap and a flattering one. Thai vehicle lending sells two products side by side:
    โอนเล่ม (registration transferred to the lender) and ไม่โอนเล่ม (borrower keeps the book) —
    which is what AutoX does. A lender's HEADLINE numbers are almost always the โอนเล่ม ones,
    because that is the cheaper, better-secured product, and the rate board's own `so_what` warns
    that our peers are the ไม่โอนเล่ม column. Two measured examples of what the headline costs you:
      · CIMB advertises 5.4%/yr. Its ไม่โอนเล่ม floor, published by CIMB itself, is 9.95%. Scoring
        our 12.99% against 5.4% would have claimed a 7.6pp advantage on a product we do not sell;
        against the real 9.95% we LOSE. The flattering read and the true read are opposite.
      · Ngern Hai Jai's headline LTV is 150%, but that is its โอนเล่ม variant — the ไม่โอนเล่ม
        variant is 140%. The operator rollup carries the 150.
    So rate comes from `by_collateral.no_transfer.lo` (lender-published, already restated by the
    board to NOMINAL reducing-balance) and LTV/tenor come from that operator's own no_transfer
    VARIANT ROWS, never the rollup. Where a rival publishes no ไม่โอนเล่ม figure the cell is left
    unscored with the reason attached — transfer-only product, or simply not published — rather
    than filled in from the variant we are not competing with.

    OUR SIDE IS THE LTVX PROGRAMME, NOT THE PUBLISHED CARD: 120% cap, and the C-code floor of
    12.99% rather than the card's 14.99%. That is what "based on our new LTVX" means. But it is a
    GATED rate — low-risk C-code cases only — so `gated` rides on the result and the verdict line
    says so. A heatmap implying every walk-in gets 12.99% would be the other flattering wrong
    answer, and it is the one an exec reader would most easily take away.

    Land-collateral operators are dropped outright: different collateral, not a weaker competitor.
    """
    x = (lv or {}).get("ltvx") or {}
    our_ltv = x.get("title_cap_pct")
    our_rate = x.get("title_best_rate_pct")
    us = next((o for o in ops if o.get("is_us")), None)
    our_tenor = (us or {}).get("tenor_max")
    if our_ltv is None or our_rate is None:
        return {}

    by_key = {}
    for r in (board_rows or []):
        by_key.setdefault(r.get("key"), []).append(r)

    def cmp_dim(ours, theirs, band, better):
        """-> dict(verdict, why, margin, narrow). `better` is 'hi'|'lo' for the BORROWER.

        `narrow` marks a decided cell that only just cleared the band — KBank's ไม่โอนเล่ม rate is
        13.5% against our 12.99%, a 0.51pp win one hundredth of a point outside a 0.5pp band.
        Painting that the same green as a 7.76pp win over Saksiam is the false precision this
        email has already had to correct once. The verdict stands; the render says it is thin.
        """
        if ours is None or theirs is None:
            return {"verdict": None, "why": "not published", "margin": None, "narrow": False}
        d = theirs - ours
        if abs(d) <= band:
            return {"verdict": "par", "why": None, "margin": abs(d), "narrow": False}
        theirs_wins = d > 0 if better == "hi" else d < 0
        return {"verdict": ("lose" if theirs_wins else "beat"), "why": None,
                "margin": abs(d), "narrow": abs(d) <= band * 1.5}

    def pick(rs, field):
        """The best figure this operator publishes for OUR product, and where it came from.

        Prefers a row explicitly tagged no_transfer. Falls back to an `unstated` row — the source
        did not say which variant — which is reported as `unstated` so a soft number never passes
        as a firm one. Never falls back to a `transfer` row: that is the wrong product, and
        silently borrowing it is exactly the Ngern Hai Jai 150-vs-140 error.
        """
        for tag in ("no_transfer", "unstated"):
            vals = [r[field] for r in rs
                    if (r.get("collateral") or "unstated") == tag and r.get(field) is not None]
            if vals:
                return max(vals), tag
        return None, None

    rows, dropped_land = [], []
    for o in ops:
        if o.get("is_us"):
            continue
        if (o.get("loan_type") or "") == "land":
            dropped_land.append(o)
            continue
        rs = by_key.get(o.get("key")) or []
        coll = o.get("collateral") or []
        has_nt = ("no_transfer" in coll) or any(
            (r.get("collateral") == "no_transfer") for r in rs)
        transfer_only = bool(coll) and not has_nt and "transfer" in coll
        cohort = "peer" if has_nt else ("transfer" if transfer_only else "unstated")

        nt = (o.get("by_collateral") or {}).get("no_transfer") or {}
        their_rate = nt.get("lo")
        their_ltv, ltv_src = pick(rs, "ltv_pct")
        their_tenor, tenor_src = pick(rs, "tenor_max")
        if their_tenor is None:                  # tenor rarely differs by variant
            their_tenor, tenor_src = o.get("tenor_max"), "headline"

        cells = {}
        cells["ltv"] = cmp_dim(our_ltv, their_ltv, BEAT_BAND_LTV, "hi")
        if their_rate is None and transfer_only:
            cells["rate"] = {"verdict": None, "why": "transfer-only product",
                             "margin": None, "narrow": False}
        else:
            cells["rate"] = cmp_dim(our_rate, their_rate, BEAT_BAND_RATE, "lo")
        cells["tenor"] = cmp_dim(our_tenor, their_tenor, BEAT_BAND_TENOR, "hi")

        wins = sum(1 for d in cells.values() if d["verdict"] == "beat")
        losses = sum(1 for d in cells.values() if d["verdict"] == "lose")
        pars = sum(1 for d in cells.values() if d["verdict"] == "par")
        scored = wins + losses + pars
        if not scored:
            verdict = "unknown"
        elif scored < 2:
            verdict = "thin"          # one dimension is a data point, not a standing
        elif wins > losses:
            verdict = "beat"
        elif wins < losses:
            verdict = "lose"
        else:
            verdict = "level"
        rows.append({
            "key": o.get("key"), "operator": o.get("operator"), "name_th": o.get("name_th"),
            "owner": o.get("owner"), "cohort": cohort, "loan_type": o.get("loan_type"),
            "confidence": o.get("confidence"), "citation": o.get("citation"),
            "their_ltv": their_ltv, "ltv_src": ltv_src,
            "their_rate": their_rate, "their_rate_hi": nt.get("hi"),
            "rate_src": nt.get("source"), "headline_rate": o.get("effective_lo"),
            "headline_ltv": o.get("ltv_pct"),
            "their_tenor": their_tenor, "tenor_src": tenor_src,
            "cells": cells,
            "wins": wins, "losses": losses, "pars": pars, "scored": scored,
            "narrow": sum(1 for d in cells.values() if d["narrow"]),
            "verdict": verdict,
        })

    # The two worked examples the email uses to show WHY the restatement matters are picked from
    # the data, not written down. They were hardcoded as "CIMB 5.4 -> 9.95" and "เงินให้ใจ 150 ->
    # 140" in the first cut, which states a live rival figure as a fact in an exec's inbox and goes
    # stale the first time either lender moves. Pick the widest headline-vs-restated gap on each
    # dimension: the biggest gap is also the most persuasive illustration.
    def widest(field_head, field_real):
        cands = [r for r in rows
                 if r[field_head] is not None and r[field_real] is not None
                 and abs(r[field_head] - r[field_real]) > 0.01]
        if not cands:
            return None
        r = max(cands, key=lambda r: abs(r[field_head] - r[field_real]))
        return {"key": r["key"], "operator": r["operator"], "name_th": r.get("name_th"),
                "headline": r[field_head], "restated": r[field_real]}

    examples = {"rate": widest("headline_rate", "their_rate"),
                "ltv": widest("headline_ltv", "their_ltv")}

    ORDER = {"beat": 0, "level": 1, "lose": 2, "thin": 3, "unknown": 4}
    rows.sort(key=lambda r: (ORDER[r["verdict"]], -r["wins"], r["losses"],
                             -(r["their_ltv"] or 0)))
    return {
        "ours": {"ltv": our_ltv, "rate": our_rate, "tenor": our_tenor,
                 "card_rate": (us or {}).get("effective_lo"),
                 "rate_at_cap": x.get("title_rate_at_cap"),
                 "standard_ltv": x.get("standard_cap_pct")},
        "rows": rows,
        "examples": examples,
        "dims": [("ltv", "LTV cap"), ("rate", "Rate %/yr"), ("tenor", "Tenor")],
        "bands": {"ltv": BEAT_BAND_LTV, "rate": BEAT_BAND_RATE, "tenor": BEAT_BAND_TENOR},
        "n_beat": sum(1 for r in rows if r["verdict"] == "beat"),
        "n_level": sum(1 for r in rows if r["verdict"] == "level"),
        "n_lose": sum(1 for r in rows if r["verdict"] == "lose"),
        "n_thin": sum(1 for r in rows if r["verdict"] in ("thin", "unknown")),
        # WHY we are behind, counted rather than narrated. The first draft of this section asserted
        # "the ones ahead are banks lending against a car at single digits", which is a tidy story
        # the rows do not support: อะมานะฮ์ is a leasing company we OUT-PRICE by 11pp and lose to
        # on ceiling and tenor, and เงินติดล้อ is a title lender at 160% LTV, not a cheap bank.
        # A losing verdict has three different causes and they need three different responses,
        # so the breakdown is computed and the sentence is built from it.
        "lose_why": {dim: sum(1 for r in rows if r["verdict"] == "lose"
                              and r["cells"][dim]["verdict"] == "lose")
                     for dim, _ in (("ltv", 0), ("rate", 0), ("tenor", 0))},
        "n_peer": sum(1 for r in rows if r["cohort"] == "peer"),
        "n_transfer": sum(1 for r in rows if r["cohort"] == "transfer"),
        "dropped_land": [o.get("operator") for o in dropped_land],
        # The SENTENCE, not `gAA&&gVeh&&occ&&age&&h12`. The raw expression is the record and stays
        # in policy_levers.json; an email that prints it has told the reader nothing.
        "gated": x.get("low_risk_gate_readable") or x.get("low_risk_gate"),
        "gated_expr": x.get("low_risk_gate"),
        "gated_note": "12.99% is the C-code floor on a low-risk case, not the walk-in rate.",
        "basis_confirmed": False,
    }


def _bm_examples(c, bm):
    """The plain-text twin of the HTML worked examples, off the same derived `examples` block —
    so the two halves cannot state different lenders or different figures."""
    ex = bm.get("examples") or {}
    out = []
    if ex.get("rate"):
        out.append("%s advertises %s%% but its own ไม่โอนเล่ม floor is %s%%"
                   % (th(c["names"], ex["rate"]["key"], ex["rate"].get("name_th")),
                      fmt(ex["rate"]["headline"]), fmt(ex["rate"]["restated"])))
    if ex.get("ltv"):
        out.append("%s's %s%% ceiling is %s%% without the book"
                   % (th(c["names"], ex["ltv"]["key"], ex["ltv"].get("name_th")),
                      fmt(ex["ltv"]["headline"]), fmt(ex["ltv"]["restated"])))
    return (" — " + "; ".join(out)) if out else ""


MIN_CROP_DEP = 0.10     # ≥10% of the largest province's crop area — see agri()


def agri(top_n=10, min_dep=MIN_CROP_DEP):
    """Crop prices and drought/rain for the provinces we have branches in AND that farm.

    "Top 10 provinces" is ranked by OUR BRANCH COUNT, not by stress score. A province with the
    worst crop prices in the country and three branches in it moves the book less than a province
    with eighty. Ranking by stress would produce a table that looks urgent and is not ours.

    BUT BRANCH COUNT ALONE IS THE WRONG GATE, and it produced a genuinely misleading first cut:
    our two densest province groups are กรุงเทพมหานคร (170 branches, crop dependence 0.016 — 83k
    rai) and สมุทรปราการ (40 branches, 0.003). Both are urban. Ranked on branches alone they led an
    AGRICULTURAL table, and สมุทรปราการ took the "driest province" headline on a rainfall anomaly
    over almost no farmland. Worse in the other direction: สมุทรสงคราม shows a −63% price move on
    35k rai, which is noise on a tiny base presented as the sharpest signal in the country.
    So a province must clear `min_dep` crop dependence to appear at all, and the branches sitting
    in provinces that fail the gate are counted and reported rather than silently dropped.

    The two numbers shown are the MEASURED ones — farm-gate price YoY and the drought index /
    24h rainfall. `agri_stress` is a composite and stays out of the headline; a composite in an
    email reads as authoritative in a way it has not earned.

    Any province in the national worst-N by price that is NOT in our top-N by branches is
    reported separately, so ranking by exposure cannot hide a move we are exposed to elsewhere.
    """
    br, cs = load("branches"), load("crop_stress")
    rain = (load("thaiwater_rain") or {}).get("provinces") or {}
    provs = cs.get("provinces") or []
    if not br or not provs:
        return {}

    counts = {}
    for b in br:
        p = b.get("v")
        if p:
            counts[p] = counts.get(p, 0) + 1
    by_th = {p.get("th"): p for p in provs if p.get("th")}

    def row(th, n):
        p = by_th.get(th) or {}
        r = rain.get(th) or {}
        mix = p.get("crop_mix") or []
        return {
            "th": th, "branches": n,
            "region": p.get("region"),
            "top_crop": (mix[0].get("crop") if mix else None),
            "top_share": (mix[0].get("share") if mix else None),
            "price_yoy": p.get("price_stress"),
            "drought": p.get("drought"),
            "rain_max_mm": r.get("max_mm"),
            "rain_heavy_pct": r.get("pct_heavy"),
            "crop_dependence": p.get("crop_dependence"),
        }

    def farms(th):
        return ((by_th.get(th) or {}).get("crop_dependence") or 0) >= min_dep

    eligible = [(th, n) for th, n in counts.items() if farms(th)]
    ranked = sorted(eligible, key=lambda kv: (-kv[1], kv[0]))[:top_n]
    rows = [row(th, n) for th, n in ranked]
    shown = set(r["th"] for r in rows)
    skipped = sorted(((th, n) for th, n in counts.items() if not farms(th)),
                     key=lambda kv: -kv[1])

    # Worst national price moves we are exposed to but which fall outside the top-N by branches.
    # Same crop-dependence gate — a big move on a tiny planted area is not a portfolio signal.
    # Only ACTUAL falls. Taking the three lowest regardless of sign listed สุพรรณบุรี at +5.07%
    # under a heading that said "falling elsewhere", which is a plain contradiction — in a month
    # where every province is up, the honest output here is an empty list.
    priced = [p for p in provs
              if p.get("price_stress") is not None and counts.get(p.get("th")) and farms(p["th"])
              and p["price_stress"] < 0]
    elsewhere = [row(p["th"], counts[p["th"]])
                 for p in sorted(priced, key=lambda x: x["price_stress"])[:3]
                 if p["th"] not in shown]

    with_price = [r for r in rows if r["price_yoy"] is not None]
    falling = [r for r in with_price if r["price_yoy"] < 0]
    return {
        "rows": rows,
        "elsewhere": elsewhere,
        "min_dep": min_dep,
        "n_skipped_prov": len(skipped),
        "n_skipped_branches": sum(n for _, n in skipped),
        "skipped_top": [th for th, _ in skipped[:3]],
        "n_falling": len(falling),
        "n_priced": len(with_price),
        "worst": min(with_price, key=lambda r: r["price_yoy"]) if with_price else None,
        "driest": max([r for r in rows if r["drought"] is not None],
                      key=lambda r: r["drought"], default=None),
        "wettest": max([r for r in rows if r["rain_max_mm"] is not None],
                       key=lambda r: r["rain_max_mm"], default=None),
        "rain_observed_to": ((load("thaiwater_rain") or {}).get("meta") or {}).get("observed_to"),
        "price_label": ((cs.get("meta") or {}).get("fields") or {}).get("price_stress"),
    }


def levers():
    """Our own collateral ceilings, or {} when the projection has not been generated.

    Degrades to an ABSENT state rather than guessing. An action asserted against a lever we
    cannot read would be an invented policy, which is worse than a shorter email.
    """
    if not os.path.exists(LEVERS):
        return {}
    try:
        with io.open(LEVERS, encoding="utf-8") as f:
            return json.load(f)
    except (ValueError, OSError):
        return {}


def actions(c, lv):
    """Turn the observations above into things we can actually DO.

    THE FEEDBACK THIS ANSWERS: the digest reported the field accurately and named nothing we
    could change. Every line was a fact about a rival. An action needs two halves — a rival
    movement AND one of our own levers — so this joins the rate board and the listening posts
    against `policy_levers.json` (our ระเบียบ ceilings, read from the underwriting workbook).

    RULES THIS FOLLOWS, all of them learned the hard way elsewhere in this repo:
      * Every action carries its own evidence, with the number, so none of them is an opinion.
      * Every action names the DECISION it needs. "Rivals are cheaper" is not an action;
        "match on this lane or accept the gap and compete on approval speed" is.
      * A comparison that depends on a rival's unconfirmed basis is flagged, never netted.
        Their advertised LTV is almost certainly quoted on a different base than ours, and the
        standing rule here is to ask the basis rather than infer it. So the LTV item asks a
        question and does NOT claim a gap.
      * Peer set = the title-loan cohort. Banks doing auto refinance at 5–7% are in the field
        but they are not our comparators, and ranking against them would read as a 5pp problem
        we have no intention of solving.
      * No wall clock. Ordering is by severity, which is derived from the data.
    """
    A = []
    ops = c["operators"]
    us = next((o for o in ops if o.get("is_us")), None)
    cohort = [o for o in ops
              if o.get("loan_type") == "title_loan" and o.get("effective_lo") is not None]
    N = c["names"]

    # OUR PRICE IS THE LTVX C-CODE FLOOR, NOT THE PUBLISHED CARD. The owner's instruction, verbatim:
    # "our new promo rate of 12.99% is what we are vying to win in the market for". So every place
    # this email states where we sit on price uses the go-to-market rate. The card figure the rate
    # board carries for us (its floor across ALL published operators) is not a second opinion about
    # our pricing — it is a different question — and quoting both put two different "our rate"
    # numbers in one email. Where the programme rate is unavailable the board figure is still the
    # honest fallback, so the email degrades to it rather than to silence.
    gtm = ((lv or {}).get("ltvx") or {}).get("title_best_rate_pct")
    our_rate = gtm if gtm is not None else (us or {}).get("effective_lo")

    def rate_of(o):
        """A cohort member's comparable floor — ours restated to what we actually go to market at."""
        return our_rate if o.get("is_us") else o.get("effective_lo")

    def nm(key, fallback=""):
        return th(N, key, fallback) or key

    # -- 1. A RIVAL SELLING BELOW ITS OWN PUBLISHED CARD, AND BELOW US -------------------------
    # The sharpest item there is: the undercut is measured against the rival's own disclosure, so
    # it cannot be argued away as a basis mismatch. Only raise it when it also beats our floor —
    # a rival undercutting itself but still dearer than us is their problem, not ours.
    for g in c["gap_hits"]:
        promo, card = g.get("cheapest_promo_effective"), g.get("card_floor")
        if promo is None or our_rate is None:
            continue
        if promo >= our_rate:
            continue
        A.append({
            "tag": "PRICE",
            "sev": 100 + (g.get("gap_pp") or 0),
            "head": "%s is selling at %s%% while its own card says %s%% — under our %s%%"
                    % (nm(g["key"], g.get("name_th")), fmt(promo), fmt(card), fmt(our_rate)),
            "evidence": "%d live quote%s in the pull; %s pp below its own published floor at its "
                        "own %s-month tenor. Read at the conservative reading — an unstated "
                        "monthly rate is scored as flat."
                        % (g.get("n_quotes") or 0, "" if (g.get("n_quotes") or 0) == 1 else "s",
                           fmt(g.get("gap_pp")), g.get("card_tenor_months")),
            "lever": "We go to market at %s%% on a low-risk C-code case. The ระเบียบ lanes all "
                     "carry 24%%/ปี as the regulated ceiling, so there is headroom below it to "
                     "price a named lane without a policy change."
                     % fmt(our_rate),
            "decision": "Match on a named lane, or hold price and compete on approval speed. "
                        "Either way it is a pricing call, not a monitoring one.",
        })

    # -- 2. WHERE OUR PRICE SITS IN THE COHORT WE ACTUALLY COMPETE WITH ------------------------
    if us and our_rate is not None and len(cohort) >= 4:
        # Ranked at the rate we SELL at, so the position moves when the programme moves. Ranking
        # our card against their promos would have compared two different things and put us
        # further down the field than we actually sit.
        srt = sorted(cohort, key=rate_of)
        rank = next((i + 1 for i, o in enumerate(srt) if o.get("is_us")), None)
        cheaper = [o for o in srt if not o.get("is_us") and o["effective_lo"] < our_rate]
        # LENDERS SITTING EXACTLY ON OUR RATE ARE COUNTED SEPARATELY. Without this the item read
        # "4 of 11 publish a floor below our 12.99%" and then "we are 6th of 11" — both true, and
        # together they look like an arithmetic error. The missing rung is KTC, level with us at
        # 12.99%, which is a competitively interesting fact in its own right rather than a rounding
        # artefact to paper over.
        level = [o for o in srt if not o.get("is_us") and abs(o["effective_lo"] - our_rate) < 0.005]
        if rank and cheaper:
            A.append({
                "tag": "PRICE",
                "sev": 60 + len(cheaper),
                "head": "%d of %d title lenders publish a floor below our %s%%"
                        % (len(cheaper), len(srt), fmt(our_rate)),
                "evidence": "We are %s of %d at %s%%%s. Below us: %s. Ranked inside the title-loan "
                            "cohort — the strip at the top of this email ranks us against every "
                            "operator including the banks, which is why that number is different."
                            % (_ord(rank), len(srt), fmt(our_rate),
                               (", level with %s" % ", ".join(nm(o["key"], o.get("name_th"))
                                                              for o in level)) if level else "",
                               ", ".join("%s %s%%" % (nm(o["key"], o.get("name_th")),
                                                     fmt(o["effective_lo"])) for o in cheaper[:5])),
                "lever": "The ระเบียบ ceiling is 24%%/ปี, so %s%% sits far below the regulated "
                         "limit — moving it is a programme decision, not a rate-cap one."
                         % fmt(our_rate),
                "decision": "Is mid-field the intended position at our go-to-market rate? If yes "
                            "this is settled and should stop being raised.",
            })

    # -- 3. TENOR — the lever that cuts the monthly payment without cutting the rate -----------
    if us and us.get("tenor_max"):
        longer = sorted([o for o in cohort
                         if (o.get("tenor_max") or 0) > us["tenor_max"] and not o.get("is_us")],
                        key=lambda o: -(o["tenor_max"] or 0))
        if longer:
            A.append({
                "tag": "TENOR",
                "sev": 50 + len(longer),
                "head": "We cap tenor at %d months; %d title lenders go longer, up to %d"
                        % (us["tenor_max"], len(longer), longer[0]["tenor_max"]),
                "evidence": ", ".join("%s %dmo" % (nm(o["key"], o.get("name_th")), o["tenor_max"])
                                      for o in longer[:5])
                            + ". A longer tenor lowers the instalment a borrower is quoted without "
                              "moving the rate, so it competes on the number they actually compare.",
                "lever": "Tenor is not one of the collateral ceilings in the workbook — the LTV "
                         "grid and eligibility gates say nothing about it. So this is a product "
                         "decision, not a ระเบียบ amendment.",
                "decision": "Confirm whether 60 months is a policy limit or just current practice. "
                            "If practice, it is the cheapest competitive move on this list.",
            })

    # -- 4. LTV — A QUESTION, NOT A FINDING ----------------------------------------------------
    # Nine rivals headline an LTV of 85–160%. Our grid tops out at 75%. That looks like a chasm
    # and almost certainly is not one: their percentage is very likely quoted on a different base.
    # Publishing "rivals lend 160%, we lend 75%" would be the single most misleading line this
    # email could carry, so it is framed as the basis question it actually is.
    st = c.get("ltv_standing") or {}
    if st:
        A.append({
            "tag": "LTV",
            "sev": 75,
            "head": "%s%% and %s%% LTV are what we are taking to market, and nothing we publish "
                    "says so" % (fmt(st["best_rate"]), fmt(st["ours"])),
            "evidence": "The LTVX booking mode reaches %s%% on a title case (vs %s%% on the plain "
                        "Redbook item), at %s%%. We are level with %s and ahead of %s. Still "
                        "ahead of us: %s."
                        % (fmt(st["ours"]), fmt(st["standard"]), fmt(st["rate_at_cap"]),
                           ", ".join(nm(o["key"], o.get("name_th")) for o in st["on_par"]) or "none",
                           ", ".join(nm(o["key"], o.get("name_th")) for o in st["better"]) or "none",
                           ", ".join("%s %s%%" % (nm(o["key"], o.get("name_th")), fmt(o["ltv_pct"]))
                                     for o in st["behind"]) or "none"),
            "lever": "Not a policy change — the cap already exists. v46 widened who qualifies by "
                     "moving the low-risk test from brand tier to vehicle type (%s), so %s%% at "
                     "up to %s%% is bookable on every PA/PU/VAN in the ratebook today."
                     % ("/".join(st["vtypes"]) or "PA/PU/VAN", fmt(st["best_rate"]),
                        fmt(st["standard"])),
            "decision": "Two calls. (1) Should the card say anything about LTV at all, given four "
                        "rivals headline 130–160%? (2) Confirm one rival's LTV basis in writing — "
                        "if theirs is not appraised value, this whole ranking changes.",
            "basis_warning": True,
        })

    # -- 5. THE FREE LEVER --------------------------------------------------------------------
    u = c.get("us") or {}
    if u.get("reply_rate_pct") is not None and u["reply_rate_pct"] < 5:
        top = (u.get("themes") or [{}])[0]
        A.append({
            "tag": "REPUTATION",
            "sev": 80,
            "head": "We answer %s%% of Play reviewers; the top complaint is a fixable app bug"
                    % fmt(u["reply_rate_pct"]),
            "evidence": "%s ratings at %s★. Loudest detractor theme: %s (%d mentions in the "
                        "sampled reviews)."
                        % ("{:,}".format(int(u.get("ratings") or 0)), fmt(u.get("score")),
                           top.get("label") or "—", top.get("n") or 0),
            "lever": "Nothing in the workbook governs this. It costs no policy change, no rate "
                     "and no LTV — it is the only item here with no trade-off.",
            "decision": "Assign the reply queue to someone this week, and route the app-crash "
                        "theme to whoever owns the app. Both are staffing calls.",
        })

    # -- 6. WHO WE CANNOT SEE AT ALL ----------------------------------------------------------
    if c["blind"]:
        A.append({
            "tag": "COVERAGE",
            "sev": 30 + len(c["blind"]),
            "head": "%d of %d operators show nothing in any source"
                    % (len(c["blind"]), c["n_universe"]),
            "evidence": ", ".join(c["blind"][:6])
                        + ". No rate card, no app, no forum volume, no channel — an absence in our "
                          "watching, not proof of an absence in the market.",
            "lever": "Not a policy lever: a pull gap. These are the competitors a lane decision "
                     "would be made blind to.",
            "decision": "Decide whether any of these matter enough to pull by hand. If none do, "
                        "say so once and they stop being listed as a gap.",
        })

    A.sort(key=lambda x: -x["sev"])
    for i, a in enumerate(A, 1):
        a["rank"] = i
    return A


def _ord(n):
    return "%d%s" % (n, "th" if 11 <= (n % 100) <= 13
                     else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th"))


def _top_lane(lv):
    """Name the collateral class our highest ceiling belongs to, so 75% is not a bare number."""
    rows = (lv or {}).get("ltv_ceilings") or []
    if not rows:
        return "collateral grid"
    top = max(rows, key=lambda r: r.get("ltv_pct") or 0)
    return "%s, %s tier" % (top.get("collateral") or "?", top.get("tier") or "?")


def subject(c):
    """Scannable in a phone notification — the movement, not the word 'digest'."""
    bits = []
    if c["promos_new"]:
        bits.append("%d new promo%s" % (len(c["promos_new"]),
                                        "" if len(c["promos_new"]) == 1 else "s"))
    if c["n_fresh_pricing"]:
        bits.append("%d new pricing ad%s" % (c["n_fresh_pricing"],
                                             "" if c["n_fresh_pricing"] == 1 else "s"))
    if c["ads_appeared"]:
        bits.append("%d brand%s pushing" % (len(c["ads_appeared"]),
                                            "" if len(c["ads_appeared"]) == 1 else "s"))
    if c["promos_gone"]:
        bits.append("%d promo%s pulled" % (len(c["promos_gone"]),
                                           "" if len(c["promos_gone"]) == 1 else "s"))
    return "Rival pulse %s — %s" % (c["asof"], ", ".join(bits) if bits else "no change")


def _subs_str(n):
    """Subscriber count, without rounding a real audience away.

    "%dk" turned 480 subscribers into "0k", which reads as no channel at all rather than a
    small one — and a small channel is a finding, not a blank.
    """
    if n >= 1e6:
        return "%.1fM" % (n / 1e6)
    if n >= 1e4:
        return "%dk" % round(n / 1e3)
    return "{:,}".format(int(n))


def rows_html(items, render):
    return "".join(render(i) for i in items) or (
        '<tr><td style="padding:6px 0;color:%s">Nothing new.</td></tr>' % DIM)


def html(c):
    """The email, built as a list of parts rather than one %-formatted page.

    The previous version formatted the whole document through a single `%` operation, which
    meant every literal `%` in CSS or in a lender's rate had to be doubled — and one missed
    escape took the whole render down with an unrelated-looking ValueError. Joining a list has
    no such failure mode, so a rate can be written as a rate.

    EMAIL, NOT A WEB PAGE. Everything here is deliberately old-fashioned: tables for layout,
    inline styles only, `bgcolor` alongside every CSS background, no flexbox, no grid, no web
    font, no external asset. Outlook renders through Word's HTML engine and silently drops the
    modern half of CSS; a design that needs any of it looks broken to the one reader who matters.
    The bar charts are nested table cells with a background colour for exactly this reason —
    they survive everywhere, including a client with images disabled.
    """
    N = c["names"]
    P = []                                          # the page, appended in order
    FONT = "-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Helvetica Neue',Arial,sans-serif"

    def sec(kicker, title, note=""):
        """A section head: heavy title over a full-bleed accent rule."""
        P.append(
            '<tr><td style="padding:30px 26px 0">'
            '<div style="font-family:%s;font-size:10px;font-weight:700;letter-spacing:1.6px;'
            'text-transform:uppercase;color:%s">%s</div>'
            '<div style="font-family:%s;font-size:21px;line-height:1.25;font-weight:800;'
            'letter-spacing:-.3px;color:%s;padding-top:5px">%s</div>'
            '</td></tr>'
            '<tr><td style="padding:11px 26px 0"><table width="100%%" cellpadding="0" '
            'cellspacing="0" border="0"><tr><td bgcolor="%s" height="3" style="height:3px;'
            'line-height:3px;font-size:1px;background:%s">&nbsp;</td></tr></table></td></tr>'
            % (FONT, ACC, esc(kicker), FONT, INK, esc(title), ACC, ACC))
        if note:
            P.append('<tr><td style="padding:11px 26px 0;font-family:%s;font-size:12px;'
                     'line-height:1.55;color:%s">%s</td></tr>' % (FONT, DIM, note))

    def block(body):
        P.append('<tr><td style="padding:6px 26px 0"><table width="100%%" cellpadding="0" '
                 'cellspacing="0" border="0" style="font-family:%s;font-size:14px;'
                 'line-height:1.5;color:%s">%s</table></td></tr>' % (FONT, FG, body))

    def empty(msg="Nothing new."):
        return ('<tr><td style="padding:14px 0;font-family:%s;font-size:13px;color:%s">%s'
                '</td></tr>' % (FONT, DIM, msg))

    def chip(txt, fg, bg):
        """A small pill. Rendered as an inline-block span with padding — the one modern-ish
        thing Outlook does honour, and it degrades to plain coloured text if it does not."""
        return ('<span style="display:inline-block;background:%s;color:%s;font-size:10px;'
                'font-weight:700;letter-spacing:.7px;text-transform:uppercase;padding:2px 7px;'
                'border-radius:3px;white-space:nowrap">%s</span>' % (bg, fg, esc(txt)))

    def bar(pct, color):
        """A horizontal bar made of two table cells. Works in every mail client there is."""
        pct = max(2, min(100, int(round(pct))))
        return ('<table width="100%%" cellpadding="0" cellspacing="0" border="0"><tr>'
                '<td width="%d%%" bgcolor="%s" style="width:%d%%;height:9px;line-height:9px;'
                'font-size:1px;background:%s;border-radius:2px">&nbsp;</td>'
                '<td bgcolor="%s" style="height:9px;line-height:9px;font-size:1px;background:%s">'
                '&nbsp;</td></tr></table>' % (pct, color, pct, color, WASH, WASH))

    # ---------------------------------------------------------------- MASTHEAD
    # The one dark surface in the email, and it is a header band rather than a reading ground:
    # the owner's instruction was that black BODY text on black is unreadable in an inbox, which
    # is right, and it is not an argument against a masthead carrying six words in 30px type.
    P.append(
        '<tr><td bgcolor="%s" style="background:%s;padding:26px 26px 24px">'
        '<div style="font-family:%s;font-size:10px;font-weight:700;letter-spacing:2.4px;'
        'text-transform:uppercase;color:%s">AutoX · เงินไชโย · Competitive intelligence</div>'
        '<div style="font-family:%s;font-size:34px;line-height:1.05;font-weight:800;'
        'letter-spacing:-1.1px;color:#FFFFFF;padding-top:10px">Rival pulse</div>'
        '<div style="font-family:%s;font-size:14px;font-weight:600;color:%s;padding-top:7px">'
        '%s</div>'
        '<div style="font-family:%s;font-size:11px;line-height:1.5;color:%s;padding-top:12px">'
        'Every date below is stamped by the source data, never by when this was sent.</div>'
        '</td></tr>'
        % (INK, INK, FONT, ACCLT, FONT, FONT, ACCLT, esc(c["asof"]), FONT, MUTED))

    # ---------------------------------------------------------------- THE NUMBERS
    # Four figures that answer "do I need to read this" before the reader scrolls at all.
    ours = next((o for o in c["operators"]
                 if o.get("key") == "AUTOX" or (o.get("name_th") or "").startswith("เงินไชโย")), None)
    # "both" belongs on this ladder and excluding it flatters us badly. A lender marked `both`
    # runs a ไม่โอนเล่ม product AND a โอนเล่ม one — CIMB, KKP, กรุงศรี, ttb, เงินให้ใจ, เงินติดล้อ
    # and เฮงลิสซิ่ง are all in that group, and every one of them competes for the same borrower
    # who wants to keep the book. Filtering to `title_loan` alone dropped seven rivals, six of
    # them CHEAPER than us, and moved AutoX from 13th of 18 to 6th of 11. Only `hp_refinance`
    # (โอนเล่ม-only) and `land` are genuinely a different product and stay out.
    ladder = [o for o in c["operators"]
              if o.get("loan_type") in ("title_loan", "both") and o.get("effective_lo") is not None]

    # OUR RUNG IS THE GO-TO-MARKET RATE. Every rival's `effective_lo` is the CHEAPEST rate that
    # lender publishes — its best offer, promos included. Our equivalent best offer is the LTVX
    # C-code floor, not the card floor, so plotting the card here compared their promo against our
    # ceiling and put us several rungs below where we actually compete. Substituted once, at the
    # source, so the sort, the KPI rank, the bar lengths and the printed figure all agree.
    def lad_rate(o):
        return c["gtm_rate"] if (o is ours and c.get("gtm_rate")) else o["effective_lo"]

    ladder.sort(key=lad_rate)
    rank = next((i + 1 for i, o in enumerate(ladder) if o is ours), None)

    stats = [
        ("%d" % (c["gap_meta"].get("n_checked") or 0), "operators<br>rate-checked", ACC),
        ("%d" % len(c["gap_hits"]), "selling BELOW<br>their own card", PD),
        ("%d" % (c["n_fresh_pricing"] or 0), "new pricing<br>ads", MERCH),
        (("#%d" % rank) if rank else "—", "our price rank<br>of %d rivals" % len(ladder), GOLD),
    ]
    cells = "".join(
        '<td width="25%%" align="center" valign="top" style="padding:0 4px">'
        '<div style="font-family:%s;font-size:32px;line-height:1;font-weight:800;'
        'letter-spacing:-1.2px;color:%s">%s</div>'
        '<div style="font-family:%s;font-size:10px;line-height:1.35;font-weight:700;'
        'letter-spacing:.8px;text-transform:uppercase;color:%s;padding-top:8px">%s</div></td>'
        % (FONT, col, big, FONT, DIM, lab) for big, lab, col in stats)
    P.append('<tr><td bgcolor="%s" style="background:%s;padding:22px 22px 20px;'
             'border-bottom:1px solid %s">'
             '<table width="100%%" cellpadding="0" cellspacing="0" border="0"><tr>%s</tr></table>'
             '</td></tr>' % (WASH, WASH, LINE, cells))

    # ---------------------------------------------------------------- FACEBOOK PROMOS
    def _fbrate(r):
        """A promo rate, printed as written plus every reading it could bear.

        Never one converted number: a post saying "0.60% ต่อเดือน" almost never says whether
        that is flat or reducing, and the two readings are ~2x apart. Publishing a single
        figure would be inventing the basis the lender declined to state.
        """
        q = "%s%%%s" % (fmt(r.get("quoted_pct")),
                        "/เดือน" if r.get("quoted_unit") == "pct_per_month" else "/ปี")
        lo, hi = r.get("effective_if_reducing"), r.get("effective_if_flat")
        if r.get("basis"):
            return chip("%s %s = %s%%/ปี eff" % (q, r["basis"],
                                                 fmt(hi if r["basis"] == "flat" else lo)),
                        "#FFFFFF", MERCH)
        if lo is None and hi is None:
            return chip(q, "#FFFFFF", MERCH)
        return (chip(q, "#FFFFFF", MERCH) + ' <span style="font-family:%s;font-size:11px;'
                'color:%s">ไม่ระบุฐาน basis unstated → %s–%s%%/ปี effective</span>'
                % (FONT, DIM, fmt(lo), fmt(hi)))

    fb = "".join(
        '<tr><td style="padding:15px 0;border-bottom:1px solid %s">'
        '<div style="font-family:%s;font-size:16px;font-weight:800;color:%s;'
        'letter-spacing:-.2px">%s <span style="font-size:11px;font-weight:600;color:%s;'
        'letter-spacing:0">%s ที่แล้ว</span> %s</div>'
        '%s'
        '<div style="font-family:%s;font-size:13px;line-height:1.6;color:%s;padding-top:8px">'
        '%s%s</div></td></tr>'
        % (LINE, FONT, INK, esc(th(N, p.get("key"), p.get("name_th"))), DIM,
           esc(p.get("posted_ago") or "?"),
           chip("ใหม่", "#FFFFFF", GOLD) if p.get("changed_since_last_run") else "",
           ('<div style="padding-top:9px">%s</div>'
            % " ".join(_fbrate(r) for r in p["rates"])) if p.get("rates") else "",
           FONT, FG, esc(" ".join((p.get("post") or "").split())),
           # WE never truncate — the owner asked for full copy. Facebook itself cuts every post
           # at "ดูเพิ่มเติม" before its login wall, and an unexplained "..." reads as our doing.
           (' <span style="font-size:10px;color:%s;white-space:nowrap">[Facebook cut it here]'
            '</span>' % DIM) if p.get("post_truncated") else "")
        for p in c["fb_promos"])
    # ------------------------------------------------------------ WHAT TO DO (goes first)
    # Owner feedback, 2026-08-17: the digest reported the field and named nothing to do about it.
    # So the decisions come BEFORE the evidence, and every other section below is now the
    # supporting detail for one of these rather than the point of the email.
    if c.get("actions"):
        sec("What to do", "สิ่งที่ต้องตัดสินใจ · Decisions this pull asks for",
            "Each item pairs a measured rival movement with one of OUR levers, and names the call "
            "it needs. Nothing here is a monitoring note. Ordered by how much is at stake.")
        for a in c["actions"]:
            warn = (' <span style="font-size:10px;color:%s">— rests on an unconfirmed rival basis'
                    '</span>' % ACC) if a.get("basis_warning") else ""
            block(
                '<tr><td style="padding:15px 0 4px">'
                '<table cellpadding="0" cellspacing="0" border="0"><tr>'
                '<td valign="top" style="padding-right:9px">%s</td>'
                '<td valign="top" style="font-family:%s;font-size:15px;font-weight:700;'
                'line-height:1.35;color:%s">%s%s</td></tr></table></td></tr>'
                '<tr><td style="padding:7px 0 0 0;font-family:%s;font-size:13px;line-height:1.55;'
                'color:%s">%s</td></tr>'
                '<tr><td style="padding:7px 0 0 0;font-family:%s;font-size:12.5px;line-height:1.55;'
                'color:%s"><b style="color:%s">Our lever ·</b> %s</td></tr>'
                '<tr><td style="padding:8px 0 13px"><table width="100%%" cellpadding="0" '
                'cellspacing="0" border="0" bgcolor="%s" style="background:%s;border-radius:4px">'
                '<tr><td style="padding:9px 11px;font-family:%s;font-size:12.5px;line-height:1.5;'
                'color:%s"><b>Decide ·</b> %s</td></tr></table></td></tr>'
                % (chip("%d · %s" % (a["rank"], a["tag"]), "#FFFFFF", ACC),
                   FONT, INK, esc(a["head"]), warn,
                   FONT, FG, esc(a["evidence"]),
                   FONT, DIM, INK, esc(a["lever"]),
                   WASH, WASH, FONT, INK, esc(a["decision"])))

    # ------------------------------------------------------------ LTVX STANDING
    st = c.get("ltv_standing") or {}
    if st:
        sec("Where LTVX puts us", "เทียบเพดาน LTV กับคู่แข่ง · Our LTV ceiling against the field",
            "LTVX is a BOOKING MODE, not a rate promotion: the plain Redbook item locks Mobius at "
            "%s%%, and the LTVX twin — legal only on a C-code — opens the cap to %s%%. Compared "
            "against every rival that publishes an LTV, banded at &plusmn;%s pp because two "
            "lenders %s pp apart are the same offer to a borrower."
            % (fmt(st["standard"]), fmt(st["ours"]), fmt(st["band_pp"]), fmt(st["band_pp"])))
        verdict = ('<tr><td style="padding:14px 0 0;font-family:%s;font-size:15px;'
                   'line-height:1.45;color:%s"><b>On par with %d, ahead of %d, behind %d.</b> '
                   'We go to market at <b>%s%%</b> up to a %s%% ceiling, and %s%% where the case '
                   'runs to the %s%% cap.</td></tr>'
                   % (FONT, INK, len(st["on_par"]), len(st["better"]), len(st["behind"]),
                      fmt(st["best_rate"]), fmt(st["standard"]), fmt(st["rate_at_cap"]),
                      fmt(st["ours"])))
        def grp(label, items, color):
            if not items:
                return ('<tr><td style="padding:9px 0 0;font-family:%s;font-size:13px;color:%s">'
                        '<b style="color:%s">%s</b> — none</td></tr>' % (FONT, DIM, color, label))
            return ('<tr><td style="padding:9px 0 0;font-family:%s;font-size:13px;line-height:1.6;'
                    'color:%s"><b style="color:%s">%s</b> &nbsp;%s</td></tr>'
                    % (FONT, FG, color, label,
                       " · ".join("%s <b>%s%%</b>" % (esc(th(N, o["key"], o.get("name_th"))),
                                                     fmt(o["ltv_pct"])) for o in items)))
        block(verdict
              + grp("Ahead of us", st["behind"], ACC)
              + grp("On par with us", st["on_par"], INK)
              + grp("We are ahead of", st["better"], "#1C8C7D")
              + ('<tr><td style="padding:13px 0 4px;font-family:%s;font-size:11.5px;line-height:1.55;'
                 'color:%s">v46 (Aug 2026) widened who qualifies: the low-risk test moved from '
                 'brand tier to vehicle type, so every %s in the ratebook is eligible instead of '
                 'four MAJOR brands. Gate: NCB AA + eligible vehicle + salaried occupation + '
                 'borrower 31&ndash;60 + &ge;12 months history.<br><br><b>Read this comparison with '
                 'the caveat:</b> our %% is of appraised value under ระเบียบ ver 9.0. A rival&rsquo;s '
                 'advertised %% may be quoted on a different base, and none has been confirmed in '
                 'writing &mdash; so treat the ranking as the best available read, not as settled. '
                 'The LTVX table itself is read from %s, not from the policy workbook.</td></tr>'
                 % (FONT, DIM, "/".join(st["vtypes"]) or "PA/PU/VAN", esc(st["source"] or "the Selector"))))

    # ------------------------------------------------- WHO WE CAN BEAT (HEATMAP)
    # A real heatmap in an email means coloured <td>s and nothing else — no CSS grid, no SVG, no
    # background-image. Every cell therefore carries bgcolor AND an inline background, and the
    # fills are light washes with dark text rather than saturated blocks with white text, because
    # a client that strips backgrounds must still leave readable text behind.
    bm = c.get("beat_matrix") or {}
    if bm.get("rows"):
        o = bm["ours"]
        FILL = {"beat": ("#DCEEEA", "#0C4A41"), "par": ("#FBF0D8", "#6B4E05"),
                "lose": ("#FBE1DF", "#8A2B25"), None: ("#F4F5F7", "#8B93A1")}
        CHIP = {"beat": (MERCH, "#FFFFFF"), "level": (GOLD, "#FFFFFF"),
                "lose": (PD, "#FFFFFF"), "thin": (WASH, DIM), "unknown": (WASH, DIM)}
        WORD = {"beat": "We win", "level": "Level", "lose": "They win",
                "thin": "Too thin", "unknown": "No data"}

        ex = bm.get("examples") or {}
        shown = []
        if ex.get("rate"):
            shown.append("%s advertises %s%% but its own ไม่โอนเล่ม floor is %s%%"
                         % (esc(th(N, ex["rate"]["key"], ex["rate"].get("name_th"))),
                            fmt(ex["rate"]["headline"]), fmt(ex["rate"]["restated"])))
        if ex.get("ltv"):
            shown.append("%s&rsquo;s %s%% ceiling is %s%% once the book stays with the borrower"
                         % (esc(th(N, ex["ltv"]["key"], ex["ltv"].get("name_th"))),
                            fmt(ex["ltv"]["headline"]), fmt(ex["ltv"]["restated"])))
        sec("Who we can beat now", "เราชนะใครได้บ้าง · The LTVX board, rival by rival",
            "Our LTVX case (%s%% LTV at a %s%% C-code floor) against every rival, on THEIR "
            "ไม่โอนเล่ม numbers &mdash; the product we actually sell. Headline figures are the "
            "โอนเล่ม ones and are not used%s. Green = we win that column."
            % (fmt(o["ltv"]), fmt(o["rate"]),
               (": " + ", and ".join(shown)) if shown else ""))

        hdr = ('<tr>'
               '<td style="padding:0 0 7px;font-family:%s;font-size:10px;font-weight:700;'
               'letter-spacing:1px;text-transform:uppercase;color:%s">Lender</td>' % (FONT, DIM))
        for _, lab in bm["dims"]:
            hdr += ('<td align="center" style="padding:0 0 7px 6px;font-family:%s;font-size:10px;'
                    'font-weight:700;letter-spacing:1px;text-transform:uppercase;color:%s">%s'
                    '</td>' % (FONT, DIM, esc(lab)))
        hdr += ('<td align="right" style="padding:0 0 7px 8px;font-family:%s;font-size:10px;'
                'font-weight:700;letter-spacing:1px;text-transform:uppercase;color:%s">Verdict'
                '</td></tr>' % (FONT, DIM))

        def cellhtml(r, dim):
            d = r["cells"][dim]
            bg, fgc = FILL.get(d["verdict"], FILL[None])
            if dim == "ltv":
                val = ("%s%%" % fmt(r["their_ltv"])) if r["their_ltv"] is not None else "&mdash;"
            elif dim == "rate":
                val = ("%s%%" % fmt(r["their_rate"])) if r["their_rate"] is not None else "&mdash;"
            else:
                val = ("%s mo" % fmt(r["their_tenor"])) if r["their_tenor"] is not None else "&mdash;"
            sub = ""
            if d["verdict"] is None and d["why"]:
                sub = ('<div style="font-size:9px;line-height:1.25;padding-top:2px">%s</div>'
                       % esc(d["why"]))
            elif d["narrow"]:
                sub = ('<div style="font-size:9px;line-height:1.25;padding-top:2px">by %s only'
                       '</div>' % fmt(d["margin"]))
            elif dim == "ltv" and r["ltv_src"] == "unstated":
                sub = ('<div style="font-size:9px;line-height:1.25;padding-top:2px">variant '
                       'unstated</div>')
            return ('<td align="center" bgcolor="%s" style="background:%s;color:%s;padding:8px 4px;'
                    'font-family:%s;font-size:13px;font-weight:700;border:2px solid #FFFFFF">%s%s'
                    '</td>' % (bg, bg, fgc, FONT, val, sub))

        body = ""
        for r in bm["rows"]:
            cbg, cfg = CHIP[r["verdict"]]
            body += ('<tr><td style="padding:8px 8px 8px 0;font-family:%s;font-size:13px;'
                     'color:%s;line-height:1.3">%s</td>'
                     % (FONT, INK, esc(th(N, r["key"], r.get("name_th")))))
            body += "".join(cellhtml(r, dim) for dim, _ in bm["dims"])
            body += ('<td align="right" style="padding:8px 0 8px 8px">%s</td></tr>'
                     % chip(WORD[r["verdict"]], cfg, cbg))

        lw = bm["lose_why"]
        why = " and ".join(x for x in [
            ", ".join(y for y in [
                "%d out-price us" % lw["rate"] if lw["rate"] else "",
                "%d beat our ceiling" % lw["ltv"] if lw["ltv"] else ""] if y),
            "%d lend for longer" % lw["tenor"] if lw["tenor"] else ""] if x)
        verdict = ('<tr><td colspan="5" style="padding:14px 0 10px;font-family:%s;font-size:15px;'
                   'line-height:1.45;color:%s"><b>LTVX wins us %d of %d, level with %d, still '
                   'behind %d.</b> The %d we beat are the classic title-loan field &mdash; %s. '
                   'Of the %d ahead, %s &mdash; three different problems, not one.</td></tr>'
                   % (FONT, INK, bm["n_beat"], len(bm["rows"]), bm["n_level"], bm["n_lose"],
                      bm["n_beat"],
                      ", ".join(esc(th(N, r["key"], r.get("name_th")))
                                for r in bm["rows"] if r["verdict"] == "beat"),
                      bm["n_lose"], why or "no single dimension dominates"))

        legend = ('<tr><td colspan="5" style="padding:12px 0 0;font-family:%s;font-size:11.5px;'
                  'line-height:1.6;color:%s">%s &nbsp;%s &nbsp;%s &nbsp;%s<br><br>'
                  '<b style="color:%s">Who qualifies for %s%%.</b> It is the C-code rate on a '
                  'LOW-RISK case &mdash; %s &mdash; and it holds to a %s%% ceiling; a case running '
                  'to the %s%% cap books at %s%%. '
                  'Rate is each lender&rsquo;s own ไม่โอนเล่ม floor restated to nominal '
                  'reducing-balance; LTV and tenor come from that lender&rsquo;s ไม่โอนเล่ม '
                  'variant, never the headline. Bands: &plusmn;%s pp LTV, &plusmn;%s pp rate, '
                  '&plusmn;%s months. %s excluded &mdash; land collateral, not a weaker '
                  'competitor. LTV basis is still unconfirmed in writing on every rival.</td></tr>'
                  % (FONT, DIM,
                     chip("we win", "#0C4A41", "#DCEEEA"), chip("level", "#6B4E05", "#FBF0D8"),
                     chip("they win", "#8A2B25", "#FBE1DF"), chip("not published", DIM, WASH),
                     INK, fmt(o["rate"]), esc(bm.get("gated") or "the low-risk gate"),
                     fmt(o["standard_ltv"]), fmt(o["ltv"]), fmt(o["rate_at_cap"]),
                     fmt(bm["bands"]["ltv"]), fmt(bm["bands"]["rate"]),
                     fmt(bm["bands"]["tenor"]),
                     esc(", ".join(bm["dropped_land"]) or "Nothing")))

        block(verdict + hdr + body + legend)

    # ------------------------------------------------------------ AGRI WATCH
    g = c.get("agri") or {}
    if g.get("rows"):
        sec("Crops and water", "ราคาพืชผลและภัยแล้ง · Crop prices and drought where we lend",
            "Our %d biggest provinces BY BRANCH COUNT that actually farm — a province must hold "
            "&ge;%d%% of the largest province&rsquo;s planted area to appear, which keeps "
            "กรุงเทพมหานคร and สมุทรปราการ out of an agricultural table. Price is farm-gate "
            "year-on-year; dryness is 3-month rainfall against normal (1.00 = driest); rain is the "
            "live 24-hour peak, observed to %s."
            % (len(g["rows"]), int(g["min_dep"] * 100), esc(g.get("rain_observed_to") or "—")))
        head = ("Prices are UP in all %d" % g["n_priced"]) if not g["n_falling"] else (
            "%d of %d have prices falling" % (g["n_falling"], g["n_priced"]))
        rows = "".join(
            '<tr><td style="padding:7px 0;border-bottom:1px solid %s;font-family:%s;font-size:13px;'
            'color:%s">%s <span style="color:%s;font-size:11px">%d br · %s</span></td>'
            '<td align="right" style="padding:7px 0;border-bottom:1px solid %s;font-family:%s;'
            'font-size:13px;font-weight:700;color:%s;white-space:nowrap">%s%s%%</td>'
            '<td align="right" style="padding:7px 0 7px 14px;border-bottom:1px solid %s;'
            'font-family:%s;font-size:12px;color:%s;white-space:nowrap">%s</td></tr>'
            % (WASH, FONT, INK, esc(r["th"]), DIM, r["branches"], esc(str(r["top_crop"] or "—")),
               WASH, FONT, ("#1C8C7D" if (r["price_yoy"] or 0) >= 0 else ACC),
               "+" if (r["price_yoy"] or 0) >= 0 else "", fmt(r["price_yoy"]),
               WASH, FONT, (ACC if (r["drought"] or 0) >= 0.7 else DIM),
               ("dry %s" % fmt(r["drought"])) if (r["drought"] or 0) >= 0.7
               else ("%smm/24h" % fmt(r["rain_max_mm"]) if r["rain_max_mm"] else "—"))
            for r in g["rows"])
        note = ""
        if g["elsewhere"]:
            note += ('<tr><td colspan="3" style="padding:12px 0 0;font-family:%s;font-size:12px;'
                     'line-height:1.55;color:%s"><b style="color:%s">Falling elsewhere in our '
                     'footprint:</b> %s.</td></tr>'
                     % (FONT, DIM, INK,
                        ", ".join("%s %s%% (%d br)" % (esc(r["th"]), fmt(r["price_yoy"]),
                                                       r["branches"]) for r in g["elsewhere"])))
        if g["n_skipped_branches"]:
            note += ('<tr><td colspan="3" style="padding:9px 0 4px;font-family:%s;font-size:11.5px;'
                     'line-height:1.5;color:%s">%d branches in %d provinces are excluded as '
                     'non-farming (largest: %s). Excluded, not missing.</td></tr>'
                     % (FONT, DIM, g["n_skipped_branches"], g["n_skipped_prov"],
                        esc(", ".join(g["skipped_top"]))))
        # Name the two DRIEST provinces, not driest + densest. Those were the same province
        # (ชลบุรี), so the verdict read "ชลบุรี at 0.82, ชลบุรี at 0.82".
        dry = sorted([r for r in g["rows"] if (r["drought"] or 0) >= 0.5],
                     key=lambda r: -(r["drought"] or 0))[:2]
        block('<tr><td colspan="3" style="padding:14px 0 6px;font-family:%s;font-size:15px;'
              'line-height:1.45;color:%s"><b>%s.</b> %s</td></tr>%s%s'
              % (FONT, INK, head,
                 ("The watch item is dryness, not price: " +
                  ", ".join("%s at %s" % (esc(r["th"]), fmt(r["drought"])) for r in dry) + ".")
                 if dry else "No province in the table is running dry either.",
                 rows, note))

    sec("What they are selling today", "โปรโมชันล่าสุดบนเฟซบุ๊ก · Live promos on Facebook",
        "%d of %d rival pages read, newest post first. This is what they are SELLING; the rate "
        "board below is what they are PERMITTED to charge — KTC posted 0.60%%/month while its "
        "own card said 12.99–24%%/yr. The two are never averaged. A monthly rate quoted with no "
        "basis gets both readings, not a guess."
        % ((c["fb_meta"].get("n_pages") or 0) - (c["fb_meta"].get("n_silent") or 0),
           (c["fb_meta"].get("n_pages") or 0)))
    block(fb or empty("No rival posted today."))

    # ---------------------------------------------------------------- UNDERCUT CARDS
    def _how(q):
        """The channel and the conversion, in words a reader has not had to learn.

        These fields are machine keys — `google_ads`, `as_quoted_per_year`, `flat_at_60m` — and
        printing them raw makes a careful method look like a debug dump. The conversion actually
        applied is the single most challengeable step on this card, so it is the last thing that
        should read as jargon.
        """
        chan = {"google_ads": "Google Ads", "facebook": "Facebook"}.get(
            q.get("channel"), (q.get("channel") or "—").replace("_", " "))
        how = q.get("read_as") or ""
        if how == "as_quoted_per_year":
            how = "quoted per year, converted by nobody"
        elif how.startswith("flat_at_"):
            how = "read as flat over %s months" % how[8:].rstrip("m")
        return "%s · %s" % (chan, how or "—")

    # The sharpest finding in the email, so it gets the loudest treatment: a red rail, a tinted
    # card and the gap set larger than anything else on the page.
    gaps = "".join(
        '<tr><td style="padding-bottom:10px">'
        '<table width="100%%" cellpadding="0" cellspacing="0" border="0" bgcolor="%s" '
        'style="background:%s;border-radius:5px"><tr>'
        '<td width="5" bgcolor="%s" style="width:5px;background:%s;border-radius:5px 0 0 5px">'
        '&nbsp;</td>'
        '<td style="padding:14px 16px">'
        '<div style="font-family:%s;font-size:16px;font-weight:800;color:%s">%s</div>'
        '<div style="font-family:%s;padding-top:9px">'
        '<span style="font-size:30px;font-weight:800;letter-spacing:-1px;color:%s">%s</span>'
        '<span style="font-size:12px;font-weight:700;color:%s"> จุดถูกกว่าการ์ดตัวเอง · '
        'points below their own card</span></div>'
        '<div style="font-family:%s;font-size:12px;color:%s;padding-top:7px">'
        'การ์ด <b style="color:%s">%s%%/ปี</b> &nbsp;→&nbsp; ขายจริง '
        '<b style="color:%s">%s%%/ปี</b></div>'
        '<div style="font-family:%s;font-size:12px;line-height:1.55;color:%s;padding-top:9px;'
        'font-style:italic">“%s”</div>'
        '<div style="font-family:%s;font-size:10px;color:%s;padding-top:6px;'
        'letter-spacing:.5px;text-transform:uppercase">Seen on %s</div>'
        '</td></tr></table></td></tr>'
        % (PDWASH, PDWASH, PD, PD, FONT, INK,
           esc(th(N, r.get("key"), r.get("name_th"))),
           FONT, PD, fmt(r.get("gap_pp")), DIM,
           FONT, DIM, FG, fmt(r.get("card_floor")), PD, fmt(r.get("cheapest_promo_effective")),
           FONT, FG, esc(" ".join(((r.get("quotes") or [{}])[0].get("context_th") or "").split())),
           FONT, DIM, esc(_how((r.get("quotes") or [{}])[0])))
        for r in c["gap_hits"])
    sec("The card is not the price", "ขายถูกกว่าการ์ดตัวเอง · Selling below their own card",
        "A published rate card is a CEILING, not a price. Deliberately conservative: a monthly "
        "rate quoted with no basis is read as FLAT — the dearer reading — at the lender's own "
        "maximum tenor, and only counts if even that lands %s points or more below the card. "
        "Only %d of %d operators advertise with a rate at all, so an absent name means we hold "
        "no promo QUOTE for them — never that their card was verified as their price."
        % (fmt(c["gap_meta"].get("material_threshold_pp")),
           c["gap_meta"].get("n_checked") or 0, c["n_universe"]))
    block(gaps or empty("Nobody is currently advertising below their own published card."))

    # ---------------------------------------------------------------- RATE LADDER
    # Bars, because a 16-row column of numbers is a table nobody reads on a phone. Scaled to the
    # dearest lender on the board so the bar lengths mean something rather than filling the row.
    top = max([lad_rate(o) for o in ladder] or [1])
    rows = []
    for o in ladder:
        us = o is ours
        rows.append(
            '<tr><td style="padding:9px 0 0"><table width="100%%" cellpadding="0" '
            'cellspacing="0" border="0"><tr>'
            '<td style="font-family:%s;font-size:13px;font-weight:%s;color:%s;'
            'padding-bottom:5px">%s%s</td>'
            '<td align="right" style="font-family:%s;font-size:15px;font-weight:800;'
            'color:%s;padding-bottom:5px;white-space:nowrap">%s%%%s</td>'
            '</tr><tr><td colspan="2">%s</td></tr></table></td></tr>'
            % (FONT, "800" if us else "600", INK if us else FG,
               esc(o.get("name_th") or th(N, o.get("key"), o.get("operator"))),
               (" " + chip("เรา · LTVX", "#FFFFFF", GOLD)) if us else "",
               FONT, GOLD if us else INK, fmt(lad_rate(o)),
               (' <span style="font-size:10px;font-weight:600;color:%s">LTV %s%%</span>'
                % (DIM, o["ltv_pct"])) if o.get("ltv_pct") is not None else "",
               bar(100.0 * lad_rate(o) / top, GOLD if us else (
                   MERCH if o.get("effective_source") in ("lender", "as_quoted") else ACC))))
    sec("Where we sit", "ตารางอัตราดอกเบี้ย · The ไม่โอนเล่ม ladder",
        "Effective %/yr on a reducing balance — the only basis on which these are comparable. "
        "Borrower keeps the book (ไม่โอนเล่ม), cheapest first. Every rung is that lender's "
        "CHEAPEST published rate, so ours is the LTVX C-code floor — best offer against best "
        "offer. Green = the lender's own published effective figure; blue = converted by us from "
        "their flat quote; gold = us. "
        "Includes every lender that runs a ไม่โอนเล่ม product, whether or not it also does "
        "โอนเล่ม — a bank that offers both still competes for the same borrower. Pure "
        "hire-purchase refinance and land-title lending are genuinely different products and "
        "are left off.")
    block("".join(rows) or empty("No comparable rate on the board."))

    # ---------------------------------------------------------------- NEW PRICING ADS
    pricing = "".join(
        '<tr><td style="padding:14px 0;border-bottom:1px solid %s">'
        '<div style="font-family:%s;font-size:15px;font-weight:800;color:%s">%s '
        '<span style="font-size:11px;font-weight:600;color:%s">first shown %s</span> %s</div>'
        '<div style="font-family:%s;font-size:13px;line-height:1.6;color:%s;padding-top:7px">'
        '%s</div></td></tr>'
        % (LINE, FONT, INK, esc(th(N, a.get("key"), a.get("brand"))), DIM, esc(a.get("first")),
           chip(a["basis_kind"], "#FFFFFF", MERCH) if a.get("basis_kind") else "",
           FONT, FG, esc(" ".join((a.get("copy") or "").split())))
        for a in c["fresh_pricing"])
    sec("New creatives that compete on cost", "โฆษณาราคาใหม่ · New pricing ads",
        "%d this cycle. Copy is shown IN FULL — the tail is where the tenor, the LTV cap and the "
        "flat-or-reducing fine print live, which is exactly what a truncation removes."
        % c["n_fresh_pricing"])
    block(pricing or empty())

    # ---------------------------------------------------------------- PROMO MOVEMENT
    promo = "".join(
        '<tr><td style="padding:10px 0;border-bottom:1px solid %s">'
        '<b style="font-family:%s;font-size:14px;color:%s">%s</b> %s'
        '<div style="font-family:%s;font-size:13px;color:%s;padding-top:4px">%s</div></td></tr>'
        % (LINE, FONT, INK, esc(th(N, p.get("key"), p.get("brand"))),
           chip(p.get("kind") or "promo", DIM, WASH), FONT, FG, esc(p.get("title") or ""))
        for p in c["promos_new"])
    sec("Straight from their own sites", "โปรโมชันใหม่ของคู่แข่ง · New rival promotions",
        "Only listed once a dated first_seen proves it is genuinely new.")
    block(promo or empty())

    gone = "".join(
        '<tr><td style="padding:10px 0;border-bottom:1px solid %s;font-family:%s;font-size:13px;'
        'color:%s"><b style="color:%s">%s</b> — %s '
        '<span style="font-size:11px">(last seen %s)</span></td></tr>'
        % (LINE, FONT, DIM, FG, esc(th(N, p.get("key"), p.get("brand"))),
           esc(p.get("title") or ""), esc(p.get("last_seen")))
        for p in c["promos_gone"])
    sec("Pulled", "โปรโมชันที่ถูกถอด · No longer listed",
        "Never inferred — each carries the last date it was MEASURABLY still up.")
    block(gone or empty())

    # ---------------------------------------------------------------- SENTIMENT
    def num(v, suffix=""):
        return ('<b style="color:%s">%s%s</b>' % (INK, esc(v), suffix)) if v is not None else (
            '<span style="color:#B6BCC6">—</span>')

    def subs(r):
        if r["subs"] is None:
            return '<span style="color:#B6BCC6">—</span>'
        # A parent corporate channel is not the product's own audience — say so rather than
        # letting KrungsriAutoTV's 521k read as Car4Cash's following.
        return '<b style="color:%s">%s</b>%s' % (
            INK, esc(_subs_str(r["subs"])),
            '<span style="font-size:10px;color:%s"> กลุ่ม</span>' % DIM if r["subs_parent"] else "")

    head = ('<tr>%s</tr>' % "".join(
        '<td%s style="font-family:%s;font-size:9px;font-weight:700;letter-spacing:.9px;'
        'text-transform:uppercase;color:%s;padding:0 0 7px%s">%s</td>'
        % (al, FONT, DIM, pad, lab)
        for al, pad, lab in ((""," ","แบรนด์"), (' align="right"'," ","Play"),
                             (' align="right"'," 0 7px 12px","App&nbsp;Store"),
                             (' align="right"'," 0 7px 12px","Pantip"),
                             (' align="right"'," 0 7px 12px","YouTube"))))
    sent = head + "".join(
        '<tr><td style="font-family:%s;font-size:13px;font-weight:%s;color:%s;padding:7px 0;'
        'border-bottom:1px solid %s">%s%s</td>'
        '<td align="right" style="font-family:%s;font-size:13px;padding:7px 0;'
        'border-bottom:1px solid %s">%s</td>'
        '<td align="right" style="font-family:%s;font-size:13px;padding:7px 0 7px 12px;'
        'border-bottom:1px solid %s">%s</td>'
        '<td align="right" style="font-family:%s;font-size:13px;padding:7px 0 7px 12px;'
        'border-bottom:1px solid %s">%s</td>'
        '<td align="right" style="font-family:%s;font-size:13px;padding:7px 0 7px 12px;'
        'border-bottom:1px solid %s">%s</td></tr>'
        % (FONT, "800" if r["is_us"] else "600", INK if r["is_us"] else FG, LINE,
           esc(r["name"]), (" " + chip("เรา", "#FFFFFF", GOLD)) if r["is_us"] else "",
           FONT, LINE, num(r["play"], "★"), FONT, LINE, num(r["apple"], "★"),
           FONT, LINE, num("{:,}".format(r["pantip"]) if r["pantip"] is not None else None),
           FONT, LINE, subs(r))
        for r in c["sentiment_board"])
    sec("Who the market is talking about", "เสียงจากตลาด · Sentiment and share of voice",
        "Play and App Store are MEASURED star averages; YouTube is a MEASURED subscriber count "
        "(กลุ่ม = a parent corporate channel, not the product's own audience); Pantip is an "
        "ESTIMATED thread count and leans high for every brand — the RANKING is the finding, "
        "not the multiple. Ordered by Pantip volume. A dash means the brand is ABSENT from that "
        "source, not silent on it — เงินให้ใจ ships no app, so it cannot appear in the two star "
        "columns at all.")
    block(sent)

    # ---------------------------------------------------------------- FOOTER
    P.append(
        '<tr><td bgcolor="%s" style="background:%s;padding:20px 26px;border-top:1px solid %s">'
        '<div style="font-family:%s;font-size:11px;line-height:1.6;color:%s">'
        '<b style="color:%s">%s of %s</b> tracked creatives state whether their rate is flat or '
        'reducing balance. That is why an advertised headline is not comparable as printed, and '
        'it is what the effective column fixes.</div></td></tr>'
        % (WASH, WASH, LINE, FONT, DIM, INK, c["basis_stated"], c["basis_scanned"]))

    return ('<!doctype html><html><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<meta name="color-scheme" content="light only">'
            '<meta name="supported-color-schemes" content="light only">'
            '<title>Rival pulse</title></head>'
            '<body style="margin:0;padding:0;background:%s;-webkit-text-size-adjust:100%%">'
            '<table width="100%%" cellpadding="0" cellspacing="0" border="0" bgcolor="%s" '
            'style="background:%s;padding:22px 0"><tr><td align="center">'
            '<table width="660" cellpadding="0" cellspacing="0" border="0" bgcolor="%s" '
            'style="max-width:660px;width:100%%;background:%s;border:1px solid %s;'
            'border-radius:10px;overflow:hidden">%s</table>'
            '</td></tr></table></body></html>'
            % (WASH, WASH, WASH, CARD, CARD, LINE, "".join(P)))


def text(c):
    L = ["RIVAL PULSE — %s" % c["asof"], "=" * 52, ""]

    # The text half carries the SAME three new sections, in the same order. A reader on a client
    # that strips HTML must not get a different email — that is the whole reason collect() returns
    # data rather than markup.
    if c.get("actions"):
        L += ["WHAT TO DO — decisions this pull asks for", "-" * 52]
        for a in c["actions"]:
            L += ["%d. [%s] %s%s" % (a["rank"], a["tag"], a["head"],
                                     "  (rests on an unconfirmed rival basis)"
                                     if a.get("basis_warning") else ""),
                  "     evidence: %s" % a["evidence"],
                  "     our lever: %s" % a["lever"],
                  "     DECIDE:    %s" % a["decision"], ""]

    st = c.get("ltv_standing") or {}
    if st:
        def _n(o):
            return "%s %s%%" % (th(c["names"], o["key"], o.get("name_th")), fmt(o["ltv_pct"]))
        L += ["WHERE LTVX PUTS US", "-" * 52,
              "LTVX is a booking mode: the plain Redbook item locks Mobius at %s%%, the LTVX twin "
              "(C-code only) opens it to %s%%." % (fmt(st["standard"]), fmt(st["ours"])),
              "On par with %d, ahead of %d, behind %d. We go to market at %s%% up to a %s%% "
              "ceiling, and %s%% where the case runs to the %s%% cap."
              % (len(st["on_par"]), len(st["better"]), len(st["behind"]), fmt(st["best_rate"]),
                 fmt(st["standard"]), fmt(st["rate_at_cap"]), fmt(st["ours"])),
              "  ahead of us : %s" % (", ".join(_n(o) for o in st["behind"]) or "none"),
              "  on par      : %s" % (", ".join(_n(o) for o in st["on_par"]) or "none"),
              "  we lead     : %s" % (", ".join(_n(o) for o in st["better"]) or "none"),
              "Caveat: our %% is of appraised value (ระเบียบ ver 9.0); a rival's %% may be on a "
              "different base and none is confirmed in writing. LTVX table read from %s, not the "
              "policy workbook." % (st.get("source") or "the Selector"), ""]

    bm = c.get("beat_matrix") or {}
    if bm.get("rows"):
        o = bm["ours"]
        MARK = {"beat": "win", "par": "=", "lose": "LOSE", None: "·"}
        WORD = {"beat": "WE WIN", "level": "level", "lose": "they win",
                "thin": "too thin", "unknown": "no data"}
        lw = bm["lose_why"]
        L += ["WHO WE CAN BEAT NOW — LTVX vs each rival's ไม่โอนเล่ม numbers", "-" * 52,
              "LTVX wins us %d of %d, level with %d, behind %d. Of the %d ahead, %d out-price us, "
              "%d beat our ceiling, %d lend for longer — three different problems."
              % (bm["n_beat"], len(bm["rows"]), bm["n_level"], bm["n_lose"], bm["n_lose"],
                 lw["rate"], lw["ltv"], lw["tenor"]),
              "Their HEADLINE numbers are the โอนเล่ม product and are not used%s. Ours: %s%% LTV "
              "at a %s%% C-code floor, %s months."
              % (_bm_examples(c, bm), fmt(o["ltv"]), fmt(o["rate"]), fmt(o["tenor"])),
              "",
              "  %-30s %-11s %-11s %-11s %s"
              % ("LENDER", "LTV", "RATE", "TENOR", "VERDICT")]
        for r in bm["rows"]:
            def cell(dim, val, unit):
                d = r["cells"][dim]
                if val is None:
                    return "%-4s n/a" % MARK[d["verdict"]]
                return "%-4s %s%s%s" % (MARK[d["verdict"]], fmt(val), unit,
                                        "*" if d["narrow"] else "")
            # Thai names are wider than the Latin column width suggests; truncate with an ellipsis
            # so a cut name reads as cut rather than as a different lender.
            nm = th(c["names"], r["key"], r.get("name_th"))
            nm = nm if len(nm) <= 30 else nm[:29] + "…"
            L += ["  %-30s %-11s %-11s %-11s %s"
                  % (nm, cell("ltv", r["their_ltv"], "%"),
                     cell("rate", r["their_rate"], "%"),
                     cell("tenor", r["their_tenor"], "mo"), WORD[r["verdict"]])]
        L += ["  * decided by less than 1.5x the band — treat as level in practice.",
              "WHO QUALIFIES for %s%%: the C-code rate on a low-risk case (%s), holding to a %s%% "
              "ceiling. A case running to the %s%% cap books at %s%%."
              % (fmt(o["rate"]), bm.get("gated") or "the low-risk gate", fmt(o["standard_ltv"]),
                 fmt(o["ltv"]), fmt(o["rate_at_cap"])),
              "Bands: ±%s pp LTV, ±%s pp rate, ±%s months. Excluded: %s (land collateral). "
              "Rival LTV basis is unconfirmed in writing."
              % (fmt(bm["bands"]["ltv"]), fmt(bm["bands"]["rate"]), fmt(bm["bands"]["tenor"]),
                 ", ".join(bm["dropped_land"]) or "nothing"), ""]

    g = c.get("agri") or {}
    if g.get("rows"):
        dry = sorted([r for r in g["rows"] if (r["drought"] or 0) >= 0.5],
                     key=lambda r: -(r["drought"] or 0))[:2]
        L += ["CROPS AND WATER — our biggest farming provinces by branch count", "-" * 52,
              (("Prices are UP in all %d." % g["n_priced"]) if not g["n_falling"]
               else ("%d of %d have prices falling." % (g["n_falling"], g["n_priced"])))
              + ((" Watch dryness, not price: "
                  + ", ".join("%s %s" % (r["th"], fmt(r["drought"])) for r in dry) + ".")
                 if dry else "")]
        for r in g["rows"]:
            L.append("  %-16s %3d br  %-9s  price %6s%%  dry %-5s  rain %smm/24h"
                     % (r["th"], r["branches"], r["top_crop"] or "—",
                        ("+" if (r["price_yoy"] or 0) >= 0 else "") + str(fmt(r["price_yoy"])),
                        fmt(r["drought"]), fmt(r["rain_max_mm"])))
        if g["elsewhere"]:
            L.append("  falling elsewhere: %s"
                     % ", ".join("%s %s%% (%d br)" % (r["th"], fmt(r["price_yoy"]), r["branches"])
                                 for r in g["elsewhere"]))
        if g["n_skipped_branches"]:
            L.append("  excluded as non-farming: %d branches in %d provinces (%s)"
                     % (g["n_skipped_branches"], g["n_skipped_prov"], ", ".join(g["skipped_top"])))
        L.append("")

    if c["headline"]:
        L += [c["headline"], ""]
    if c["comparable"].get("lo") is not None:
        L.append("Against our own collateral (borrower keeps the book) the field charges "
                 "%s%%-%s%% a year effective." % (c["comparable"]["lo"], c["comparable"]["hi"]))
        if c["cheapest_flat"]:
            cf = c["cheapest_flat"]
            L.append("Lowest headline anywhere: %s%% flat (%s) = %s%% effective — โอนเล่ม money, "
                     "a different product." % (cf["quoted"], cf["operator"], cf["effective"]))
        L.append("")
    N = c["names"]

    def blk(title, items, fmt):
        L.append(title.upper())
        L.extend(["  " + fmt(i) for i in items] or ["  (nothing new)"])
        L.append("")
    def _fbline(p):
        r = ""
        if p.get("rates"):
            x = p["rates"][0]
            r = "  [%s%%%s%s]" % (
                fmt(x.get("quoted_pct")),
                "/mo" if x.get("quoted_unit") == "pct_per_month" else "/yr",
                "" if x.get("basis") else " basis unstated → %s-%s%%/yr eff" % (
                    fmt(x.get("effective_if_reducing")), fmt(x.get("effective_if_flat"))))
        return "%s (%s ago)%s — %s" % (th(N, p.get("key"), p.get("name_th")),
                                       p.get("posted_ago") or "?", r,
                                       " ".join((p.get("post") or "").split()))
    blk("Live promos on Facebook — what they are SELLING", c["fb_promos"], _fbline)
    blk("Selling below their own published card", c["gap_hits"],
        lambda r: "%s — card %s%%/yr, actually selling %s%%/yr (%s points cheaper): %s"
                  % (th(N, r.get("key"), r.get("name_th")), fmt(r.get("card_floor")),
                     fmt(r.get("cheapest_promo_effective")), fmt(r.get("gap_pp")),
                     " ".join(((r.get("quotes") or [{}])[0].get("context_th") or "").split())))
    blk("New rival promotions", c["promos_new"],
        lambda p: "%s — %s" % (th(N, p.get("key"), p.get("brand")), p.get("title") or ""))
    blk("New pricing ads (%d)" % c["n_fresh_pricing"], c["fresh_pricing"],
        lambda a: "%s (%s)%s — %s" % (th(N, a.get("key"), a.get("brand")), a.get("first"),
                                      " [%s]" % a["basis_kind"] if a.get("basis_kind") else "",
                                      " ".join((a.get("copy") or "").split())))
    blk("Promotions no longer listed", c["promos_gone"],
        lambda p: "%s — %s (last seen %s)" % (th(N, p.get("key"), p.get("brand")),
                                              p.get("title") or "", p.get("last_seen")))
    L.append("RATE BOARD (effective %/yr, reducing balance — each lender's CHEAPEST published rate)")

    # Ours is the LTVX go-to-market floor, exactly as on the HTML ladder. Left as the card figure
    # here, the plain-text half would have quietly contradicted the HTML half of the same email —
    # and the text half is what a phone client with images off actually shows.
    def _brate(o):
        return c["gtm_rate"] if (o.get("is_us") and c.get("gtm_rate")) else o["effective_lo"]

    # SORTED BY THE FIGURE SHOWN. This list was ordered by the raw card rate, so once ours moved to
    # 12.99% we printed 12.99% two rows BELOW 14.45% — a board that contradicts its own sort order.
    board = sorted([o for o in c["operators"] if o.get("effective_lo") is not None], key=_brate)
    for o in board:
        rate = _brate(o)
        L.append("  %-30s %7s  %s%s" % (
            (o.get("name_th") or th(N, o.get("key"), o.get("operator")))[:30],
            "%s%%" % fmt(rate),
            ("LTV %s%%" % o["ltv_pct"]) if o.get("ltv_pct") is not None else "",
            "  (us, LTVX)" if o.get("is_us") else ""))
    L.append("")
    L.append("SENTIMENT AND SHARE OF VOICE")
    L.append("  %-26s %6s %6s %9s %9s" % ("brand", "Play", "Apple", "Pantip", "YouTube"))
    for r in c["sentiment_board"]:
        subs = "-" if r["subs"] is None else _subs_str(r["subs"])
        L.append("  %-26s %6s %6s %9s %9s%s" % (
            (r["name"] or "")[:26],
            r["play"] if r["play"] is not None else "-",
            r["apple"] if r["apple"] is not None else "-",
            "{:,}".format(r["pantip"]) if r["pantip"] is not None else "-",
            subs, "  (us)" if r["is_us"] else ""))
    L.append("  Play/Apple = measured stars; YouTube = measured subscribers; Pantip = ESTIMATED")
    L.append("  threads, high for everyone — the ranking is the finding, not the multiple.")
    L.append("  A dash = absent from that source, not silent on it.")
    L += ["", "%s of %s creatives state their rate basis." % (c["basis_stated"], c["basis_scanned"])]
    return "\n".join(L)


def _env(name, default=None):
    """An UNSET GitHub Actions secret arrives as the empty string, not as an absent key, so
    os.environ.get(name, default) hands back "" and the default never fires. Every optional
    setting here has to treat blank as absent or the job dies on a secret nobody set on
    purpose — SMTP_PORT="" crashed the first real send with
    ValueError: invalid literal for int() with base 10: ''."""
    v = os.environ.get(name)
    return v.strip() if v and v.strip() else default


def send(subj, body_html, body_text):
    """SMTP via stdlib only — no third-party action, no vendor SDK in the send path."""
    host, port = _env("SMTP_HOST"), int(_env("SMTP_PORT", "587"))
    user, pw = _env("SMTP_USER"), _env("SMTP_PASS")
    to = _env("MAIL_TO")
    if not (host and user and pw and to):
        missing = [n for n, v in (("SMTP_HOST", host), ("SMTP_USER", user),
                                  ("SMTP_PASS", pw), ("MAIL_TO", to)) if not v]
        print("SKIP: no mail credentials (%s unset) — digest rendered, not sent"
              % ", ".join(missing))
        return 3
    m = EmailMessage()
    m["Subject"] = subj
    m["From"] = formataddr((_env("MAIL_FROM_NAME", "AutoX Rival Pulse"),
                            _env("MAIL_FROM", user)))
    m["To"] = to
    m.set_content(body_text)
    m.add_alternative(body_html, subtype="html")
    with smtplib.SMTP(host, port, timeout=60) as s:
        s.starttls()
        s.login(user, pw)
        s.send_message(m)
    print("sent to %s — %s" % (to, subj))
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", help="write the HTML here")
    ap.add_argument("--send", action="store_true", help="email it (needs SMTP_* + MAIL_TO)")
    ap.add_argument("--stdout", action="store_true", help="print the plain-text version")
    ap.add_argument("--subject-only", action="store_true")
    a = ap.parse_args()

    c = collect()
    subj = subject(c)
    if a.subject_only:
        print(subj)
        return 0
    h, t = html(c), text(c)
    if a.out:
        with io.open(a.out, "w", encoding="utf-8", newline="\n") as f:
            f.write(h)
        print("wrote %s" % a.out)
    if a.stdout:
        print(t)
    if not a.out and not a.stdout and not a.send:
        print(t)
    print("SUBJECT: %s" % subj)
    return send(subj, h, t) if a.send else 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    sys.exit(main())
