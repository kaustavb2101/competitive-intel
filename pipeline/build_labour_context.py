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

FRESHER OVERRIDE (owner escalation 2026-08-02: "AGRI JOBS 28.3% = 2025" and "SELF-EMPLOYED 50.4% =
2025" were called out as stale — ILOSTAT mirrors NSO's LFS only ANNUALLY, while NSO's own LFS is
QUARTERLY). When source-data/nso_lfs_status.json is present (pipeline/pull_nso_lfs_status.py — NSO's
own quarterly region x industry / region x work-status cross-tabs, summed to national), its latest
quarter OVERRIDES the self_employment block and the Agriculture row of employment.sectors with the
SAME concepts (own-account + contributing-family + employers for self-employment; agriculture share
of total employment for the sector row — see pull_nso_lfs_status.py's docstring for the exact
ICSE-93-class mapping), just a fresher, quarterly cut. informality is NOT touched: NSO's own annual
Informal Employment Survey (the primary source ILOSTAT's informality mirror is itself derived from)
currently tops out at survey year 2566 (2023, published May 2024) — OLDER than the 2024-vintage
ILOSTAT figure already shown, so there is nothing fresher to fold in there yet.

  python3 build_labour_context.py
  python3 build_labour_context.py --check
"""
import argparse, json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "source-data", "ilostat_labour.json")
SRC_NSO = os.path.join(ROOT, "source-data", "nso_lfs_status.json")
SRC_PLFS = os.path.join(ROOT, "source-data", "staging", "nso_lfs.json")
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


def _nso_quarter_label(snapshot):
    """{'year_be': '2569', 'quarter': 'ไตรมาส 1'} -> '2026-Q1' (bare ISO-ish period the chip-strip's
    MACRO_PERIOD regex on the live page can read directly)."""
    y_ad = int(snapshot["year_be"]) - 543
    q_num = snapshot["quarter"].replace("ไตรมาส", "").strip()
    return "%04d-Q%s" % (y_ad, q_num)


def _apply_nso_override(self_emp, sectors):
    """Mutates self_emp (in place) and the Agriculture entry of sectors (in place) with NSO's own
    latest quarterly cut, when source-data/nso_lfs_status.json is present. Returns a short note for
    meta describing what happened (or why not), never silently."""
    if not os.path.exists(SRC_NSO):
        return ("source-data/nso_lfs_status.json absent — self_employment and the Agriculture "
                "sector row remain the ILOSTAT annual figures (run pipeline/pull_nso_lfs_status.py "
                "to fold in NSO's own quarterly cut).")
    nso = json.load(open(SRC_NSO, encoding="utf-8"))
    latest = nso.get("latest")
    if not latest:
        return "source-data/nso_lfs_status.json has no 'latest' quarter — override skipped."
    as_of = _nso_quarter_label(latest)
    trend = (nso.get("trend") or {}).get("vs_year_ago_quarter") or {}

    if self_emp is not None:
        comp = latest["self_employed"]["components_thousand"]
        own = comp.get("ทำงานส่วนตัว")
        fam = comp.get("ช่วยธุรกิจครอบครัว")
        emprs = comp.get("นายจ้าง")
        wsb = latest.get("work_status_breakdown_thousand") or {}
        employees = (wsb.get("ลูกจ้างเอกชน") or 0) + (wsb.get("ลูกจ้างรัฐบาล") or 0)
        self_emp["as_of"] = as_of
        self_emp["self_employed_thousands"] = latest["self_employed"]["employed_thousand"]
        self_emp["self_employed_pct"] = latest["self_employed"]["share_pct"]
        self_emp["own_account_thousands"] = own
        self_emp["contributing_family_thousands"] = fam
        self_emp["employers_thousands"] = emprs
        self_emp["employees_thousands"] = round(employees, 2) if employees else None
        self_emp["note"] = ("self-employed = own-account + contributing-family + employers — no "
                            "payslip-issuing employer, the exact vehicle-title borrower profile. "
                            "NSO LFS quarterly (national, summed over 7 regions x 2 sexes) — "
                            "supersedes the ILOSTAT annual mirror of this same indicator.")

    for s in sectors:
        if s["sector"] != "Agriculture":
            continue
        s["employed_thousands"] = latest["agriculture"]["employed_thousand"]
        s["share_pct"] = latest["agriculture"]["share_pct"]
        s["yoy_change_thousands"] = trend.get("agri_employed_delta_thousand")
        s["as_of"] = as_of

    return ("OVERRODE self_employment and the Agriculture sector row with NSO LFS quarterly %s "
            "(source-data/nso_lfs_status.json, pipeline/pull_nso_lfs_status.py) — fresher than "
            "the ILOSTAT annual mirror both were carrying." % as_of)


def _apply_nso_unemployment_override(unemployment):
    """Mutates unemployment (in place): replaces total_rate_pct — an ILOSTAT ANNUAL mirror figure —
    with the labour-force-weighted NATIONAL aggregate of NSO's own quarterly provincial LFS
    (source-data/staging/nso_lfs.json, the SAME measured source as the district-unemployment map
    lens and platform/data/province_lfs.json), when that staging file is present.

    Uses NSO's own definition: unemployment rate = unemployed / labour force. Seasonal-waiting
    workers (ผู้รอฤดูกาล) are a SEPARATE labour-force category, NOT counted as unemployed — folding
    them in (labour_force - employed) overstates the rate ~1.8x (1.71% vs the correct 0.94%), so we
    sum the published unemployed_k, matching how NSO computes each province's own rate.

    youth_15_24_rate_pct stays the ILOSTAT annual figure: the provincial cut carries employed-by-age
    but no unemployed-by-age, so no youth rate is derivable. Returns a meta note, never silently."""
    if unemployment is None:
        return "unemployment block absent — NSO quarterly override skipped."
    prior = unemployment.get("total_rate_pct")
    prior_asof = unemployment.get("as_of")
    prior_str = ("%s%% %s" % (prior, prior_asof)) if prior is not None else "n/a"
    if not os.path.exists(SRC_PLFS):
        return ("source-data/staging/nso_lfs.json absent — unemployment.total_rate_pct stays the "
                "ILOSTAT annual mirror (%s)." % prior_str)
    doc = json.load(open(SRC_PLFS, encoding="utf-8"))
    provs = doc.get("provinces") or []
    lf = sum((p.get("labor_force_total_k") or 0) for p in provs)
    une = sum((p.get("unemployed_k") or 0) for p in provs)
    if not provs or not lf:
        return ("source-data/staging/nso_lfs.json has no usable labour-force totals — "
                "unemployment.total_rate_pct stays the ILOSTAT annual mirror (%s)." % prior_str)
    rate = round(100.0 * une / lf, 2)
    sw = round(sum((p.get("seasonal_waiting_k") or 0) for p in provs))
    as_of = _nso_quarter_label(provs[0])   # year_be / quarter present on every province row
    unemployment["total_rate_pct"] = rate
    unemployment["as_of"] = as_of
    unemployment["nso_source"] = (
        "total_rate_pct is the labour-force-weighted NATIONAL aggregate of NSO LFS %s provincial "
        "data (source-data/staging/nso_lfs.json — the SAME measured source as the district-"
        "unemployment map lens and platform/data/province_lfs.json), on NSO's own definition "
        "(unemployed ÷ labour force; the %dk seasonal-waiting workers are a separate category, "
        "not counted as unemployed). It SUPERSEDES the ILOSTAT annual mirror this entry carried "
        "(%s). youth_15_24_rate_pct remains the ILOSTAT annual figure — the provincial LFS cut "
        "carries employed-by-age but no unemployed-by-age, so no youth rate is derivable."
        % (as_of, sw, prior_str))
    return ("OVERRODE unemployment.total_rate_pct with the NSO LFS %s national aggregate "
            "(%.2f%%, labour-force-weighted over %d provinces, NSO definition) — fresher than and "
            "consistent with the district-unemployment lens; was the ILOSTAT annual mirror (%s)."
            % (as_of, rate, len(provs), prior_str))


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

    nso_note = _apply_nso_override(self_emp, sectors)

    unemployment = {
        "total_rate_pct": round(une_tot, 2) if une_tot is not None else None,
        "youth_15_24_rate_pct": round(une_youth, 2) if une_youth is not None else None,
        "as_of": une_tot_t,
        "note": "headline unemployment is structurally low in Thailand because "
                "informal work absorbs slack — read WITH the informality rate, "
                "not instead of it",
    }
    nso_unemp_note = _apply_nso_unemployment_override(unemployment)

    return {
        "meta": {
            "title": "National labour context — the informal-borrower base (measured)",
            "generated_by": "pipeline/build_labour_context.py",
            "label": "MEASURED — ILOSTAT mirror of Thailand's official NSO LFS submissions "
                     "(informality, other sectors), OVERLAID with NSO's own quarterly LFS "
                     "cross-tabs for self-employment + the agriculture sector "
                     "(source-data/nso_lfs_status.json) AND for the national unemployment rate "
                     "(source-data/staging/nso_lfs.json, labour-force-weighted over 77 provinces) "
                     "where those files are present (see nso_source notes on those entries). "
                     "NATIONAL level only (the geoblock verdict: no cloud path to per-province "
                     "LFS; vendored SES 2566 remains the per-province source).",
            "source": "source-data/ilostat_labour.json (pull_ilostat_labour.py, pulled %s)"
                      % src.get("meta", {}).get("pulled", "?"),
            "nso_override": nso_note,
            "nso_unemployment_override": nso_unemp_note,
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
        "unemployment": unemployment,
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
            print("build_labour_context.py --check: SKIP (labour_context.json not generated yet)")
            sys.exit(3)
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
