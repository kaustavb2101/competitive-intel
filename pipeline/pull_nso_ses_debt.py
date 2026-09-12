#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pull_nso_ses_debt.py — PORTFOLIO RISK (objective #1): the AUTHORITATIVE per-province household
debt figure, pulled live from NSO's own CKAN and distilled into a small committed layer.

WHY THIS EXISTS
---------------
`build_household_risk.py` (the hhdti / pstress National-map risk lens) was joining a *vendored*
household-debt file (`source-data/household_debt_by_province.json`, carried over the TMLI bridge).
That file's own meta claimed its `debt_per_household` was "MEASURED (NSO SES 2566, matches the
independently-vendored nso-ses-debt-2566.json)". It does NOT: audited 2026-09-12 against NSO's own
CKAN, only 4 of 77 provinces matched the authoritative figure; the rest diverged by up to ~4.5x
(e.g. Khon Kaen shipped 280,791 vs the authoritative 62,884; Bangkok shipped 88,856 vs 161,050),
and the two vendored files do not agree with each other either. So the shipped household-DTI risk
ranking was materially wrong for the great majority of provinces.

The authoritative source IS reachable from CI (the `data.go.th` aggregator is geo-blocked, but
NSO's own catalog `catalogapi.nso.go.th` answers 200 — see docs/BLOCKED_SOURCES.md, the NSO
recheck trigger). This puller reads it, reconstructs the province average, and commits a small
distilled layer with the citable resource id, so the risk lens rests on a source anyone can verify.

SOURCE (all-household basis, NOT indebted-only)
-----------------------------------------------
  package  0705_08_0009  "หนี้สินเฉลี่ยต่อครัวเรือน"                     (NSO กองสถิติสังคม)
  table    SFD_SPB0806   "หนี้สินเฉลี่ยต่อครัวเรือนทั้งสิ้น จำแนกตาม
                          วัตถุประสงค์ของการกู้ยืม และสถานะทางเศรษฐสังคม"  SES 2566, pub 2026-02-27
  url      https://catalogapi.nso.go.th/api/index?table=SFD_SPB0806&format=csv

METHOD (deterministic reconstruction of the province average)
------------------------------------------------------------
The table has no pre-aggregated "all households" row — debt is broken out by 10 mutually-exclusive
socioeconomic leaf groups (soc_eco_class1 x soc_eco_class2) per province. The province average
household debt is therefore the household-weighted mean of each leaf's average-debt-per-household,
weighted by that leaf's total-household count:

    debt(province) = Σ_leaf ( avg_debt_leaf * n_households_leaf ) / Σ_leaf n_households_leaf

INTEGRITY SELF-CHECK: the national household-weighted mean this reconstruction produces is
197,255 THB, which is exactly NSO's published SES 2566 national headline — proof the method is
right. The puller ASSERTS this (within rounding) and refuses to write if it drifts, so a silent
upstream schema change can never launder a wrong number into the committed layer.

NOT IN THE DETERMINISM GATE: this is a network puller (its input is off-repo and live), exactly
like ingest_tmli.py and the other pull_*.py. What IS gated is everything downstream of the
committed JSON: build_household_risk.py reads source-data/nso_ses_debt_2566.json and is --check'd.

USAGE
-----
    python3 pipeline/pull_nso_ses_debt.py            # pull, distil, write the committed layer
    python3 pipeline/pull_nso_ses_debt.py --check    # pull, distil, compare to the committed file
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
OUT = os.path.join(ROOT, "source-data", "nso_ses_debt_2566.json")

PACKAGE = "0705_08_0009"
RESOURCE = "SFD_SPB0806"
RESOURCE_ID = "89cc71ae-f596-4307-b38f-10d61d084801"
URL = "https://catalogapi.nso.go.th/api/index?table=%s&format=csv" % RESOURCE
PUBLISHED = "2026-02-27"          # CKAN resource `created` date (the SES 2566 publication)
AS_OF = "2566"                    # SES survey round (2023 CE)

# the two row selectors we need from the (purpose x source x socio) cube
HH_COUNT = "จำนวนครัวเรือนทั้งสิ้น"          # total households in the leaf group
AVG_DEBT = "จำนวนหนี้สินเฉลี่ยต่อครัวเรือน"  # average debt per household in the leaf group

# integrity anchor: NSO's published SES 2566 national headline (all-household mean debt, THB)
NATIONAL_HEADLINE = 197255
NATIONAL_TOL = 5  # THB; the reconstruction lands exactly on it — a tiny band guards rounding only


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


def distil(csv_text):
    """CSV text -> {province(th): int debt}, plus the national reconstruction for the self-check."""
    rows = list(csv.DictReader(io.StringIO(csv_text)))
    if not rows:
        sys.exit("pull_nso_ses_debt: SFD_SPB0806 returned 0 rows — refusing to write")

    # per province, per socio leaf: gather the household count and the avg-debt-per-household
    prov = {}
    for r in rows:
        p = r.get("province")
        leaf = (r.get("soc_eco_class1"), r.get("soc_eco_class2"))
        g = prov.setdefault(p, {}).setdefault(leaf, {})
        if r.get("purpose_source_bor") == HH_COUNT and r.get("hhdebt_totaldebt") == HH_COUNT:
            g["nhh"] = _num(r.get("value"))
        if r.get("purpose_source_bor") == AVG_DEBT and r.get("hhdebt_totaldebt") == AVG_DEBT:
            g["debt"] = _num(r.get("value"))

    out = {}
    nat_num = 0.0
    nat_den = 0.0
    for p, leaves in prov.items():
        num = 0.0
        den = 0.0
        for g in leaves.values():
            nhh = g.get("nhh")
            debt = g.get("debt")
            if nhh and debt is not None:
                num += debt * nhh
                den += nhh
        if den > 0:
            out[p] = int(round(num / den))
            nat_num += num
            nat_den += den

    national = int(round(nat_num / nat_den)) if nat_den else None
    return out, national


def build():
    csv_text = _fetch_csv(URL)
    provinces, national = distil(csv_text)

    if len(provinces) != 77:
        sys.exit("pull_nso_ses_debt: got %d provinces, expected 77 — refusing to write"
                 % len(provinces))
    if national is None or abs(national - NATIONAL_HEADLINE) > NATIONAL_TOL:
        sys.exit("pull_nso_ses_debt: national reconstruction %s != NSO headline %d (tol %d) — "
                 "the table's schema likely changed; refusing to write a suspect layer"
                 % (national, NATIONAL_HEADLINE, NATIONAL_TOL))

    doc = {
        "meta": {
            "title": "Per-province household debt (all households) — NSO SES 2566, AUTHORITATIVE",
            "generated_by": "pipeline/pull_nso_ses_debt.py",
            "label": "MEASURED — average household debt (THB) per canonical Thai province, all "
                     "households, from the National Statistical Office Socio-Economic Survey "
                     "(SES) 2566 (2023 CE), pulled from NSO's own open-data catalog and "
                     "reconstructed to the province level by household-weighted mean over the "
                     "survey's socioeconomic strata.",
            "source": "NSO (สำนักงานสถิติแห่งชาติ), กองสถิติสังคม — CKAN package %s, "
                      "resource %s (%s)." % (PACKAGE, RESOURCE, RESOURCE_ID),
            "package": PACKAGE,
            "resource": RESOURCE,
            "resource_id": RESOURCE_ID,
            "url": URL,
            "as_of": AS_OF,
            "published": PUBLISHED,
            "basis": "ALL households (table SFD_SPB0806 'ครัวเรือนทั้งสิ้น'), NOT the "
                     "indebted-only subset (SFD_SPB0807).",
            "method": "Province average = household-weighted mean of each socioeconomic leaf "
                      "group's (soc_eco_class1 x soc_eco_class2) average debt-per-household, "
                      "weighted by that leaf's total-household count. The table carries no "
                      "pre-aggregated 'all households' row, so the province total is "
                      "reconstructed from the strata.",
            "national_avg_debt_per_household": national,
            "national_check": "Equals NSO's published SES 2566 national headline (%d THB) — the "
                              "reconstruction's built-in correctness proof." % NATIONAL_HEADLINE,
            "n_provinces": len(provinces),
            "gate": "network puller, NOT in the determinism gate (live off-repo input, like "
                    "ingest_tmli.py). Everything downstream of this committed file IS gated: "
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

    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    doc = json.loads(text)
    print("wrote %s (%d provinces, national avg %d THB)"
          % (OUT, doc["meta"]["n_provinces"], doc["meta"]["national_avg_debt_per_household"]))


if __name__ == "__main__":
    main()
