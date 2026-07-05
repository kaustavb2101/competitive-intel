#!/usr/bin/env python3
"""
build_fuel_prices.py — project the live Bangchak retail fuel-price pull into platform/data
=============================================================================================
`source-data/fuel_prices.json` (pipeline/pull_fuel_prices.py, refreshed daily by
.github/workflows/data-fuel-prices.yml from Bangchak's public oil-price API) has sat
uncommitted-to-any-view since it first landed — nothing in platform/data or app.js reads it.

Diesel price tracks the cost of running a pickup/farm vehicle; gasohol tracks motorcycles —
both are AutoX's dominant title-loan collateral types, so a fuel-price move is a real, cheap,
daily macro-pressure signal on borrower cash flow. This builder does no math: it validates the
committed source and re-projects it verbatim (same numbers, byte-for-byte) into
platform/data/fuel_prices.json, the shape app.js's other lazy-loaded Home-tab layers use.

INPUT:  source-data/fuel_prices.json  {meta, headline:{diesel,gasohol95,...}, fuels:{...}}
OUTPUT: platform/data/fuel_prices.json — meta (+generated_by, +provenance) + headline + fuels,
        every number carried through unchanged (no fabrication, no recomputation).

Usage:
  python3 build_fuel_prices.py            # write platform/data/fuel_prices.json
  python3 build_fuel_prices.py --check    # byte-compare (exit 3 / SKIP if source absent)
"""
import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(ROOT)
SRC = os.path.join(REPO, "source-data", "fuel_prices.json")
OUT = os.path.join(REPO, "platform", "data", "fuel_prices.json")

# sane bound for a Thai pump price — catches a malformed/garbage pull rather than shipping it.
MIN_THB_L, MAX_THB_L = 10.0, 100.0


class BadFuelDataError(Exception):
    """Source values fall outside a sane THB/litre range — malformed pull, not real drift."""


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
    headline = src.get("headline") or {}
    fuels = src.get("fuels") or {}

    diesel = headline.get("diesel")
    gasohol = headline.get("gasohol95")
    if diesel is None or gasohol is None:
        raise BadFuelDataError("headline.diesel/gasohol95 missing from source-data/fuel_prices.json")
    for label, v in (("diesel", diesel), ("gasohol95", gasohol)):
        if not (MIN_THB_L <= v <= MAX_THB_L):
            raise BadFuelDataError(
                "headline.%s = %r THB/L is outside the sane %g-%g range — looks malformed, "
                "not shipping it" % (label, v, MIN_THB_L, MAX_THB_L))

    return {
        "meta": {
            "generated_by": "build_fuel_prices.py",
            "source": smeta.get("source", "Bangchak retail oil-price API"),
            "label": smeta.get("label", "MEASURED — live Thai retail fuel prices (THB/litre)"),
            "pulled": smeta.get("pulled"),
            "unit": smeta.get("unit", "THB/litre"),
            "n_fuels": smeta.get("n_fuels", len(fuels)),
            "provenance": (
                "Verbatim projection of source-data/fuel_prices.json (pipeline/pull_fuel_prices.py, "
                "refreshed daily by .github/workflows/data-fuel-prices.yml). No recomputation — "
                "every price carried through unchanged."
            ),
            "note": smeta.get("note", ""),
            "collateral_read": (
                "Diesel = pickup/farm-vehicle title-loan borrowers; gasohol = motorcycle-title "
                "borrowers. Rising pump prices compress those borrowers' disposable income."
            ),
        },
        "headline": headline,
        "fuels": fuels,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true",
                    help="re-run and byte-compare against the committed JSON; exit 1 on drift "
                         "(exit 3 / SKIP when source-data/fuel_prices.json is absent)")
    args = ap.parse_args()

    try:
        data = build()
    except BadFuelDataError as e:
        print("CHECK FAIL: %s" % e, file=sys.stderr)
        sys.exit(1)

    if args.check:
        if data is None:
            print("CHECK SKIP: source-data/fuel_prices.json absent — fuel_prices not byte-checkable",
                  file=sys.stderr)
            sys.exit(3)
        text = dumps(data)
        if not os.path.exists(OUT):
            print("CHECK FAIL: %s does not exist" % OUT)
            sys.exit(1)
        with open(OUT, encoding="utf-8") as f:
            existing = f.read()
        if existing == text:
            print("CHECK OK: %s reproduces byte-for-byte (diesel=%s, gasohol95=%s)" %
                  (OUT, data["headline"].get("diesel"), data["headline"].get("gasohol95")))
            sys.exit(0)
        print("CHECK FAIL: %s differs from a fresh build" % OUT)
        sys.exit(1)

    if data is None:
        print("SKIP: source-data/fuel_prices.json absent — nothing to build", file=sys.stderr)
        sys.exit(3)

    text = dumps(data)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(text)
    print("wrote %s (diesel=%s THB/L, gasohol95=%s THB/L)" %
          (OUT, data["headline"].get("diesel"), data["headline"].get("gasohol95")))


if __name__ == "__main__":
    main()
