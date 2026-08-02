#!/usr/bin/env python3
"""
build_commodity_history.py — retain World Bank Pink Sheet MONTHLY PRICE HISTORY for sparklines
================================================================================================
Today autox_enrich_loop.py's stage_commodities() reads the Pink Sheet's full monthly column per
commodity and throws away everything except the latest value + YoY (source-data/commodities.json,
platform/data/commodities.json via build_commodities.py). No chart of price history is drawable
anywhere in the product because the history itself is never retained. This script fixes that by
keeping a rolling window of monthly observations per series, so the app can draw sparklines.

Two modes:
  --refresh  (owner-side, needs the cached Pink Sheet xlsx): parses the "Monthly Prices" sheet
             with the EXACT SAME header/row contract as stage_commodities() in autox_enrich_loop.py
             — hdr=rows[4], data=rows[6:], match header names against the imported WB_COMMODITIES
             dict (never redefined here, so the two pipelines can't drift apart) — and writes
             source-data/commodity_history.json, a COMMITTED mirror carrying the last
             MONTHS_KEEP monthly observations for EVERY matched series (no hand-picked subset).
  (default)  network-free, deterministic: projects source-data/commodity_history.json verbatim
             into platform/data/commodity_history.json. THIS is the gated step — `--check` must
             reproduce it byte-for-byte. Exits 3 (SKIP, not FAIL) if the source-data mirror is
             absent, matching the house convention for network-pulled-input builders.

The xlsx itself is a network-pulled input (gitignored, ~575KB) and is looked for at the path
autox_enrich_loop.py's own CACHE constant would create (pipeline/cache/pinksheet.xlsx) as well as
the pipeline/.cache/pinksheet.xlsx path the file actually lands at on this box (both gitignored —
same file, harmless path variance between environments).

Usage:
  python3 build_commodity_history.py --refresh   # owner-side: cached xlsx -> source-data mirror
  python3 build_commodity_history.py             # source-data -> platform/data (gated)
  python3 build_commodity_history.py --check      # byte-compare (exit 3 if source-data absent)
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
S = os.path.join(ROOT, "source-data")
P = os.path.join(ROOT, "platform", "data")
SRC_OUT = os.path.join(S, "commodity_history.json")
OUT = os.path.join(P, "commodity_history.json")

# same file, two possible on-disk locations depending on environment (both gitignored).
XLSX_CANDIDATES = [
    os.path.join(HERE, ".cache", "pinksheet.xlsx"),
    os.path.join(HERE, "cache", "pinksheet.xlsx"),
]

MONTHS_KEEP = 60
SHEET_NAME = "Monthly Prices"

# reuse the enrichment loop's own header->label map — never redefine it here, so the two parsing
# paths can never silently drift apart (same pattern pull_osm_gapcheck.py uses for OSM_LAYERS).
from autox_enrich_loop import WB_COMMODITIES  # noqa: E402


def _numify(x):
    """Exact same numeric guard as autox_enrich_loop.stage_commodities()'s inline lambda."""
    s = str(x)
    return float(x) if s.replace(".", "", 1).replace("-", "").isdigit() else None


def dumps(obj):
    return json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _find_xlsx():
    for p in XLSX_CANDIDATES:
        if os.path.exists(p):
            return p
    return None


def refresh():
    """Parse the cached Pink Sheet xlsx -> the source-data/commodity_history.json payload."""
    xlsx = _find_xlsx()
    if not xlsx:
        sys.exit("build_commodity_history.py --refresh: no cached Pink Sheet xlsx found (looked "
                  "in: %s) — run autox_enrich_loop.py once (or place the file) first."
                  % ", ".join(XLSX_CANDIDATES))
    import openpyxl
    ws = openpyxl.load_workbook(xlsx, read_only=True, data_only=True)[SHEET_NAME]
    rows = [list(r) for r in ws.iter_rows(values_only=True)]
    hdr = rows[4]
    unit_row = rows[5]
    data = rows[6:]

    col_of = {}       # label -> column index
    header_of = {}     # label -> original Pink Sheet header string
    for j, n in enumerate(hdr):
        nm = str(n).strip() if n else ""
        if nm in WB_COMMODITIES:
            lab = WB_COMMODITIES[nm]
            col_of[lab] = j
            header_of[lab] = nm

    unmatched = sorted(set(WB_COMMODITIES.values()) - set(col_of))

    series = {}
    for lab in sorted(col_of):  # sort keys — never rely on dict/parse insertion order
        j = col_of[lab]
        vals = [_numify(r[j]) for r in data]
        valid_idx = [i for i, v in enumerate(vals) if v is not None]
        if not valid_idx:
            continue  # matched header, but the column is entirely empty — nothing to retain
        li = max(valid_idx)  # this series' own latest reported month (some lag the sheet's newest)
        lo = max(0, li - (MONTHS_KEEP - 1))
        months = [str(data[i][0]) for i in range(lo, li + 1)]
        values = [round(v, 3) if v is not None else None for v in vals[lo:li + 1]]
        unit = unit_row[j] if j < len(unit_row) else None
        series[lab] = {
            "header": header_of[lab],
            "unit": str(unit).strip() if unit else None,
            "months": months,
            "values": values,
        }

    vintage = max((s["months"][-1] for s in series.values()), default=None)

    payload = {
        "meta": {
            "generated_by": "pipeline/build_commodity_history.py --refresh",
            "source": "World Bank Pink Sheet (Commodity Markets), sheet '%s'" % SHEET_NAME,
            "source_page": "https://www.worldbank.org/en/research/commodity-markets",
            "label": ("MEASURED — World Bank Pink Sheet nominal-USD monthly prices. Last %d "
                      "monthly observations kept per series (for sparkline history; NOT the full "
                      "1960-present run stage_commodities() reads and discards). A series can end "
                      "before the sheet's newest month if the Pink Sheet itself stopped reporting "
                      "it — that is a real reporting gap, not a pull failure (see 'shrimp' below)."
                      % MONTHS_KEEP),
            "months_kept": MONTHS_KEEP,
            "vintage": vintage,
            "n_series": len(series),
            "unmatched": unmatched if unmatched else None,
            "unmatched_note": (
                "These WB_COMMODITIES labels have no exact header match in this sheet vintage. "
                "The contract is deliberately byte-identical to autox_enrich_loop.py's "
                "stage_commodities(), so a key is fixed in BOTH scripts or neither. ('Fishmeal' -> "
                "'Fish meal' was fixed that way on 2026-08-02, verified against the live sheet's "
                "row-5 header, which restored fishmeal's 60-month series to the commodities board.)"
            ) if unmatched else None,
        },
        "series": series,
    }
    return payload


def project():
    """Read source-data/commodity_history.json -> the platform/data payload (verbatim projection,
    no recomputation). Returns None if the source-data mirror is absent (SKIP, not FAIL)."""
    if not os.path.exists(SRC_OUT):
        return None
    with open(SRC_OUT, encoding="utf-8") as f:
        src = json.load(f)
    smeta = src.get("meta") or {}
    series = src.get("series") or {}
    return {
        "meta": {
            "generated_by": "pipeline/build_commodity_history.py",
            "source": smeta.get("source"),
            "source_page": smeta.get("source_page"),
            "label": smeta.get("label"),
            "months_kept": smeta.get("months_kept"),
            "vintage": smeta.get("vintage"),
            "n_series": smeta.get("n_series", len(series)),
            "unmatched": smeta.get("unmatched"),
            "unmatched_note": smeta.get("unmatched_note"),
            "provenance": (
                "Verbatim projection of source-data/commodity_history.json "
                "(pipeline/build_commodity_history.py --refresh, owner-side Pink Sheet parse). "
                "No recomputation — every month label and price carried through unchanged."
            ),
        },
        "series": series,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--refresh", action="store_true",
                    help="owner-side: parse the cached Pink Sheet xlsx into "
                         "source-data/commodity_history.json")
    ap.add_argument("--check", action="store_true",
                    help="byte-compare platform/data/commodity_history.json against a fresh "
                         "projection of source-data/commodity_history.json (exit 3 / SKIP if the "
                         "source-data mirror is absent)")
    args = ap.parse_args()

    if args.refresh:
        payload = refresh()
        text = dumps(payload)
        with open(SRC_OUT, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        print("wrote %s — %d series, vintage %s" %
              (SRC_OUT, len(payload["series"]), payload["meta"]["vintage"]))
        for lab in sorted(payload["series"]):
            sr = payload["series"][lab]
            print("  %-10s %3d months (%s .. %s)  header=%r unit=%r" %
                  (lab, len(sr["months"]), sr["months"][0], sr["months"][-1],
                   sr["header"], sr["unit"]))
        if payload["meta"]["unmatched"]:
            print("unmatched WB_COMMODITIES labels (no header match this vintage): %s" %
                  payload["meta"]["unmatched"])
        return

    data = project()

    if args.check:
        if data is None:
            print("CHECK SKIP: %s absent — commodity_history not byte-checkable" % SRC_OUT,
                  file=sys.stderr)
            sys.exit(3)
        text = dumps(data)
        if not os.path.exists(OUT):
            print("CHECK FAIL: %s does not exist" % OUT)
            sys.exit(1)
        with open(OUT, encoding="utf-8") as f:
            existing = f.read()
        if existing == text:
            print("CHECK OK: %s reproduces byte-for-byte (%d series, vintage %s)" %
                  (OUT, len(data["series"]), data["meta"]["vintage"]))
            sys.exit(0)
        print("CHECK FAIL: %s differs from a fresh build" % OUT)
        sys.exit(1)

    if data is None:
        print("SKIP: %s absent — nothing to build (run --refresh first)" % SRC_OUT,
              file=sys.stderr)
        sys.exit(3)

    text = dumps(data)
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    print("wrote %s — %d series, vintage %s" %
          (OUT, len(data["series"]), data["meta"]["vintage"]))


if __name__ == "__main__":
    main()
