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

    return {
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
    ladder.sort(key=lambda o: o["effective_lo"])
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
    top = max([o["effective_lo"] for o in ladder] or [1])
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
               (" " + chip("เรา", "#FFFFFF", GOLD)) if us else "",
               FONT, GOLD if us else INK, fmt(o["effective_lo"]),
               (' <span style="font-size:10px;font-weight:600;color:%s">LTV %s%%</span>'
                % (DIM, o["ltv_pct"])) if o.get("ltv_pct") is not None else "",
               bar(100.0 * o["effective_lo"] / top, GOLD if us else (
                   MERCH if o.get("effective_source") in ("lender", "as_quoted") else ACC))))
    sec("Where we sit", "ตารางอัตราดอกเบี้ย · The ไม่โอนเล่ม ladder",
        "Effective %/yr on a reducing balance — the only basis on which these are comparable. "
        "Borrower keeps the book (ไม่โอนเล่ม), cheapest first. Green = the lender's own "
        "published effective figure; blue = converted by us from their flat quote; gold = us. "
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
    L.append("RATE BOARD (effective %/yr, reducing balance)")
    for o in [o for o in c["operators"] if o.get("effective_lo") is not None]:
        L.append("  %-30s %7s  %s" % (
            (o.get("name_th") or th(N, o.get("key"), o.get("operator")))[:30],
            ("%s%%" % o["effective_lo"]) if o.get("effective_lo") is not None else "-",
            ("LTV %s%%" % o["ltv_pct"]) if o.get("ltv_pct") is not None else ""))
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
