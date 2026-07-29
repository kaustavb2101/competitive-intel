#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_dbd_formation.py — per-province new-company formation (business-formation demand, MEASURED).

Distils the DBD (Department of Business Development) monthly registry of newly registered juristic
persons (companies + partnerships) into a clean, canonical-77-province-keyed count + registered-capital
layer. New business formation is a forward DEMAND / economic-vitality signal: provinces where new firms
and capital are forming are provinces with a growing base of small-business owners and vehicles — the
customer pool AutoX's small-ticket title/personal book draws on. It is DISTINCT from the competitor
layers (pico_census.json / competitors_census.json): this measures demand-side vitality, not rivals.

INPUT  source-data/datagoth/dbd_newco.csv — the DBD open-data new-registration file for ONE month (one
       row per newly registered juristic person; columns include วันที่จดทะเบียน (registration date) /
       ทุนจดทะเบียน (registered capital, THB) / จังหวัด (province) / อำเภอ (district)). Pulled by
       pull_datagoth.py (--only dbd_newco) from openapi.dbd.go.th. The raw CSV is gitignored +
       re-pullable; this builder's committed OUTPUT is the repo's source of truth.

OUTPUT platform/data/dbd_formation.json — { meta, by_province{prov:{n,capital_thb}}, top, national }.
       Every count is MEASURED (a straight tally of the government registry for the snapshot month);
       no synthesis, no scoring. Province strings are folded to the canonical 77 via regionmap.canonical
       after stripping the registry's จ./จังหวัด prefix; rows whose province is blank or malformed (a
       column-shifted postal code) are counted honestly as unmapped, never guessed.

PROVENANCE is stable + byte-exact: the output is a pure function of the CSV CONTENT (not of the pull
timestamp). The registry snapshot month + download URL are pinned as constants below (from the DBD
resource filename 99_202606_1.csv = registrations dated BE 2569-06 = CE 2026-06); bump them when a
newer month is pulled.

DETERMINISTIC + NETWORK-FREE. Carries --check; SKIP-passes (exit 3) when the gitignored dbd_newco.csv
is absent (the CI gate has no such pull committed), so the determinism gate never breaks on a missing
input — same convention as build_pico_census / build_branch_cropland / build_branch_density.

  python3 build_dbd_formation.py
  python3 build_dbd_formation.py --check
"""
import argparse, csv, json, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.regionmap import canonical, REGION

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CSV_IN = os.path.join(ROOT, "source-data", "datagoth", "dbd_newco.csv")
OUT = os.path.join(ROOT, "platform", "data", "dbd_formation.json")

# Pinned to the pulled DBD resource (openapi.dbd.go.th …/99_202606_1.csv). Constants — NOT read from the
# volatile pull manifest — so the output is byte-stable across re-pulls of the same month.
SNAPSHOT_URL = "https://openapi.dbd.go.th/juristic_person/registration/99_202606_1.csv"
SNAPSHOT_MONTH = "2026-06"          # CE; the file is BE 2569-06 (registration dates วันที่จดทะเบียน)
SNAPSHOT_MONTH_BE = "2569-06"

COL_PROV = "จังหวัด"                 # province of the registered head office
COL_CAP = "ทุนจดทะเบียน"            # registered (authorised) capital, THB
_PREFIX = re.compile(r"^(จังหวัด|จ\.)\s*")


def _clean_prov(raw):
    return _PREFIX.sub("", (raw or "").strip()).strip()


def build():
    by_prov = {}          # canonical prov -> [n, capital_thb]
    n_total = n_mapped = n_blank = n_unmapped = 0
    cap_total = 0
    with open(CSV_IN, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            n_total += 1
            raw = (row.get(COL_PROV) or "").strip()
            prov = canonical(_clean_prov(raw))
            if prov not in REGION:                    # blank, foreign, or a column-shifted postcode
                if raw:
                    n_unmapped += 1
                else:
                    n_blank += 1
                continue
            cap = 0
            try:
                cap = int(float((row.get(COL_CAP) or "0").strip().replace(",", "") or 0))
            except ValueError:
                cap = 0
            rec = by_prov.setdefault(prov, [0, 0])
            rec[0] += 1
            rec[1] += cap
            n_mapped += 1
            cap_total += cap

    by_province = {p: {"n": v[0], "capital_thb": v[1]}
                   for p, v in sorted(by_prov.items())}
    zero_provinces = sorted(set(REGION.keys()) - set(by_prov.keys()))
    top = sorted(((p, v["n"], v["capital_thb"]) for p, v in by_province.items()),
                 key=lambda kv: (-kv[1], kv[0]))[:15]

    meta = {
        "generated_by": "pipeline/build_dbd_formation.py",
        "label": ("MEASURED per-province new-company (juristic-person) formation for the snapshot month "
                  "— a business-formation DEMAND / economic-vitality signal (new firms + registered "
                  "capital), NOT a competitor layer. Counts per canonical province."),
        "source": ("MEASURED — DBD (Department of Business Development) open-data monthly new-registration "
                   "registry, openapi.dbd.go.th (juristic_person/registration CSV). One row per newly "
                   "registered juristic person carrying its head-office province; tallied by canonical "
                   "province — a direct count of the registry for the snapshot month, not modelled or "
                   "annualised."),
        "provenance": "measured (government business registry, tallied by the registry's own province field)",
        "source_url": SNAPSHOT_URL,
        "snapshot_month": SNAPSHOT_MONTH,
        "snapshot_month_be": SNAPSHOT_MONTH_BE,
        "vintage": SNAPSHOT_MONTH,
        "n_registrations": n_mapped,
        "n_rows_total": n_total,
        "n_blank_province": n_blank,
        "n_unmapped_province": n_unmapped,
        "capital_thb_total": cap_total,
        "n_provinces_present": len(by_prov),
        "n_provinces_zero": len(zero_provinces),
        "objective": ("Demand context for both objectives: where new firms + capital are forming maps the "
                      "growing small-business owner / vehicle base AutoX's small-ticket book draws on, "
                      "province by province."),
        "gaps": [
            "This is ONE month's new registrations (the pulled DBD snapshot), a flow — not a stock of "
            "active businesses and not annualised. Read it as a monthly formation pulse, not a level.",
            "ทุนจดทะเบียน is REGISTERED (authorised) capital at incorporation, not paid-up capital or "
            "revenue; it overstates real deployed capital and is dominated by a few large registrations.",
            "Keyed by head-office PROVINCE only (the registry's own จังหวัด field). The อำเภอ (district) "
            "column is present but not tallied here; a later run can add a district breakdown.",
            "%d of %d rows carry a blank province and %d a malformed (column-shifted) province; both are "
            "counted as unmapped and excluded, never guessed." % (n_blank, n_total, n_unmapped),
        ],
    }
    return {"meta": meta, "by_province": by_province, "zero_provinces": zero_provinces, "top": top}


def serialize(o):
    return json.dumps(o, ensure_ascii=False, separators=(",", ":"))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    for s in (sys.stdout, sys.stderr):
        try: s.reconfigure(encoding="utf-8")
        except Exception: pass

    if not os.path.exists(CSV_IN):
        if args.check:
            print("build_dbd_formation.py --check: SKIP (source-data/datagoth/dbd_newco.csv absent — "
                  "re-pullable pull_datagoth input, not committed)")
            sys.exit(3)
        sys.exit("dbd_newco.csv missing — run: python3 pull_datagoth.py --only dbd_newco")

    payload = serialize(build())
    if args.check:
        if not os.path.exists(OUT):
            print("build_dbd_formation.py --check: SKIP (dbd_formation.json not generated yet)")
            sys.exit(3)
        if open(OUT, encoding="utf-8").read() != payload:
            sys.exit("build_dbd_formation.py --check: dbd_formation.json drifted — run "
                     "python3 pipeline/build_dbd_formation.py")
        print("build_dbd_formation.py --check: OK (byte-exact)")
        return
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(payload)
    obj = json.loads(payload)
    m = obj["meta"]
    print("wrote %s (%d registrations, ฿%.2fbn capital, %s, across %d provinces; %d blank / %d unmapped)"
          % (OUT, m["n_registrations"], m["capital_thb_total"] / 1e9, m["snapshot_month"],
             m["n_provinces_present"], m["n_blank_province"], m["n_unmapped_province"]))
    print("  top: %s" % ", ".join("%s=%d" % (p, n) for p, n, _ in obj["top"][:6]))
    if obj["zero_provinces"]:
        print("  zero-formation provinces: %s" % ", ".join(obj["zero_provinces"]))


if __name__ == "__main__":
    main()
