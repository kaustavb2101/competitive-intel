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
BG, CARD, FG, DIM = "#F4F5F7", "#FFFFFF", "#1B1F27", "#5C6572"
LINE = "#E3E6EB"
ACC, GOLD, MERCH, PD = "#3B5BD9", "#8A6206", "#12695C", "#A6332C"


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

    return {
        "asof": asof,
        "names": names,
        "fb_promos": fb_promos,
        "fb_meta": fb.get("meta") or {},
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
    def sec(title, body, note=""):
        return ('<tr><td style="padding:18px 22px 4px">'
                '<div style="font:600 13px/1.3 -apple-system,Segoe UI,Roboto,sans-serif;'
                'color:%s;letter-spacing:.3px;text-transform:uppercase">%s</div>'
                '%s</td></tr><tr><td style="padding:0 22px 6px">'
                '<table width="100%%" cellpadding="0" cellspacing="0" style="font:14px/1.5 '
                '-apple-system,Segoe UI,Roboto,sans-serif;color:%s">%s</table></td></tr>'
                % (ACC, esc(title),
                   ('<div style="font:12px/1.45 -apple-system,sans-serif;color:%s;margin-top:3px">%s</div>'
                    % (DIM, note)) if note else "", FG, body))

    N = c["names"]
    BD = "border-bottom:1px solid " + LINE

    def _fbrate(r):
        """A promo rate, printed the way it was written plus every reading it could bear.

        Never one converted number: a post saying "0.60% ต่อเดือน" almost never says whether
        that is flat or reducing, and the two readings are ~2x apart. Publishing a single
        figure would be inventing the basis the lender declined to state.
        """
        q = "%s%%%s" % (fmt(r.get("quoted_pct")),
                        "/เดือน" if r.get("quoted_unit") == "pct_per_month" else "/ปี")
        lo, hi = r.get("effective_if_reducing"), r.get("effective_if_flat")
        if r.get("basis"):
            return "%s %s = %s%%/ปี effective" % (
                q, esc(r["basis"]), fmt(hi if r["basis"] == "flat" else lo))
        if lo is None and hi is None:
            return q
        return ("%s <span style=\"color:%s\">· ไม่ระบุฐาน basis unstated → %s–%s%%/ปี effective"
                "</span>" % (q, DIM, fmt(lo), fmt(hi)))

    fbpromo = rows_html(c["fb_promos"], lambda p: (
        '<tr><td style="padding:9px 0;%s">'
        '<b>%s</b> <span style="color:%s;font-size:11px">%s ที่แล้ว</span>%s<br>'
        '<span style="color:%s;font-size:13px;line-height:1.55">%s</span>%s</td></tr>'
        % (BD, esc(th(N, p.get("key"), p.get("name_th"))), DIM, esc(p.get("posted_ago") or "?"),
           (' <span style="color:%s;font-size:11px">· ใหม่</span>' % GOLD)
           if p.get("changed_since_last_run") else "",
           FG, esc(" ".join((p.get("post") or "").split())),
           ('<div style="margin-top:4px;font-size:12px;color:%s">%s</div>'
            % (MERCH, " · ".join(_fbrate(r) for r in p["rates"]))) if p.get("rates") else "")))

    promo = rows_html(c["promos_new"], lambda p: (
        '<tr><td style="padding:7px 0;%s">'
        '<b>%s</b> <span style="color:%s">%s</span><br>'
        '<span style="color:%s;font-size:13px">%s</span></td></tr>'
        % (BD, esc(th(N, p.get("key"), p.get("brand"))), DIM, esc(p.get("kind") or ""),
           FG, esc(p.get("title") or ""))))          # full title, no truncation

    gone = rows_html(c["promos_gone"], lambda p: (
        '<tr><td style="padding:7px 0;%s;color:%s">'
        '<b style="color:%s">%s</b> — %s <span style="font-size:11px">(last seen %s)</span>'
        '</td></tr>' % (BD, DIM, FG, esc(th(N, p.get("key"), p.get("brand"))),
                        esc(p.get("title") or ""), esc(p.get("last_seen")))))

    # FULL ad copy, on the owner's instruction. A pricing creative truncated at 190 characters
    # loses exactly the tail that matters — the tenor, the LTV cap and the fine print saying
    # whether the rate is flat or reducing balance.
    pricing = rows_html(c["fresh_pricing"], lambda a: (
        '<tr><td style="padding:9px 0;%s">'
        '<b>%s</b> <span style="color:%s;font-size:11px">first shown %s</span>%s<br>'
        '<span style="color:%s;font-size:13px;line-height:1.55">%s</span></td></tr>'
        % (BD, esc(th(N, a.get("key"), a.get("brand"))), DIM, esc(a.get("first")),
           (' <span style="color:%s;font-size:11px">· %s</span>'
            % (GOLD, esc(a["basis_kind"]))) if a.get("basis_kind") else "",
           FG, esc(" ".join((a.get("copy") or "").split())))))

    board = rows_html(c["operators"][:10], lambda o: (
        '<tr><td style="padding:5px 0;%s">%s'
        '<div style="color:%s;font-size:11px">%s</div></td>'
        '<td align="right" style="padding:5px 0;%s;white-space:nowrap">'
        '<b style="color:%s">%s</b></td>'
        '<td align="right" style="padding:5px 0 5px 14px;%s;color:%s;white-space:nowrap">%s</td>'
        '</tr>'
        % (BD, esc(o.get("name_th") or th(N, o.get("key"), o.get("operator"))), DIM,
           esc({"title_loan": "ไม่โอนเล่ม", "hp_refinance": "โอนเล่ม",
                "both": "ทั้งสองแบบ"}.get(o.get("loan_type"), "")),
           BD, MERCH if o.get("effective_source") in ("lender", "as_quoted") else GOLD,
           ("%s%%" % o["effective_lo"]) if o.get("effective_lo") is not None else "—",
           BD, DIM, ("LTV %s%%" % o["ltv_pct"]) if o.get("ltv_pct") is not None else "")))

    def num(v, suffix=""):
        return ('<b>%s%s</b>' % (esc(v), suffix)) if v is not None else (
            '<span style="color:#B6BCC6">—</span>')

    def subs(r):
        if r["subs"] is None:
            return '<span style="color:#B6BCC6">—</span>'
        s = _subs_str(r["subs"])
        # A parent corporate channel is not the product's own audience — say so rather than
        # letting KrungsriAutoTV's 521k read as Car4Cash's following.
        return '<b>%s</b>%s' % (esc(s), '<span style="color:%s;font-size:10px"> กลุ่ม</span>'
                                % DIM if r["subs_parent"] else "")

    sentiment = rows_html(c["sentiment_board"], lambda r: (
        '<tr><td style="padding:6px 0;%s">%s%s</td>'
        '<td align="right" style="padding:6px 0;%s">%s</td>'
        '<td align="right" style="padding:6px 0 6px 12px;%s">%s</td>'
        '<td align="right" style="padding:6px 0 6px 12px;%s">%s</td>'
        '<td align="right" style="padding:6px 0 6px 12px;%s">%s</td></tr>'
        % (BD, esc(r["name"]),
           ' <span style="color:%s;font-size:11px">เรา</span>' % GOLD if r["is_us"] else "",
           BD, num(r["play"], "★"), BD, num(r["apple"], "★"),
           BD, num("{:,}".format(r["pantip"]) if r["pantip"] is not None else None),
           BD, subs(r))))

    sent_head = ('<tr><td style="padding:0 0 5px;color:%s;font-size:11px">แบรนด์</td>'
                 '<td align="right" style="padding:0 0 5px;color:%s;font-size:11px">Play</td>'
                 '<td align="right" style="padding:0 0 5px 12px;color:%s;font-size:11px">'
                 'App&nbsp;Store</td>'
                 '<td align="right" style="padding:0 0 5px 12px;color:%s;font-size:11px">'
                 'Pantip</td>'
                 '<td align="right" style="padding:0 0 5px 12px;color:%s;font-size:11px">'
                 'YouTube</td></tr>' % (DIM, DIM, DIM, DIM, DIM))
    sentiment = sent_head + sentiment

    lead = ""
    if c["comparable"].get("lo") is not None:
        lead = ("Against our own collateral — borrower keeps the book — the field charges "
                "<b>%s%% to %s%%</b> a year effective." % (c["comparable"]["lo"],
                                                           c["comparable"]["hi"]))
        cf = c["cheapest_flat"]
        if cf:
            lead += (" The lowest headline anywhere is <b>%s%% flat</b> (%s), which is "
                     "<b>%s%% effective</b> — and it is โอนเล่ม money, a different product."
                     % (cf["quoted"], esc(cf["operator"]), cf["effective"]))

    return """<!doctype html><html><body style="margin:0;background:%s">
<table width="100%%" cellpadding="0" cellspacing="0" style="background:%s;padding:20px 0">
<tr><td align="center">
<table width="640" cellpadding="0" cellspacing="0" style="max-width:640px;background:%s;
 border:1px solid %s;border-radius:10px;overflow:hidden">
<tr><td style="padding:20px 22px 6px">
  <div style="font:700 19px/1.25 -apple-system,Segoe UI,Roboto,sans-serif;color:%s">
    Rival pulse — %s</div>
  <div style="font:12px/1.5 -apple-system,sans-serif;color:%s;margin-top:5px">
    AutoX / เงินไชโย competitive intelligence · every date below is stamped by the source data,
    never by when this email was sent.</div>
  %s
</td></tr>
%s%s%s%s%s%s
<tr><td style="padding:14px 22px 20px;border-top:1px solid %s">
  <div style="font:11px/1.55 -apple-system,sans-serif;color:%s">
   %s of %s tracked creatives state whether their rate is flat or reducing balance, so an
   advertised headline is not comparable as printed — that is what the effective column fixes.</div>
</td></tr>
</table></td></tr></table></body></html>""" % (
        BG, BG, CARD, LINE, FG, esc(c["asof"]), DIM,
        ('<div style="font:14px/1.55 -apple-system,sans-serif;color:%s;margin-top:12px;'
         'padding:11px 13px;background:#F0F4FF;border-left:3px solid %s;border-radius:4px">%s</div>'
         % (FG, MERCH, lead)) if lead else "",
        sec("โปรโมชันล่าสุดบนเฟซบุ๊ก · Live promos on Facebook", fbpromo,
            "%d of %d rival pages read today, newest post first. This is what they are "
            "SELLING; the rate board below is what they are permitted to charge — KTC posted "
            "0.60%%/month while its own card says 12.99–24%%/yr. The two are never averaged. "
            "A monthly rate quoted with no basis gets both readings, not a guess."
            # Pages are counted by SECTION, not by a "has a post" flag: a page that posted
            # nothing is the `silent` section, so pages read = universe minus silent.
            % ((c["fb_meta"].get("n_pages") or 0) - (c["fb_meta"].get("n_silent") or 0),
               (c["fb_meta"].get("n_pages") or 0))),
        sec("โปรโมชันใหม่ของคู่แข่ง · New rival promotions", promo,
            "From the rivals' own sites. Only listed once a dated first_seen proves it is new."),
        sec("โฆษณาราคาใหม่ · New pricing ads", pricing,
            "Creatives that compete on cost, newest first — %d in total this cycle. Copy is "
            "shown in full: the tail carries the tenor, the LTV cap and the flat-or-reducing "
            "fine print." % c["n_fresh_pricing"]),
        sec("ตารางอัตราดอกเบี้ย · Rate board", board,
            "Effective %/yr, reducing balance. Green = the lender's own published figure, "
            "gold = converted by us from their flat quote."),
        sec("โปรโมชันที่ถูกถอด · Promotions no longer listed", gone,
            "Never inferred — each carries the last date it was measurably still up."),
        sec("เสียงจากตลาด · Sentiment and share of voice", sentiment,
            "Play and App Store are MEASURED star averages; YouTube is a MEASURED subscriber "
            "count (กลุ่ม = a parent corporate channel, not the product's own audience); Pantip "
            "is an ESTIMATED thread count and leans high for every brand — the RANKING is the "
            "finding, not the multiple. Ordered by Pantip volume: who the market is talking "
            "about. A dash means the brand is absent from that source, not silent on it — "
            "เงินให้ใจ ships no app, so it cannot appear in the two star columns at all."),
        LINE, DIM, c["basis_stated"], c["basis_scanned"])


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
    for o in c["operators"][:10]:
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
