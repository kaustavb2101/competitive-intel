#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pull_apple_reviews.py — MEASURED customer sentiment from the **Apple Thai storefront**: app
ratings + newest review text for the title lenders (incl. our own เงินไชโย), plus the digital
personal-loan cohort that competes for the same borrower. Writes source-data/apple_reviews.json.

WHY THIS EXISTS. `pull_app_reviews.py` covers Google Play only. Android dominates this segment, but
iOS is not noise: it skews higher-income and higher-ticket — exactly the borrower whose collateral
is a car rather than a motorcycle. Half the voice-of-customer picture was missing.

No API key, no auth, works from ANY IP (CI-schedulable), same as the Play puller. Two endpoints:
  * itunes.apple.com/lookup           — rating, rating count, seller, bundleId  (stable)
  * itunes.apple.com/th/rss/customerreviews — dated review BODIES, ~50/page     (long deprecated by
    Apple but still live as of 2026-07-30; if it dies we degrade to ratings-only, which is still a
    real signal, and `meta.reviews_live` says which happened)

IDS ARE PINNED, NEVER SEARCHED. Resolving by search rank is provably wrong here: querying
"เฮงลิสซิ่ง" returns **Rabbit Cash**, a different lender entirely, and a naive sellerName filter
matched GSB's retail banking app **MyMo** instead of its Good Money lending app. Every id below was
verified via lookup?id= against BOTH sellerName and bundleId (which mirrors the Android package in
pull_app_reviews.py for almost every operator). Same discipline as the advertiser ids in
pull_google_ads.py and the channel ids in pull_rival_youtube.py.

Each run merges the newest reviews into a growing per-app store (dedup by review id, newest CAP
kept) so history accumulates across runs — matching pull_app_reviews.py exactly.

NETWORK script: not in the offline determinism gate. The committed apple_reviews.json is the
artifact; the builder derives from it deterministically.

  python3 pull_apple_reviews.py                  # refresh every tracked app
  python3 pull_apple_reviews.py --brand TIDLOR   # just one
  python3 pull_apple_reviews.py --pages 4        # deeper review history per app
"""
import argparse
import datetime
import io
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "source-data", "apple_reviews.json")

CAP = 1500            # newest reviews kept per app (mirrors pull_app_reviews.py)
PAGES = 10            # review pages per app; Apple caps the feed around 10
POLITE = 1.2          # seconds between requests — this is a courtesy scrape, not an API contract
STORE = "th"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/120.0.0.0 Safari/537.36")

# ---------------------------------------------------------------------------------------------
# TRACKED APPS.  (key, apple_id, expect_seller_contains, display, cohort, is_us)
#
# cohort "title"   — the จำนำทะเบียน operators, directly comparable to our own book.
# cohort "digital" — personal-loan / nano-finance apps. NOT title lenders, so they must never be
#   mixed into title-lender share. They are tracked because the Apple sweep showed they outweigh
#   every title lender on mobile by 2–3 orders of magnitude (FINNIX 171k ratings vs เงินไชโย 208)
#   while chasing the same borrower with minutes-to-cash approval. That is substitution pressure on
#   the branch product and it is invisible to a title-lender-only competitor set.
# ---------------------------------------------------------------------------------------------
APPS = [
    ("AUTOX",       1604782763, "AUTO X",              "เงินไชโย (AutoX)",            "title", True),
    ("TIDLOR",      1505259341, "Ngern Tid Lor",       "ติดใจ โดย เงินติดล้อ",         "title", False),
    ("MTC",         1322301792, "Muangthai Leasing",   "เมืองไทย แคปปิตอล",            "title", False),
    ("SAWAD",       6464282089, "SRISAWAD",            "ศรีสวัสดิ์",                   "title", False),
    ("NGERNTURBO",  6444042917, "NGERNTURBO",          "เงินเทอร์โบ",                  "title", False),
    ("SOMWANG",     6737461047, "HI-WAY",              "สมหวัง เงินสั่งได้ (TISCO)",    "title", False),
    ("KTC_PBERM",   1566340665, "KRUNGTHAI",           "พี่เบิ้ม Mobile (KTC)",        "title", False),
    ("GSB_MONEYDD", 6476857961, "MONEY DD",            "Good Money by GSB",           "title", False),
    ("SAKSIAM",     6446016964, "SAKSIAM",             "ศักดิ์สยาม (SAK)",             "title", False),
    ("KRUNGSRI_GO", 1489440875, "Ayudhya",             "GO by Krungsri Auto",         "title", False),
]

# Resolved by EXACT bundleId lookup rather than a hardcoded numeric id, because these were found
# during the sweep and bundleId is an exact key while a numeric id copied from a search result is
# not self-verifying.
DIGITAL = [
    ("FINNIX",       "com.monix.ios.loan",           "MONIX",   "FINNIX (MONIX/SCB)"),
    ("MONEYTHUNDER", "com.scbabacus.l2020",          "ABACUS",  "MoneyThunder (Abacus/SCB)"),
    ("PROMISE",      "com.promisethai.mobileapp.ios", "PROMISE", "PROMISE Thailand"),
    ("AMONEY",       "th.co.amoney",                 "AIRA",    "A money (AIRA & AIFUL)"),
    ("RABBITCASH",   "th.co.rabbitcash.app",         "RABBIT",  "Rabbit Cash (BTS)"),
    ("MONEYHUB",     "com.tfg.moneyhub",             "money hub", "มันนี่ฮับ"),
]

# NOT TRACKED, with the reason, so a future run does not "helpfully" add them back:
EXCLUDED = {
    "HENG": ("id 6754239684 — 'HENG การให้เช่า' carries Heng's seller name but three red flags at "
             "once: bundleId 'com.lutoe.menwo' (every genuine peer's bundleId mirrors its company), "
             "sellerUrl on hengleasing.CO (Heng's real site is .com), and 4.71★/2913 ratings — the "
             "highest score AND volume in a field spanning 1.71–3.62★, from an app first released "
             "2026-03-24. Consistent with impersonation / rating farming. Flagged, not asserted; "
             "excluded so it can never be published as Heng's app."),
    "NGERNHAIJAI": ("เงินให้ใจ (KBank) ships no consumer iOS app — sold through K-branches/online. "
                    "Same reason it is absent from the Play set."),
    "TTB_CYC/KKP": ("whole-bank apps only; a bank-wide app score cannot isolate title-loan CX. "
                    "Covered in rival_universe.json instead."),
}


class Unreachable(RuntimeError):
    """Raised when the storefront itself fails, so an empty pull is never read as 'no reviews'."""


def get(url, tries=3):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept-Language": "th-TH,th;q=0.9,en-US;q=0.8",
    })
    last = None
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.getcode(), r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            if e.code in (403, 429, 503):        # throttled — back off rather than record a zero
                last = e
                time.sleep(POLITE * (attempt + 2) * 2)
                continue
            return e.code, ""
        except Exception as e:                   # noqa: BLE001 — transport, retry
            last = e
            time.sleep(POLITE * (attempt + 1))
    if last is not None:
        raise Unreachable("%s: %s" % (url, last))
    return None, ""


def lookup(**params):
    params.setdefault("country", STORE)
    code, body = get("https://itunes.apple.com/lookup?" + urllib.parse.urlencode(params))
    if code != 200 or not body:
        return None
    try:
        res = json.loads(body).get("results") or []
    except ValueError:
        return None
    return res[0] if res else None


def reviews_page(app_id, page):
    """One page of the public customer-reviews feed. Returns [] when the feed is exhausted/dead."""
    url = ("https://itunes.apple.com/%s/rss/customerreviews/page=%d/id=%s/sortby=mostrecent/json"
           % (STORE, page, app_id))
    code, body = get(url)
    if code != 200 or not body:
        return []
    try:
        entries = (json.loads(body).get("feed") or {}).get("entry") or []
    except ValueError:
        return []
    if isinstance(entries, dict):
        entries = [entries]
    out = []
    for e in entries:
        if not isinstance(e, dict) or "content" not in e:
            continue                              # the feed's first entry is the app itself
        rid = ((e.get("id") or {}).get("label")) or ""
        out.append({
            "id": rid,
            "at": None,                           # Apple's RSS carries no review date (see meta)
            "score": _int((e.get("im:rating") or {}).get("label")),
            "title": (e.get("title") or {}).get("label"),
            "content": ((e.get("content") or {}).get("label") or "").strip()[:400],
            "version": (e.get("im:version") or {}).get("label"),
            "votes": _int((e.get("im:voteCount") or {}).get("label")),
        })
    return out


def _int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def pull_one(key, meta_row, prev, pages):
    """meta_row: dict with either apple_id or bundle_id, plus expect/display/cohort/own."""
    if meta_row.get("apple_id"):
        info = lookup(id=meta_row["apple_id"])
    else:
        info = lookup(bundleId=meta_row["bundle_id"])
    if not info:
        print("  %-13s NOT FOUND in the %s storefront — keeping previous" % (key, STORE))
        return prev.get(key)

    seller = info.get("sellerName") or ""
    expect = meta_row.get("expect") or ""
    verified = expect.upper() in seller.upper()
    if not verified:
        # identity is the whole point of pinning; refuse rather than publish someone else's app
        print("  %-13s SELLER MISMATCH — expected ~%r, got %r — SKIPPED" % (key, expect, seller))
        return prev.get(key)

    app_id = info.get("trackId")
    store = {r["id"]: r for r in (prev.get(key) or {}).get("reviews_store", [])}
    fetched = 0
    for p in range(1, pages + 1):
        rs = reviews_page(app_id, p)
        if not rs:
            break
        for r in rs:
            if r["id"]:
                store[r["id"]] = r
        fetched += len(rs)
        time.sleep(POLITE)

    kept = sorted(store.values(), key=lambda x: x["id"], reverse=True)[:CAP]
    row = {
        "apple_id": app_id,
        "bundle_id": info.get("bundleId"),
        "seller": seller,
        "name": meta_row.get("display") or info.get("trackName"),
        "store_name": info.get("trackName"),
        "cohort": meta_row.get("cohort"),
        "own": bool(meta_row.get("own")),
        "stats": {
            "score": info.get("averageUserRating"),
            "ratings": info.get("userRatingCount"),
            "score_current_version": info.get("averageUserRatingForCurrentVersion"),
            "ratings_current_version": info.get("userRatingCountForCurrentVersion"),
            "version": info.get("version"),
            "app_updated": (info.get("currentVersionReleaseDate") or "")[:10] or None,
            "released": (info.get("releaseDate") or "")[:10] or None,
            "genre": info.get("primaryGenreName"),
        },
        "reviews_store": kept,
    }
    print("  %-13s %.2f★ %7s ratings  seller ok  +%d fetched, store %d"
          % (key, info.get("averageUserRating") or 0, info.get("userRatingCount"), fetched,
             len(kept)))
    return row


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--brand", help="only this key")
    ap.add_argument("--pages", type=int, default=PAGES, help="review pages per app (default %d)"
                    % PAGES)
    ap.add_argument("--no-digital", action="store_true",
                    help="skip the digital personal-loan cohort")
    a = ap.parse_args()

    prev = {}
    if os.path.exists(OUT):
        try:
            prev = json.load(io.open(OUT, encoding="utf-8")).get("apps", {})
        except ValueError:
            prev = {}

    rows = [(k, {"apple_id": i, "expect": e, "display": d, "cohort": c, "own": o})
            for k, i, e, d, c, o in APPS]
    if not a.no_digital:
        rows += [(k, {"bundle_id": b, "expect": e, "display": d, "cohort": "digital",
                      "own": False}) for k, b, e, d in DIGITAL]
    if a.brand:
        rows = [r for r in rows if r[0] == a.brand.upper()]
        if not rows:
            sys.exit("unknown brand %r — known: %s"
                     % (a.brand, ", ".join([r[0] for r in APPS] + [d[0] for d in DIGITAL])))

    print("Apple %s storefront — %d app(s), up to %d review pages each"
          % (STORE.upper(), len(rows), a.pages))
    out, failed = dict(prev), 0
    any_reviews = False
    for key, meta_row in rows:
        try:
            row = pull_one(key, meta_row, prev, a.pages)
        except Unreachable as e:
            print("  %-13s UNREACHABLE (%s)" % (key, e))
            failed += 1
            continue
        if row:
            out[key] = row
            any_reviews = any_reviews or bool(row["reviews_store"])
        time.sleep(POLITE)

    if failed and failed == len(rows):
        sys.exit("pull_apple_reviews.py: every request failed — refusing to write a file that "
                 "would read as 'no reviews'. Retry later.")

    today = datetime.date.today().isoformat()
    payload = {
        "meta": {
            "title": "Title-lender app sentiment — Apple App Store (TH) ratings + newest reviews",
            "generated_by": "pipeline/pull_apple_reviews.py",
            "label": "MEASURED — Apple Thai storefront. Aggregate rating + public review text. "
                     "Ids are hand-pinned and verified against sellerName + bundleId, never "
                     "resolved by search rank (searching 'เฮงลิสซิ่ง' returns a different "
                     "lender entirely).",
            "store": STORE,
            "pulled_at": today,
            "cap_per_app": CAP,
            "pages_per_app": a.pages,
            "reviews_live": any_reviews,
            "caveat": "Apple's public review feed carries NO review date, so unlike the Google "
                      "Play store these reviews cannot be placed on a timeline — they are ordered "
                      "most-recent-first and nothing more. Any trend claim must come from the "
                      "Play data. iOS also under-represents this segment overall; it is read as "
                      "the higher-income slice, not as the market.",
            "cohorts": {
                "title": "จำนำทะเบียน operators — directly comparable to our own book.",
                "digital": "personal-loan / nano-finance apps. NOT title lenders and never to be "
                           "mixed into title-lender share. Tracked because they outweigh every "
                           "title lender on mobile by 2–3 orders of magnitude while competing for "
                           "the same borrower — substitution pressure on the branch product.",
            },
            "excluded": EXCLUDED,
        },
        "apps": out,
    }
    with io.open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1)
    n = sum(len(v.get("reviews_store") or []) for v in out.values())
    print("wrote %s — %d apps, %d reviews stored" % (OUT, len(out), n))
    return 0


if __name__ == "__main__":
    sys.exit(main())
