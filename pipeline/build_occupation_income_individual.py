#!/usr/bin/env python3
"""build_occupation_income_individual.py — INDIVIDUAL (per-person) income by occupation.

Why: the borrower is an individual, but the existing occupation-income panel shows NSO SES
HOUSEHOLD income by the household head's occupation class (multi-earner) — which reads ~2x an
individual salary (e.g. "Office staff" SES-household ~37k vs a measured individual clerical wage
~17k). This layer gives the per-person figure.

Provenance is deliberately split:
  - national     = MEASURED. ILOSTAT `EAR_EMTA_SEX_OCU_NB` — average monthly earnings of EMPLOYEES
                   by ISCO-08 occupation, Thailand, latest year (THB/month). A real individual wage.
  - by-province  = ESTIMATED. There is no reachable measured individual-wage-by-province source
                   (NSO provincial LFS is geoblocked). We take the province SPREAD from the measured
                   SES household layer and rescale it to the measured national INDIVIDUAL level:
                       individual_est[prov] = household[prov] * (ilostat_individual / ses_household_natl_mean)
                   i.e. the province distribution is measured, the absolute individual level is measured,
                   and the single rescale ratio (the implied earners-per-household) is the estimated leg.

  SME owners are SELF-EMPLOYED, not employees, so ILOSTAT earnings (employees only) has no individual
  figure for them — that category stays HOUSEHOLD-only, flagged, with no per-person estimate invented.

Inputs (both MEASURED):
  source-data/ilostat_labour.json          (series EAR_EMTA_SEX_OCU_NB — ILOSTAT, pulled by pull_ilostat_labour.py)
  source-data/household_income_by_province.json  (NSO SES 2566 household income by occupation class)
Output:
  platform/data/occupation_income_individual.json

  python3 build_occupation_income_individual.py            # write
  python3 build_occupation_income_individual.py --check     # re-run, byte-compare; exit 1 on drift
SKIP-passes (exit 3) when either MEASURED source is absent — same convention as the other builders.
"""
import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ILO = os.path.join(ROOT, "source-data", "ilostat_labour.json")
SES = os.path.join(ROOT, "source-data", "household_income_by_province.json")
OUT = os.path.join(ROOT, "platform", "data", "occupation_income_individual.json")

# SES household category -> the closest ISCO-08 major group with a MEASURED individual wage.
# label: how the category reads to the exec; isco_note: the honesty caveat on the mapping.
MAP = {
    "OfficeStaff":    ("Office / clerical", "OCU_ISCO08_4", "Clerical support workers",
                       "SES 'office staff' is a broad class (also spans technicians/professionals/managers, "
                       "which earn more individually — see the ISCO ladder); clerical is the representative core."),
    "FactoryWorkers": ("Factory / plant", "OCU_ISCO08_8", "Plant & machine operators", ""),
    "Transport":      ("Transport", "OCU_ISCO08_8", "Plant & machine operators (incl. drivers)",
                       "ISCO-08 places most transport drivers in group 8 (plant/machine operators)."),
    "Agriculture":    ("Agriculture", "OCU_ISCO08_6", "Skilled agricultural workers", ""),
    "SMEOwners":      ("SME owners", None, None,
                       "Self-employed, not employees — ILOSTAT earnings covers employees only, so no "
                       "measured individual wage exists; household figure carried, no per-person estimate."),
}
# full ISCO ladder for the reference table (readable labels)
ISCO_LABELS = {
    "OCU_ISCO08_1": "Managers", "OCU_ISCO08_2": "Professionals", "OCU_ISCO08_3": "Technicians",
    "OCU_ISCO08_4": "Clerical support", "OCU_ISCO08_5": "Service & sales",
    "OCU_ISCO08_6": "Skilled agricultural", "OCU_ISCO08_7": "Craft & trades",
    "OCU_ISCO08_8": "Plant & machine operators", "OCU_ISCO08_9": "Elementary",
    "OCU_ISCO08_0": "Armed forces",
}


def _load(path):
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _absent(reason):
    return {"meta": {"generated_by": "pipeline/build_occupation_income_individual.py",
                     "absent": True, "absent_reason": reason},
            "national": [], "isco_ladder": [], "provinces": {}}


def build():
    ilo = _load(ILO)
    ses = _load(SES)
    if ilo is None:
        return _absent("source-data/ilostat_labour.json missing"), True
    if ses is None:
        return _absent("source-data/household_income_by_province.json missing"), True

    series = (ilo.get("series") or {}).get("EAR_EMTA_SEX_OCU_NB")
    if not series or not series.get("rows"):
        return _absent("ilostat_labour.json has no EAR_EMTA_SEX_OCU_NB rows (re-run pull_ilostat_labour.py)"), True

    rows = series["rows"]
    latest = max(r["time"] for r in rows)
    ilo_val = {r["classif1"]: r["obs_value"] for r in rows if r["time"] == latest}

    provs = ses.get("provinces", {})
    # unweighted national household mean per category (matches build_occupation_income.py)
    ses_natl = {}
    for cat in MAP:
        vals = [rec[cat] for rec in provs.values() if isinstance(rec.get(cat), (int, float))]
        ses_natl[cat] = round(sum(vals) / len(vals)) if vals else None

    national = []
    provinces = {p: {} for p in provs}
    for cat, (label, isco, isco_lbl, note) in MAP.items():
        hh = ses_natl.get(cat)
        if isco is None or isco not in ilo_val:
            # SME owners: household-only, no measured individual, no estimate
            national.append({
                "key": cat, "label": label, "isco_code": isco, "isco_label": isco_lbl,
                "individual_national": None, "household_national_avg": hh,
                "measured_individual": False, "note": note,
            })
            for p, rec in provs.items():
                if isinstance(rec.get(cat), (int, float)):
                    provinces[p][cat] = {"household": round(rec[cat]), "individual_est": None}
            continue
        indiv = round(ilo_val[isco])
        ratio = indiv / hh if hh else None
        national.append({
            "key": cat, "label": label, "isco_code": isco, "isco_label": isco_lbl,
            "individual_national": indiv, "household_national_avg": hh,
            "ratio_individual_to_household": round(ratio, 4) if ratio else None,
            "measured_individual": True, "note": note,
        })
        for p, rec in provs.items():
            v = rec.get(cat)
            if isinstance(v, (int, float)) and ratio is not None:
                provinces[p][cat] = {"household": round(v),
                                     "individual_est": round(v * ratio)}
    national.sort(key=lambda r: (r["individual_national"] is None, r["individual_national"] or 0, r["key"]))

    ladder = [{"isco_code": c, "label": ISCO_LABELS[c], "individual": round(ilo_val[c])}
              for c in sorted(ISCO_LABELS) if c in ilo_val]
    ladder.sort(key=lambda r: r["individual"])

    meta = {
        "title": "Individual (per-person) income by occupation — the borrower is an individual",
        "generated_by": "pipeline/build_occupation_income_individual.py",
        "deterministic": True, "network_free": True, "absent": False,
        "currency": "THB/month", "vintage_individual": latest,
        "source_individual": "ILOSTAT EAR_EMTA_SEX_OCU_NB (rplumber.ilo.org) — average monthly earnings "
                             "of EMPLOYEES by ISCO-08 occupation, Thailand. MEASURED, national.",
        "source_household": "NSO SES 2566 household income by occupation class "
                            "(source-data/household_income_by_province.json). MEASURED, per-province.",
        "provenance": {
            "national.individual_national": "MEASURED — ILOSTAT individual employee earnings, national.",
            "national.household_national_avg": "MEASURED — unweighted 77-province mean of the SES household figure.",
            "provinces.*.household": "MEASURED — NSO SES 2566 household income for that province/category.",
            "provinces.*.individual_est": "ESTIMATED — household * (measured national individual / measured "
                                          "national household). Province SPREAD measured; absolute individual "
                                          "level measured; the rescale ratio (implied earners/household) is the estimate.",
        },
        "caveats": [
            "Individual figures are EMPLOYEE earnings (ILOSTAT); self-employed SME owners have no measured "
            "individual wage and stay household-only.",
            "Per-province individual is ESTIMATED (no reachable measured provincial wage source — NSO provincial "
            "LFS is geoblocked); the national individual figure is MEASURED.",
            "Reads structural income-floor risk for the occupation, not the AutoX borrower book or realized PD.",
        ],
    }
    return {"meta": meta, "national": national, "isco_ladder": ladder, "provinces": provinces}, False


def dumps(obj):
    return json.dumps(obj, ensure_ascii=False, indent=2) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true",
                    help="re-run and byte-compare against the committed JSON; exit 1 on drift")
    args = ap.parse_args()

    data, skip = build()
    if skip:
        print("SKIP: %s" % data["meta"]["absent_reason"])
        sys.exit(3)
    text = dumps(data)

    if args.check:
        if not os.path.exists(OUT):
            print("CHECK FAIL: %s does not exist" % OUT)
            sys.exit(1)
        with open(OUT, encoding="utf-8") as f:
            existing = f.read()
        if existing == text:
            print("CHECK OK: %s reproduces byte-for-byte (%d categories)" % (OUT, len(data["national"])))
            sys.exit(0)
        print("CHECK FAIL: %s differs from a fresh build" % OUT)
        sys.exit(1)

    with open(OUT, "w", encoding="utf-8") as f:
        f.write(text)
    print("wrote %s (%d categories, national vintage %s)" % (
        OUT, len(data["national"]), data["meta"]["vintage_individual"]))


if __name__ == "__main__":
    main()
