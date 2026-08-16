#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_rival_facebook.py — the rivals' LIVE promotional offer (objective #2).

Turns `source-data/rival_facebook.json` (pull_rival_facebook.js) into
`platform/data/rival_facebook.json` for the Competition tab and the daily digest.

WHY THIS LAYER OUTRANKS THE RATE BOARD. Kaustav, 2026-08-16: "facebook is always the promo."
A lender's published rate card is the BoT-mandated disclosure — the legal outer bound. Its
Facebook post is what it is actually winning customers with this week, and the two are not the
same number. KTC พี่เบิ้ม posted "ลดดอกถูกลง เริ่มต้นเพียง 0.60% ต่อเดือน" while its published card
said 12.99%–24% ต่อปี: the teaser appears NOWHERE in the disclosure. Reading only the card
systematically understates how aggressive the field is, so this layer leads and the card is
carried beside it as the ceiling. They are never averaged.

WHAT IS MEASURED vs WHAT IS NOT.
  * followers / talking_about / reactions — numbers Facebook prints. MEASURED, but Facebook
    rounds at scale ("1.3 แสน"), so they are bands. `followers_text` keeps the published string
    and `followers_approx` is the band's midpoint, labelled ESTIMATED because we widened it.
  * post / posted_ago — MEASURED, but ONE post per page and truncated by Facebook at
    "ดูเพิ่มเติม". `post_truncated` says so per row. This is a movement signal, not an archive.
  * any rate inside a post — read with pipeline/rate_basis.py, which NEVER infers a basis. A
    promo post almost always quotes a bare monthly number with no basis stated, so it comes
    back with BOTH readings and `basis: null`. That is the honest answer, not a failure.

THE TRAP THIS LAYER MUST NOT SPRING. Five operators map to a bank's CORPORATE page, not a
product page — their newest posts are credit cards, savings and concert presales. Those rows
carry `is_product_page: false` and are separated into `corporate` rather than being ranked
among the promos, because "SCB posted 7 hours ago" is not a vehicle-loan promotion.

Deterministic: ordering comes from Facebook's own relative stamp parsed to minutes, which is a
pure function of the input string. No wall clock is read anywhere — consistent with every other
layer here, where a date is only ever copied from a field the source stamped. `--check`
byte-compares; exits 3 (SKIP) when the network pull has not been run.

  python3 build_rival_facebook.py
  python3 build_rival_facebook.py --check
"""
import argparse
import io
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rate_basis                                  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
IN = os.path.join(ROOT, "source-data", "rival_facebook.json")
UNIVERSE = os.path.join(ROOT, "source-data", "rival_universe.json")
OUT = os.path.join(ROOT, "platform", "data", "rival_facebook.json")

# Thai magnitude words, and the band each implies. Facebook prints "1.3 แสน", not 130,755 —
# the precise figure is only in og:description and only sometimes, so the unit IS the precision.
UNIT = {"พัน": 1000, "หมื่น": 10000, "แสน": 100000, "ล้าน": 1000000}
FOLLOW = re.compile(r"([\d.,]+)\s*(พัน|หมื่น|แสน|ล้าน)?")

# Facebook's relative stamp -> minutes, for ORDERING ONLY. Never turned into a calendar date:
# that needs the wall clock, and this repo copies dates from the source or does without.
AGO_MIN = {"นาที": 1, "ชั่วโมง": 60, "วัน": 1440, "สัปดาห์": 10080, "เดือน": 43200, "ปี": 525600}
AGO = re.compile(r"(\d+)\s*(นาที|ชั่วโมง|วัน|สัปดาห์|เดือน|ปี)")

# A post is PRICING when it puts a number next to a rate word. Anything else is brand noise —
# a lottery result, a public-holiday card, a customer testimonial.
RATE_NUM = re.compile(r"(\d{1,2}(?:\.\d{1,2})?)\s*%")
RATE_CUE = ("ดอกเบี้ย", "อัตรา", "ลดต้นลดดอก", "คงที่", "แท้จริง", "ต่อเดือน", "ต่อปี")
# Offer language that is promotional even without a percentage.
OFFER_CUE = ("โปรโมชั่น", "โปรโมชัน", "พิเศษ", "ฟรี", "ลด", "แลกเงิน", "จำนำ", "รีไฟแนนซ์",
             "รีก่อน", "วงเงิน", "อนุมัติ", "ผ่อน", "ค่างวด", "สินเชื่อ", "ดาวน์")

# Is the POST about lending against a vehicle? This decides where a row is filed — NOT whether
# the page is a product page. A bank's corporate page carries card promos AND car-loan promos,
# and routing by page type buried the single most valuable find of the first run: KTC พี่เบิ้ม
# advertising 0.60% ต่อเดือน sat in `corporate` and was reported as "0 pricing posts". The page
# flag still matters, but only for whether the FOLLOWER COUNT is that product's share of voice.
VEHICLE_CUE = ("รถ", "ทะเบียน", "จำนำเล่ม", "โอนเล่ม", "เล่มทะเบียน", "รีไฟแนนซ์", "ค่างวด",
               "ออโต้", "มอเตอร์ไซค์", "กระบะ", "เก๋ง", "บิ๊กไบค์", "ดาวน์")
# Collateral lending that is not a vehicle but is still this market (land/deed title loans).
COLLATERAL_CUE = ("โฉนด", "ที่ดิน", "บ้านแลกเงิน")


def _round2(x):
    return rate_basis._round2(x)


def followers_band(text):
    """('1.3 แสน') -> (130000, '1.3 แสน'). ESTIMATED: the unit is the precision Facebook gave."""
    if not text:
        return None
    m = FOLLOW.search(text.strip())
    if not m:
        return None
    try:
        n = float(m.group(1).replace(",", ""))
    except ValueError:
        return None
    return int(round(n * UNIT.get(m.group(2) or "", 1)))


def ago_minutes(text):
    if not text:
        return None
    m = AGO.search(text)
    if not m:
        return None
    return int(m.group(1)) * AGO_MIN[m.group(2)]


def rates_in(text):
    """Every rate the post states, with BOTH readings when it does not say which basis.

    A promo post quotes "0.60% ต่อเดือน" and stops. That is 7.20%/yr read flat and 7.20%/yr
    nominal read reducing — the same headline number annualises identically, but the COST is
    very different, and which one applies is not written down. rate_basis refuses to guess and
    so does this: `basis` stays null and both readings are published side by side.
    """
    if not text:
        return []
    out = []
    for m in RATE_NUM.finditer(text):
        lo, hi = max(0, m.start() - 60), min(len(text), m.end() + 60)
        window = text[lo:hi]
        if not any(c in window for c in RATE_CUE):
            continue
        pct = float(m.group(1))
        per_month = "ต่อเดือน" in window
        basis = rate_basis.basis_kind_in(window)      # None unless the post SAYS
        annual = _round2(rate_basis.per_month_to_per_year(pct)) if per_month else _round2(pct)
        row = {"quoted_pct": pct,
               "quoted_unit": "pct_per_month" if per_month else "pct_per_year",
               "basis": basis,
               "annualised_pct": annual,
               "quote_th": window.strip()}
        if basis is None:
            # Both readings, because the post did not say. tenor is unstated in a promo post,
            # so the flat->effective conversion uses the product's common 60-month term and is
            # labelled ESTIMATED by the caller.
            row["effective_if_flat"] = _round2(rate_basis.flat_to_effective(annual, 60))
            row["effective_if_reducing"] = annual
        out.append(row)
    return out


def classify(text):
    if not text:
        return "none"
    if rates_in(text):
        return "pricing"
    if any(c in text for c in OFFER_CUE):
        return "offer"
    return "brand"


def on_product(text):
    """Is this post about lending against a vehicle (or land, the adjacent collateral)?

    Decided from the POST, never from the page. See VEHICLE_CUE for why that distinction cost
    us the best finding in the first run.
    """
    if not text:
        return False
    return (any(c in text for c in VEHICLE_CUE) or any(c in text for c in COLLATERAL_CUE))


def build():
    raw = json.load(io.open(IN, encoding="utf-8"))
    uni = json.load(io.open(UNIVERSE, encoding="utf-8"))
    names = {o["key"]: o.get("name_th") or o["key"] for o in uni["operators"]}

    promos, corporate, silent = [], [], []
    for key, p in sorted(raw.get("pages", {}).items()):
        post = (p.get("post") or "").strip() or None
        rates = rates_in(post) if post else []
        row = {
            "key": key,
            "name_th": names.get(key, p.get("name_th") or key),
            "fb_page": p.get("fb_page"),
            "url": p.get("url"),
            "is_product_page": p.get("is_product_page", True),
            "followers_text": p.get("followers"),
            "followers_approx": followers_band(p.get("followers")),
            "talking_about": p.get("talking_about"),
            "reactions": p.get("reactions"),
            "post": post,
            "post_truncated": bool(p.get("post_truncated")),
            "posted_ago": p.get("posted_ago"),
            "age_minutes": ago_minutes(p.get("posted_ago")),
            "kind": classify(post),
            "on_product": on_product(post),
            "rates": rates,
            "bio": p.get("bio"),
            "previous_post": p.get("previous_post"),
            "changed_since_last_run": bool(p.get("previous_post")),
        }
        # A row whose page covers the whole company still counts as a promo when the POST is
        # about vehicle lending — the flag only warns that its follower count is not this
        # product's audience.
        row["followers_are_product_audience"] = row["is_product_page"]
        if not post:
            silent.append(row)
        elif row["on_product"]:
            promos.append(row)
        else:
            corporate.append(row)

    # Freshest first — "facebook is always the promo", so recency IS the signal. A row whose
    # stamp did not parse sorts last rather than being dropped or guessed at.
    def order(r):
        return (r["age_minutes"] is None, r["age_minutes"] or 0, r["key"])
    promos.sort(key=order)
    corporate.sort(key=order)
    silent.sort(key=lambda r: r["key"])

    pricing = [r for r in promos if r["kind"] == "pricing"]
    return {
        "meta": {
            "title": "What the rivals are actually offering — their own Facebook posts",
            "label": (
                "MEASURED from each operator's own Facebook page, read ANONYMOUSLY (no account, "
                "no session). Facebook serves the page identity, follower and engagement counts "
                "and THE SINGLE NEWEST POST before its login wall; the post is truncated by "
                "Facebook itself at 'ดูเพิ่มเติม'. This is a daily movement signal, NOT a promo "
                "archive — it is one post per page per run and must not be read as the "
                "operator's full promotions."),
            "why_this_leads": (
                "A lender's published rate card is the BoT-mandated disclosure: the legal outer "
                "bound. Its Facebook post is the offer it is winning customers with this week, "
                "and they differ — KTC พี่เบิ้ม advertised 0.60% ต่อเดือน while its card said "
                "12.99%-24% ต่อปี. The card is the CEILING and is carried beside this, never "
                "averaged with it."),
            "basis_caveat": (
                "A promo post quotes a bare monthly rate and almost never states its basis. "
                "rate_basis.py refuses to infer one, so those rows carry basis=null with BOTH "
                "readings: effective_if_reducing (the annualised number as-is) and "
                "effective_if_flat (ESTIMATED, converted at a 60-month term because the post "
                "states no tenor)."),
            "followers_caveat": (
                "Facebook rounds follower counts at scale and prints them as bands ('1.3 แสน'). "
                "followers_text is what it published; followers_approx is the band midpoint and "
                "is ESTIMATED."),
            "routing_rule": (
                "Rows are filed by what the POST is about, not by what the page is. `promos` "
                "is every newest post about lending against a vehicle or land; `corporate` is "
                "everything else that page happened to post (cards, deposits, sponsorships). "
                "Routing by page type instead buried KTC พี่เบิ้ม's 0.60% ต่อเดือน promo in "
                "`corporate` and reported '0 pricing posts'."),
            "corporate_page_caveat": (
                "`followers_are_product_audience: false` marks the operators whose page covers "
                "a whole bank rather than the vehicle-loan product. Their posts still count as "
                "promos when they are on-product, but their FOLLOWER COUNTS are not that "
                "product's share of voice and must not be charted as if they were."),
            "source_label": raw.get("meta", {}).get("label"),
            "session_used": bool(raw.get("meta", {}).get("session")),
            "n_promo_pages": len(promos),
            "n_pricing_posts": len(pricing),
            "n_corporate_pages": len(corporate),
            "n_silent": len(silent),
            "n_pages": len(promos) + len(corporate) + len(silent),
            "fb_page_missing": raw.get("meta", {}).get("fb_page_missing", []),
        },
        "promos": promos,
        "corporate": corporate,
        "silent": silent,
    }


def serialize(obj):
    return json.dumps(obj, ensure_ascii=False, indent=1, sort_keys=True) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    if not os.path.exists(IN):
        if args.check:
            print("build_rival_facebook.py --check: SKIP (no rival_facebook — network pull)")
            sys.exit(3)
        sys.exit("build_rival_facebook.py: run pipeline/pull_rival_facebook.js first")
    payload = serialize(build())
    if args.check:
        if not os.path.exists(OUT):
            sys.exit("build_rival_facebook.py --check: output missing — run the builder.")
        if io.open(OUT, encoding="utf-8").read() != payload:
            sys.exit("build_rival_facebook.py --check: drifted — re-run the builder.")
        print("build_rival_facebook.py --check: OK (byte-exact)")
        return
    with io.open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write(payload)
    obj = json.loads(payload)
    m = obj["meta"]
    print("wrote %s — %d promo pages (%d quoting a rate), %d corporate, %d silent"
          % (OUT, m["n_promo_pages"], m["n_pricing_posts"], m["n_corporate_pages"], m["n_silent"]))
    for r in obj["promos"]:
        rate = (" | %s%% %s" % (r["rates"][0]["quoted_pct"], r["rates"][0]["quoted_unit"])
                if r["rates"] else "")
        print("  %-12s %-9s %-8s %s%s"
              % (r["key"], r["posted_ago"] or "-", r["kind"], (r["post"] or "")[:70], rate))


if __name__ == "__main__":
    main()
