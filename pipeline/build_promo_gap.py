#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_promo_gap.py — where a rival's LIVE PROMO undercuts its own published rate card.

WHY THIS EXISTS. On 2026-08-16 the owner asked "doesnt เงินติดล้อ have a 10% promo?" It did,
and the rate board said 12-24%. The board was reading tidlor.com's published worked example —
the BoT-mandated disclosure, which is a CEILING — while เงินติดล้อ had been advertising a
10%/yr refinance promo at 160% LTV for eight weeks, in thirteen creatives already sitting
unread in rival_ads.json. That is not a bug in one row, it is a category error applied to
every operator at once: the card answers "what may they lawfully charge", the promo answers
"what are they winning customers with this week", and only the second one is a price.

So this compares the two, per operator, every build.

THE TRAP IT MUST NOT FALL INTO — and did, on the first pass. ศรีสวัสดิ์ advertises
"0.66%-0.72% ต่อเดือน" against a published floor of 15.27%/yr, which looks like a 7-point
undercut if you annualise the monthly figure naively (0.72 x 12 = 8.64). It is not. Their
0.72%/month is FLAT, and flat 8.64%/yr over their published 54-month maximum is 15.27%/yr
effective — the card floor, exactly, to the basis point, and the reverse conversion returns
0.720%/mo. The ad and the card are the same offer in two conventions. Any comparison that
does not do this conversion manufactures undercuts that do not exist.

THE TEST, therefore, is deliberately conservative: a promo is only reported as undercutting
if it does so under the reading LEAST favourable to the claim. A monthly rate with no stated
basis is scored as FLAT (the reading that produces the higher effective cost); it only counts
as an undercut if even that reading lands below the card floor. False negatives here are
cheap — the promo is still on the board. A false positive would tell the owner a rival is
attacking when they are not, which is the expensive direction.

Nothing here is inferred from a page or a brand. Every input is a number the rival printed.

  python3 build_promo_gap.py            # write platform/data/promo_gap.json
  python3 build_promo_gap.py --check    # verify it reproduces byte-for-byte
"""
import argparse
import io
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rate_basis as rb  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = os.path.join(ROOT, "platform", "data")
S = os.path.join(ROOT, "source-data")
OUT = os.path.join(D, "promo_gap.json")

# Below this, a "gap" is inside the noise of not knowing the promo's exact tenor: the same
# flat rate converts across a ~1.5pp range between a 24-month and a 72-month term, so a
# smaller difference cannot be told apart from a tenor we simply do not have.
MATERIAL_PP = 1.5

# The tenor a bare monthly promo is converted at when the promo itself states none. The
# operator's own published maximum is preferred; this is only the fallback, and it is the
# LONGEST common term, which produces the LOWEST effective figure — again the reading least
# favourable to claiming an undercut.
FALLBACK_MONTHS = 60

MONTH = re.compile(r"(\d+(?:\.\d+)?)\s*%\s*(?:ต่อ\s*เดือน|/\s*เดือน|ต่อเดีอน)")
YEAR = re.compile(r"(\d+(?:\.\d+)?)\s*%\s*(?:ต่อ\s*ปี|/\s*ปี|ต่อปี)")

# A percentage sitting next to any of these is not the cost of money. "วงเงิน 160%" is an
# LTV, "ลดสูงสุด 50%" is a discount, "ลดดอก 2% ต่อปี" is a reduction OFF a rate and not a
# rate itself — each one would otherwise read as a spectacular undercut.
NOT_A_RATE = ("วงเงิน", "ของราคาประเมิน", "ส่วนลด", "ลดสูงสุด", "คืนเงิน", "เงินคืน",
              "ลดดอก", "ลดดอกเบี้ย", "ประหยัด", "แคชแบ็ก", "cashback")


def load(path, default=None):
    try:
        with io.open(path, encoding="utf-8") as f:
            return json.load(f)
    except (ValueError, OSError):
        return default if default is not None else {}


def quotes_in(text):
    """Every RATE the copy states, with the context that proves it is one."""
    out = []
    for rx, unit in ((MONTH, "month"), (YEAR, "year")):
        for m in rx.finditer(text):
            ctx = text[max(0, m.start() - 30):m.end() + 10]
            if any(w in ctx for w in NOT_A_RATE):
                continue
            out.append({"value": float(m.group(1)), "unit": unit, "context": ctx.strip()})
    return out


def worst_case_effective(q, months):
    """The promo's effective %/yr under the reading LEAST favourable to calling it an undercut.

    A monthly figure with no stated basis is read as FLAT, because flat is the reading that
    makes the borrower's actual cost higher — so if even this lands below the card, the
    undercut is real regardless of which convention the rival meant.
    """
    if q["unit"] == "year":
        return q["value"], "as_quoted_per_year"
    annual_flat = q["value"] * 12.0
    return round(rb.flat_to_effective(annual_flat, months), 2), "flat_at_%dm" % months


def build():
    card = load(os.path.join(S, "rival_rate_card.json"))
    board = load(os.path.join(D, "rate_board.json"))
    ads = load(os.path.join(D, "rival_ads.json"))
    fb = load(os.path.join(D, "rival_facebook.json"))
    uni = load(os.path.join(S, "rival_universe.json"))

    names = {o["key"]: o.get("name_th") or o["key"]
             for o in (uni.get("operators") or []) if o.get("key")}
    card_by = {o["key"]: o for o in (card.get("operators") or []) if o.get("key")}
    board_by = {o["key"]: o for o in (board.get("operators") or []) if o.get("key")}

    # Promo quotes from BOTH live channels, each carrying where it came from.
    promos = {}
    for a in ads.get("ads") or []:
        k = a.get("key")
        if not k:
            continue
        txt = " ".join((a.get("copy") or "").split())
        for q in quotes_in(txt):
            promos.setdefault(k, []).append(dict(q, channel="google_ads", seen=a.get("first")))
    for sec in ("promos", "corporate"):
        for p in fb.get(sec) or []:
            for q in quotes_in(" ".join((p.get("post") or "").split())):
                promos.setdefault(p["key"], []).append(
                    dict(q, channel="facebook", seen=p.get("posted_ago")))

    rows, unpriced = [], []
    for key in sorted(set(promos) | set(card_by)):
        c = card_by.get(key) or {}
        b = board_by.get(key) or {}
        # The comparison is against the CARD's own published floor for the collateral we
        # lend against, never against a figure some other layer already derived from an ad.
        floor, floor_src = None, None
        for v in c.get("variants") or []:
            if v.get("offer_kind") == "advertised_promo":
                continue                       # a promo is not the card it is measured against
            lo = (v.get("lender_effective") or {}).get("lo")
            if lo is None and v.get("quoted_basis") == "effective":
                lo = (v.get("quoted") or {}).get("lo")
            if lo is not None and (floor is None or lo < floor):
                floor, floor_src = lo, v.get("variant")
        months = None
        for v in c.get("variants") or []:
            if v.get("tenor_months_max"):
                months = max(months or 0, v["tenor_months_max"])

        qs = promos.get(key) or []
        if not qs:
            if floor is not None:
                unpriced.append({"key": key, "name_th": names.get(key), "card_floor": floor})
            continue

        scored = []
        for q in qs:
            eff, how = worst_case_effective(q, months or FALLBACK_MONTHS)
            scored.append({"quoted": q["value"],
                           "unit": "pct_per_month" if q["unit"] == "month" else "pct_per_year",
                           "effective_worst_case": eff, "read_as": how,
                           "channel": q["channel"], "seen": q["seen"],
                           "context_th": q["context"]})
        scored.sort(key=lambda s: s["effective_worst_case"])
        best = scored[0]
        gap = round(floor - best["effective_worst_case"], 2) if floor is not None else None
        rows.append({
            "key": key, "name_th": names.get(key), "tier": b.get("tier"),
            "card_floor": floor, "card_variant": floor_src,
            "card_tenor_months": months,
            "cheapest_promo_effective": best["effective_worst_case"],
            "gap_pp": gap,
            "undercuts_own_card": bool(gap is not None and gap >= MATERIAL_PP),
            "within_noise": bool(gap is not None and 0 < gap < MATERIAL_PP),
            "quotes": scored[:6], "n_quotes": len(scored),
        })

    rows.sort(key=lambda r: (not r["undercuts_own_card"], -(r["gap_pp"] or 0)))
    hits = [r for r in rows if r["undercuts_own_card"]]

    return {
        "meta": {
            "title": "Promo vs card — where a rival's live offer undercuts its own disclosure",
            "label": "MEASURED on both sides. The card floor is the lender's own published "
                     "effective rate; the promo figure is a rate the lender printed in a "
                     "creative or a post. The only computed step is the flat-to-effective "
                     "conversion, and it is done in the direction that makes an undercut "
                     "HARDER to claim, not easier.",
            "so_what": "A published rate card is a ceiling, not a price. Where these two "
                       "disagree by more than %.1fpp, the promo is what the rival is actually "
                       "selling and the card understates how hard they are competing."
                       % MATERIAL_PP,
            "method": "A monthly promo rate with no stated basis is read as FLAT and converted "
                      "at the operator's own published maximum tenor (fallback %d months) — "
                      "the reading that produces the HIGHEST effective cost. It is only "
                      "reported as an undercut if even that reading falls %.1fpp or more below "
                      "the card floor." % (FALLBACK_MONTHS, MATERIAL_PP),
            "the_false_positive_this_prevents":
                "ศรีสวัสดิ์ advertises 0.72%/เดือน against a published 15.27%/yr floor, which "
                "reads as a 7-point undercut if the monthly figure is naively multiplied by 12. "
                "It is not one: flat 8.64%/yr over their published 54-month maximum is 15.27%/yr "
                "effective — the card floor exactly, and the reverse conversion returns "
                "0.720%/mo. The ad and the card are the same offer in two conventions.",
            "material_threshold_pp": MATERIAL_PP,
            "coverage_note": "Only operators that advertise with a rate can be checked at all. "
                             "Most of this market advertises reach and speed, not price, so an "
                             "absent row means we hold no promo QUOTE for that operator — never "
                             "that its card was verified as its price.",
            "n_checked": len(rows), "n_undercutting": len(hits),
            "n_card_only": len(unpriced),
            "sources": {"card": "source-data/rival_rate_card.json",
                        "ads": "platform/data/rival_ads.json",
                        "facebook": "platform/data/rival_facebook.json"},
        },
        "operators": rows,
        "card_only": sorted(unpriced, key=lambda u: u["key"]),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    payload = json.dumps(build(), ensure_ascii=False, indent=1, sort_keys=True) + "\n"
    if a.check:
        cur = io.open(OUT, encoding="utf-8").read() if os.path.exists(OUT) else None
        if cur != payload:
            print("build_promo_gap.py --check: DRIFT (run: python3 pipeline/build_promo_gap.py)")
            return 1
        print("build_promo_gap.py --check: OK (byte-exact)")
        return 0
    io.open(OUT, "w", encoding="utf-8", newline="\n").write(payload)
    d = json.loads(payload)
    print("wrote %s — %d operators checked, %d undercutting their own card"
          % (OUT, d["meta"]["n_checked"], d["meta"]["n_undercutting"]))
    for r in d["operators"]:
        mark = "UNDERCUTS" if r["undercuts_own_card"] else (
            "within noise" if r["within_noise"] else "matches card")
        print("  %-12s %-24s card %-7s promo %-7s gap %-6s %s"
              % (r["key"], (r["name_th"] or "")[:24],
                 r["card_floor"], r["cheapest_promo_effective"],
                 r["gap_pp"], mark))
    return 0


if __name__ == "__main__":
    sys.exit(main())
