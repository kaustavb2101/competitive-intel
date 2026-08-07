#!/usr/bin/env python3
"""
build_farmgate_platform.py — project the daily Thai farm-gate prices into platform/data
=============================================================================================
NOT to be confused with `build_farmgate_prices.py`, which is the upstream step: it distils the
raw NABC pull into `source-data/farmgate_prices.json`. This one is the downstream half — it
projects that committed file into `platform/data/`, which is the only directory the app and the
live board can read.

WHY IT EXISTS
-------------
The Live board's "Farm income" group has been showing "Rice · world price" — the World Bank Pink
Sheet, a MONTHLY GLOBAL proxy in $/mt — while the real thing, a DAILY Thai farm-gate price in
฿/tonne, has been pulled every morning and left in source-data where nothing can see it. The
executive freshness readout was therefore reporting the retired proxy as the farm-income signal
and showing no sign that a better, fresher, domestic one existed. `build_crop_stress.py` already
switched to the farm-gate series internally; the board never did.

This is what a borrower's crop actually sells for, which is the number that decides whether a farm
household can service a title loan. The world price is a different quantity in a different currency
on a different clock.

This builder does no math: it validates the committed source and re-projects it verbatim, every
price carried through unchanged.

INPUT:  source-data/farmgate_prices.json  {meta, commodities:{rice,...}, crop_yoy:{...}}
OUTPUT: platform/data/farmgate_prices.json — same numbers, plus provenance.

Usage:
  python3 build_farmgate_platform.py            # write platform/data/farmgate_prices.json
  python3 build_farmgate_platform.py --check    # byte-compare (exit 3 / SKIP if source absent)
"""
import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(ROOT)
SRC = os.path.join(REPO, "source-data", "farmgate_prices.json")
OUT = os.path.join(REPO, "platform", "data", "farmgate_prices.json")

# Sane bounds PER UNIT — NABC quotes each commodity in its own trade unit, not a common one
# (paddy per tonne, cassava/maize/palm/rubber per kg, coconut per hundred fruit). A single band
# across all of them is wrong in both directions: it rejects a real ฿3.75/kg cassava price and
# would wave through a ฿17,738 number that had silently switched to per-kg. Bands are wide on
# purpose — this is a garbage-pull tripwire, not a forecast. An unrecognised unit is not rejected
# (NABC may add a commodity), but must still be a positive number.
UNIT_BOUNDS = {
    "บาท/ตัน": (100.0, 500000.0),      # THB per tonne
    "บาท/กก.": (0.1, 1000.0),          # THB per kg
    "บาท/ร้อยผล": (10.0, 100000.0),    # THB per hundred fruit
}


class BadFarmgateDataError(Exception):
    """Source values fall outside a sane THB/tonne range — malformed pull, not real drift."""


def _load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def dumps(obj):
    return json.dumps(obj, ensure_ascii=False, indent=2) + "\n"


def build():
    if not os.path.exists(SRC):
        return None  # honest absent — no pull yet, nothing to project

    src = _load(SRC)
    smeta = src.get("meta") or {}
    commodities = src.get("commodities") or {}
    crop_yoy = src.get("crop_yoy") or {}

    if not commodities:
        raise BadFarmgateDataError("no commodities in source-data/farmgate_prices.json")
    if "rice" not in commodities:
        # Rice is the headline the board reads and the only crop with full 77-province coverage.
        raise BadFarmgateDataError("rice missing from source-data/farmgate_prices.json")

    for key, c in sorted(commodities.items()):
        price = (c or {}).get("price")
        unit = (c or {}).get("unit")
        if price is None:
            raise BadFarmgateDataError("commodities.%s has no price" % key)
        if not price > 0:
            raise BadFarmgateDataError("commodities.%s.price = %r is not positive" % (key, price))
        bounds = UNIT_BOUNDS.get(unit)
        if bounds and not (bounds[0] <= price <= bounds[1]):
            raise BadFarmgateDataError(
                "commodities.%s.price = %r %s is outside the sane %g-%g range for that unit — "
                "looks malformed (a unit change would do this), not shipping it"
                % (key, price, unit, bounds[0], bounds[1]))

    return {
        "meta": {
            "title": smeta.get("title", "Measured Thai farm-gate crop prices"),
            "generated_by": "build_farmgate_platform.py",
            "source": smeta.get("source", "NABC Agricultural Data Service (agriapi.nabc.go.th)"),
            "label": smeta.get("label", "MEASURED — Thai farm-gate prices for raw farm commodities"),
            "pulled": smeta.get("pulled"),
            "vintage": smeta.get("vintage"),
            "unit": "บาท/ตัน (THB/tonne)",
            "n_commodities": len(commodities),
            "provenance": (
                "Verbatim projection of source-data/farmgate_prices.json "
                "(pipeline/build_farmgate_prices.py, refreshed daily by "
                ".github/workflows/data-nabc-prices.yml). No recomputation — every price carried "
                "through unchanged."
            ),
            "not_the_world_price": (
                "This is the DOMESTIC Thai farm-gate price in ฿/tonne, updated daily. It is not "
                "the World Bank Pink Sheet rice quote shown beside it on the Live board, which is "
                "a GLOBAL price in $/mt on a monthly vintage. Different quantity, currency and "
                "clock — do not read them as two versions of one number."
            ),
            "borrower_read": (
                "What a farm household's crop actually sells for is what decides whether it can "
                "service a title loan. A falling farm-gate price is portfolio pressure before it "
                "is ever a delinquency."
            ),
        },
        "commodities": commodities,
        "crop_yoy": crop_yoy,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true",
                    help="re-run and byte-compare against the committed JSON; exit 1 on drift "
                         "(exit 3 / SKIP when source-data/farmgate_prices.json is absent)")
    args = ap.parse_args()

    try:
        data = build()
    except BadFarmgateDataError as e:
        print("CHECK FAIL: %s" % e, file=sys.stderr)
        sys.exit(1)

    if args.check:
        if data is None:
            print("CHECK SKIP: source-data/farmgate_prices.json absent — farmgate_prices not "
                  "byte-checkable", file=sys.stderr)
            sys.exit(3)
        text = dumps(data)
        if not os.path.exists(OUT):
            print("CHECK FAIL: %s does not exist" % OUT)
            sys.exit(1)
        with open(OUT, encoding="utf-8") as f:
            existing = f.read()
        if existing == text:
            print("CHECK OK: %s reproduces byte-for-byte (rice=%s %s)" %
                  (OUT, data["commodities"]["rice"].get("price"),
                   data["commodities"]["rice"].get("unit")))
            sys.exit(0)
        print("CHECK FAIL: %s differs from a fresh build" % OUT)
        sys.exit(1)

    if data is None:
        print("SKIP: source-data/farmgate_prices.json absent — nothing to build", file=sys.stderr)
        sys.exit(3)

    text = dumps(data)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(text)
    print("wrote %s (%d commodities, rice=%s %s, as of %s)" %
          (OUT, len(data["commodities"]), data["commodities"]["rice"].get("price"),
           data["commodities"]["rice"].get("unit"),
           data["commodities"]["rice"].get("latest_date")))


if __name__ == "__main__":
    main()
