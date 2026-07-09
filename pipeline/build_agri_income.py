#!/usr/bin/env python3
"""
build_agri_income.py — per-province agriculture-worker income floor (portfolio risk, objective #1)

Network-free, deterministic. Mirrors build_factory_income.py's pattern for a different NSO SES
occupation column. The Simulator's crop-price/rainfall what-if (computeSim() in app.js) already
models an ESTIMATED agri-stress proxy per province (price + drought hazard × crop dependence); this
adds a MEASURED context layer alongside it — WHICH agri-relevant provinces already sit below the
national agriculture-worker income floor, independent of the price/rain scenario.

Input (MEASURED, NSO SES 2566 via the TMLI bridge, ingest_tmli.py):
  source-data/household_income_by_province.json
    provinces: { <Thai province name>: {Agriculture, ...} }  (THB/month)

Output: platform/data/agri_income_by_province.json
  national_avg          MEASURED — unweighted mean of Agriculture income across all provinces with a value.
  provinces[<name>]:
    agri_income           MEASURED THB/month (NSO SES 2566).
    ratio_to_national     agri_income / national_avg, rounded 3dp — <1 means below the national floor.

GRACEFUL DEGRADE: if the source file is absent, ships meta.absent=true + an empty provinces dict so
the frontend read hides itself without erroring. --check still byte-compares whatever was last
committed.

Run:
  python3 build_agri_income.py            # write platform/data/agri_income_by_province.json
  python3 build_agri_income.py --check    # re-run, byte-compare against the committed file
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, "source-data", "household_income_by_province.json")
OUT = os.path.join(ROOT, "platform", "data", "agri_income_by_province.json")

CATEGORY = "Agriculture"


def _load():
    if not os.path.exists(SRC):
        return None
    with open(SRC, encoding="utf-8") as f:
        return json.load(f)


def build():
    src = _load()

    if src is None:
        meta = {
            "title": "Agriculture-worker income floor by province (portfolio risk, objective #1)",
            "generated_by": "pipeline/build_agri_income.py",
            "deterministic": True,
            "network_free": True,
            "absent": True,
            "absent_reason": "missing source-data/household_income_by_province.json",
            "source": "NSO SES 2566 income-by-occupation via the TMLI bridge (ingest_tmli.py) — NOT FOUND",
            "provenance": "ABSENT — run pipeline/ingest_tmli.py to land the MEASURED NSO SES "
                          "income-by-occupation layer, then re-run this builder.",
            "n_provinces": 0,
            "national_avg": None,
        }
        return {"meta": meta, "provinces": {}}

    provs_src = src.get("provinces", {})
    rows = []  # (province, value)
    for prov, rec in provs_src.items():
        v = rec.get(CATEGORY)
        if isinstance(v, (int, float)):
            rows.append((prov, v))
    rows.sort(key=lambda t: t[0])  # deterministic order: province name

    if not rows:
        meta = {
            "title": "Agriculture-worker income floor by province (portfolio risk, objective #1)",
            "generated_by": "pipeline/build_agri_income.py",
            "deterministic": True,
            "network_free": True,
            "absent": True,
            "absent_reason": "source-data/household_income_by_province.json has no %s values" % CATEGORY,
            "source": "NSO SES 2566 income-by-occupation via the TMLI bridge (ingest_tmli.py)",
            "provenance": "ABSENT",
            "n_provinces": 0,
            "national_avg": None,
        }
        return {"meta": meta, "provinces": {}}

    national_avg = round(sum(v for _, v in rows) / len(rows))

    provinces = {}
    for prov, v in rows:
        provinces[prov] = {
            "agri_income": v,
            "ratio_to_national": round(v / national_avg, 3),
        }

    meta = {
        "title": "Agriculture-worker income floor by province (portfolio risk, objective #1)",
        "generated_by": "pipeline/build_agri_income.py",
        "deterministic": True,
        "network_free": True,
        "absent": False,
        "n_provinces": len(provinces),
        "national_avg": national_avg,
        "source": "NSO SES 2566 income-by-occupation, via data.go.th / TMLI bridge "
                  "(pipeline/ingest_tmli.py); source-data/household_income_by_province.json.",
        "provenance": "MEASURED. agri_income is the NSO SES 2566 Agriculture-occupation monthly "
                      "income for that province; national_avg is the unweighted mean across all "
                      "provinces with a value; ratio_to_national is a pure derived ratio — no modeling.",
        "fields": {
            "agri_income": "MEASURED — NSO SES 2566 average monthly agriculture-occupation income, THB.",
            "ratio_to_national": "MEASURED (derived ratio) — agri_income / national_avg, 3dp. "
                                 "<1.0 means this province's agriculture-worker income floor sits below "
                                 "the national average.",
        },
        "formula": {
            "national_avg": "round(sum(province Agriculture values) / n_provinces)",
            "ratio_to_national": "round(agri_income / national_avg, 3)",
        },
        "measured_vs_estimated": "Every field here is MEASURED (NSO SES 2566) — this builder only "
                                 "aggregates and divides, it does not model or estimate anything.",
        "caveats": [
            "NSO SES occupation-category income is a province AVERAGE, not the AutoX borrower "
            "book — it reads structural income-floor risk for agriculture households in that "
            "province, not realized PD.",
            "Unweighted across provinces (not population-weighted).",
            "Distinct from crop_stress.json's price/drought-driven agri_stress proxy — this is a "
            "static income-floor context, not a price or weather scenario.",
        ],
    }

    return {"meta": meta, "provinces": provinces}


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
            print("CHECK OK: %s reproduces byte-for-byte (%d provinces%s)" % (
                OUT, len(data["provinces"]),
                ", ABSENT-state" if data["meta"].get("absent") else ""))
            sys.exit(0)
        print("CHECK FAIL: %s differs from a fresh build" % OUT)
        sys.exit(1)

    with open(OUT, "w", encoding="utf-8") as f:
        f.write(text)
    if data["meta"].get("absent"):
        print("wrote %s (ABSENT-state: %s)" % (OUT, data["meta"]["absent_reason"]))
        return
    n_below = sum(1 for p in data["provinces"].values() if p["ratio_to_national"] < 1.0)
    print("wrote %s (%d provinces, national_avg=%d THB/mo, %d below the national floor)" % (
        OUT, len(data["provinces"]), data["meta"]["national_avg"], n_below))


if __name__ == "__main__":
    main()
