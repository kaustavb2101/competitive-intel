#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_rate_board.py — ONE comparable table of what every vehicle-refinance rival charges.

Answers the question the ads feed cannot: not "what are rivals saying" but "what do they
actually charge, on what basis, against what collateral, at what LTV" — with every rate
restated on a single basis so the numbers can be read down a column without misleading.

TWO SOURCES, DELIBERATELY KEPT APART AND LABELLED.
  * PUBLISHED (source-data/rival_rate_card.json) — standing rate cards the banks publish. The
    hire-purchase refinancers (SCB, ttb, CIMB, UOB, TISCO, Krungsri, KBank, KKP) all publish
    one, so their pricing is MEASURED from publication.
  * ADVERTISED (platform/data/rival_ads.json) — what operators actually put in creatives. The
    pure title lenders (MTC, TIDLOR, SAWAD, TURBO) do NOT publish a standing card; they price
    by campaign, so the only honest read of their pricing is what they advertise.
Neither is a substitute for the other and the board never silently merges them: every row
carries which it is, and a published card outranks an ad for the same operator.

THE ONE THING THIS TABLE IS FOR. Thai vehicle lending quotes two incompatible conventions:
โอนเล่ม (registration transferred) is advertised FLAT, ไม่โอนเล่ม (registration retained — the
AutoX product) is advertised REDUCING BALANCE. Flat 3.18%/yr and reducing 12%/yr look four
times apart and cost about the same. So every row is restated to reducing-balance %/yr, which
is the basis AutoX's own book accrues on, and the quoted figure is kept beside it so nothing
is hidden. The conversion is pipeline/rate_basis.py, validated against the pairs the lenders
themselves publish.

WHAT IS REFUSED, AND WHAT IS OFFERED INSTEAD. A rate whose basis is not written down is never
silently converted — assuming a basis would manufacture the exact error the board exists to
prevent. But a blank is a poor answer when only 7 of 770 tracked creatives state a basis at
all, which would leave the pure title lenders (our own peer group) as a column of nothing.
So an unstated rate is published BOTH ways: `effective_if_reducing` and `effective_if_flat`,
the two readings the quote could bear, with `basis: "unstated"` saying we do not know which.
Tidlor's "0.46% ต่อเดือน" is 5.52%/yr if it is reducing balance and 10.35%/yr if it is flat;
showing that spread is honest and useful, whereas picking one is neither. `effective` itself
stays reserved for rates whose basis IS established.

A flat rate with no tenor anywhere is likewise unconvertible; where the operator publishes a
maximum tenor for that product we convert at it and say so in `at_months` / `tenor_assumed`.

Deterministic and network-free: every date derives from the inputs' own stamps, never the wall
clock. `--check` byte-compares; exits 3 (SKIP) when rival_ads.json has not been built.

  python3 build_rate_board.py
  python3 build_rate_board.py --check
"""
import argparse
import io
import json
import os
import sys

import rate_basis

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IN_CARD = os.path.join(ROOT, "source-data", "rival_rate_card.json")
IN_UNI = os.path.join(ROOT, "source-data", "rival_universe.json")
IN_ADS = os.path.join(ROOT, "platform", "data", "rival_ads.json")
OUT = os.path.join(ROOT, "platform", "data", "rate_board.json")

# Per operator, the most distinct advertised rates worth a row. Beyond this the table stops
# being readable and starts being a log; the dropped ones are counted, never silently lost.
MAX_AD_ROWS = 5
# Advertised rates below this are teasers for something other than the loan's interest
# ("ฟรี 0%", a 0.1% fee), and above it they are not a lending rate at all.
AD_RATE_LO, AD_RATE_HI = 0.1, 36.0
# When an ad quotes a flat rate with no term, convert at the operator's own published maximum
# tenor if we have one, else this. 60 months is the modal Thai vehicle-loan term and the
# conversion is only mildly tenor-sensitive at these rates, but `tenor_assumed` still says so.
DEFAULT_TENOR = 60


def jload(p):
    with io.open(p, encoding="utf-8") as f:
        return json.load(f)


def ann(v, unit):
    """Restate a rate as %/yr. A monthly rate is x12 — nominal, never compounded."""
    if v is None:
        return None
    return rate_basis.per_month_to_per_year(v) if unit == "pct_per_month" else v


def effective_of(basis, lo, hi, lender_eff, months):
    """The reducing-balance restatement of one quote, plus where it came from.

    Order of preference is provenance, not convenience: the lender's own published effective
    rate beats anything we compute, because it carries their fee schedule and we do not have it.
    """
    if lender_eff and lender_eff.get("lo") is not None:
        return {"lo": lender_eff["lo"], "hi": lender_eff.get("hi"),
                "source": "lender", "at_months": None, "tenor_assumed": False}
    if basis == "effective":
        return {"lo": lo, "hi": hi, "source": "as_quoted",
                "at_months": None, "tenor_assumed": False}
    if basis == "flat":
        if not months:
            return None                     # honestly unconvertible — no term anywhere
        c_lo = rate_basis.flat_to_effective(lo, months)
        c_hi = rate_basis.flat_to_effective(hi, months) if hi is not None else None
        if c_lo is None:
            return None
        return {"lo": c_lo, "hi": c_hi, "source": "computed", "at_months": months,
                "tenor_assumed": False}
    return None                             # basis unstated -> refuse to guess


def published_rows(card, uni):
    rows = []
    for op in card.get("operators") or []:
        u = uni.get(op["key"]) or {}
        for var in op.get("variants") or []:
            q, qm = var.get("quoted") or {}, var.get("quoted_monthly") or {}
            unit = q.get("unit", "pct_per_year")
            lo, hi = ann(q.get("lo"), unit), ann(q.get("hi"), unit)
            basis = var.get("quoted_basis")
            months = var.get("tenor_months_max")
            eff = effective_of(basis, lo, hi, var.get("lender_effective"), months)
            rows.append({
                "key": op["key"],
                "operator": op.get("name_en") or op["key"],
                "name_th": op.get("name_th"),
                "owner": op.get("owner"),
                "tier": u.get("tier") or "bank",
                "loan_type": op.get("loan_type"),
                "source": "published",
                "source_kind": op.get("source_kind"),
                "citation": op.get("citation"),
                "confidence": op.get("confidence"),
                "variant": var.get("variant"),
                "collateral": var.get("collateral"),
                "quoted": {"lo": lo, "hi": hi, "basis": basis, "unit": "pct_per_year"},
                "quoted_monthly": ({"lo": qm.get("lo"), "hi": qm.get("hi")} if qm else None),
                "effective": eff,
                "effective_note": var.get("lender_effective_note"),
                "tenor_max": months,
                "tenor_min": var.get("tenor_months_min"),
                "ltv_pct": var.get("ltv_pct"),
                "ltv_note": var.get("ltv_note") or op.get("ltv_note"),
                "max_baht": var.get("max_baht"),
                "quote_th": var.get("quote_th"),
                "n_ads": None,
                "last_seen": None,
                "asof": op.get("verified"),
            })
    return rows


def conditions_observed(ads):
    """Per operator: the LTV and tenor its ads claim, read across ALL of them.

    Deliberately NOT restricted to ads that also quote a rate. Tidlor's "ให้วงเงินสูงสุด 160%"
    creatives carry no percentage rate at all, so scoping this to priced ads would drop the
    most aggressive advance rate in the market — higher than SCB's 140% and ttb's 120% — purely
    because it was advertised on its own. The claim is the competitive fact; whether it shares
    a creative with a rate is an accident of media planning.
    """
    out = {}
    for a in ads.get("ads") or []:
        copy = a.get("copy") or ""
        if not copy:
            continue
        o = out.setdefault(a["key"], {"ltv": None, "ltv_n": 0, "ltv_last": None,
                                      "tenor": None, "tenor_n": 0, "basis_n": 0})
        ltv = rate_basis.ltv_in(copy)
        if ltv is not None:
            o["ltv_n"] += 1
            if o["ltv"] is None or ltv > o["ltv"]:
                o["ltv"] = ltv
            if (a.get("last") or "") > (o["ltv_last"] or ""):
                o["ltv_last"] = a.get("last")
        tenor = rate_basis.tenor_in(copy)
        if tenor is not None:
            o["tenor_n"] += 1
            if o["tenor"] is None or tenor > o["tenor"]:
                o["tenor"] = tenor
        if rate_basis.basis_kind_in(copy):
            o["basis_n"] += 1
    return out


def both_readings(yr, months):
    """The two rates an unstated quote could mean, so neither has to be guessed.

    `yr` is already annualised. If the quote is reducing balance it IS the effective rate; if
    it is flat, the effective rate is what that flat rate converts to over `months`.
    """
    if yr is None:
        return None, None
    return yr, rate_basis.flat_to_effective(yr, months)


def advertised_rows(ads, uni, carded, tenor_hint):
    """One row per distinct rate an operator is currently advertising.

    The basis kind (flat vs reducing) is read from the ad's own rate line first, falling back
    to the rest of THAT creative's copy — never another creative, and never the operator's
    published card, because a lender runs both products and the whole point of the row is
    which one THIS creative is pricing.
    """
    rows, dropped = [], 0
    by_key = {}
    for a in ads.get("ads") or []:
        for r in a.get("rates") or []:
            v, basis = r.get("value"), r.get("basis")
            if v is None or not (AD_RATE_LO <= v <= AD_RATE_HI):
                continue
            line = r.get("line") or ""
            kind = rate_basis.basis_kind_in(line) or rate_basis.basis_kind_in(a.get("copy") or "")
            # (value, per-month-or-year, flat-or-reducing) is the identity of an offer. Two ads
            # quoting 0.66%/mo reducing are the same offer advertised twice, not two data points.
            sig = (v, basis, kind or "unstated")
            slot = by_key.setdefault(a["key"], {})
            cur = slot.get(sig)
            tenor = rate_basis.tenor_in(line) or rate_basis.tenor_in(a.get("copy") or "")
            ltv = rate_basis.ltv_in(line) or rate_basis.ltv_in(a.get("copy") or "")
            if cur is None:
                slot[sig] = {"n": 1, "last": a.get("last"), "line": line.strip(),
                             "tenor": tenor, "ltv": ltv}
            else:
                cur["n"] += 1
                if (a.get("last") or "") > (cur["last"] or ""):
                    cur["last"], cur["line"] = a.get("last"), line.strip()
                cur["tenor"] = cur["tenor"] or tenor
                cur["ltv"] = cur["ltv"] or ltv

    brands = dict((b["key"], b) for b in ads.get("brands") or [])
    for key in sorted(by_key):
        u = uni.get(key) or {}
        b = brands.get(key) or {}
        # Newest first, then cheapest — an exec reads the current offer, not the archive.
        offers = sorted(by_key[key].items(),
                        key=lambda kv: (kv[1]["last"] or "", -kv[1]["n"], -kv[0][0]),
                        reverse=True)
        if len(offers) > MAX_AD_ROWS:
            dropped += len(offers) - MAX_AD_ROWS
            offers = offers[:MAX_AD_ROWS]
        for (v, basis, kind), info in offers:
            unit = "pct_per_month" if basis == "month" else "pct_per_year"
            yr = ann(v, unit) if basis in ("month", "year") else None
            months = info["tenor"] or tenor_hint.get(key) or DEFAULT_TENOR
            eff = if_red = if_flat = None
            if yr is not None and kind in ("flat", "effective"):
                eff = effective_of(kind, yr, None, None, months)
            elif yr is not None:
                # Basis not disclosed. Publish both readings rather than a blank or a guess.
                if_red, if_flat = both_readings(yr, months)
            rows.append({
                "key": key,
                "operator": b.get("brand") or u.get("name_en") or key,
                "name_th": u.get("name_th") or b.get("name_th"),
                "owner": u.get("owner"),
                "tier": u.get("tier") or b.get("tier"),
                "loan_type": u.get("loan_type"),
                "source": "advertised",
                "source_kind": "ad",
                "citation": None,
                "confidence": "high" if kind else "basis_unstated",
                "variant": None,
                "collateral": None,
                "quoted": {"lo": yr, "hi": None, "basis": kind or "unstated",
                           "unit": "pct_per_year",
                           "as_quoted": v, "as_quoted_basis": basis},
                "quoted_monthly": ({"lo": v, "hi": None} if basis == "month" else None),
                "effective": eff,
                "effective_if_reducing": if_red,
                "effective_if_flat": if_flat,
                "effective_note": None,
                "tenor_max": months,
                "tenor_assumed": not info["tenor"],
                "tenor_min": None,
                "ltv_pct": info["ltv"],
                "ltv_note": None,
                "max_baht": None,
                "quote_th": info["line"][:180] or None,
                "n_ads": info["n"],
                "last_seen": info["last"],
                "asof": info["last"],
                "carded": key in carded,
            })
    return rows, dropped


def summarise(rows, cond, uni, ads):
    """One row per OPERATOR — the table an exec reads, with the detail rows behind it.

    The 24 offer rows answer "what exactly does ttb quote on a transferred book". This answers
    the question that gets asked first: who is in this market, what is their cheapest money,
    and how much will they lend against the car. Everything here is picked from the offer rows
    rather than recomputed, so the summary can never disagree with the detail.
    """
    brands = dict((b["key"], b) for b in ads.get("brands") or [])
    out = []
    for key in sorted(set(r["key"] for r in rows)):
        mine = [r for r in rows if r["key"] == key]
        pub = [r for r in mine if r["source"] == "published"]
        adv = [r for r in mine if r["source"] == "advertised"]
        u = uni.get(key) or {}
        c = cond.get(key) or {}
        b = brands.get(key) or {}
        # The comparable floor: the cheapest ESTABLISHED reducing-balance rate this operator
        # has on the board. Rows with an unstated basis are excluded on purpose — they cannot
        # be ranked against a known one without assuming the thing we refused to assume.
        withEff = [r for r in mine
                   if r.get("effective") and r["effective"].get("lo") is not None]
        effs = [r["effective"]["lo"] for r in withEff]
        # Carry the PROVENANCE of the floor alongside it. A 5.4% that the lender published and
        # a 5.4% we derived from a flat quote are not the same claim, and the table has to be
        # able to say which without the reader opening the detail rows.
        floor = min(withEff, key=lambda r: r["effective"]["lo"]) if withEff else None
        # SPLIT BY COLLATERAL, always. Several operators run both variants, and โอนเล่ม money
        # is structurally cheaper than ไม่โอนเล่ม money because the lender holds the book. A
        # single operator-level range blends 5.40% (CIMB, book transferred) with 18.65% (CIMB,
        # book retained) into "5.40-18.65%", which reads as one wildly-priced lender and hides
        # the only comparison that matters: ไม่โอนเล่ม is the column AutoX competes in.
        buckets = {}
        for r in withEff:
            coll = r.get("collateral")
            if not coll or coll == "unstated":
                # An advertised rate carries no collateral field of its own, so the operator's
                # product type is the best available read — and only when it is unambiguous.
                coll = "no_transfer" if r.get("loan_type") == "title_loan" else "unstated"
            lo = r["effective"]["lo"]
            hi = r["effective"].get("hi") or lo
            b = buckets.setdefault(coll, {"lo": lo, "hi": hi, "source": r["effective"]["source"]})
            if lo < b["lo"]:
                b["lo"], b["source"] = lo, r["effective"]["source"]
            if hi > b["hi"]:
                b["hi"] = hi
        # LTV: the highest claim from either source. Published cards state it exactly;
        # ads state it loudly. Both are the operator's own claim about the same thing.
        ltvs = [r["ltv_pct"] for r in mine if r.get("ltv_pct") is not None]
        tenors = [r["tenor_max"] for r in mine if r.get("tenor_max")]
        collat = sorted(set(r["collateral"] for r in pub if r.get("collateral")
                            and r["collateral"] != "unstated"))
        row0 = pub[0] if pub else (adv[0] if adv else {})
        out.append({
            "key": key,
            "operator": row0.get("operator") or key,
            "name_th": row0.get("name_th") or u.get("name_th"),
            "owner": row0.get("owner") or u.get("owner"),
            "tier": row0.get("tier") or u.get("tier"),
            "loan_type": row0.get("loan_type") or u.get("loan_type"),
            "is_us": key == "AUTOX",
            "effective_lo": min(effs) if effs else None,
            "effective_hi": max(effs) if effs else None,
            "by_collateral": buckets or None,
            "effective_source": floor["effective"]["source"] if floor else None,
            "effective_at_months": floor["effective"].get("at_months") if floor else None,
            "quoted_lo": floor["quoted"]["lo"] if floor else None,
            "quoted_basis": floor["quoted"]["basis"] if floor else None,
            # When nothing is established, the two readings of its cheapest advertised quote —
            # so the operator still says something rather than showing a dash.
            "if_reducing": min([r["effective_if_reducing"] for r in mine
                                if r.get("effective_if_reducing") is not None] or [None]),
            "if_flat": min([r["effective_if_flat"] for r in mine
                            if r.get("effective_if_flat") is not None] or [None]),
            "ltv_pct": max(ltvs) if ltvs else None,
            "tenor_max": max(tenors) if tenors else None,
            "collateral": collat,
            "has_published": bool(pub),
            "n_offers": len(mine),
            "n_ads_priced": sum(r["n_ads"] or 0 for r in adv),
            "n_ads_basis_stated": c.get("basis_n", 0),
            "n_creatives": b.get("n_creatives"),
            "last_seen": max([r["last_seen"] for r in adv if r.get("last_seen")] or [None]),
            "source": ("published+ads" if pub and adv else "published" if pub else "ads"),
            "confidence": row0.get("confidence"),
            "citation": row0.get("citation"),
        })
    # Cheapest established money first; operators with no established rate sink to the bottom
    # rather than sorting as if they were free.
    out.sort(key=lambda r: (r["effective_lo"] is None, r["effective_lo"] or 0, r["key"]))
    return out


def build():
    if not os.path.exists(IN_CARD):
        return None
    card = jload(IN_CARD)
    uni = {}
    if os.path.exists(IN_UNI):
        for o in (jload(IN_UNI).get("operators") or []):
            uni[o.get("key")] = o
    ads = jload(IN_ADS) if os.path.exists(IN_ADS) else {"meta": {}, "ads": [], "brands": []}

    carded = set(o["key"] for o in (card.get("operators") or []))
    # A rate-card key that is not in the census means the operator appears TWICE on the board —
    # once from its card and once from its ads — under two keys that never reconcile, and the
    # summary silently double-counts the field. Cheap to check, invisible to debug.
    if uni:
        orphan = sorted(carded - set(uni))
        if orphan:
            raise SystemExit(
                "rival_rate_card.json keys absent from rival_universe.json: %s\n"
                "Use the census key for an operator already in it, or add the operator there."
                % ", ".join(orphan))
    # An operator's published maximum tenor is the best available term for converting one of
    # its OWN ads that omits the term — better than a market default, and stated either way.
    tenor_hint = {}
    for o in card.get("operators") or []:
        for v in o.get("variants") or []:
            if v.get("tenor_months_max"):
                tenor_hint[o["key"]] = max(tenor_hint.get(o["key"], 0), v["tenor_months_max"])

    rows = published_rows(card, uni)
    ad_rows, ad_dropped = advertised_rows(ads, uni, carded, tenor_hint)
    rows.extend(ad_rows)
    cond = conditions_observed(ads)
    for r in ad_rows:                       # an operator's LTV claim belongs on its rows
        c = cond.get(r["key"]) or {}
        if r["ltv_pct"] is None:
            r["ltv_pct"] = c.get("ltv")
    summary = summarise(rows, cond, uni, ads)

    # How often does an ad actually say which basis it is quoting? This is the honesty stat:
    # if it is low, every advertised headline in this market is unreadable as stated, which is
    # itself the finding a pricing decision needs.
    ad_stated = sum(1 for r in ad_rows if r["quoted"]["basis"] in ("flat", "effective"))

    # THE COMPARABLE SLICE — the only band that can honestly be read against our own book:
    # ไม่โอนเล่ม, borrower keeps the registration. Rows whose collateral the lender did not
    # state are EXCLUDED rather than assumed in; including them pulled โอนเล่ม money into this
    # band and made the market look 5pp cheaper than it is against our product.
    comp = [r["by_collateral"]["no_transfer"] for r in summary
            if (r.get("by_collateral") or {}).get("no_transfer")]
    comp_lo = min((c["lo"] for c in comp), default=None)
    comp_hi = max((c["hi"] for c in comp), default=None)

    # The headline contrast: cheapest FLAT headline in the market vs what it really costs.
    flats = [r for r in rows if r["quoted"]["basis"] == "flat"
             and r["quoted"].get("lo") is not None and r.get("effective")]
    cheap = min(flats, key=lambda r: r["quoted"]["lo"]) if flats else None

    out = {
        "meta": {
            "title": "Rate board — every vehicle-refinance operator, restated on one basis",
            "label": "MIXED PROVENANCE, labelled per row. 'published' rows are MEASURED from the lender's own rate card. 'advertised' rows are MEASURED from creatives in Google's Ads Transparency Center. Effective figures marked source 'lender' or 'as_quoted' are the lender's own; 'computed' is ESTIMATED by us from the flat quote and the stated tenor.",
            "asof_card": (card.get("meta") or {}).get("verified"),
            "asof_ads": (ads.get("meta") or {}).get("pulled"),
            "basis_note": "Every rate is restated to NOMINAL reducing-balance %/yr — monthly x 12, never compounded. That is AutoX's own accrual convention and the one Thai lenders publish (CIMB: '0.83% ต่อเดือน ... ลดต้นลดดอก 9.95% ต่อปี'; 0.83 x 12 = 9.96).",
            "the_trap": (card.get("meta") or {}).get("the_trap"),
            "so_what": (card.get("meta") or {}).get("so_what"),
            "refusal_note": "A rate whose basis is not written down is published with basis 'unstated' and NO effective figure. Guessing the basis would manufacture the exact error this board exists to prevent. A flat rate with no term is likewise left unconverted unless the operator publishes a maximum tenor for that product, in which case `at_months` says which term was used.",
            "conversion": "pipeline/rate_basis.py, validated against the flat<->effective pairs ttb, CIMB, SCB, UOB and TISCO publish themselves; it reproduces ttb's pair to 0.01pp and all eight within 0.33pp.",
            "n_rows": len(rows),
            "n_published": len(rows) - len(ad_rows),
            "n_advertised": len(ad_rows),
            "n_ads_basis_stated": ad_stated,
            "n_ad_rows_dropped": ad_dropped,
            "n_operators": len(set(r["key"] for r in rows)),
            "n_creatives_scanned": len(ads.get("ads") or []),
            "n_creatives_basis_stated": sum(1 for c in cond.values() for _ in range(c["basis_n"])),
            "disclosure_note": "Of the creatives tracked in the last 90 days, almost none state whether the rate they quote is flat or reducing balance. That is the single most important thing to know about this table: rival ADVERTISED rates are, as advertised, not comparable to each other or to our book. The published bank rate cards are, which is why they are carried separately.",
            "comparable_effective": ({"lo": comp_lo, "hi": comp_hi} if comp_lo is not None else None),
            "cheapest_flat": ({
                "key": cheap["key"], "operator": cheap["operator"],
                "quoted": cheap["quoted"]["lo"],
                "effective": cheap["effective"]["lo"],
                "at_months": cheap["effective"].get("at_months"),
            } if cheap else None),
            "sources": {
                "card": "source-data/rival_rate_card.json",
                "ads": "platform/data/rival_ads.json",
            },
        },
        "operators": summary,
        "rows": rows,
    }
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    out = build()
    if out is None:
        print("SKIP: source-data/rival_rate_card.json absent")
        return 3
    txt = json.dumps(out, ensure_ascii=False, indent=1, sort_keys=True) + "\n"
    if a.check:
        if not os.path.exists(OUT):
            print("SKIP: %s not built yet" % OUT)
            return 3
        with io.open(OUT, encoding="utf-8") as f:
            cur = f.read()
        if cur != txt:
            print("DRIFT: %s differs from a fresh build" % OUT)
            return 1
        print("OK: %s reproduces byte-for-byte" % OUT)
        return 0
    with io.open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write(txt)
    m = out["meta"]
    print("wrote %s — %d rows (%d published, %d advertised) over %d operators"
          % (OUT, m["n_rows"], m["n_published"], m["n_advertised"], m["n_operators"]))
    if m["cheapest_flat"]:
        c = m["cheapest_flat"]
        at = ("computed at %d months" % c["at_months"]) if c["at_months"] else "lender's own figure"
        print("  cheapest flat headline: %s %.2f%%/yr flat = %.2f%%/yr effective (%s)"
              % (c["operator"], c["quoted"], c["effective"], at))
    print("  advertised rates stating their basis: %d of %d"
          % (m["n_ads_basis_stated"], m["n_advertised"]))
    print("  creatives scanned: %d, of which state a basis: %d"
          % (m["n_creatives_scanned"], m["n_creatives_basis_stated"]))
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    sys.exit(main())
