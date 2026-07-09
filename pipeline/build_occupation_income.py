#!/usr/bin/env python3
"""
build_occupation_income.py — lowest-paid occupation nationally (portfolio risk, objective #1)

Network-free, deterministic. `province.html`'s "Income by occupation" panel (2026-07-03 (8))
already surfaces `source-data/household_income_by_province.json` per province, but there is no
NATIONAL read — a reader has to open all 77 province pages to notice which occupation category is
structurally the lowest-paid. This projects the same already-committed MEASURED file into one
small national-aggregate layer so Overview/Exposure can lead with a concrete callout (per
CLAUDE.md: "concrete facts, not abstract indices").

Input (MEASURED, NSO SES 2566 via the TMLI bridge, ingest_tmli.py):
  source-data/household_income_by_province.json
    provinces: { <Thai province name>: {Agriculture, FactoryWorkers, OfficeStaff, SMEOwners,
                                         Transport, avg_monthly_income} }  (THB/month)

Output: platform/data/occupation_income.json
  categories: one row per occupation category, each carrying:
    national_avg   MEASURED — unweighted mean of that category's value across all provinces
                   with a value (THB/month), rounded to the nearest THB.
    min_province / min_value   the single province with the LOWEST value for that category
                               (a concrete worst case, not just the average).
    max_province / max_value   the single province with the HIGHEST value.
  Sorted ascending by national_avg, so categories[0] is the lowest-paid occupation nationally.

GRACEFUL DEGRADE: if the source file is absent, ships meta.absent=true + an empty categories list
so the frontend callout hides itself without erroring. --check still byte-compares whatever was
last committed.

Run:
  python3 build_occupation_income.py            # write platform/data/occupation_income.json
  python3 build_occupation_income.py --check    # re-run, byte-compare against the committed file
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, "source-data", "household_income_by_province.json")
OUT = os.path.join(ROOT, "platform", "data", "occupation_income.json")

CATEGORIES = ("Agriculture", "FactoryWorkers", "OfficeStaff", "SMEOwners", "Transport")
LABEL = {
    "Agriculture": "Agriculture",
    "FactoryWorkers": "Factory workers",
    "OfficeStaff": "Office staff",
    "SMEOwners": "SME owners",
    "Transport": "Transport",
}


def _load():
    if not os.path.exists(SRC):
        return None
    with open(SRC, encoding="utf-8") as f:
        return json.load(f)


def build():
    src = _load()

    if src is None:
        meta = {
            "title": "Lowest-paid occupation nationally (portfolio risk, objective #1)",
            "generated_by": "pipeline/build_occupation_income.py",
            "deterministic": True,
            "network_free": True,
            "absent": True,
            "absent_reason": "missing source-data/household_income_by_province.json",
            "source": "NSO SES 2566 income-by-occupation via the TMLI bridge (ingest_tmli.py) — NOT FOUND",
            "provenance": "ABSENT — run pipeline/ingest_tmli.py to land the MEASURED NSO SES "
                          "income-by-occupation layer, then re-run this builder.",
            "n_provinces": 0,
        }
        return {"meta": meta, "categories": []}

    provs = src.get("provinces", {})
    rows = []
    for cat in CATEGORIES:
        vals = []  # (province, value)
        for prov, rec in provs.items():
            v = rec.get(cat)
            if isinstance(v, (int, float)):
                vals.append((prov, v))
        if not vals:
            continue
        avg = round(sum(v for _, v in vals) / len(vals))
        vals_sorted = sorted(vals, key=lambda t: (t[1], t[0]))
        min_prov, min_val = vals_sorted[0]
        max_prov, max_val = vals_sorted[-1]
        rows.append({
            "key": cat,
            "label": LABEL[cat],
            "n_provinces": len(vals),
            "national_avg": avg,
            "min_province": min_prov,
            "min_value": min_val,
            "max_province": max_prov,
            "max_value": max_val,
        })

    # worst (lowest-paid) first — deterministic tie-break by key
    rows.sort(key=lambda r: (r["national_avg"], r["key"]))

    meta = {
        "title": "Lowest-paid occupation nationally (portfolio risk, objective #1)",
        "generated_by": "pipeline/build_occupation_income.py",
        "deterministic": True,
        "network_free": True,
        "absent": False,
        "n_categories": len(rows),
        "sort": "worst-first (lowest national_avg first)",
        "source": "NSO SES 2566 income-by-occupation, via data.go.th / TMLI bridge "
                  "(pipeline/ingest_tmli.py); source-data/household_income_by_province.json.",
        "provenance": "MEASURED. national_avg/min_value/max_value are the unweighted mean/min/max "
                      "of that occupation category's MEASURED per-province monthly income across "
                      "all 77 provinces — no modeling or estimation.",
        "fields": {
            "national_avg": "MEASURED — unweighted mean across provinces, THB/month.",
            "min_province": "MEASURED — the single province with the lowest value for this "
                            "category (a concrete worst case, not just the national mean).",
            "max_province": "MEASURED — the single province with the highest value.",
        },
        "formula": {
            "national_avg": "round(sum(province values) / n_provinces)",
        },
        "measured_vs_estimated": "Every field here is MEASURED (NSO SES 2566) — this builder only "
                                 "aggregates, it does not model or estimate anything.",
        "caveats": [
            "NSO SES occupation-category incomes are province AVERAGES, not the AutoX borrower "
            "book — they read structural income-floor risk for that occupation, not realized PD.",
            "Unweighted mean across provinces (not population-weighted) — a small province counts "
            "the same as Bangkok.",
        ],
    }

    return {"meta": meta, "categories": rows}


def dumps(obj):
    return json.dumps(obj, ensure_ascii=False, indent=2) + "\n"


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true",
                    help="re-run and byte-compare against the committed JSON; exit 1 on drift")
    args = ap.parse_args()

    data = build()
    text = dumps(data)

    if args.check:
        if not os.path.exists(OUT):
            print("CHECK FAIL: %s does not exist" % OUT)
            sys.exit(1)
        with open(OUT, encoding="utf-8") as f:
            existing = f.read()
        if existing == text:
            print("CHECK OK: %s reproduces byte-for-byte (%d categories%s)" % (
                OUT, len(data["categories"]),
                ", ABSENT-state" if data["meta"].get("absent") else ""))
            sys.exit(0)
        print("CHECK FAIL: %s differs from a fresh build" % OUT)
        sys.exit(1)

    with open(OUT, "w", encoding="utf-8") as f:
        f.write(text)
    if data["meta"].get("absent"):
        print("wrote %s (ABSENT-state: %s)" % (OUT, data["meta"]["absent_reason"]))
        return
    print("wrote %s (%d categories, worst-first)" % (OUT, len(data["categories"])))
    for r in data["categories"]:
        print("  %-16s avg=%-7d min=%s (%d) max=%s (%d)" % (
            r["label"], r["national_avg"], r["min_province"], r["min_value"],
            r["max_province"], r["max_value"]))


if __name__ == "__main__":
    main()
