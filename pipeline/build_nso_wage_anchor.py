#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_nso_wage_anchor.py — project the MEASURED NSO regional wage series into a small app-facing
wage anchor (platform/data/nso_wage_anchor.json).

Reads source-data/nso_wages.json (pulled by pull_nso_wages.py — NSO Labour Force Survey table
LFS_02_20545_18, average monthly wage of employees by region × industry × quarter) and projects it
into an app-region-keyed anchor. It picks the latest COMPLETE year (all four quarters present) and
averages across those four quarters — NOT the newest partial year — so the anchor is a stable,
seasonally-smoothed, final figure rather than a single preliminary quarter. It excludes the "ไม่ทราบ"
(unknown) junk industry, and groups industries into the app's occupation/SES buckets
(FactoryWorkers / Construction / Merchants / Agriculture / OfficeStaff) plus the all-industry
headline (รวม).

WHY THIS EXISTS: the app's occupation-income layer (build_occupation_income*.py) is an ESTIMATED
proxy that reads too high for provincial white-collar workers. This is a MEASURED regional wage
reference to sanity-check it — surfaced on province.html beside the estimated individual figure.
It does NOT feed any risk composite.

A GENUINE DATA GAP, handled honestly (not papered over): from BE2568 onward NSO's ทั่วประเทศ
(national) row in this table publishes ONLY the all-industry aggregate ("รวม") — the per-industry
national breakdown present in BE2563-2567 is absent (verified directly against the pulled data). So
National carries the headline wage only; its per-occupation buckets are null, and `ratio_to_national`
would be null everywhere, so we do not emit it. The practical, fully-measured comparison this anchor
exists for is `ratio_to_bangkok` (กรุงเทพมหานคร is fully measured at every vintage), for all buckets.

Region crosswalk (NSO region -> app region): National=ทั่วประเทศ; Bangkok=กรุงเทพมหานคร;
Central&BKK = mean(กรุงเทพมหานคร, ภาคกลาง); East=ภาคตะวันออก; Isan=ภาคตะวันออกเฉียงเหนือ;
North=ภาคเหนือ; South = mean(ภาคใต้, ภาคใต้ชายแดน). The two multi-region app regions (Central&BKK,
South) are the UNWEIGHTED mean of their constituent NSO regions (no employment weights are available
to weight them, so an unweighted mean is used and documented — it is NOT a fabricated figure). The
five single-region app regions are exact. `by_nso_region` carries the exact per-NSO-region values for
anywhere precision matters.

Deterministic, no network. All wages are integer baht (round of the quarter mean) so the output is
byte-identical across Python builds. `--check` byte-compares; SKIPs (exit 3) if source-data/
nso_wages.json is absent (a network-pulled input, not drift).

Run:
  python3 build_nso_wage_anchor.py           # rebuild platform/data/nso_wage_anchor.json
  python3 build_nso_wage_anchor.py --check   # verify byte-exact (SKIP if source absent)
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, "source-data", "nso_wages.json")
OUT = os.path.join(ROOT, "platform", "data", "nso_wage_anchor.json")

JUNK_INDUSTRY = "ไม่ทราบ"
NATIONAL_REGION = "ทั่วประเทศ"
BANGKOK_REGION = "กรุงเทพมหานคร"

# app occupation/SES bucket -> the exact NSO industry string(s) (verified against the pulled data).
HEADLINE_INDUSTRY = "รวม"
SES_SINGLE = {
    "FactoryWorkers": "การผลิต",
    "Construction": "การก่อสร้าง",
    "Merchants": "การขายส่ง และการขายปลีก การซ่อมยานยนต์",
    "Agriculture": "เกษตรกรรม การป่าไม้ และการประมง",
}
OFFICE_INDUSTRIES = [
    "กิจกรรมทางการเงินและการประกันภัย",
    "กิจกรรมทางวิชาชีพ วิทยาศาสตร์ และเทคนิค",
    "การบริหารราชการ การป้องกันประเทศ การประกันสังคม",
]
# emit order for every region's bucket dict (stable, human-first).
BUCKETS = ["headline", "OfficeStaff", "FactoryWorkers", "Merchants", "Construction", "Agriculture"]

# NSO region -> app region composition (unweighted mean of the listed NSO regions).
APP_REGIONS = {
    "National": [NATIONAL_REGION],
    "Bangkok": [BANGKOK_REGION],
    "Central&BKK": [BANGKOK_REGION, "ภาคกลาง"],
    "East": ["ภาคตะวันออก"],
    "Isan": ["ภาคตะวันออกเฉียงเหนือ"],
    "North": ["ภาคเหนือ"],
    "South": ["ภาคใต้", "ภาคใต้ชายแดน"],
}
# render order for by_app_region / headline_rows.
APP_ORDER = ["National", "Bangkok", "Central&BKK", "East", "Isan", "North", "South"]


def _mean_int(vals):
    """Unweighted mean of a list of numbers -> int baht; None if the list has no non-null value."""
    vals = [v for v in vals if v is not None]
    if not vals:
        return None
    return round(sum(vals) / len(vals))


def _pick_complete_year(rows):
    """The highest year for which the national row carries all four quarters."""
    quarters = {}
    for r in rows:
        if r["region"] == NATIONAL_REGION:
            quarters.setdefault(r["year"], set()).add(r["quarter"])
    complete = sorted(y for y, qs in quarters.items() if len(qs) >= 4)
    if not complete:
        sys.exit("build_nso_wage_anchor.py: no year has 4 complete quarters in nso_wages.json")
    return complete[-1]


def _region_industry_wage(rows, year):
    """{region: {industry: int baht}} = mean across the chosen year's quarters."""
    acc = {}
    for r in rows:
        if r["year"] != year or r["industry"] == JUNK_INDUSTRY:
            continue
        try:
            v = float(r["value"])
        except (TypeError, ValueError):
            continue
        acc.setdefault(r["region"], {}).setdefault(r["industry"], []).append(v)
    return {reg: {ind: _mean_int(vs) for ind, vs in inds.items()} for reg, inds in acc.items()}


def _region_buckets(ind_wage):
    """One NSO region's {industry: wage} -> {bucket: wage or None}."""
    out = {"headline": ind_wage.get(HEADLINE_INDUSTRY)}
    for bucket, industry in SES_SINGLE.items():
        out[bucket] = ind_wage.get(industry)
    out["OfficeStaff"] = _mean_int([ind_wage.get(i) for i in OFFICE_INDUSTRIES])
    return out


def _app_region_buckets(nso_buckets, members):
    """Roll component NSO regions up to one app region (unweighted mean per bucket)."""
    return {b: _mean_int([nso_buckets.get(m, {}).get(b) for m in members]) for b in BUCKETS}


def _ratio(v, base):
    if v is None or base in (None, 0):
        return None
    return round(v / base, 3)


def _fmt(n):
    return "{:,}".format(n) if n is not None else None


def _context(app):
    natl = app["National"]["headline"]
    bkk_h = app["Bangkok"]["headline"]
    bkk_o = app["Bangkok"]["OfficeStaff"]
    isan_o = app["Isan"]["OfficeStaff"]
    parts = []
    if natl is not None:
        parts.append("national headline (รวม) is ฿{}/month".format(_fmt(natl)))
    if bkk_h is not None and bkk_o is not None:
        parts.append("Bangkok is the high-wage benchmark at ฿{} headline / ฿{} office-staff".format(_fmt(bkk_h), _fmt(bkk_o)))
    if isan_o is not None and bkk_o:
        parts.append("provincial regions run materially below Bangkok — e.g. Isan office-staff ฿{} (~{}% of Bangkok)".format(_fmt(isan_o), round(isan_o / bkk_o * 100)))
    return "NSO measured monthly wage, 2568 (4-quarter average): " + "; ".join(parts) + "."


def build(src):
    rows = src["rows"]
    year = _pick_complete_year(rows)
    ind_wage = _region_industry_wage(rows, year)
    nso_buckets = {reg: _region_buckets(iw) for reg, iw in ind_wage.items()}

    by_app_region = {app: _app_region_buckets(nso_buckets, members) for app, members in APP_REGIONS.items()}
    by_nso_region = {reg: nso_buckets[reg] for reg in sorted(nso_buckets)}

    bkk = by_app_region["Bangkok"]
    ratio_to_bangkok = {
        app: {b: _ratio(by_app_region[app][b], bkk.get(b)) for b in BUCKETS} for app in APP_REGIONS
    }
    headline_rows = [
        {
            "region": app,
            "headline_wage": by_app_region[app]["headline"],
            "office_staff_wage": by_app_region[app]["OfficeStaff"],
            "headline_ratio_to_bangkok": _ratio(by_app_region[app]["headline"], bkk.get("headline")),
            "office_staff_ratio_to_bangkok": _ratio(by_app_region[app]["OfficeStaff"], bkk.get("OfficeStaff")),
        }
        for app in APP_ORDER
    ]

    ce_year = int(year) - 543
    meta = {
        "title": "NSO measured wage anchor — real monthly wage by region (objective #1)",
        "generated_by": "pipeline/build_nso_wage_anchor.py",
        "label": "MEASURED — NSO Labour Force Survey average monthly wage of employees (฿/month) by region, latest complete year (4-quarter average).",
        "source": "source-data/nso_wages.json (NSO LFS table LFS_02_20545_18, สำนักงานสถิติแห่งชาติ, MEASURED)",
        "dataset_table": "LFS_02_20545_18",
        "vintage": "2568 (4-quarter average)",
        "vintage_be": year,
        "vintage_ce": ce_year,
        "unit": "THB/month",
        "ses_industry_map": {
            "headline": [HEADLINE_INDUSTRY],
            "FactoryWorkers": [SES_SINGLE["FactoryWorkers"]],
            "Construction": [SES_SINGLE["Construction"]],
            "Merchants": [SES_SINGLE["Merchants"]],
            "Agriculture": [SES_SINGLE["Agriculture"]],
            "OfficeStaff": list(OFFICE_INDUSTRIES),
        },
        "region_crosswalk": {app: list(members) for app, members in APP_REGIONS.items()},
        "multiregion_note": "Central&BKK and South each span two NSO regions; their by_app_region figure is the UNWEIGHTED mean of the constituent NSO regions (no employment weights available). The five single-region app regions are exact. by_nso_region carries the exact per-NSO-region measured values.",
        "note": "Measured reality-check on the ESTIMATED occupation-income surface (build_occupation_income*.py); not an input to any risk composite.",
        "national_gap": "From BE2568 onward NSO's ทั่วประเทศ (national) row publishes only the all-industry aggregate (รวม) — the per-industry national breakdown present in BE2563-2567 is absent. National therefore carries the headline wage only; its per-occupation buckets are null (nothing is synthesized). ratio_to_bangkok is the fully-measured comparison.",
    }

    return {
        "meta": meta,
        "context": _context(by_app_region),
        "by_app_region": by_app_region,
        "by_nso_region": by_nso_region,
        "ratio_to_bangkok": ratio_to_bangkok,
        "headline_rows": headline_rows,
    }


def serialize(data):
    return json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="verify the committed file reproduces byte-exact")
    args = ap.parse_args()

    if not os.path.exists(SRC):
        if args.check:
            print("build_nso_wage_anchor.py --check: SKIP (source-data/nso_wages.json absent — "
                  "network-pulled input, not data drift)")
            sys.exit(3)
        sys.exit("build_nso_wage_anchor.py: source-data/nso_wages.json missing — run pull_nso_wages.py first")

    with open(SRC, encoding="utf-8") as f:
        src = json.load(f)
    out = serialize(build(src))

    if args.check:
        if not os.path.exists(OUT):
            sys.exit("build_nso_wage_anchor.py --check: platform/data/nso_wage_anchor.json missing — run the builder")
        with open(OUT, encoding="utf-8") as f:
            if f.read() != out:
                sys.exit("build_nso_wage_anchor.py --check: nso_wage_anchor.json drifted — re-run "
                         "python3 pipeline/build_nso_wage_anchor.py")
        print("build_nso_wage_anchor.py --check: OK (byte-exact)")
        return

    with open(OUT, "w", encoding="utf-8") as f:
        f.write(out)
    print("build_nso_wage_anchor.py: wrote platform/data/nso_wage_anchor.json")


if __name__ == "__main__":
    main()
