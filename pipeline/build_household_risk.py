#!/usr/bin/env python3
"""
build_household_risk.py — PORTFOLIO RISK (objective #1): household debt-to-income risk lens.

Network-free, deterministic. Joins two LOCAL, MEASURED source-data files:

  nso_ses_debt_2566.json             debt (THB, NSO SES 2566) — AUTHORITATIVE, pulled from NSO's
                                     own CKAN (pull_nso_ses_debt.py); preferred debt source.
  household_income_by_province.json  avg_monthly_income (THB/month, NSO SES 2566, MEASURED)

DEBT PROVENANCE (corrected 2026-09-12). The debt side used to come from the vendored TMLI file
household_debt_by_province.json, whose meta claimed its debt_per_household was "MEASURED (NSO SES
2566)". An audit against NSO's own CKAN (table SFD_SPB0806, package 0705_08_0009) found that claim
false: only 4 of 77 provinces matched the authoritative figure and the rest diverged by up to
~4.5x (Khon Kaen 280,791 vs 62,884; Bangkok 88,856 vs 161,050), so the shipped household-DTI risk
ranking was materially wrong. The debt input is now the authoritative NSO CKAN layer
(source-data/nso_ses_debt_2566.json); the vendored file is a fallback only, kept for graceful
degrade. Income is still the vendored NSO SES layer pending its own authoritative CKAN
verification (a documented follow-up).

It computes, PER PROVINCE:
  debt              average household debt, THB.                       [MEASURED · NSO SES]
  income            average ANNUAL household income, THB
                    (= avg_monthly_income * 12).                       [MEASURED · NSO SES]
  debt_to_income    debt / income (guarded; None if income<=0).       [MEASURED ratio of two
                    MEASURED inputs — household debt as a multiple of annual income.]
  stress_index      0..100 PERCENTILE RANK of debt_to_income across
                    all provinces with a value (higher = more stressed
                    relative to the rest of the country).             [ESTIMATED composite]

Province / region keys are competitive-intel's canonical 77 Thai-name set (regionmap.REGION),
which is exactly what the two source files already use (they were normalized by ingest_tmli.py).

GRACEFUL DEGRADE: if either source file is missing, the projector STILL writes the output with an
empty provinces list and meta.absent=true (a clear absent-state), so the frontend lens can hide
itself without erroring. --check still byte-compares whatever was last committed.

Run:
  python3 build_household_risk.py            # write platform/data/household_risk_by_province.json
  python3 build_household_risk.py --check    # re-run, byte-compare against the committed file
"""
import argparse
import json
import os
import sys

from lib.regionmap import REGION

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, "source-data")
OUT = os.path.join(ROOT, "platform", "data", "household_risk_by_province.json")

AUTH_DEBT_FILE = "nso_ses_debt_2566.json"          # authoritative NSO CKAN (preferred)
DEBT_FILE = "household_debt_by_province.json"       # vendored TMLI (fallback only)
INCOME_FILE = "household_income_by_province.json"

MONTHS = 12  # annualize the MEASURED monthly income before forming the debt/income ratio


def _load(name):
    path = os.path.join(SRC, name)
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _percentile_rank(value, sorted_values):
    """0..100 percentile rank of `value` within `sorted_values` (ascending), using the
    fraction of values strictly below plus half of those equal (mid-rank). Deterministic;
    ties get the same rank. With a single value the rank is 50.0 (mid)."""
    n = len(sorted_values)
    if n <= 1:
        return 50.0
    below = sum(1 for v in sorted_values if v < value)
    equal = sum(1 for v in sorted_values if v == value)
    return round(100.0 * (below + 0.5 * equal) / n, 2)


def _load_debt():
    """Debt source, preferring the authoritative NSO CKAN layer over the vendored TMLI file.

    Returns (dprov, citation) where dprov maps province -> {"debt_per_household": int} (the shape
    the join below expects), or (None, None) if neither source is present. `citation` carries the
    provenance strings for meta so the output always names the source it actually used."""
    auth = _load(AUTH_DEBT_FILE)
    if auth is not None:
        am = auth.get("meta", {})
        dprov = {p: {"debt_per_household": v}
                 for p, v in auth.get("provinces", {}).items() if v is not None}
        citation = {
            "which": "authoritative",
            "source": "NSO SES 2566 household debt — AUTHORITATIVE, from NSO's own CKAN "
                      "(%s); income from the NSO SES vendored layer (pending its own CKAN "
                      "verification)." % am.get("source", "catalogapi.nso.go.th"),
            "provenance": "debt = MEASURED NSO SES 2566 (2023 CE), CKAN package %s / resource %s, "
                          "reconstructed to the province level (household-weighted mean over "
                          "socioeconomic strata; national mean reproduces NSO's published "
                          "headline %s THB). See pipeline/pull_nso_ses_debt.py. income = "
                          "avg_monthly_income*12 from the vendored NSO SES layer "
                          "(source-data/%s), still to be verified against its own CKAN table."
                          % (am.get("package", "0705_08_0009"),
                             am.get("resource", "SFD_SPB0806"),
                             am.get("national_avg_debt_per_household", "197255"),
                             INCOME_FILE),
        }
        return dprov, citation

    vend = _load(DEBT_FILE)
    if vend is not None:
        citation = {
            "which": "vendored-fallback",
            "source": "NSO SES 2566 (household debt + income), via data.go.th / TMLI bridge "
                      "(pipeline/ingest_tmli.py) — FALLBACK: the authoritative "
                      "source-data/%s was not found." % AUTH_DEBT_FILE,
            "provenance": "FALLBACK to the vendored TMLI debt file. NOTE: this file's "
                          "debt_per_household was found (2026-09-12 audit) to disagree with NSO's "
                          "own CKAN for 73 of 77 provinces — run pipeline/pull_nso_ses_debt.py to "
                          "restore the authoritative debt source.",
        }
        return vend.get("provinces", {}), citation

    return None, None


def build():
    dprov, debt_cite = _load_debt()
    income = _load(INCOME_FILE)

    # --- graceful degrade: a missing source still ships a clear absent-state ---
    if dprov is None or income is None:
        missing = [n for n, d in (("household debt (%s / %s)" % (AUTH_DEBT_FILE, DEBT_FILE), dprov),
                                  (INCOME_FILE, income)) if d is None]
        meta = {
            "title": "Per-province household debt-to-income risk (portfolio risk, objective #1)",
            "generated_by": "pipeline/build_household_risk.py",
            "deterministic": True,
            "network_free": True,
            "absent": True,
            "absent_reason": "missing source file(s): %s" % ", ".join(missing),
            "source": "NSO SES 2566 via the TMLI bridge (ingest_tmli.py) — NOT FOUND",
            "provenance": "ABSENT — run pipeline/ingest_tmli.py to land the MEASURED NSO SES "
                          "household debt/income layers, then re-run this builder.",
            "n_provinces": 0,
        }
        return {"meta": meta, "provinces": []}

    iprov = income.get("provinces", {})

    # only provinces present in BOTH MEASURED layers (clean join; both already 77-canonical)
    common = sorted(set(dprov.keys()) & set(iprov.keys()))

    rows = []
    for prov in common:
        d = dprov[prov]
        i = iprov[prov]
        debt_thb = d.get("debt_per_household")
        monthly = i.get("avg_monthly_income")
        if debt_thb is None or monthly is None:
            continue
        annual = float(monthly) * MONTHS
        # guard divide-by-zero / non-positive income
        if annual > 0:
            dti = round(float(debt_thb) / annual, 2)
        else:
            dti = None
        rows.append({
            "province": prov,
            "region": REGION.get(prov),  # canonical region, or None if unmapped (honest)
            "debt": int(debt_thb),
            "income": int(round(annual)),
            "debt_to_income": dti,
        })

    # --- stress_index = 0..100 percentile rank of debt_to_income (ESTIMATED composite) ---
    dti_values = sorted(r["debt_to_income"] for r in rows if r["debt_to_income"] is not None)
    for r in rows:
        if r["debt_to_income"] is None:
            r["stress_index"] = None
        else:
            r["stress_index"] = _percentile_rank(r["debt_to_income"], dti_values)

    # sort worst-first by debt_to_income (desc); None last; tie-break by province for determinism
    rows.sort(key=lambda r: (
        -(r["debt_to_income"] if r["debt_to_income"] is not None else -1.0),
        r["province"],
    ))

    meta = {
        "title": "Per-province household debt-to-income risk (portfolio risk, objective #1)",
        "generated_by": "pipeline/build_household_risk.py",
        "deterministic": True,
        "network_free": True,
        "absent": False,
        "n_provinces": len(rows),
        "sort": "worst-first by debt_to_income (desc)",
        "source": debt_cite["source"],
        "provenance": debt_cite["provenance"],
        "debt_source": debt_cite["which"],  # 'authoritative' (NSO CKAN) or 'vendored-fallback'
        "fields": {
            "debt": "MEASURED · NSO SES 2566 (authoritative NSO CKAN, SFD_SPB0806) — average "
                    "household debt, THB, all households.",
            "income": "MEASURED · NSO SES — average ANNUAL household income, THB "
                      "(avg_monthly_income * 12). Still vendored (TMLI), pending its own CKAN "
                      "verification.",
            "debt_to_income": "MEASURED ratio — debt / income (household debt as a multiple of "
                              "annual income). None when income is non-positive.",
            "stress_index": "ESTIMATED — 0..100 PERCENTILE RANK of debt_to_income across the "
                            "provinces (mid-rank for ties). A relative triage score, NOT a "
                            "measured default rate. None when debt_to_income is None.",
        },
        "formula": {
            "income": "avg_monthly_income * %d" % MONTHS,
            "debt_to_income": "debt / income  (guarded: None when income <= 0)",
            "stress_index": "100 * (#provinces with lower DTI + 0.5*#ties) / #provinces, rounded 2dp",
        },
        "measured_vs_estimated": "debt + income + debt_to_income are MEASURED (NSO SES). "
                                 "stress_index is an ESTIMATED percentile rank (relative ordering).",
        "caveats": [
            "NSO SES debt/income are province AVERAGES, not the AutoX borrower book; they read "
            "household balance-sheet pressure, not realized portfolio default.",
            "stress_index is a relative rank across the 77 provinces — it shifts if the province "
            "set changes; it is a triage ordering, not an absolute risk level.",
            "debt is now the authoritative NSO CKAN figure (2026-09-12 fix); income is still the "
            "vendored NSO SES layer, not yet re-verified against its own CKAN table.",
        ],
    }

    return {"meta": meta, "provinces": rows}


def dumps(obj):
    # deterministic: insertion key order, ensure_ascii=False, indent=2, trailing newline
    # (matches crop_stress.json / meta.json convention across the pipeline).
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

    # newline="\n": the Windows default turns every \n into \r\n, inflating the byte sizes
    # build_provenance.py censuses and diverging the local tree from the LF blob CI reads.
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    if data["meta"].get("absent"):
        print("wrote %s (ABSENT-state: %s)" % (OUT, data["meta"]["absent_reason"]))
        return
    print("wrote %s (%d provinces, worst-first)" % (OUT, data["meta"]["n_provinces"]))
    for r in data["provinces"][:5]:
        print("  %-16s DTI=%-5s stress=%-5s debt=%s income=%s" % (
            r["province"], r["debt_to_income"], r["stress_index"], r["debt"], r["income"]))


if __name__ == "__main__":
    main()
