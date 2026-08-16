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
SITE = os.environ.get("SITE_URL", "https://competitive-intel.vercel.app")

BG, CARD, FG, DIM, ACC = "#0F1216", "#171B21", "#E8EAED", "#9AA3AE", "#5B7CFA"
GOLD, MERCH, PD = "#E6B450", "#1C8C7D", "#C8433B"


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


def collect():
    """Everything the digest says, as plain data — so the HTML and text stay in step."""
    watch, pulse = load("rival_watch"), load("rival_pulse")
    board, ads = load("rate_board"), load("rival_ads")
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

    return {
        "asof": asof,
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

    promo = rows_html(c["promos_new"], lambda p: (
        '<tr><td style="padding:5px 0;border-bottom:1px solid #222">'
        '<b>%s</b> <span style="color:%s">%s</span><br>'
        '<a href="%s" style="color:%s;font-size:12px;text-decoration:none">%s</a></td></tr>'
        % (esc(p.get("brand")), DIM, esc(p.get("kind") or ""), esc(p.get("url") or "#"),
           ACC, esc((p.get("title") or "")[:150]))))

    gone = rows_html(c["promos_gone"], lambda p: (
        '<tr><td style="padding:5px 0;border-bottom:1px solid #222;color:%s">'
        '<b style="color:%s">%s</b> — %s <span style="font-size:11px">(last seen %s)</span>'
        '</td></tr>' % (DIM, FG, esc(p.get("brand")),
                        esc((p.get("title") or "")[:120]), esc(p.get("last_seen")))))

    pricing = rows_html(c["fresh_pricing"], lambda a: (
        '<tr><td style="padding:6px 0;border-bottom:1px solid #222">'
        '<b>%s</b> <span style="color:%s;font-size:11px">first shown %s</span>%s<br>'
        '<span style="color:%s;font-size:12px">%s</span></td></tr>'
        % (esc(a.get("brand")), DIM, esc(a.get("first")),
           (' <span style="color:%s;font-size:11px">· %s</span>'
            % (GOLD, esc(a["basis_kind"]))) if a.get("basis_kind") else "",
           DIM, esc((a.get("copy") or "")[:190]))))

    board = rows_html(c["operators"][:10], lambda o: (
        '<tr><td style="padding:4px 0;border-bottom:1px solid #222">%s'
        '<div style="color:%s;font-size:11px">%s</div></td>'
        '<td align="right" style="padding:4px 0;border-bottom:1px solid #222;white-space:nowrap">'
        '<b style="color:%s">%s</b></td>'
        '<td align="right" style="padding:4px 0 4px 14px;border-bottom:1px solid #222;'
        'color:%s;white-space:nowrap">%s</td></tr>'
        % (esc(o.get("operator")), DIM,
           esc({"title_loan": "ไม่โอนเล่ม", "hp_refinance": "โอนเล่ม",
                "both": "both"}.get(o.get("loan_type"), "")),
           MERCH if o.get("effective_source") in ("lender", "as_quoted") else GOLD,
           ("%s%%" % o["effective_lo"]) if o.get("effective_lo") is not None else "—",
           DIM, ("LTV %s%%" % o["ltv_pct"]) if o.get("ltv_pct") is not None else "")))

    sentiment = rows_html(c["sentiment"], lambda s: (
        '<tr><td style="padding:4px 0;border-bottom:1px solid #222">%s%s</td>'
        '<td align="right" style="padding:4px 0;border-bottom:1px solid #222">'
        '<b style="color:%s">%s★</b></td></tr>'
        % (esc(s.get("brand")),
           ' <span style="color:%s;font-size:11px">us</span>' % GOLD if s.get("is_us") else "",
           GOLD if s.get("is_us") else FG, esc(s.get("score")))))

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
 border:1px solid #232830;border-radius:10px;overflow:hidden">
<tr><td style="padding:20px 22px 6px">
  <div style="font:700 19px/1.25 -apple-system,Segoe UI,Roboto,sans-serif;color:%s">
    Rival pulse — %s</div>
  <div style="font:12px/1.5 -apple-system,sans-serif;color:%s;margin-top:5px">
    AutoX / เงินไชโย competitive intelligence · every date below is stamped by the source data,
    never by when this email was sent.</div>
  %s
</td></tr>
%s%s%s%s%s
<tr><td style="padding:14px 22px 20px;border-top:1px solid #232830">
  <a href="%s/#acq" style="display:inline-block;background:%s;color:#fff;text-decoration:none;
   font:600 13px -apple-system,sans-serif;padding:9px 16px;border-radius:6px">
   Open the Competition tab</a>
  <div style="font:11px/1.5 -apple-system,sans-serif;color:%s;margin-top:12px">
   %s of %s tracked creatives state whether their rate is flat or reducing balance, so an
   advertised headline is not comparable as printed — that is what the effective column fixes.
   Generated by pipeline/build_rival_digest.py from rival_watch.json, rate_board.json,
   rival_ads.json and rival_pulse.json.</div>
</td></tr>
</table></td></tr></table></body></html>""" % (
        BG, BG, CARD, FG, esc(c["asof"]), DIM,
        ('<div style="font:14px/1.55 -apple-system,sans-serif;color:%s;margin-top:12px;'
         'padding:11px 13px;background:#12161C;border-left:3px solid %s;border-radius:4px">%s</div>'
         % (FG, MERCH, lead)) if lead else "",
        sec("New rival promotions", promo,
            "From the rivals' own sites. Only listed once a dated first_seen proves it is new."),
        sec("New pricing ads", pricing,
            "Creatives that compete on cost, newest first — %d in total this cycle."
            % c["n_fresh_pricing"]),
        sec("Rate board", board,
            "Effective %/yr, reducing balance. Green = the lender's own published figure, "
            "gold = converted by us from their flat quote."),
        sec("Promotions no longer listed", gone,
            "Never inferred — each carries the last date it was measurably still up."),
        sec("App sentiment", sentiment, "Google Play, last 90 days."),
        SITE, ACC, DIM, c["basis_stated"], c["basis_scanned"])


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
    def blk(title, items, fmt):
        L.append(title.upper())
        L.extend(["  " + fmt(i) for i in items] or ["  (nothing new)"])
        L.append("")
    blk("New rival promotions", c["promos_new"],
        lambda p: "%s — %s  %s" % (p.get("brand"), (p.get("title") or "")[:90], p.get("url") or ""))
    blk("New pricing ads (%d)" % c["n_fresh_pricing"], c["fresh_pricing"],
        lambda a: "%s (%s)%s — %s" % (a.get("brand"), a.get("first"),
                                      " [%s]" % a["basis_kind"] if a.get("basis_kind") else "",
                                      " ".join((a.get("copy") or "").split())[:110]))
    blk("Promotions no longer listed", c["promos_gone"],
        lambda p: "%s — %s (last seen %s)" % (p.get("brand"), (p.get("title") or "")[:80],
                                              p.get("last_seen")))
    L.append("RATE BOARD (effective %/yr, reducing balance)")
    for o in c["operators"][:10]:
        L.append("  %-26s %7s  %s" % (
            (o.get("operator") or "")[:26],
            ("%s%%" % o["effective_lo"]) if o.get("effective_lo") is not None else "-",
            ("LTV %s%%" % o["ltv_pct"]) if o.get("ltv_pct") is not None else ""))
    L += ["", "%s of %s creatives state their rate basis." % (c["basis_stated"], c["basis_scanned"]),
          "%s/#acq" % SITE]
    return "\n".join(L)


def send(subj, body_html, body_text):
    """SMTP via stdlib only — no third-party action, no vendor SDK in the send path."""
    host, port = os.environ.get("SMTP_HOST"), int(os.environ.get("SMTP_PORT", "587"))
    user, pw = os.environ.get("SMTP_USER"), os.environ.get("SMTP_PASS")
    to = os.environ.get("MAIL_TO")
    if not (host and user and pw and to):
        missing = [n for n, v in (("SMTP_HOST", host), ("SMTP_USER", user),
                                  ("SMTP_PASS", pw), ("MAIL_TO", to)) if not v]
        print("SKIP: no mail credentials (%s unset) — digest rendered, not sent"
              % ", ".join(missing))
        return 3
    m = EmailMessage()
    m["Subject"] = subj
    m["From"] = formataddr((os.environ.get("MAIL_FROM_NAME", "AutoX Rival Pulse"),
                            os.environ.get("MAIL_FROM", user)))
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
