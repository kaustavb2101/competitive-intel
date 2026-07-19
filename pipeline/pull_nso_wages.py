#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pull_nso_wages.py — NSO Labour Force Survey average monthly wage of employees, by REGION x
INDUSTRY x QUARTER (table LFS_02_20545_18, สำนักงานสถิติแห่งชาติ / National Statistical Office).

Pulls the full measured series from the NSO CKAN catalog API and lands a DISTILLED
source-data/nso_wages.json (committed). This is the wage-anchor input: it exists to sanity-check
the app's ESTIMATED provincial occupation-income layer (build_occupation_income*.py), which
currently reads too high for provincial white-collar workers. Nothing here feeds any composite.

WHAT IS MEASURED: every (year, quarter, region, industry) cell NSO publishes in this table — up to
8 regions (7 NSO regions + the ทั่วประเทศ national row) x up to 28 industries. One industry,
ไม่ทราบ ("unknown"), is a genuine outlier/junk row — kept in this raw pull for completeness (nothing
hidden), but the downstream build (build_nso_wage_anchor.py) excludes it. VALUE is stored EXACTLY as
the string in the CSV (no float-parse here) so a byte-for-byte re-parse of the cached raw CSV always
reproduces this file; rounding/averaging happens only in the downstream build.

FLOW (network — run from a host that can reach catalogapi.nso.go.th; verified reachable, HTTP 200,
from Kaustav's Thai IP):
  1. GET the full-table CSV in one shot (no pagination / resource resolution needed).
  2. Parse header-by-name (never a fixed column index), distil every row, sort deterministically.
  3. Cache the raw CSV verbatim in the gitignored source-data/.nso_wage_raw/ scratch dir (audit +
     --check re-parse).

DETERMINISM / PROVENANCE:
  - `pulled` comes ONLY from --stamp (required for a real write); no other wall clock is used, so a
    re-run against the same upstream with the same --stamp is byte-identical.
  - Fails loudly and writes nothing if fewer than 6 distinct regions or fewer than 10 distinct
    industries parse (never demote the honest layer with a junk file).

Run:
  python3 pull_nso_wages.py --stamp 2026-07-18     # real pull + write
  python3 pull_nso_wages.py                        # default --stamp = today (embedded verbatim)
  python3 pull_nso_wages.py --dry-run              # fetch + parse + validate only, no write
  python3 pull_nso_wages.py --check                # OFFLINE re-parse of the cached raw CSV
"""
import argparse
import csv
import datetime
import io
import json
import os
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PIPE = os.path.dirname(os.path.abspath(__file__))

OUT = os.path.join(ROOT, "source-data", "nso_wages.json")
RAW_DIR = os.path.join(ROOT, "source-data", ".nso_wage_raw")
RAW_FILE = os.path.join(RAW_DIR, "LFS_02_20545_18.csv")
TABLE = "LFS_02_20545_18"
CSV_URL = "https://catalogapi.nso.go.th/api/index?table=%s&format=csv" % TABLE
UA = {"User-Agent": "Mozilla/5.0"}
MIN_REGIONS = 6
MIN_INDUSTRIES = 10


def _get(url):
    req = urllib.request.Request(url, headers=UA)
    return urllib.request.urlopen(req, timeout=90).read()   # default SSL context


def _parse_csv(raw_bytes):
    """Parse the raw CSV bytes into distilled row dicts. Header resolved by name, never index."""
    text = raw_bytes.decode("utf-8-sig", errors="replace")
    all_rows = [[c.strip() for c in r] for r in csv.reader(io.StringIO(text)) if any(r)]
    if not all_rows:
        sys.exit("pull_nso_wages.py: empty CSV from %s" % CSV_URL)
    hdr = all_rows[0]
    need = ("YEAR", "QUARTER", "REGION", "INDUSTRY", "VALUE")
    ix = {h: i for i, h in enumerate(hdr)}
    if not all(k in ix for k in need):
        sys.exit("pull_nso_wages.py: unexpected CSV header: %s" % hdr)
    rows = []
    for r in all_rows[1:]:
        if len(r) <= max(ix[k] for k in need):
            continue
        rows.append({
            "year": r[ix["YEAR"]],
            "quarter": r[ix["QUARTER"]],
            "region": r[ix["REGION"]],
            "industry": r[ix["INDUSTRY"]],
            "value": r[ix["VALUE"]],
        })
    rows.sort(key=lambda d: (d["year"], d["quarter"], d["region"], d["industry"]))
    return rows


def _validate(rows):
    regions = sorted(set(r["region"] for r in rows))
    industries = sorted(set(r["industry"] for r in rows))
    years = sorted(set(r["year"] for r in rows))
    if len(regions) < MIN_REGIONS:
        sys.exit("pull_nso_wages.py: only %d distinct regions parsed (<%d) - abort, writing nothing."
                 % (len(regions), MIN_REGIONS))
    if len(industries) < MIN_INDUSTRIES:
        sys.exit("pull_nso_wages.py: only %d distinct industries parsed (<%d) - abort, writing nothing."
                 % (len(industries), MIN_INDUSTRIES))
    return regions, industries, years


def _assemble(rows, regions, industries, years, stamp):
    return {
        "meta": {
            "title": "NSO Labour Force Survey - average monthly wage of employees by region x industry x quarter",
            "generated_by": "pipeline/pull_nso_wages.py",
            "label": ("MEASURED — NSO Labour Force Survey average monthly wage of employees "
                      "(บาท/เดือน) by region × industry × quarter; table LFS_02_20545_18, "
                      "สำนักงานสถิติแห่งชาติ."),
            "source": CSV_URL,
            "dataset_table": TABLE,
            "unit": "baht/month",
            "pulled": stamp,
            "regions": regions,
            "industries": industries,
            "years": years,
            "n_rows": len(rows),
            "provenance": "MEASURED. Raw CSV cached verbatim in the gitignored "
                          "source-data/.nso_wage_raw/ scratch dir for audit + --check re-parse. "
                          "VALUE is stored exactly as the CSV string here (no float-parse); "
                          "industry \"ไม่ทราบ\" (unknown) is a junk/outlier row kept for completeness "
                          "and excluded downstream by build_nso_wage_anchor.py.",
            "consumer": "pipeline/build_nso_wage_anchor.py (vintage pick + SES-bucket projection).",
        },
        "rows": rows,
    }


def build_live(stamp, dry_run=False):
    """Network pull: download the full-table CSV, cache raw, parse + validate + distil."""
    os.makedirs(RAW_DIR, exist_ok=True)
    raw = _get(CSV_URL)
    rows = _parse_csv(raw)
    regions, industries, years = _validate(rows)
    if dry_run:
        print("dry-run: rows=%d regions=%d industries=%d years=%s..%s"
              % (len(rows), len(regions), len(industries), years[0], years[-1]))
        return None
    with open(RAW_FILE, "wb") as f:
        f.write(raw)
    return _assemble(rows, regions, industries, years, stamp)


def _dumps(data):
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def main():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:
            pass
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stamp", default=datetime.date.today().isoformat(),
                    help="YYYY-MM-DD pull date embedded in meta.pulled (default: today)")
    ap.add_argument("--dry-run", action="store_true",
                    help="fetch + parse + validate only; no raw cache write, no distilled JSON write")
    ap.add_argument("--check", action="store_true",
                    help="OFFLINE: re-parse the cached raw CSV and byte-compare against "
                         "source-data/nso_wages.json; exit 1 on drift, exit 3 SKIP if the "
                         "committed file or the gitignored raw scratch is absent")
    args = ap.parse_args()

    if args.check:
        if not os.path.exists(RAW_FILE) or not os.path.exists(OUT):
            print("pull_nso_wages.py --check: SKIP (committed nso_wages.json or gitignored raw "
                  "scratch source-data/.nso_wage_raw/ absent - network-pulled input, not drift)")
            sys.exit(3)
        prev = json.load(open(OUT, encoding="utf-8"))
        raw = open(RAW_FILE, "rb").read()
        rows = _parse_csv(raw)
        regions, industries, years = _validate(rows)
        data = _assemble(rows, regions, industries, years, prev["meta"]["pulled"])
        if _dumps(data) != open(OUT, encoding="utf-8").read():
            sys.exit("pull_nso_wages.py --check: nso_wages.json drifted from a fresh parse of the "
                     "cached raw CSV - re-run python3 pipeline/pull_nso_wages.py")
        print("pull_nso_wages.py --check: OK (byte-exact from cached raw)")
        return

    if args.dry_run:
        build_live(args.stamp, dry_run=True)
        return

    data = build_live(args.stamp)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(_dumps(data))
    print("wrote %s" % OUT)
    print("  rows=%d regions=%d industries=%d years=%s..%s"
          % (len(data["rows"]), len(data["meta"]["regions"]), len(data["meta"]["industries"]),
             data["meta"]["years"][0], data["meta"]["years"][-1]))


if __name__ == "__main__":
    main()
