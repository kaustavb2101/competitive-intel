#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_labour_context.py — MEASURED national labour context from the ILOSTAT battery.

Source: source-data/ilostat_labour.json (pipeline/pull_ilostat_labour.py — ILOSTAT rplumber
mirror of Thailand's official NSO LFS submissions; NSO's own hosts are geoblocked from cloud).
Pulled 2026-07-10; previously an ORPHAN input with no consumer (E0 wave, revamp analysis).

Why (objective #1): the informal-employment rate IS the title-loan borrower base — informal
workers lack payslips, which is why they pledge vehicle titles. This distills the battery to
the few numbers an exec needs: informality, sector employment + trend, unemployment (total vs
youth), and the agri-vs-factory hours gap (underemployment context).

Deterministic over the committed JSON; --check byte-exact; exits 3 (SKIP) when source absent.

  python3 build_labour_context.py
  python3 build_labour_context.py --check
"""
import argparse, json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "source-data", "ilostat_labour.json")
OUT = os.path.join(ROOT, "platform", "data", "labour_context.json")

SECTORS = {  # ILO aggregate -> plain label (segment-relevant order)
    "ECO_AGGREGATE_AGR": "Agriculture",
    "ECO_AGGREGATE_MAN": "Manufacturing",
    "ECO_AGGREGATE_MKT": "Market services (trade/transport/food)",
    "ECO_AGGREGATE_CON": "Construction",
    "ECO_AGGREGATE_PUB": "Public/social services",
}


def _latest(series, classif=None):
    """(time, value) of the newest row matching classif (None matches None)."""
    rows = [r for r in series.get("rows", []) if r.get("classif1") == classif]
    rows.sort(key=lambda r: str(r.get("time")))
    return (rows[-1]["time"], rows[-1]["obs_value"]) if rows else (None, None)


def _at(series, classif, time):
    for r in series.get("rows", []):
        if r.get("classif1") == classif and str(r.get("time")) == str(time):
            return r.get("obs_value")
    return None


def build():
    src = json.load(open(SRC, encoding="utf-8"))
    S = src.get("series", {})
    emp = S.get("EMP_TEMP_SEX_ECO_NB", {})
    une = S.get("UNE_DEAP_SEX_AGE_RT", {})
    nifl = S.get("EMP_NIFL_SEX_RT", {})
    how = S.get("HOW_TEMP_SEX_ECO_NB", {})
    ste = S.get("EMP_TEMP_SEX_STE_NB", {})   # status in employment (own-account / employees / …)

    inf_t, inf_v = _latest(nifl, None)
    tot_t, tot_v = _latest(emp, "ECO_AGGREGATE_TOTAL")
    prev_year = str(int(tot_t) - 1) if tot_t else None

    # self-employment: own-account (ICSE93_3) + contributing-family (ICSE93_5) + employers (ICSE93_2)
    # = workers without a payslip-issuing employer, the exact vehicle-title borrower profile.
    ste_t, ste_tot = _latest(ste, "STE_AGGREGATE_TOTAL")
    _, own = _latest(ste, "STE_ICSE93_3")
    _, fam = _latest(ste, "STE_ICSE93_5")
    _, emprs = _latest(ste, "STE_ICSE93_2")
    _, ees = _latest(ste, "STE_ICSE93_1")
    self_emp = None
    if None not in (ste_tot, own, fam, emprs) and ste_tot:
        selfn = own + fam + emprs
        self_emp = {"as_of": ste_t,
                    "self_employed_thousands": round(selfn, 1),
                    "self_employed_pct": round(100.0 * selfn / ste_tot, 1),
                    "own_account_thousands": round(own, 1),
                    "contributing_family_thousands": round(fam, 1),
                    "employers_thousands": round(emprs, 1),
                    "employees_thousands": round(ees, 1) if ees is not None else None,
                    "note": "self-employed = own-account + contributing-family + employers — no "
                            "payslip-issuing employer, the exact vehicle-title borrower profile"}

    sectors = []
    for code, label in SECTORS.items():
        t, v = _latest(emp, code)
        if v is None:
            continue
        prev = _at(emp, code, prev_year) if prev_year else None
        yoy = round(v - prev, 1) if (prev is not None) else None
        _, hours = _latest(how, code)
        sectors.append({"sector": label, "employed_thousands": round(v, 1),
                        "yoy_change_thousands": yoy,
                        "share_pct": round(100.0 * v / tot_v, 1) if tot_v else None,
                        "mean_weekly_hours": round(hours, 1) if hours is not None else None,
                        "as_of": t})

    une_tot_t, une_tot = _latest(une, "AGE_10YRBANDS_YGE15")
    _, une_youth = _latest(une, "AGE_10YRBANDS_Y15-24")

    return {
        "meta": {
            "title": "National labour context — the informal-borrower base (measured)",
            "generated_by": "pipeline/build_labour_context.py",
            "label": "MEASURED — ILOSTAT mirror of Thailand's official NSO LFS submissions. "
                     "NATIONAL level only (the geoblock verdict: no cloud path to per-province "
                     "LFS; vendored SES 2566 remains the per-province source).",
            "source": "source-data/ilostat_labour.json (pull_ilostat_labour.py, pulled %s)"
                      % src.get("meta", {}).get("pulled", "?"),
            "why": "Informal workers lack payslips — that is the title-loan borrower base. "
                   "Informality + sector employment set the demand backdrop for every segment "
                   "score on this platform.",
        },
        "informality": {"rate_pct": round(inf_v, 1) if inf_v is not None else None,
                        "as_of": inf_t,
                        "note": "share of employment that is INFORMAL (no payslip/social cover) "
                                "— the core title-loan demographic"},
        "self_employment": self_emp,
        "employment": {"total_thousands": round(tot_v, 1) if tot_v is not None else None,
                       "as_of": tot_t, "sectors": sectors},
        "unemployment": {"total_rate_pct": round(une_tot, 2) if une_tot is not None else None,
                         "youth_15_24_rate_pct": round(une_youth, 2) if une_youth is not None else None,
                         "as_of": une_tot_t,
                         "note": "headline unemployment is structurally low in Thailand because "
                                 "informal work absorbs slack — read WITH the informality rate, "
                                 "not instead of it"},
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    if not os.path.exists(SRC):
        print("build_labour_context.py: source-data/ilostat_labour.json absent — run pull_ilostat_labour.py (SKIP).")
        sys.exit(3)
    payload = json.dumps(build(), ensure_ascii=False, separators=(",", ":"))
    if args.check:
        if not os.path.exists(OUT):
            sys.exit("build_labour_context.py --check: output missing — run the builder.")
        if open(OUT, encoding="utf-8").read() != payload:
            sys.exit("build_labour_context.py --check: drifted — re-run the builder.")
        print("build_labour_context.py --check: OK (byte-exact)")
        return
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(payload)
    d = json.loads(payload)
    print("wrote %s — informality %.1f%% (%s), employment %.1fM (%s)" % (
        OUT, d["informality"]["rate_pct"], d["informality"]["as_of"],
        (d["employment"]["total_thousands"] or 0) / 1000.0, d["employment"]["as_of"]))
    for s in d["employment"]["sectors"]:
        print("   %-40s %8.0fk (%+.0fk YoY) · %4.1f%% · %.1fh/wk" % (
            s["sector"], s["employed_thousands"], s["yoy_change_thousands"] or 0,
            s["share_pct"] or 0, s["mean_weekly_hours"] or 0))


if __name__ == "__main__":
    main()
