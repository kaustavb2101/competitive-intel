#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pull_app_reviews.py — MEASURED customer sentiment: Google Play ratings + newest reviews for the
title-lender apps, INCLUDING AutoX's own เงินไชโย app. Writes source-data/app_reviews.json.

Why Google Play: this borrower segment is overwhelmingly Android; every big brand ships an app and
its store page carries a public, measured voice-of-customer signal (star histogram + dated review
text + dev replies). Works from ANY IP (no Thai network needed) — CI-schedulable.

Each run pulls current app stats + the ~200 newest reviews per app and MERGES them into a growing
per-app store (dedup by reviewId, capped at 1,500 newest) — so history accumulates across runs.

NETWORK script: not in the offline determinism gate; the committed app_reviews.json is the artifact
and build_rival_pulse.py derives the app layer deterministically from it. Requires:
  pip install google-play-scraper

  python3 pull_app_reviews.py                 # refresh all 5 apps -> source-data/app_reviews.json
"""
import json
import os
import sys
import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "source-data", "app_reviews.json")
CAP = 1500                       # newest reviews kept per app

# brand -> (Play appId, display, is_our_own). IDs resolved 2026-07-19/20 via Play developer pages
# + web search. Tier 2 (bank-backed จำนำทะเบียน entrants) added 2026-07-20: TISCO's Somwang, KTC's
# dedicated พี่เบิ้ม app, GSB's เงินดีดี (Good Money), Saksiam (SET:SAK), and Krungsri's GO auto
# super-app (Car4Cash lives inside it — score reads on the whole auto app, noted in the builder).
# No app to track for: เงินให้ใจ (KBank — sells through K-branches/online, no consumer app),
# ttb cash your car / KKP รถเรียกเงิน (whole-bank apps only — a bank app score wouldn't isolate
# title-loan CX, so they are covered in rival_universe.json instead).
APPS = {
    "AUTOX":      ("th.co.autox.chaiyo",              "เงินไชโย (AutoX)",        True),
    "TIDLOR":     ("com.ntl.cxm_mobile",              "ติดใจ โดย เงินติดล้อ",     False),
    "MTC":        ("co.th.muangthaileasing.mtls",     "เมืองไทย แคปปิตอล",        False),
    "SAWAD":      ("com.srisawad.mobileApplications", "ศรีสวัสดิ์",               False),
    "NGERNTURBO": ("com.ntbx.external.ngernturbo",    "เงินเทอร์โบ",              False),
    "SOMWANG":    ("com.tisconet.mewang",             "สมหวัง เงินสั่งได้ (TISCO)", False),
    "KTC_PBERM":  ("com.ktc.pberm",                   "KTC พี่เบิ้ม รถแลกเงิน",    False),
    "GSB_MONEYDD":("com.moneydd.goodmoney",           "Good Money เงินดีดี (GSB)", False),
    "SAKSIAM":    ("net.saksiam.northstar",           "ศักดิ์สยาม (SAK)",          False),
    "KRUNGSRI_GO":("com.krungsriauto.superapp.go",    "GO by Krungsri Auto",      False),
}


def main():
    try:
        from google_play_scraper import app, reviews, Sort
    except ImportError:
        sys.exit("pull_app_reviews.py: pip install google-play-scraper (the committed "
                 "app_reviews.json is the artifact; this script only refreshes it).")

    prev = {}
    if os.path.exists(OUT):
        prev = json.load(open(OUT, encoding="utf-8")).get("apps", {})

    today = datetime.date.today().isoformat()
    out_apps = {}
    for brand, (aid, display, own) in APPS.items():
        try:
            a = app(aid, lang="th", country="th")
            rs, _ = reviews(aid, lang="th", country="th", sort=Sort.NEWEST, count=200)
        except Exception as e:
            print("%-10s FAILED (%s) — keeping previous" % (brand, e))
            if brand in prev:
                out_apps[brand] = prev[brand]
            continue
        store = {r["id"]: r for r in prev.get(brand, {}).get("reviews_store", [])}
        for r in rs:
            store[r["reviewId"]] = {
                "id": r["reviewId"],
                "at": r["at"].strftime("%Y-%m-%d") if r.get("at") else None,
                "score": r["score"],
                "content": (r.get("content") or "").strip()[:400],
                "thumbs": r.get("thumbsUpCount", 0),
                "replied": bool(r.get("replyContent")),
            }
        kept = sorted(store.values(), key=lambda x: (x["at"] or "", x["id"]), reverse=True)[:CAP]
        out_apps[brand] = {
            "appId": aid, "name": display, "own": own,
            "stats": {
                "score": a.get("score"), "ratings": a.get("ratings"),
                "reviews_total": a.get("reviews"), "installs": a.get("installs"),
                "histogram": a.get("histogram"),          # [1★..5★] counts
                "app_updated": datetime.date.fromtimestamp(a["updated"]).isoformat() if a.get("updated") else None,
                "version": a.get("version"),
            },
            "reviews_store": kept,
        }
        print("%-10s %.2f★ %6d ratings — store %d reviews (newest %s)"
              % (brand, a.get("score") or 0, a.get("ratings") or 0, len(kept),
                 kept[0]["at"] if kept else "-"))

    payload = {
        "meta": {
            "title": "Title-lender app sentiment — Google Play ratings + newest reviews (incl. our own)",
            "generated_by": "pipeline/pull_app_reviews.py",
            "label": "MEASURED — Google Play store pages (th/th). Star histogram + dated public "
                     "reviews; review store accumulates across pulls (dedup by reviewId, newest "
                     "%d kept per app)." % CAP,
            "pulled_at": today,
        },
        "apps": out_apps,
    }
    json.dump(payload, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    n = sum(len(v["reviews_store"]) for v in out_apps.values())
    print("wrote %s — %d apps, %d reviews stored" % (OUT, len(out_apps), n))


if __name__ == "__main__":
    main()
