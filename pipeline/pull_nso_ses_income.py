#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pull_nso_ses_income.py — PORTFOLIO RISK (objective #1): the AUTHORITATIVE per-province average
monthly household income, pulled live from NSO's own CKAN and distilled into a small committed
layer. The income sibling of pull_nso_ses_debt.py.

WHY THIS EXISTS
---------------
`build_household_risk.py` (the hhdti / pstress National-map risk lens) forms debt-to-income from
an authoritative NSO-CKAN debt numerator (fixed 2026-09-12, pull_nso_ses_debt.py) but was still
dividing by a *vendored* income denominator (`source-data/household_income_by_province.json`,
carried over the TMLI bridge). That file's `avg_monthly_income` is NOT a household income at all:
its own meta admits it is the UNWEIGHTED mean across five occupation rows
(OfficeStaff/FactoryWorkers/Transport/SMEOwners/Agriculture), and it comes from the same vendored
source whose debt figures were found wrong for 73 of 77 provinces. Audited 2026-09-12 against NSO's
own CKAN (table SFD_SPB0802_66, package 0705_08_0007), the unweighted-occupation mean diverges from
the true household-weighted average income by up to ~1.3x (e.g. Sisaket 25,597 vs the authoritative
19,858 — a 1.29x overstatement that hid its true DTI), and re-ranks 67 of 77 provinces on DTI; the
most-stressed province flips. So the shipped household-DTI denominator was materially wrong.

The authoritative source IS reachable from CI (the `data.go.th` aggregator is geo-blocked, but
NSO's own catalog `catalogapi.nso.go.th` answers 200 — see docs/BLOCKED_SOURCES.md, the NSO recheck
trigger). This puller reads it, reconstructs the province average, and commits a small distilled
layer with the citable resource id, so the risk lens rests on a source anyone can verify.

SOURCE (all-household basis)
----------------------------
  income   package  0705_08_0007  "รายได้เฉลี่ยต่อเดือนของครัวเรือน"                     (NSO กองสถิติสังคม)
           table    SFD_SPB0802_66 "รายได้เฉลี่ยต่อเดือนของครัวเรือน จำแนกตามแหล่งที่มา
                                    ของรายได้ และสถานะทางเศรษฐสังคมของครัวเรือน"          SES 2566, pub 2026-02-27
           url      https://catalogapi.nso.go.th/api/index?table=SFD_SPB0802_66&format=csv
  weights  table    SFD_SPB0806    the DEBT table's total-household counts per socioeconomic leaf
                                    (จำนวนครัวเรือนทั้งสิ้น) — the same survey, same strata; the
                                    income table carries no household-count column of its own.

METHOD (deterministic reconstruction of the province average — mirrors pull_nso_ses_debt.py)
--------------------------------------------------------------------------------------------
Income is broken out by income source (source_income1/2/3) x the same 10 mutually-exclusive
socioeconomic leaf groups (soc_eco_class1 x soc_eco_class2) per province. There is no
pre-aggregated "all households" row. The province average monthly household income is therefore the
household-weighted mean of each leaf's total-monthly-income (source_income1/2/3 all
'รายได้ทั้งสิ้นต่อเดือน'), weighted by that leaf's total-household count from SFD_SPB0806:

    income(province) = Σ_leaf ( income_leaf * n_households_leaf ) / Σ_leaf n_households_leaf

Weighting the income denominator by the SAME per-leaf household counts as the debt numerator keeps
the debt-to-income ratio a like-for-like household-weighted comparison over identical strata.

INTEGRITY SELF-CHECK: the national household-weighted mean this reconstruction produces is
29,030 THB/month, which is exactly NSO's published SES 2566 national headline (widely cited, e.g.
SCB EIC on the 2023 SES) — proof the method and the weights are right. The puller ASSERTS this
(within rounding) and refuses to write if it drifts, so a silent upstream schema change can never
launder a wrong number into the committed layer.

NOT IN THE DETERMINISM GATE: this is a network puller (its input is off-repo and live), exactly
like pull_nso_ses_debt.py / ingest_tmli.py and the other pull_*.py. What IS gated is everything
downstream of the committed JSON: build_household_risk.py reads source-data/nso_ses_income_2566.json
and is --check'd.

USAGE
-----
    python3 pipeline/pull_nso_ses_income.py            # pull, distil, write the committed layer
    python3 pipeline/pull_nso_ses_income.py --check    # pull, distil, compare to the committed file
                                                       #   (exit 1 on drift) — for a manual refresh
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import os
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(ROOT, "source-data", "nso_ses_income_2566.json")

# canonical 77 Thai province names — the same set build_household_risk.py joins on
sys.path.insert(0, HERE)
from lib.regionmap import REGION  # noqa: E402

# --- income table (the values) ---
PACKAGE = "0705_08_0007"
RESOURCE = "SFD_SPB0802_66"
RESOURCE_ID = "b0817d48-5eec-4ed9-a677-639d304d20ec"
INCOME_URL = "https://catalogapi.nso.go.th/api/index?table=%s&format=csv" % RESOURCE
PUBLISHED = "2026-02-27"          # CKAN resource `created` date (the SES 2566 publication)
AS_OF = "2566"                    # SES survey round (2023 CE)

# --- debt table (the household weights only — the income table has no household count) ---
WEIGHT_RESOURCE = "SFD_SPB0806"
WEIGHT_URL = "https://catalogapi.nso.go.th/api/index?table=%s&format=csv" % WEIGHT_RESOURCE
HH_COUNT = "จำนวนครัวเรือนทั้งสิ้น"          # total households in the leaf group (debt table)

# the income row we need: the leaf's TOTAL monthly income (all three source levels are the total)
TOTAL_INCOME = "รายได้ทั้งสิ้นต่อเดือน"

# the source's fixed structure: this many mutually-exclusive socioeconomic leaves per province
# (soc_eco_class1 x soc_eco_class2). Enforced so a truncated pull can't silently drop a stratum.
LEAVES_PER_PROVINCE = 10

# integrity anchor: NSO's published SES 2566 national headline (all-household mean monthly income,
# THB). The reconstruction lands on 29,030.26 -> 29,030; a tiny band guards rounding only.
NATIONAL_HEADLINE = 29030
NATIONAL_TOL = 3  # THB


def _num(s):
    s = (s or "").strip().replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None


def _fetch_csv(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read().decode("utf-8-sig")


def _weights(csv_text):
    """Debt-table CSV -> {(province, leaf): n_households}. The income table carries no household
    count, so the per-leaf weights come from the debt table's total-household rows (same survey,
    same socioeconomic strata)."""
    rows = list(csv.DictReader(io.StringIO(csv_text)))
    if not rows:
        sys.exit("pull_nso_ses_income: %s returned 0 rows — refusing to write" % WEIGHT_RESOURCE)
    w = {}
    for r in rows:
        if r.get("purpose_source_bor") == HH_COUNT and r.get("hhdebt_totaldebt") == HH_COUNT:
            leaf = (r.get("soc_eco_class1"), r.get("soc_eco_class2"))
            w[(r.get("province"), leaf)] = _num(r.get("value"))
    return w


def distil(income_csv, weight_csv):
    """(income CSV, weight CSV) -> {province(th): int monthly income}, plus the national
    reconstruction for the self-check."""
    weights = _weights(weight_csv)

    rows = list(csv.DictReader(io.StringIO(income_csv)))
    if not rows:
        sys.exit("pull_nso_ses_income: %s returned 0 rows — refusing to write" % RESOURCE)

    # per province, per socioeconomic leaf: the leaf's total monthly income
    prov = {}
    for r in rows:
        if (r.get("source_income1") == TOTAL_INCOME
                and r.get("source_income2") == TOTAL_INCOME
                and r.get("source_income3") == TOTAL_INCOME):
            leaf = (r.get("soc_eco_class1"), r.get("soc_eco_class2"))
            prov.setdefault(r.get("province"), {})[leaf] = _num(r.get("value"))

    out = {}
    nat_num = 0.0
    nat_den = 0.0
    for p, leaves in prov.items():
        # Exactly LEAVES_PER_PROVINCE mutually-exclusive socioeconomic leaves per province, each
        # with a total-monthly-income figure. Enforce it: a truncated response that drops one leaf
        # could otherwise still leave 77 provinces and keep the national mean within tolerance while
        # silently changing one province's published income. Any shortfall means the pull is
        # incomplete — refuse it.
        if len(leaves) != LEAVES_PER_PROVINCE:
            sys.exit("pull_nso_ses_income: province %r has %d socioeconomic leaves, expected %d — "
                     "incomplete pull; refusing to write" % (p, len(leaves), LEAVES_PER_PROVINCE))
        num = 0.0
        den = 0.0
        for leaf, inc in leaves.items():
            if inc is None:
                sys.exit("pull_nso_ses_income: province %r leaf %r missing income — incomplete "
                         "pull; refusing to write" % (p, leaf))
            nhh = weights.get((p, leaf))
            if nhh is None:
                sys.exit("pull_nso_ses_income: province %r leaf %r has no household weight in the "
                         "debt table — the two tables' strata disagree; refusing to write"
                         % (p, leaf))
            # a 0-household leaf legitimately contributes 0 weight (e.g. Bangkok agriculture)
            num += inc * nhh
            den += nhh
        if den <= 0:
            sys.exit("pull_nso_ses_income: province %r has 0 total households — refusing to write"
                     % p)
        out[p] = int(round(num / den))
        nat_num += num
        nat_den += den

    national = int(round(nat_num / nat_den)) if nat_den else None
    return out, national


def build():
    income_csv = _fetch_csv(INCOME_URL)
    weight_csv = _fetch_csv(WEIGHT_URL)
    provinces, national = distil(income_csv, weight_csv)

    # exact-identity check, not just a count: the downstream join (build_household_risk.py)
    # intersects on province NAME, so a single renamed/mismatched key would silently drop a
    # province and recompute every percentile over 76 rows while the count still reads 77. Require
    # the key set to equal the canonical 77 Thai names exactly.
    canonical = set(REGION)
    got = set(provinces)
    if got != canonical:
        missing = sorted(canonical - got)
        unexpected = sorted(got - canonical)
        sys.exit("pull_nso_ses_income: province key set != canonical regionmap.REGION — "
                 "missing=%s unexpected=%s; refusing to write" % (missing, unexpected))
    if national is None or abs(national - NATIONAL_HEADLINE) > NATIONAL_TOL:
        sys.exit("pull_nso_ses_income: national reconstruction %s != NSO headline %d (tol %d) — "
                 "the table's schema likely changed; refusing to write a suspect layer"
                 % (national, NATIONAL_HEADLINE, NATIONAL_TOL))

    doc = {
        "meta": {
            "title": "Per-province average monthly household income — NSO SES 2566, AUTHORITATIVE",
            "generated_by": "pipeline/pull_nso_ses_income.py",
            "label": "MEASURED — average monthly household income (THB) per canonical Thai "
                     "province, all households, from the National Statistical Office "
                     "Socio-Economic Survey (SES) 2566 (2023 CE), pulled from NSO's own open-data "
                     "catalog and reconstructed to the province level by household-weighted mean "
                     "over the survey's socioeconomic strata.",
            "source": "NSO (สำนักงานสถิติแห่งชาติ), กองสถิติสังคม — CKAN package %s, "
                      "resource %s (%s). Household weights from the debt table %s." % (
                          PACKAGE, RESOURCE, RESOURCE_ID, WEIGHT_RESOURCE),
            "package": PACKAGE,
            "resource": RESOURCE,
            "resource_id": RESOURCE_ID,
            "url": INCOME_URL,
            "weight_resource": WEIGHT_RESOURCE,
            "as_of": AS_OF,
            "published": PUBLISHED,
            "basis": "ALL households; leaf total monthly income (source_income 'รายได้ทั้งสิ้น"
                     "ต่อเดือน'), household-weighted to the province level.",
            "method": "Province average = household-weighted mean of each socioeconomic leaf "
                      "group's (soc_eco_class1 x soc_eco_class2) total monthly income, weighted by "
                      "that leaf's total-household count from the debt table (SFD_SPB0806). The "
                      "income table carries no household-count column and no pre-aggregated 'all "
                      "households' row, so the province total is reconstructed from the strata.",
            "national_avg_monthly_income": national,
            "national_check": "Equals NSO's published SES 2566 national headline (%d THB/month) — "
                              "the reconstruction's built-in correctness proof." % NATIONAL_HEADLINE,
            "n_provinces": len(provinces),
            "unit": "THB per month",
            "gate": "network puller, NOT in the determinism gate (live off-repo input, like "
                    "pull_nso_ses_debt.py). Everything downstream of this committed file IS gated: "
                    "build_household_risk.py --check.",
        },
        # sorted by Thai province key for a stable, diff-friendly committed file
        "provinces": {k: provinces[k] for k in sorted(provinces)},
    }
    return doc


def dumps(obj):
    return json.dumps(obj, ensure_ascii=False, indent=2) + "\n"


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true",
                    help="pull + distil, then byte-compare against the committed file (exit 1 on "
                         "drift). A live refresh check, not part of the offline gate.")
    args = ap.parse_args()

    text = dumps(build())

    if args.check:
        if not os.path.exists(OUT):
            print("CHECK FAIL: %s does not exist" % OUT)
            sys.exit(1)
        with open(OUT, encoding="utf-8") as f:
            existing = f.read()
        if existing == text:
            print("CHECK OK: %s reproduces from a fresh NSO pull" % OUT)
            sys.exit(0)
        print("CHECK FAIL: %s differs from a fresh NSO pull (upstream data moved)" % OUT)
        sys.exit(1)

    # newline="\n": keep the committed blob LF so build_provenance's census and the gate's
    # byte-compare match what CI reads.
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    print("wrote %s (%d provinces; national avg %d THB/month)" % (
        OUT, len(json.loads(text)["provinces"]), json.loads(text)["meta"][
            "national_avg_monthly_income"]))


if __name__ == "__main__":
    main()
