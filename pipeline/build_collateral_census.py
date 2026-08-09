#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_collateral_census.py — a MEASURED market price for the collateral we lend against.

WHY THIS EXISTS
---------------
382,735 accounts are secured on vehicles, and until now nothing in the platform said what any of
those vehicles is worth on the open market. The only external anchor was the BoT UVPI (EC_EI_040):
monthly, national, aggregate, and carrying exactly three series — car, truck, overall. There is NO
motorcycle series in it. Motorcycles are 127,628 accounts, the single largest collateral type in the
book, so a third of the book was carried at an appraised value with nothing measured to check it
against. `vehicle_types.MC.eval_avg` was a number no outside source could confirm or contradict.

This closes that. pull_collateral_census.py harvests five venues; this projects them into one price
board and joins it onto the book, so every brand and age band we lend on gets a market read next to
the value we booked it at.

THE TWO STAGES, AND WHY THEY ARE SPLIT
--------------------------------------
Identical in shape to the loan-tape pair (ingest_real_tape.py -> build_tape_layers.py), for the same
reason: the raw input is far too large to commit, so the determinism gate cannot see it.

  --aggregate   Reads source-data/census/*.jsonl (gitignored, ~500 MB) and writes the small committed
                aggregate source-data/staging/collateral_census_agg.json. NOT gate-checked — its
                input is off-repo, exactly like ingest_real_tape.py.
  (default)     Reads that committed aggregate and writes platform/data/collateral_census.json.
                Deterministic, network-free, --check-gated. Everything downstream of staging IS
                gated, which is the property that matters.

WHAT IS MEASURED AND WHAT IS NOT — read this before quoting a number from it
---------------------------------------------------------------------------
MEASURED  Every price. They are observed listings and auction lots, counted, not modelled. Each cell
          carries its own n and the venues it came from.
MEASURED  eval_avg — our own appraised value, straight from the loan tape.
ESTIMATED The BRAND MAPPING onto the tape's collateral classes. The tape says "TOYOTA PU"; a venue
          says brand "Toyota", model "HILUX VIGO". Deciding those are the same collateral class is a
          judgement, so the mapping is declared in TAPE_BRANDS below rather than inferred, and the
          output labels it. The prices under it stay measured; the bucketing is the estimate.
ESTIMATED The retail-to-auction RECOVERY CORRIDOR. Retail ask and auction opening price are not the
          same instrument — one is what a seller hopes for, the other is where bidding starts. The
          ratio is a corridor, not a realised recovery rate, and it is named that way.

A NOTE ON THE ANCHOR YEAR. Vehicle age is computed against the newest auction date present IN THE
DATA, never against wall clock. A builder that reads today's date produces a different file tomorrow
from the same input, which would fail --check for a reason that has nothing to do with the data.
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import statistics as st
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CENSUS = os.path.join(ROOT, "source-data", "census")
STAGING = os.path.join(ROOT, "source-data", "staging", "collateral_census_agg.json")
OUT = os.path.join(ROOT, "platform", "data", "collateral_census.json")
TAPE = os.path.join(ROOT, "platform", "data", "tape_real.json")

# A cell smaller than this is not published. Three listings of a model do not establish its price,
# and a median over three numbers invites more confidence than it can carry.
MIN_CELL = 8

# The tape's own age bands, reproduced exactly so the join lands on the same buckets the book uses.
AGE_BANDS = [(0, 5, "1.<=5 yr."), (5, 10, "2.(5-10]yr."), (10, 12, "3.(10-12]yr."),
             (12, 15, "4.(12-15]yr."), (15, 18, "5.(15-18]yr."), (18, 20, "6.(18-20]yr."),
             (20, 25, "7.(20-25]yr."), (25, 999, "8.>25 yr.")]

# ESTIMATED mapping — see the header. Each tape collateral class lists the (brand, model-substring)
# rules that identify it in venue data. A None model matches any model of that brand. Order matters:
# the FIRST matching rule wins, so the specific classes (HONDA WAVE) are declared before the general
# one (HONDA), or every Wave would be swallowed by the brand-level bucket.
#
# The third element is the BODY the class is made of, and it is not decoration — it is the control
# that stops the join producing nonsense. The first build of this file mapped bare "HONDA" to any
# Honda and reported the class at a retail median of ฿738,500 against an auction median of ฿39,000.
# Neither number was wrong; they were different vehicles. one2car sells only cars, the auction feed
# is 74% motorcycles, and Honda is the one marque in Thailand that sells both in volume. So a class
# only ever pools listings of its own body type, and the one class whose body genuinely cannot be
# resolved is excluded from the book join rather than published with a plausible-looking ratio.
#
# Every other marque here is single-body in the Thai market: Yamaha sells no cars, and Toyota,
# Isuzu, Mitsubishi, Nissan and Mazda sell no motorcycles.
MOTO, CAR, MIXED = "moto", "car", "mixed"
TAPE_BRANDS = [
    ("HONDA WAVE",    [("HONDA", "WAVE")], MOTO),
    ("HONDA PCX",     [("HONDA", "PCX")], MOTO),
    ("TOYOTA PU",     [("TOYOTA", "HILUX"), ("TOYOTA", "VIGO"), ("TOYOTA", "REVO"),
                       ("TOYOTA", "TIGER"), ("TOYOTA", "MIGHTY-X")], CAR),
    ("ISUZU PU",      [("ISUZU", "D-MAX"), ("ISUZU", "DMAX"), ("ISUZU", "SPACECAB"),
                       ("ISUZU", "TFR"), ("ISUZU", "RODEO")], CAR),
    ("MITSUBISHI PU", [("MITSUBISHI", "TRITON"), ("MITSUBISHI", "STRADA"),
                       ("MITSUBISHI", "L200")], CAR),
    ("NISSAN PU",     [("NISSAN", "NAVARA"), ("NISSAN", "FRONTIER"), ("NISSAN", "BIG-M")], CAR),
    # Bare HONDA is the tape's leftover Honda bucket after Wave and PCX are broken out, and it holds
    # BOTH Honda cars and the remaining Honda bikes — visible in the tape itself, where eval_avg
    # RISES from ฿63,928 at <=5 years to ฿163,409 at 15-18 years. Collateral does not appreciate;
    # the mix is shifting from bikes to cars as the band ages. No single market price is comparable
    # to a blended appraisal, so this class is priced on the board and withheld from book_check.
    ("HONDA",         [("HONDA", None)], MIXED),
    ("YAMAHA",        [("YAMAHA", None)], MOTO),
    ("TOYOTA",        [("TOYOTA", None)], CAR),
    ("ISUZU",         [("ISUZU", None)], CAR),
    ("MITSUBISHI",    [("MITSUBISHI", None)], CAR),
    ("NISSAN",        [("NISSAN", None)], CAR),
    ("MAZDA",         [("MAZDA", None)], CAR),
]
CLASS_BODY = {cls: body for cls, _, body in TAPE_BRANDS}

# Which venue answers which question. Retail ask and auction opening are different instruments and
# are never pooled into one median — pooling them would manufacture a number that is neither.
RETAIL = {"one2car", "kaidee", "taladrod", "truck2hand"}
AUCTION = {"auct"}


# ---------------------------------------------------------------------- shared normalisation
def _num(v):
    try:
        f = float(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return None
    return f if f > 0 else None


def _year(v):
    try:
        y = int(str(v)[:4])
    except (TypeError, ValueError):
        return None
    # A bare Buddhist-era stamp reads 543 years into the future; fold anything past 2400.
    y = y - 543 if y > 2400 else y
    return y if 1980 < y < 2100 else None


def _norm(s):
    return " ".join(str(s or "").upper().split())


def _tape_class(brand, model, body):
    """Match a venue row onto a tape collateral class, refusing any cross-body match."""
    b, m = _norm(brand), _norm(model)
    for cls, rules, cls_body in TAPE_BRANDS:
        if cls_body != MIXED and cls_body != body:
            continue                      # a Honda Civic is never HONDA WAVE, whatever the string says
        for rb, rm in rules:
            if b == rb and (rm is None or rm in m):
                return cls
    return None


def _band(age):
    for lo, hi, name in AGE_BANDS:
        if lo < age <= hi or (lo == 0 and age <= hi):
            return name
    return None


def _stats(xs):
    xs = sorted(xs)
    n = len(xs)
    q = st.quantiles(xs, n=4) if n >= 4 else [xs[0], st.median(xs), xs[-1]]
    return dict(n=n, median=round(st.median(xs)), p25=round(q[0]), p75=round(q[2]))


# ---------------------------------------------------------------------- stage 1: aggregate
def _iter_harvest():
    """Every harvested row, normalised to one shape regardless of which venue wrote it."""
    for fn in sorted(os.listdir(CENSUS)):
        if not fn.endswith(".jsonl"):
            continue
        path = os.path.join(CENSUS, fn)
        for line in open(path, encoding="utf-8"):
            try:
                r = json.loads(line)
            except ValueError:
                continue
            venue = r.get("venue")
            if venue == "auct":
                yield dict(venue=venue, brand=r.get("Brand_Name"), model=r.get("Model_Name"),
                           year=_year(r.get("Manufacturing_Year")),
                           price=_num(r.get("Sales_Price")), sold=_num(r.get("Sold_Price")),
                           km=_num(r.get("Mile")), date=str(r.get("Auction_Date") or "")[:10],
                           body=(MOTO if r.get("Asset_Type") == "รถจักรยานยนต์" else CAR))
            else:
                yield dict(venue=venue, brand=r.get("brand"), model=r.get("model"),
                           year=_year(r.get("year")), price=_num(r.get("price")), sold=None,
                           km=_num(r.get("km") or r.get("mileage")), date="",
                           body=_venue_body(venue, r))


def _venue_body(venue, r):
    """Resolve moto vs car from whatever each venue happens to say. Each rule is the venue's own
    vocabulary, checked against live data rather than guessed — a guessed Thai string returns silent
    false matches, which here would mean pricing a pickup off motorcycle listings."""
    if venue == "one2car":
        return CAR                                    # a car-and-pickup marketplace; no bikes at all
    if venue == "taladrod":
        return CAR                                    # schc.aspx is the car classifieds
    if venue == "kaidee":
        return MOTO if "มอเตอร์ไซค์" in str(r.get("categoryName") or "") else CAR
    if venue == "truck2hand":
        return MOTO if "motorbike" in str(r.get("subCategory1Slug") or "") else CAR
    return CAR


def aggregate():
    if not os.path.isdir(CENSUS):
        print("build_collateral_census.py: %s is absent — run pull_collateral_census.py first."
              % CENSUS, file=sys.stderr)
        return 3
    cells = collections.defaultdict(lambda: collections.defaultdict(list))
    venues = collections.Counter()
    anchor, rows, priced = "", 0, 0
    for r in _iter_harvest():
        rows += 1
        venues[r["venue"]] += 1
        if r["date"] > anchor:
            anchor = r["date"]                    # newest date IN the data, never wall clock
        cls = _tape_class(r["brand"], r["model"], r["body"])
        if not (cls and r["year"] and r["price"]):
            continue
        priced += 1
        kind = "retail" if r["venue"] in RETAIL else "auction"
        key = (cls, r["body"], r["year"])
        cells[key][kind].append(r["price"])
        if r["sold"]:
            cells[key]["realised"].append(r["sold"])
        if r["km"] and r["km"] < 400000:
            cells[key]["km"].append(r["km"])

    out = {}
    for (cls, body, year), by in sorted(cells.items()):
        keep = {k: v for k, v in by.items() if len(v) >= MIN_CELL}
        if not keep:
            continue
        out["%s|%s|%d" % (cls, body, year)] = {k: _stats(v) for k, v in sorted(keep.items())}
    agg = dict(
        meta=dict(
            generated_by="pipeline/build_collateral_census.py --aggregate",
            note=("Stage-1 aggregate of the gitignored venue harvests. Committed so that stage 2 is "
                  "reproducible from the repo alone; the ~500 MB of raw rows never enters git."),
            anchor_date=anchor, rows_read=rows, rows_priced=priced, min_cell=MIN_CELL,
            venues=dict(sorted(venues.items()))),
        cells=out)
    os.makedirs(os.path.dirname(STAGING), exist_ok=True)
    with open(STAGING, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(agg, ensure_ascii=False, indent=1, sort_keys=True) + "\n")
    print("aggregated %d rows (%d priced & classified) from %d venues -> %d cells\n  -> %s"
          % (rows, priced, len(venues), len(out), STAGING))
    return 0


# ---------------------------------------------------------------------- stage 2: project
def build():
    if not os.path.exists(STAGING):
        print("build_collateral_census.py: %s is absent — run --aggregate first." % STAGING,
              file=sys.stderr)
        return 3
    agg = json.load(open(STAGING, encoding="utf-8"))
    tape = json.load(open(TAPE, encoding="utf-8")) if os.path.exists(TAPE) else {}
    anchor_year = _year(agg["meta"].get("anchor_date")) or 0

    # ---- the price board: one row per collateral class x body x model year
    board = []
    for key in sorted(agg["cells"]):
        cls, body, year = key.rsplit("|", 2)
        c = agg["cells"][key]
        row = dict(collateral_class=cls, body=body, year=int(year),
                   age=(anchor_year - int(year)) if anchor_year else None)
        for kind in ("retail", "auction", "realised", "km"):
            if kind in c:
                row[kind] = c[kind]
        # ESTIMATED, and named as such in meta: retail ask and auction opening are different
        # instruments, so their ratio is a corridor to reason inside, not a recovery rate.
        if "retail" in c and "auction" in c and c["retail"]["median"]:
            row["recovery_corridor"] = round(c["auction"]["median"] / c["retail"]["median"], 3)
        board.append(row)

    # ---- the join that makes this worth building: our appraised value vs the measured market
    book, withheld = [], []
    cb = (tape.get("collateral_brands") or {})
    for cls, bands in sorted(cb.items()):
        body = CLASS_BODY.get(cls)
        if body is None:
            withheld.append(dict(collateral_class=cls, reason="not a vehicle class — no venue prices it"))
            continue
        if body == MIXED:
            withheld.append(dict(
                collateral_class=cls, n_accounts=sum(b.get("n") or 0 for b in bands.values()),
                reason=("the class blends cars and motorcycles, so its eval_avg is a blended "
                        "appraisal with no single comparable market price. Priced on the board by "
                        "body; deliberately NOT reduced to one ratio here.")))
            continue
        for band, cell in sorted(bands.items()):
            ev = cell.get("eval_avg")
            if not ev:
                continue
            pref = "%s|%s|" % (cls, body)
            years = [int(k.rsplit("|", 1)[1]) for k in agg["cells"] if k.startswith(pref)]
            in_band = [y for y in years if anchor_year and _band(anchor_year - y) == band]
            if not in_band:
                continue
            ret = [x for x in (agg["cells"][pref + str(y)].get("retail") for y in in_band) if x]
            auc = [x for x in (agg["cells"][pref + str(y)].get("auction") for y in in_band) if x]
            if not (ret or auc):
                continue
            r = dict(collateral_class=cls, body=body, age_band=band, n_accounts=cell.get("n"),
                     eval_avg=round(ev), dpd30p_pct=cell.get("dpd30p_pct"),
                     model_years=sorted(in_band))
            if ret:
                r["market_retail"] = round(st.median([x["median"] for x in ret]))
                r["retail_n"] = sum(x["n"] for x in ret)
                r["eval_vs_retail"] = round(ev / r["market_retail"], 3)
            if auc:
                r["market_auction"] = round(st.median([x["median"] for x in auc]))
                r["auction_n"] = sum(x["n"] for x in auc)
                r["eval_vs_auction"] = round(ev / r["market_auction"], 3)
            book.append(r)

    doc = dict(
        meta=dict(
            title="Used-collateral price census — measured market value of the collateral we lend on",
            generated_by="pipeline/build_collateral_census.py",
            label=("MEASURED prices (observed listings and auction lots, every cell carries its own n, "
                   "nothing below %d published) x MEASURED eval_avg from the real loan tape. "
                   "The mapping of venue brand/model onto the tape's collateral classes is an "
                   "ESTIMATED classification, and the retail-to-auction recovery corridor is an "
                   "ESTIMATED corridor, not a realised recovery rate." % MIN_CELL),
            why=("BoT UVPI publishes car, truck and overall only — there is no motorcycle series, and "
                 "motorcycles are the largest collateral type in the book at 127,628 accounts. This is "
                 "the first measured price anchor that layer has ever had."),
            anchor_date=agg["meta"].get("anchor_date"),
            anchor_note="Vehicle age is measured against the newest auction date IN THE DATA, not wall clock.",
            venues=agg["meta"].get("venues"), rows_read=agg["meta"].get("rows_read"),
            min_cell=MIN_CELL, n_board=len(board), n_book_cells=len(book),
            body_note=("A collateral class only ever pools listings of its own body type. Honda is "
                       "the one marque selling both cars and motorcycles in Thailand at volume, so "
                       "the tape's bare HONDA class cannot be reduced to one market price — it is "
                       "withheld from book_check rather than published with a plausible ratio."),
            tape_source=(tape.get("meta") or {}).get("source")),
        board=board, book_check=book, withheld=withheld)
    payload = json.dumps(doc, ensure_ascii=False, indent=1, sort_keys=True) + "\n"
    return doc, payload


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--aggregate", action="store_true",
                    help="stage 1: read the gitignored harvests -> committed staging aggregate")
    ap.add_argument("--check", action="store_true",
                    help="stage 2: rebuild and byte-compare against the committed output")
    a = ap.parse_args(argv)
    if a.aggregate:
        return aggregate()
    built = build()
    if isinstance(built, int):
        return built
    doc, payload = built
    if a.check:
        if not os.path.exists(OUT):
            print("build_collateral_census.py: %s absent — nothing to check." % OUT, file=sys.stderr)
            return 3
        cur = open(OUT, encoding="utf-8", newline="").read()
        if cur != payload:
            print("build_collateral_census.py: FAIL — output is not byte-identical.", file=sys.stderr)
            return 2
        print("build_collateral_census.py: OK — %d board rows, %d book cells reproduce byte-exact."
              % (len(doc["board"]), len(doc["book_check"])))
        return 0
    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(payload)
    print("build_collateral_census.py: %d price-board rows, %d book cells -> %s"
          % (len(doc["board"]), len(doc["book_check"]), OUT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
