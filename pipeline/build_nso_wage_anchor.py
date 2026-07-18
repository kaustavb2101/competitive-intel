#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_nso_wage_anchor.py — project the MEASURED NSO regional wage series into a small app-facing
wage anchor (platform/data/nso_wage_anchor.json).

Reads source-data/nso_wages.json (pulled by pull_nso_wages.py — NSO LFS table LFS_02_20545_18,
average monthly wage of employees by region x industry x quarter) and picks the latest published
vintage (the highest YEAR present; averaged across whichever quarters that year has), excludes the
"ไม่ทราบ" (unknown) junk industry row, and groups industries into the app's SES/occupation buckets
(FactoryWorkers / Construction / Merchants-Trade / Agriculture / OfficeStaff).

WHY THIS EXISTS: the app's occupation-income layer (build_occupation_income*.py) is an ESTIMATED
proxy that currently reads too high for provincial white-collar workers. This is a MEASURED regional
wage reference to sanity-check it. It does NOT feed any composite.

A GENUINE DATA GAP, handled honestly (not papered over): NSO's ทั่วประเทศ (national) row only
publishes the all-industry aggregate ("รวม") at the latest vintage — the per-industry / per-SES-
bucket national breakdown that was published in earlier years (BE2563-2567) is absent from BE2568
onward in this table (verified directly against a live pull, not assumed). So `ratio_to_national`
is null for every region — nothing is synthesized to fill the gap. As a genuinely useful, fully-
measured substitute, `ratio_to_bangkok_officestaff` is also provided (กรุงเทพมหานคร IS fully
measured at this vintage), since "vs Bangkok" is the practical comparison this anchor exists for.

Deterministic, no network. `--check` byte-compares; SKIPs (exit 3) if source-data/nso_wages.json is
absent (a network-pulled input, not drift).

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

# SES/occupation bucket -> source industry string(s), matched EXACT against the strings NSO
# actually publishes for the latest vintage (verified against a live pull on 2026-07-18 — not
# guessed from the table's older/truncated label variants).
SES_SINGLE = {
    "FactoryWorkers": "การผลิต",
    "Construction": "การก่อสร้าง",
    "Merchants/Trade": "การขายส่ง และการขายปลีก การซ่อมยานยนต์",
    "Agriculture": "เกษตรกรรม การป่าไม้ และการประมง",
}
OFFICE_INDUSTRIES = [
    "กิจกรรมทางการเงินและการประกันภัย",
    "กิจกรรมทางวิชาชีพ วิทยาศาสตร์ และเทคนิค",
    "การบริหารราชการ การป้องกันประเทศ การประกันสังคม",
]
SES_BUCKETS = list(SES_SINGLE) + ["OfficeStaff"]

# Documented crosswalk only — NOT used to average across NSO regions (no employment weights
# available to do that honestly; would be fabrication). The app displays the constituent
# NSO-region figures under each app-region label instead.
APP_REGION_CROSSWALK = {
    "Central&BKK": ["กรุงเทพมหานคร", "ภาคกลาง"],
    "East": ["ภาคตะวันออก"],
    "Isan": ["ภาคตะวันออกเฉียงเหนือ"],
    "North": ["ภาคเหนือ"],
    "South": ["ภาคใต้", "ภาคใต้ชายแดน"],
}


def _pick_vintage(rows):
    """Latest YEAR present; all quarters that year has."""
    years = sorted(set(r["year"] for r in rows))
    latest = years[-1]
    quarters = sorted(set(r["quarter"] for r in rows if r["year"] == latest))
    return latest, quarters


def _region_industry_means(rows, year, quarters):
    """{region: {industry: mean_float}} across the chosen quarters, excluding the junk industry."""
    buckets = {}
    for r in rows:
        if r["year"] != year or r["quarter"] not in quarters:
            continue
        if r["industry"] == JUNK_INDUSTRY:
            continue
        try:
            v = float(r["value"])
        except (TypeError, ValueError):
            continue
        buckets.setdefault(r["region"], {}).setdefault(r["industry"], []).append(v)
    return {
        region: {ind: sum(vals) / len(vals) for ind, vals in inds.items()}
        for region, inds in buckets.items()
    }


def _ses_for_region(raw_industries):
    """(ses_int_map, office_components_used) for one region's {industry: mean_float} dict.
    Averaging is done in float across whichever OfficeStaff components are present, rounded to
    int only at the very end — never double-rounded."""
    ses = {}
    for bucket, ind in SES_SINGLE.items():
        v = raw_industries.get(ind)
        ses[bucket] = round(v) if v is not None else None
    used = [k for k in OFFICE_INDUSTRIES if k in raw_industries]
    ses["OfficeStaff"] = round(sum(raw_industries[k] for k in used) / len(used)) if used else None
    return ses, used


def build(src):
    rows = src["rows"]
    year, quarters = _pick_vintage(rows)
    means = _region_industry_means(rows, year, quarters)

    regions_out = {}
    office_raw = {}   # region -> raw (unrounded) OfficeStaff float, for the ratio calcs below
    for region in sorted(means):
        raw = means[region]
        industries_int = {ind: round(v) for ind, v in sorted(raw.items())}
        ses, used = _ses_for_region(raw)
        regions_out[region] = {
            "industries": industries_int,
            "ses_map": ses,
            "OfficeStaff_components_used": used,
        }
        if used:
            office_raw[region] = sum(raw[k] for k in used) / len(used)

    national = regions_out.get(NATIONAL_REGION, {
        "industries": {}, "ses_map": {k: None for k in SES_BUCKETS},
        "OfficeStaff_components_used": [],
    })

    national_office = office_raw.get(NATIONAL_REGION)
    ratio_to_national = {
        region: (round(v / national_office, 2) if national_office else None)
        for region, v in office_raw.items()
    }
    for region in regions_out:
        ratio_to_national.setdefault(region, None)

    bangkok_office = office_raw.get(BANGKOK_REGION)
    ratio_to_bangkok = {
        region: (round(v / bangkok_office, 2) if bangkok_office else None)
        for region, v in office_raw.items()
    }
    for region in regions_out:
        ratio_to_bangkok.setdefault(region, None)

    year_ce = int(year) - 543
    return {
        "meta": {
            "title": "NSO regional wage anchor - measured monthly wage by region x SES/occupation bucket",
            "generated_by": "pipeline/build_nso_wage_anchor.py",
            "label": ("MEASURED — NSO Labour Force Survey average monthly wage of employees "
                      "(บาท/เดือน) by region × industry × quarter; table LFS_02_20545_18, "
                      "สำนักงานสถิติแห่งชาติ. Vintage: BE %s (CE %d), %s.")
                     % (year, year_ce, ", ".join(quarters)),
            "source": src["meta"].get("source", ""),
            "dataset_table": src["meta"].get("dataset_table", ""),
            "vintage": {"year_be": year, "year_ce": year_ce, "quarters": quarters},
            "unit": "baht/month",
            "provenance": ("MEASURED. Pure projection of source-data/nso_wages.json (NSO "
                          "LFS_02_20545_18). Nothing modelled; junk industry \"%s\" excluded."
                          % JUNK_INDUSTRY),
            "ses_map_definitions": {**SES_SINGLE, "OfficeStaff": OFFICE_INDUSTRIES},
            "national_industry_gap": (
                "NSO's ทั่วประเทศ (national) row at this vintage publishes only the all-industry "
                "aggregate ('รวม') — the per-industry / per-SES-bucket national breakdown that was "
                "published in earlier years (BE2563-2567) is absent from BE%s onward in this table. "
                "So ratio_to_national is null for every region — nothing is filled in to paper over "
                "the gap. ratio_to_bangkok_officestaff is provided instead, using กรุงเทพมหานคร "
                "(fully measured at this vintage) as the practical anchor." % year
            ),
        },
        # NOTE lives outside `meta` on purpose: build_provenance.py's MEASURED/ESTIMATED verdict
        # scans meta.{label,source,provenance,title,note,...} for an ESTIMATED/PROXY/SYNTH marker
        # substring, and this note necessarily names the ESTIMATED layer it sanity-checks — inside
        # meta that would mis-flip this fully MEASURED layer to "estimated" on the data-room shame
        # board. Mirrors build_credit_anchor.py's "context" field, which is a sibling of meta for
        # the same reason.
        "note": ("Measured regional wage reference to sanity-check the app's occupation-income "
                 "layer (build_occupation_income*.py), which is an estimated proxy for provincial "
                 "white-collar workers. Does NOT feed any risk composite."),
        "app_region_crosswalk": APP_REGION_CROSSWALK,
        "national": national,
        "regions": regions_out,
        "ratio_to_national": ratio_to_national,
        "ratio_to_bangkok_officestaff": ratio_to_bangkok,
    }


def _dumps(data):
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def main():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:
            pass
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true",
                    help="verify platform/data/nso_wage_anchor.json reproduces byte-exact from "
                         "source-data/nso_wages.json; exit 3 SKIP if the source is absent")
    args = ap.parse_args()

    if args.check:
        if not os.path.exists(SRC):
            print("build_nso_wage_anchor.py --check: SKIP (source-data/nso_wages.json absent - "
                  "network-pulled input, not drift)")
            sys.exit(3)
        if not os.path.exists(OUT):
            sys.exit("build_nso_wage_anchor.py --check: platform/data/nso_wage_anchor.json missing "
                     "- run python3 pipeline/build_nso_wage_anchor.py")
        src = json.load(open(SRC, encoding="utf-8"))
        if _dumps(build(src)) != open(OUT, encoding="utf-8").read():
            sys.exit("build_nso_wage_anchor.py --check: nso_wage_anchor.json drifted - re-run "
                     "python3 pipeline/build_nso_wage_anchor.py")
        print("build_nso_wage_anchor.py --check: OK (byte-exact)")
        return

    if not os.path.exists(SRC):
        sys.exit("build_nso_wage_anchor.py: source-data/nso_wages.json absent - run "
                 "python3 pipeline/pull_nso_wages.py first")
    src = json.load(open(SRC, encoding="utf-8"))
    data = build(src)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(_dumps(data))
    print("wrote %s" % OUT)
    v = data["meta"]["vintage"]
    q_ascii = ",".join("Q" + "".join(ch for ch in q if ch.isdigit()) for q in v["quarters"])
    print("  vintage: BE %s (CE %d), quarters=%s" % (v["year_be"], v["year_ce"], q_ascii))
    print("  regions=%d" % len(data["regions"]))


if __name__ == "__main__":
    main()
