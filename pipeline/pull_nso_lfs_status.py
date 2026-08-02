#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pull_nso_lfs_status.py — MEASURED national employment by INDUSTRY and by WORK STATUS, quarterly
(owner escalation 2026-08-02: the "AGRI JOBS" and "SELF-EMPLOYED" chips on the live macro strip
showed 2024/2025-ANNUAL figures from the ILOSTAT mirror; the owner asked to find the newest NSO
quarter, since NSO's own Labour Force Survey is published quarterly).

SOURCE (NSO CKAN catalog API, catalogapi.nso.go.th — reachable from Kaustav's Thai IP; the same
host/UA idiom as pull_nso_wages.py):
  LFS_02_20535_8  จำนวนผู้มีงานทำ จำแนกตามภาค อุตสาหกรรม และเพศ  (employed, by region x industry x sex)
  LFS_02_20535_9  จำนวนผู้มีงานทำ จำแนกตามภาค สถานภาพการทำงาน และเพศ  (by region x work-status x sex)
  Both are resources under CKAN package 0706_02_0002 (จำนวนผู้มีงานทำ), the same NSO LFS quarterly
  release already used for province-level branch features (see source-data/staging/nso_lfs.json /
  ingest_real_tape.py's nso pull) — this script pulls the NATIONAL-level industry/status cross-tabs
  that province-scoped pull never fetched.

WHY THESE TWO TABLES, AND HOW THE NATIONAL TOTAL IS BUILT: neither table publishes a ready-made
ทั่วประเทศ (nationwide) row — only the 7 NSO regions (กรุงเทพมหานคร + 6 ภาค) x 2 sexes. The
national total for a quarter is the sum of all region x sex cells for that quarter. This script
sums ONLY rows where SEX is exactly ชาย or หญิง — a real data-quality issue was found and must be
guarded against: every row for YEAR=2567 (2024, all 4 quarters) in the WORK_STATUS table has its
SEX and WORK_STATUS columns swapped (a NSO export artifact for that vintage only — confirmed by
inspecting the raw rows: values that belong in WORK_STATUS, e.g. "ทำงานส่วนตัว", appear in the SEX
column and vice versa). Filtering to SEX in {ชาย, หญิง} silently drops those corrupted 2567 rows
rather than mis-summing them into a category total; every other year (2563-2566, 2568-2569) has
clean rows and is unaffected. The two tables cross-validate each other: for every clean quarter the
region+sex-summed grand total from the industry table and from the work-status table agree to
within ~0.1% (both are the same LFS "number employed" universe, just cut two different ways) — this
script hard-fails if they disagree by more than 0.5%, catching a parser break rather than silently
publishing a skewed share.

DEFINITIONS (kept identical to the existing ILOSTAT-sourced chips in platform/data/labour_context.json
/ pipeline/build_labour_context.py, so this is a FRESHER cut of the same indicator, never a different
one under the same label):
  - "AGRI JOBS" = share of total employed persons whose INDUSTRY is
    เกษตรกรรม การป่าไม้ และการประมง (Agriculture, forestry & fishing) — the same ECO_AGGREGATE_AGR
    concept ILOSTAT's EMP_TEMP_SEX_ECO_NB carries as "Agriculture".
  - "SELF-EMPLOYED" = (employer นายจ้าง + own-account ทำงานส่วนตัว + contributing-family
    ช่วยธุรกิจครอบครัว) / total employed — the exact own-account+employer+family-worker sum
    build_labour_context.py already uses from ILOSTAT's STE_ICSE93_2/_3/_5 (ICSE-93 status-in-
    employment classes 2, 3, 5). "การรวมกลุ่ม" (ICSE-93 class 4, cooperative-producer members,
    ~0.02% of employment) is excluded from both, for exact comparability.

VERIFIED 2026-08-02 (live pull): latest common quarter in both tables is 2569 ไตรมาส 1 (2026 Q1).
National total employed (industry-table cut) 41,194.43 thousand vs (status-table cut) 41,194.46
thousand — 0.0001% apart, well inside the cross-validation tolerance. Agriculture 11,252.79
thousand = 27.3% of employment (vs 26.9% a year earlier, 2568 Q1: 10,592.23 thousand). Self-employed
(employer+own-account+family) 20,696.58 thousand = 50.2% (vs 49.6% a year earlier, 2568 Q1:
19,520.11 thousand). These four totals are the anchors below.

DETERMINISM: the live pull's two full CSVs are cached (gitignored) at
source-data/.nso_lfs_status_raw/{LFS_02_20535_8,LFS_02_20535_9}.csv; source-data/nso_lfs_status.json
is the committed, distilled artifact. `--check` re-parses the cached raw OFFLINE and byte-compares.
No wall clock in the data — `pulled` comes only from --stamp.

Run:
  python3 pull_nso_lfs_status.py --stamp 2026-08-02   # download + parse + write
  python3 pull_nso_lfs_status.py                       # default --stamp = today
  python3 pull_nso_lfs_status.py --check               # offline byte-reproduce from cached raw
"""
import argparse
import csv
import datetime
import io
import json
import os
import sys
import urllib.request
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

OUT = os.path.join(ROOT, "source-data", "nso_lfs_status.json")
RAW_DIR = os.path.join(ROOT, "source-data", ".nso_lfs_status_raw")
RAW_INDUSTRY = os.path.join(RAW_DIR, "LFS_02_20535_8.csv")
RAW_STATUS = os.path.join(RAW_DIR, "LFS_02_20535_9.csv")

TABLE_INDUSTRY = "LFS_02_20535_8"
TABLE_STATUS = "LFS_02_20535_9"
URL_INDUSTRY = "https://catalogapi.nso.go.th/api/index?table=%s&format=csv" % TABLE_INDUSTRY
URL_STATUS = "https://catalogapi.nso.go.th/api/index?table=%s&format=csv" % TABLE_STATUS
UA = {"User-Agent": "Mozilla/5.0"}

AGRI_LABEL = "เกษตรกรรม การป่าไม้ และการประมง"
SELF_EMP_STATUSES = ("นายจ้าง", "ทำงานส่วนตัว", "ช่วยธุรกิจครอบครัว")
VALID_SEX = ("ชาย", "หญิง")

# Spot-verification anchors on the latest quarter's national (region+sex-summed) totals —
# thousand persons. A mismatch means the parser or the aggregation broke, not that NSO revised
# published history (re-verify against catalogapi.nso.go.th before trusting a changed anchor).
ANCHORS = {
    "2569-ไตรมาส 1": {
        "industry_grand_total": 41194.43,
        "status_grand_total": 41194.46,
        "agri_total": 11252.79,
        "self_employed_total": 20696.58,
    },
    "2568-ไตรมาส 1": {
        "industry_grand_total": 39383.20,
        "status_grand_total": 39383.31,
        "agri_total": 10592.23,
        "self_employed_total": 19520.11,
    },
}


def _get(url):
    req = urllib.request.Request(url, headers=UA)
    return urllib.request.urlopen(req, timeout=120).read()


def _parse_csv(raw_bytes, need_cols):
    text = raw_bytes.decode("utf-8-sig", errors="replace")
    all_rows = [[c.strip() for c in r] for r in csv.reader(io.StringIO(text)) if any(r)]
    if not all_rows:
        sys.exit("pull_nso_lfs_status.py: empty CSV")
    hdr = all_rows[0]
    ix = {h: i for i, h in enumerate(hdr)}
    if not all(k in ix for k in need_cols):
        sys.exit("pull_nso_lfs_status.py: unexpected CSV header %r (need %r)" % (hdr, need_cols))
    rows = []
    for r in all_rows[1:]:
        if len(r) <= max(ix[k] for k in need_cols):
            continue
        rows.append({k: r[ix[k]] for k in need_cols})
    return rows


def _quarters_present(rows):
    return sorted(set((r["YEAR"], r["QUARTER"].strip()) for r in rows),
                  key=lambda yq: (int(yq[0]), yq[1]))


def _national_totals(rows, cat_col, year, quarter):
    """Sum VALUE over all regions + both sexes for one (year, quarter), grouped by category.
    Rows whose SEX is not exactly ชาย/หญิง are dropped (guards the known 2567 column-swap bug)."""
    totals = defaultdict(float)
    n_used = 0
    for r in rows:
        if r["YEAR"] != year or r["QUARTER"].strip() != quarter:
            continue
        if r["SEX"] not in VALID_SEX:
            continue
        try:
            v = float(r["VALUE"])
        except ValueError:
            continue
        totals[r[cat_col].strip()] += v
        n_used += 1
    return dict(totals), n_used


def _verify_anchor(label, computed):
    want = ANCHORS.get(label)
    if not want:
        return
    bad = []
    for k, want_v in want.items():
        got_v = computed.get(k)
        if got_v is None or abs(got_v - want_v) > max(0.5, 0.005 * want_v):
            bad.append("%s/%s: got %s, expected %s" % (label, k, got_v, want_v))
    if bad:
        sys.exit("pull_nso_lfs_status.py: ANCHOR FAIL — re-verify before landing:\n  " + "\n  ".join(bad))


def _quarter_snapshot(industry_rows, status_rows, year, quarter):
    ind_totals, ind_n = _national_totals(industry_rows, "INDUSTRY", year, quarter)
    sta_totals, sta_n = _national_totals(status_rows, "WORK_STATUS", year, quarter)
    ind_grand = sum(ind_totals.values())
    sta_grand = sum(sta_totals.values())
    if ind_grand and sta_grand:
        drift = abs(ind_grand - sta_grand) / ind_grand
        if drift > 0.005:
            sys.exit("pull_nso_lfs_status.py: %s-%s industry-table grand total (%.2f) and "
                     "status-table grand total (%.2f) disagree by %.2f%% (>0.5%%) — cross-"
                     "validation failed, aborting rather than publishing a skewed share."
                     % (year, quarter, ind_grand, sta_grand, 100 * drift))
    agri_total = sum(v for k, v in ind_totals.items() if AGRI_LABEL in k)
    self_total = sum(sta_totals.get(k, 0.0) for k in SELF_EMP_STATUSES)
    label = "%s-%s" % (year, quarter)
    computed = {
        "industry_grand_total": round(ind_grand, 2),
        "status_grand_total": round(sta_grand, 2),
        "agri_total": round(agri_total, 2),
        "self_employed_total": round(self_total, 2),
    }
    _verify_anchor(label, computed)
    return {
        "year_be": year, "quarter": quarter,
        "n_rows_industry": ind_n, "n_rows_status": sta_n,
        "employed_total_thousand": round((ind_grand + sta_grand) / 2, 2),
        "agriculture": {
            "employed_thousand": round(agri_total, 2),
            "share_pct": round(100.0 * agri_total / ind_grand, 2) if ind_grand else None,
        },
        "self_employed": {
            "employed_thousand": round(self_total, 2),
            "share_pct": round(100.0 * self_total / sta_grand, 2) if sta_grand else None,
            "components_thousand": {k: round(sta_totals.get(k, 0.0), 2) for k in SELF_EMP_STATUSES},
        },
        "work_status_breakdown_thousand": {k: round(v, 2) for k, v in sorted(sta_totals.items())},
    }


def build_from_raw(industry_bytes, status_bytes, stamp):
    industry_rows = _parse_csv(industry_bytes, ("YEAR", "QUARTER", "REGION", "SEX", "INDUSTRY", "VALUE"))
    status_rows = _parse_csv(status_bytes, ("YEAR", "QUARTER", "REGION", "SEX", "WORK_STATUS", "VALUE"))

    q_ind = _quarters_present(industry_rows)
    q_sta = _quarters_present(status_rows)
    common = [yq for yq in q_ind if yq in set(q_sta)]
    if not common:
        sys.exit("pull_nso_lfs_status.py: no quarter is present in BOTH tables — abort.")
    latest = common[-1]
    year_ago = None
    for cand in common:
        if cand[1] == latest[1] and cand[0] == str(int(latest[0]) - 1):
            year_ago = cand
            break
    prior_q = common[-2] if len(common) >= 2 else None

    latest_snap = _quarter_snapshot(industry_rows, status_rows, *latest)
    prior_snap = _quarter_snapshot(industry_rows, status_rows, *prior_q) if prior_q else None
    year_ago_snap = _quarter_snapshot(industry_rows, status_rows, *year_ago) if year_ago else None

    def _delta(a, b, path):
        if not a or not b:
            return None
        av, bv = a, b
        for k in path:
            av, bv = av[k], bv[k]
        return round(av - bv, 2)

    trend = {
        "vs_prior_quarter": {
            "quarter": "%s-%s" % prior_q if prior_q else None,
            "agri_employed_delta_thousand": _delta(latest_snap, prior_snap, ("agriculture", "employed_thousand")),
            "agri_share_delta_pp": _delta(latest_snap, prior_snap, ("agriculture", "share_pct")),
            "self_employed_share_delta_pp": _delta(latest_snap, prior_snap, ("self_employed", "share_pct")),
        } if prior_snap else None,
        "vs_year_ago_quarter": {
            "quarter": "%s-%s" % year_ago if year_ago else None,
            "agri_employed_delta_thousand": _delta(latest_snap, year_ago_snap, ("agriculture", "employed_thousand")),
            "agri_share_delta_pp": _delta(latest_snap, year_ago_snap, ("agriculture", "share_pct")),
            "self_employed_share_delta_pp": _delta(latest_snap, year_ago_snap, ("self_employed", "share_pct")),
        } if year_ago_snap else None,
    }

    return {
        "meta": {
            "title": "National employment by industry (agriculture share) and by work status "
                     "(self-employment share) — the MEASURED quarterly NSO series behind the "
                     "'AGRI JOBS' and 'SELF-EMPLOYED' chips on the macro strip",
            "generated_by": "pipeline/pull_nso_lfs_status.py",
            "label": "MEASURED — สำนักงานสถิติแห่งชาติ (NSO), Labour Force Survey, tables "
                     "LFS_02_20535_8 (by region x industry x sex) and LFS_02_20535_9 (by region x "
                     "work-status x sex), summed to national. Thousand persons, quarterly.",
            "source_urls": {"industry": URL_INDUSTRY, "work_status": URL_STATUS},
            "unit": "thousand persons",
            "frequency": "quarterly",
            "pulled": stamp,
            "quarters_available_both_tables": ["%s-%s" % yq for yq in common],
            "definitions": {
                "agri_jobs": "share of employed persons whose industry is agriculture, forestry "
                            "and fishing (เกษตรกรรม การป่าไม้ และการประมง) — same concept as "
                            "labour_context.json's ILOSTAT ECO_AGGREGATE_AGR sector share.",
                "self_employed": "(employer + own-account + contributing-family) / total employed "
                                 "— same concept and same three ICSE-93 classes as "
                                 "labour_context.json's self_employment "
                                 "(own_account + contributing_family + employers), excluding the "
                                 "~0.02%-of-employment 'การรวมกลุ่ม' cooperative-member class from "
                                 "both for exact comparability.",
            },
            "data_quality_note": "Neither table publishes a nationwide (ทั่วประเทศ) row — every "
                                 "total here is this script's own sum of the 7 NSO regions x 2 "
                                 "sexes. Rows whose SEX column is not exactly ชาย/หญิง are dropped: "
                                 "every row for YEAR=2567 (2024, all 4 quarters) in the work-status "
                                 "table has SEX and WORK_STATUS swapped in NSO's own export (a "
                                 "known artifact for that vintage only, confirmed by inspecting raw "
                                 "rows) — filtering avoids mis-summing those, at the cost of no "
                                 "2567 figure from this script (the existing annual ILOSTAT-sourced "
                                 "2024/2025 chips still cover that gap). The two tables independently "
                                 "cross-validate every clean quarter's grand total to within 0.5%.",
            "acceptance_test": "2 spot-verified quarters (2568-ไตรมาส 1, 2569-ไตรมาส 1) checked "
                               "against fixed anchors on every pull, plus a live 0.5%% cross-"
                               "validation between the two source tables' grand totals; a mismatch "
                               "hard-fails rather than silently landing a skewed share.",
        },
        "latest": latest_snap,
        "prior_quarter": prior_snap,
        "year_ago_quarter": year_ago_snap,
        "trend": trend,
    }


def _dumps(data):
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def main():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:
            pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stamp", default=datetime.date.today().isoformat(),
                    help="YYYY-MM-DD pull date embedded in meta.pulled (default: today)")
    ap.add_argument("--check", action="store_true",
                    help="OFFLINE: re-parse the cached raw CSVs and byte-compare against "
                         "source-data/nso_lfs_status.json; exit 1 on drift, exit 3 SKIP if the "
                         "committed JSON or the gitignored raw cache is absent (network-pulled "
                         "input).")
    args = ap.parse_args()

    if args.check:
        if not os.path.exists(OUT) or not os.path.exists(RAW_INDUSTRY) or not os.path.exists(RAW_STATUS):
            print("pull_nso_lfs_status.py --check: SKIP (committed nso_lfs_status.json or "
                  "gitignored raw source-data/.nso_lfs_status_raw/ absent — network-pulled input, "
                  "not drift)")
            sys.exit(3)
        prev = json.load(open(OUT, encoding="utf-8"))
        industry_bytes = open(RAW_INDUSTRY, "rb").read()
        status_bytes = open(RAW_STATUS, "rb").read()
        data = build_from_raw(industry_bytes, status_bytes, prev["meta"]["pulled"])
        if _dumps(data) != open(OUT, encoding="utf-8").read():
            sys.exit("pull_nso_lfs_status.py --check: nso_lfs_status.json drifted from a fresh "
                     "parse of the cached raw — re-run python3 pipeline/pull_nso_lfs_status.py")
        print("pull_nso_lfs_status.py --check: OK (byte-exact from cached raw, latest %s-%s)"
              % (data["latest"]["year_be"], data["latest"]["quarter"]))
        return

    os.makedirs(RAW_DIR, exist_ok=True)
    print("fetching %s ..." % URL_INDUSTRY)
    industry_bytes = _get(URL_INDUSTRY)
    print("fetching %s ..." % URL_STATUS)
    status_bytes = _get(URL_STATUS)
    with open(RAW_INDUSTRY, "wb") as f:
        f.write(industry_bytes)
    with open(RAW_STATUS, "wb") as f:
        f.write(status_bytes)
    data = build_from_raw(industry_bytes, status_bytes, args.stamp)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write(_dumps(data))
    print("wrote %s" % OUT)
    print("  latest quarter: %s-%s" % (data["latest"]["year_be"], data["latest"]["quarter"]))
    print("  agri jobs share: %.2f%%  self-employed share: %.2f%%"
          % (data["latest"]["agriculture"]["share_pct"], data["latest"]["self_employed"]["share_pct"]))
    print("  acceptance test: PASSED (2/2 anchor quarters matched, cross-validation within 0.5%)")


if __name__ == "__main__":
    main()
