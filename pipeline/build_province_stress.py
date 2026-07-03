#!/usr/bin/env python3
"""
build_province_stress.py — PORTFOLIO RISK (objective #1): combined province structural-stress
index, blending household leverage (DTI) with the local labour market (unemployment).

Network-free, deterministic. Joins two already-committed MEASURED layers that today live in
separate views (per docs/IMPROVEMENT_BACKLOG.md — "Combine household DTI + unemployment into
one province portfolio-stress index"):

  platform/data/household_risk_by_province.json   debt_to_income + its 0-100 percentile
                                                    (stress_index), built by build_household_risk.py
                                                    from NSO SES 2566 debt/income                 [MEASURED]
  source-data/unemployment_by_province.json        unemployment_rate, %, NSO Labour Force Survey  [MEASURED]

Per province it computes:
  debt_to_income          carried through from household_risk_by_province.json.        [MEASURED]
  dti_percentile          carried through (household_risk's stress_index).              [ESTIMATED
                          0-100 percentile rank of debt_to_income across provinces]
  unemployment_rate       carried through from unemployment_by_province.json, percent.  [MEASURED]
  unemployment_percentile 0-100 percentile rank of unemployment_rate across the same
                          province set (same method as dti_percentile, for comparability). [ESTIMATED]
  composite_stress        0.5*dti_percentile + 0.5*unemployment_percentile.             [ESTIMATED —
                          equal-weighted blend of two percentile ranks; an editorial choice, NOT
                          calibrated to realized default/loss. See meta.caveats.]

Only provinces present in BOTH measured inputs are included (clean join; both source files
already use competitive-intel's canonical 77 Thai-name province keys).

GRACEFUL DEGRADE: if either input is missing/absent, writes an ABSENT-state (empty provinces
list, meta.absent=true) so the frontend lens can hide itself without erroring.

Run:
  python3 build_province_stress.py            # write platform/data/province_stress_index.json
  python3 build_province_stress.py --check    # re-run, byte-compare against the committed file
"""
import argparse
import json
import os
import sys

from regionmap import REGION

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, "source-data")
DATA = os.path.join(ROOT, "platform", "data")
OUT = os.path.join(DATA, "province_stress_index.json")

HH_FILE = os.path.join(DATA, "household_risk_by_province.json")
UNEMP_FILE = os.path.join(SRC, "unemployment_by_province.json")

W_DTI = 0.5
W_UNEMP = 0.5


def _load(path):
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _percentile_rank(value, sorted_values):
    """0..100 percentile rank of `value` within `sorted_values` (ascending), fraction of
    values strictly below plus half of those equal (mid-rank ties). Deterministic. With a
    single value the rank is 50.0 (mid). Same method as build_household_risk.py, reused here
    so the two percentile ranks being blended are directly comparable."""
    n = len(sorted_values)
    if n <= 1:
        return 50.0
    below = sum(1 for v in sorted_values if v < value)
    equal = sum(1 for v in sorted_values if v == value)
    return round(100.0 * (below + 0.5 * equal) / n, 2)


def _absent(reason):
    meta = {
        "title": "Combined province structural-stress index — household DTI + unemployment "
                 "(portfolio risk, objective #1)",
        "generated_by": "pipeline/build_province_stress.py",
        "deterministic": True,
        "network_free": True,
        "absent": True,
        "absent_reason": reason,
        "provenance": "ABSENT — needs both platform/data/household_risk_by_province.json "
                      "(run build_household_risk.py) and source-data/unemployment_by_province.json "
                      "(run ingest_tmli.py) present, then re-run this builder.",
        "n_provinces": 0,
    }
    return {"meta": meta, "provinces": []}


def build():
    hh = _load(HH_FILE)
    unemp = _load(UNEMP_FILE)

    if hh is None or unemp is None:
        missing = [n for n, d in ((HH_FILE, hh), (UNEMP_FILE, unemp)) if d is None]
        return _absent("missing source file(s): %s" % ", ".join(missing))
    if hh.get("meta", {}).get("absent"):
        return _absent("household_risk_by_province.json is itself in an ABSENT-state "
                        "(its own NSO SES sources are missing)")

    hh_rows = {r["province"]: r for r in hh.get("provinces", [])
               if r.get("debt_to_income") is not None and r.get("stress_index") is not None}
    unemp_rows = {p: r for p, r in unemp.get("provinces", {}).items()
                  if r.get("unemployment_rate") is not None}

    common = sorted(set(hh_rows) & set(unemp_rows))
    if not common:
        return _absent("no province is present with a value in BOTH inputs")

    unemp_values = sorted(unemp_rows[p]["unemployment_rate"] for p in common)

    rows = []
    for prov in common:
        h = hh_rows[prov]
        u = unemp_rows[prov]
        dti_pct = h["stress_index"]
        unemp_rate = u["unemployment_rate"]
        unemp_pct = _percentile_rank(unemp_rate, unemp_values)
        composite = round(W_DTI * dti_pct + W_UNEMP * unemp_pct, 2)
        rows.append({
            "province": prov,
            "region": REGION.get(prov),
            "debt_to_income": h["debt_to_income"],
            "dti_percentile": dti_pct,
            "unemployment_rate": unemp_rate,
            "unemployment_percentile": unemp_pct,
            "composite_stress": composite,
        })

    # worst-first by composite_stress (desc); tie-break by province for determinism
    rows.sort(key=lambda r: (-r["composite_stress"], r["province"]))
    for i, r in enumerate(rows, start=1):
        r["rank"] = i

    meta = {
        "title": "Combined province structural-stress index — household DTI + unemployment "
                 "(portfolio risk, objective #1)",
        "generated_by": "pipeline/build_province_stress.py",
        "deterministic": True,
        "network_free": True,
        "absent": False,
        "n_provinces": len(rows),
        "sort": "worst-first by composite_stress (desc)",
        "source": "platform/data/household_risk_by_province.json (NSO SES 2566 debt-to-income, "
                  "via build_household_risk.py) + source-data/unemployment_by_province.json "
                  "(NSO Labour Force Survey unemployment_rate, via ingest_tmli.py).",
        "provenance": "MEASURED inputs (debt_to_income, unemployment_rate — both NSO). "
                      "dti_percentile and unemployment_percentile are ESTIMATED 0-100 percentile "
                      "ranks of those measured values across the joined province set. "
                      "composite_stress is an ESTIMATED %g/%g weighted average of the two "
                      "percentile ranks." % (W_DTI, W_UNEMP),
        "fields": {
            "debt_to_income": "MEASURED · NSO SES — household debt as a multiple of annual income "
                              "(carried from household_risk_by_province.json).",
            "dti_percentile": "ESTIMATED — 0-100 percentile rank of debt_to_income across the "
                              "joined province set (carried from household_risk's stress_index).",
            "unemployment_rate": "MEASURED · NSO Labour Force Survey — percent.",
            "unemployment_percentile": "ESTIMATED — 0-100 percentile rank of unemployment_rate "
                                       "across the joined province set (same method as "
                                       "dti_percentile, for comparability).",
            "composite_stress": "ESTIMATED — %g*dti_percentile + %g*unemployment_percentile, "
                                "0-100. A relative triage ordering, NOT a measured default rate."
                                % (W_DTI, W_UNEMP),
            "rank": "1 = most structurally stressed province by composite_stress.",
        },
        "formula": {
            "unemployment_percentile": "100 * (#provinces with lower unemployment_rate + "
                                       "0.5*#ties) / #provinces, rounded 2dp",
            "composite_stress": "round(%g*dti_percentile + %g*unemployment_percentile, 2)"
                                % (W_DTI, W_UNEMP),
        },
        "measured_vs_estimated": "debt_to_income + unemployment_rate are MEASURED (NSO). Both "
                                 "percentile ranks and composite_stress are ESTIMATED (relative "
                                 "ordering, equal-weighted by editorial choice — no calibration "
                                 "to realized portfolio default/loss).",
        "caveats": [
            "Equal 50/50 weighting between DTI-percentile and unemployment-percentile is an "
            "editorial choice, not derived from AutoX loss history — treat as a triage ordering, "
            "not a calibrated risk score.",
            "Both inputs are province AVERAGES (NSO SES / NSO LFS), not the AutoX borrower book.",
            "Only provinces with a value in BOTH inputs are included; a province missing from "
            "either source is silently absent from this file (not zero-filled).",
        ],
    }

    return {"meta": meta, "provinces": rows}


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
                OUT, data["meta"]["n_provinces"],
                ", ABSENT-state" if data["meta"].get("absent") else ""))
            sys.exit(0)
        print("CHECK FAIL: %s differs from a fresh build" % OUT)
        sys.exit(1)

    with open(OUT, "w", encoding="utf-8") as f:
        f.write(text)
    if data["meta"].get("absent"):
        print("wrote %s (ABSENT-state: %s)" % (OUT, data["meta"]["absent_reason"]))
        return
    print("wrote %s (%d provinces, worst-first)" % (OUT, data["meta"]["n_provinces"]))
    for r in data["provinces"][:5]:
        print("  #%-2d %-16s composite=%-6s DTI%%=%-6s unemp%%=%-6s (DTI=%.2f, unemp=%.2f%%)" % (
            r["rank"], r["province"], r["composite_stress"], r["dti_percentile"],
            r["unemployment_percentile"], r["debt_to_income"], r["unemployment_rate"]))


if __name__ == "__main__":
    main()
