#!/usr/bin/env python3
"""
build_household_risk.py — PORTFOLIO RISK (objective #1): household debt-to-income risk lens.

Network-free, deterministic. Joins two LOCAL, MEASURED source-data files:

  nso_ses_debt_2566.json             debt (THB, NSO SES 2566) — AUTHORITATIVE, pulled from NSO's
                                     own CKAN (pull_nso_ses_debt.py); the only debt source.
  nso_ses_income_2566.json           avg monthly household income (THB, NSO SES 2566) —
                                     AUTHORITATIVE, from NSO's own CKAN (pull_nso_ses_income.py);
                                     the only income source.

PROVENANCE (both sides corrected 2026-09-12). Both inputs used to come from vendored TMLI files
whose meta claimed "MEASURED (NSO SES 2566)". Audits against NSO's own CKAN found both false:
  - DEBT (household_debt_by_province.json): only 4 of 77 provinces matched the authoritative
    figure (table SFD_SPB0806, package 0705_08_0009); the rest diverged up to ~4.5x (Khon Kaen
    280,791 vs 62,884; Bangkok 88,856 vs 161,050).
  - INCOME (household_income_by_province.json): its avg_monthly_income is not a household income
    at all but an UNWEIGHTED mean across five occupation rows; against NSO's own CKAN (table
    SFD_SPB0802_66, package 0705_08_0007) it diverged up to ~1.3x (Sisaket 25,597 vs the
    authoritative 19,858) and re-ranked 67 of 77 provinces on DTI.
Both inputs are now the authoritative NSO CKAN layers, and each is the ONLY source for its side —
there is deliberately no vendored fallback, because silently reverting to a wrong file while the
ranking and meta still read as authoritative would republish a materially incorrect risk map; if
either authoritative layer is missing the builder emits the honest absent-state.

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

AUTH_DEBT_FILE = "nso_ses_debt_2566.json"          # authoritative NSO CKAN — the ONLY debt source
AUTH_INCOME_FILE = "nso_ses_income_2566.json"      # authoritative NSO CKAN — the ONLY income source

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
    the join below expects), or (None, None) if the authoritative file is absent. `citation`
    carries the provenance strings for meta.

    There is deliberately NO vendored fallback. The vendored TMLI debt file
    (household_debt_by_province.json) was found (2026-09-12 audit vs NSO's own CKAN) to be WRONG
    for 73 of 77 provinces, so silently reverting to it — while the ranking and meta still read as
    authoritative — would republish a materially incorrect risk map. If the authoritative layer is
    missing, the caller emits the honest absent-state instead (run pipeline/pull_nso_ses_debt.py to
    restore it)."""
    auth = _load(AUTH_DEBT_FILE)
    if auth is None:
        return None, None
    am = auth.get("meta", {})
    dprov = {p: {"debt_per_household": v}
             for p, v in auth.get("provinces", {}).items() if v is not None}
    citation = {
        "which": "authoritative",
        "source": "NSO SES 2566 household debt — AUTHORITATIVE, from NSO's own CKAN "
                  "(%s)." % am.get("source", "catalogapi.nso.go.th"),
        "provenance": "debt = MEASURED NSO SES 2566 (2023 CE), CKAN package %s / resource %s, "
                      "reconstructed to the province level (household-weighted mean over "
                      "socioeconomic strata; national mean reproduces NSO's published "
                      "headline %s THB). See pipeline/pull_nso_ses_debt.py."
                      % (am.get("package", "0705_08_0009"),
                         am.get("resource", "SFD_SPB0806"),
                         am.get("national_avg_debt_per_household", "197255")),
    }
    return dprov, citation


def _load_income():
    """Income source: the authoritative NSO CKAN layer (pull_nso_ses_income.py).

    Returns (iprov, citation) where iprov maps province -> int monthly household income (THB), or
    (None, None) if the authoritative file is absent. `citation` carries the provenance strings.

    Like the debt side, there is deliberately NO vendored fallback. The vendored TMLI income file
    (household_income_by_province.json) carried, as its `avg_monthly_income`, an UNWEIGHTED mean
    across five occupation rows — not a household income — from the same source whose debt figures
    were wrong for 73/77 provinces; audited against NSO's own CKAN it diverged by up to ~1.3x and
    re-ranked 67/77 provinces on DTI. Silently reverting to it — while the ranking and meta still
    read as authoritative — would republish a materially incorrect risk map. If the authoritative
    layer is missing, the caller emits the honest absent-state instead (run
    pipeline/pull_nso_ses_income.py to restore it)."""
    auth = _load(AUTH_INCOME_FILE)
    if auth is None:
        return None, None
    am = auth.get("meta", {})
    iprov = {p: v for p, v in auth.get("provinces", {}).items() if v is not None}
    citation = {
        "source": "NSO SES 2566 average monthly household income — AUTHORITATIVE, from NSO's own "
                  "CKAN (%s)." % am.get("source", "catalogapi.nso.go.th"),
        "provenance": "income = MEASURED NSO SES 2566 (2023 CE), CKAN package %s / resource %s, "
                      "reconstructed to the province level (household-weighted mean of each "
                      "socioeconomic leaf's total monthly income, weighted by the leaf's "
                      "household count; national mean reproduces NSO's published headline %s "
                      "THB/month). See pipeline/pull_nso_ses_income.py."
                      % (am.get("package", "0705_08_0007"),
                         am.get("resource", "SFD_SPB0802_66"),
                         am.get("national_avg_monthly_income", "29030")),
    }
    return iprov, citation


def build():
    dprov, debt_cite = _load_debt()
    iprov, income_cite = _load_income()

    # --- graceful degrade: a missing source still ships a clear absent-state ---
    if dprov is None or iprov is None:
        missing = [n for n, d in ((AUTH_DEBT_FILE, dprov), (AUTH_INCOME_FILE, iprov)) if d is None]
        meta = {
            "title": "Per-province household debt-to-income risk (portfolio risk, objective #1)",
            "generated_by": "pipeline/build_household_risk.py",
            "deterministic": True,
            "network_free": True,
            "absent": True,
            "absent_reason": "missing source file(s): %s" % ", ".join(missing),
            "source": "NSO SES 2566 authoritative CKAN layers — NOT FOUND",
            "provenance": "ABSENT — run pipeline/pull_nso_ses_debt.py and "
                          "pipeline/pull_nso_ses_income.py to land the MEASURED NSO SES "
                          "household debt/income layers, then re-run this builder.",
            "n_provinces": 0,
        }
        return {"meta": meta, "provinces": []}

    # only provinces present in BOTH MEASURED layers (clean join; both already 77-canonical)
    common = sorted(set(dprov.keys()) & set(iprov.keys()))

    rows = []
    for prov in common:
        d = dprov[prov]
        debt_thb = d.get("debt_per_household")
        monthly = iprov[prov]
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
        "source": debt_cite["source"] + " " + income_cite["source"],
        "provenance": debt_cite["provenance"] + " " + income_cite["provenance"],
        "debt_source": debt_cite["which"],  # 'authoritative' (NSO CKAN)
        "income_source": "authoritative",   # NSO CKAN (SFD_SPB0802_66)
        "fields": {
            "debt": "MEASURED · NSO SES 2566 (authoritative NSO CKAN, SFD_SPB0806) — average "
                    "household debt, THB, all households.",
            "income": "MEASURED · NSO SES 2566 (authoritative NSO CKAN, SFD_SPB0802_66) — average "
                      "ANNUAL household income, THB (household-weighted monthly income * 12).",
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
            "both debt and income are now the authoritative NSO CKAN figures (debt fix "
            "2026-09-12; income fix 2026-09-12, SFD_SPB0802_66). The prior income denominator was "
            "an unweighted mean across five occupation rows, which re-ranked 67/77 provinces.",
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
