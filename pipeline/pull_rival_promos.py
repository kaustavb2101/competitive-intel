#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pull_rival_promos.py — MEASURED rival promotions & campaign watch (objective #2), pulled from the
competitors' OWN websites. Writes source-data/rival_promos.json with per-item first_seen/last_seen
so every re-run tells you exactly what is NEW since the last pull.

THAI-IP ONLY for the corporate sites (tidlor.com / muangthaicap.com / sawad.co.th are geoblocked
from foreign/cloud IPs) — run from Kaustav's laptop, same as autox_dgt_ingest.py. NETWORK script:
not in the offline determinism gate; the committed rival_promos.json is the artifact and
build_rival_pulse.py derives the app layer deterministically from it.

Per-brand adapters (each degrades to a logged skip, never a crash):
  TIDLOR   www.tidlor.com/th/promotion-activity           static listing -> per-promo og:title/date
  MTC      muangthaicap.com/news/                          WP listing (title + <time datetime>) —
                                                           MTC publishes campaigns via news, no promo page
  SAWAD    www.sawad.co.th/wp-json/wp/v2/posts?search=โปรโมชั่น   open WordPress REST API
  HENG     www.hengleasing.com — NO parseable promo page (their /th/promotion is an unfinished
           theme-demo stub, checked 2026-07-19) — recorded as a coverage note, not silently absent.

  python3 pull_rival_promos.py            # refresh + merge -> source-data/rival_promos.json
"""
import datetime
import json
import os
import re
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "source-data", "rival_promos.json")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

TH_MONTHS = {"มกราคม": 1, "กุมภาพันธ์": 2, "มีนาคม": 3, "เมษายน": 4, "พฤษภาคม": 5, "มิถุนายน": 6,
             "กรกฎาคม": 7, "สิงหาคม": 8, "กันยายน": 9, "ตุลาคม": 10, "พฤศจิกายน": 11, "ธันวาคม": 12,
             "ม.ค.": 1, "ก.พ.": 2, "มี.ค.": 3, "เม.ย.": 4, "พ.ค.": 5, "มิ.ย.": 6,
             "ก.ค.": 7, "ส.ค.": 8, "ก.ย.": 9, "ต.ค.": 10, "พ.ย.": 11, "ธ.ค.": 12}


def fetch(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "th,en;q=0.8"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def thai_date_iso(text):
    """'02 กรกฎาคม 2569' / '10 ก.ค. 26' -> ISO date (Buddhist year -543). None if not found."""
    m = re.search(r"(\d{1,2})\s*(%s)\s*(\d{2,4})" % "|".join(map(re.escape, TH_MONTHS)), text)
    if not m:
        return None
    d, mon, y = int(m.group(1)), TH_MONTHS[m.group(2)], int(m.group(3))
    if y < 100:
        y += 2500                       # '26' -> 2569 (Buddhist short year, as MTC prints it)
    if y > 2400:
        y -= 543
    try:
        return datetime.date(y, mon, d).isoformat()
    except ValueError:
        return None


def pull_tidlor():
    base = "https://www.tidlor.com"
    listing = fetch(base + "/th/promotion-activity")
    hrefs, seen = [], set()
    for m in re.finditer(r'href="(/th/promotion-activity/[^"#?]+)"', listing):
        if m.group(1) not in seen:
            seen.add(m.group(1)); hrefs.append(m.group(1))
    items = []
    for h in hrefs[:12]:                                    # listing carries the live set (~6)
        try:
            page = fetch(base + h)
        except Exception as e:
            print("  tidlor detail skip %s (%s)" % (h, e)); continue
        t = re.search(r'<meta property="og:title" content="([^"]+)"', page)
        desc = re.search(r'<meta property="og:description" content="([^"]+)"', page)
        items.append({"brand": "TIDLOR", "kind": "promotion",
                      "title": (t.group(1) if t else h.rsplit("/", 1)[-1]).strip(),
                      "detail": (desc.group(1).strip()[:220] if desc else None),
                      "date": thai_date_iso(page), "url": base + h})
    return items


def pull_mtc():
    page = fetch("https://muangthaicap.com/news/")
    items = []
    for art in page.split("<article")[1:]:
        u = re.search(r'href="(https://muangthaicap\.com/news/[^"#?]+/)"', art)
        t = re.search(r'title="Permalink to ([^"]+)"', art)
        dt = re.search(r'<time class="entry-date published" datetime="(\d{4}-\d{2}-\d{2})', art)
        if u and t:
            items.append({"brand": "MTC", "kind": "news",
                          "title": t.group(1).strip(), "detail": None,
                          "date": dt.group(1) if dt else None, "url": u.group(1)})
    return items


def pull_sawad():
    url = ("https://www.sawad.co.th/wp-json/wp/v2/posts?search=%E0%B9%82%E0%B8%9B%E0%B8%A3"
           "%E0%B9%82%E0%B8%A1%E0%B8%8A%E0%B8%B1%E0%B9%88%E0%B8%99&per_page=20"
           "&_fields=date,link,title")
    posts = json.loads(fetch(url))
    items = []
    for p in posts:
        title = re.sub(r"&#\d+;|<[^>]+>", "", p["title"]["rendered"]).strip()
        promo = ("promotion" in p["link"]) or re.search(r"โปรโมชั่น|ส่วนลด|แจก|ฟรี!|พิเศษ|คุ้ม", title)
        if promo:
            items.append({"brand": "SAWAD", "kind": "promotion", "title": title, "detail": None,
                          "date": p["date"][:10], "url": p["link"]})
    return items


def main():
    today = datetime.date.today().isoformat()
    prev = {}
    if os.path.exists(OUT):
        for it in json.load(open(OUT, encoding="utf-8")).get("items", []):
            prev[it["url"]] = it

    pulled, errors = [], []
    for name, fn in [("TIDLOR", pull_tidlor), ("MTC", pull_mtc), ("SAWAD", pull_sawad)]:
        try:
            got = fn()
            pulled.extend(got)
            print("%-6s %d items" % (name, len(got)))
        except Exception as e:
            errors.append("%s: %s" % (name, e))
            print("%-6s FAILED (%s) — keeping previous items" % (name, e))
            pulled.extend([it for it in prev.values() if it["brand"] == name])

    items, new = [], 0
    for it in pulled:
        old = prev.get(it["url"])
        it["first_seen"] = old["first_seen"] if old else today
        it["last_seen"] = today
        if not old:
            new += 1
        items.append(it)
    # keep items that dropped off a listing (promo ended) for 120 days of history
    for url, old in prev.items():
        if not any(i["url"] == url for i in items) and old.get("last_seen", today) >= \
                (datetime.date.today() - datetime.timedelta(days=120)).isoformat():
            items.append(old)
    items.sort(key=lambda i: (i.get("date") or i["first_seen"]), reverse=True)

    payload = {
        "meta": {
            "title": "Rival promotions & campaign watch — pulled from the competitors' own sites",
            "generated_by": "pipeline/pull_rival_promos.py",
            "label": "MEASURED — what TIDLOR/MTC/SAWAD publish on their own websites (Thai-IP pull). "
                     "MTC has no promo page, so its news/campaign feed stands in. HENG has no "
                     "parseable promo page at all (theme-demo stub, checked 2026-07-19).",
            "pulled_at": today,
            "new_this_pull": new,
            "errors": errors,
            "coverage_note": "HENG (Heng Leasing) not covered — no machine-readable promo page.",
        },
        "items": items,
    }
    json.dump(payload, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("wrote %s — %d items (%d new this pull)" % (OUT, len(items), new))


if __name__ == "__main__":
    main()
