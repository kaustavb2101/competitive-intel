#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_pico_operators.py — per-province LICENSED PICO-FINANCE operator census (competitor risk, MEASURED).

Distils the FPO (Fiscal Policy Office) licensed pico-finance operator registry
(source-data/datagoth/fpo_pico.csv, pulled by pipeline/pull_datagoth.py --only fpo_pico) into a clean,
77-province-keyed count layer → platform/data/pico_operators.json.

WHY THIS MATTERS (objective #2, competitive risk on the network we already run)
    Pico-finance (พิโกไฟแนนซ์) operators are the SUB-SCALE, SINGLE-PROVINCE-LICENSED tier of the Thai
    small-loan field — a DISTINCT competitor class from the big-4 title-lenders (Muangthai / Srisawad /
    Tidlor / Heng) already censused in competitors_census.json. Each is licensed by the Ministry of
    Finance (via FPO) to lend up to ฿50k (pico) / ฿100k (pico-plus) WITHIN ONE registered province, and
    many lend against vehicle title — so this is exactly the sub-scale-operator census that the exit /
    fragility work (build_exit_whitespace.py) flagged as blocked ("a true rival-fragility index needs a
    sub-scale-operator census"). This layer is that census, at the honest granularity the registry gives.

PROVENANCE — MEASURED (FPO official licence registry). Every count is a straight tally of the registry;
    no scores, no weights, no synthesis. HONEST LIMITS (carried in meta, not buried):
      - Granularity is PROVINCE-OF-LICENCE only (จังหวัดที่ให้บริการ). The registry carries a full street
        address but the operators are NOT geocoded here — so this joins to the network at province level,
        NOT as branch coordinates like the big-4 census. It complements, does not merge into, that census.
      - Counts are LICENSED entities (head-office + sub-branch registrations), not verified-active
        storefronts; a licence can be dormant. It is a licence-count upper bound on active competition.
      - A distinct competitor class from title-lenders: overlap with AutoX's exact product varies.

Deterministic + network-free (pure function of the committed CSV). Carries --check; SKIP-passes (exit 3)
when the gitignored raw pull (fpo_pico.csv) is absent, and when the committed output is not yet generated
— mirroring build_branch_cropland.py — so the gate never FAILs on a missing pull.

    python3 build_pico_operators.py
    python3 build_pico_operators.py --check
"""
import argparse, csv, json, os, sys
from collections import Counter

from regionmap import canonical, REGION

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CSV_PATH = os.path.join(ROOT, "source-data", "datagoth", "fpo_pico.csv")
OUT = os.path.join(ROOT, "platform", "data", "pico_operators.json")

# CSV column headers (Thai) from the FPO registry.
COL_PROV = "จังหวัดที่ให้บริการ"     # province of service (licence province)
COL_OFF = "ประเภทสำนักงาน"         # office type: สำนักงานใหญ่ (HQ) / สำนักสาขา (branch)
OFF_HQ = "สำนักงานใหญ่"
OFF_BRANCH = "สำนักสาขา"

# Registry snapshot vintage — read from the FPO resource filename (picofinanceoperate-DDMMYYYY.csv),
# kept as a stable constant so meta is a pure function of the CSV content (byte-exact --check survives a
# re-pull of the same snapshot). Update alongside a newer pull.
REGISTRY_VINTAGE = "2026-05-22"
SOURCE_URL = ("https://catalog.fpo.go.th/dataset/2b8aadd9-e0a7-45fc-8301-ea2fbdb781a2"
              " (FPO licensed pico-finance operators)")


def _load_rows():
    with open(CSV_PATH, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def build():
    rows = _load_rows()
    total = Counter()
    hq = Counter()
    branch = Counter()
    n_unresolved = 0
    for r in rows:
        prov = canonical((r.get(COL_PROV) or "").strip())
        if prov not in REGION:
            n_unresolved += 1
            continue
        total[prov] += 1
        off = (r.get(COL_OFF) or "").strip()
        if off == OFF_HQ:
            hq[prov] += 1
        elif off == OFF_BRANCH:
            branch[prov] += 1

    # Complete 77-province rollup (genuine zeros included), sorted by count desc then canonical Thai name.
    provinces = []
    for prov in sorted(REGION, key=lambda p: (-total[prov], p)):
        provinces.append({
            "th": prov,
            "region": REGION[prov],
            "n": total[prov],       # total licensed pico operators registered to serve this province
            "hq": hq[prov],         # head-office registrations
            "branch": branch[prov], # sub-branch registrations
        })

    region_totals = Counter()
    for prov, c in total.items():
        region_totals[REGION[prov]] += c

    n_total = sum(total.values())
    n_covered = sum(1 for p in REGION if total[p] > 0)
    meta = {
        "title": "Per-province licensed PICO-finance operator census (competitor risk, objective #2)",
        "generated_by": "pipeline/build_pico_operators.py",
        "deterministic": True,
        "network_free": True,
        "provenance": "MEASURED",
        "source": ("FPO (Fiscal Policy Office) licensed pico-finance operator registry, "
                   "snapshot %s, via pipeline/pull_datagoth.py --only fpo_pico" % REGISTRY_VINTAGE),
        "source_url": SOURCE_URL,
        "registry_vintage": REGISTRY_VINTAGE,
        "granularity": "province of licence (จังหวัดที่ให้บริการ) — NOT geocoded to branch coordinates",
        "competitor_class": ("sub-scale, single-province-licensed pico-finance lenders (฿50k pico / "
                             "฿100k pico-plus, MoF licence) — a DISTINCT tier from the big-4 title-lenders "
                             "in competitors_census.json; complements, does not merge into, that census"),
        "measures": {
            "n": "total licensed operators registered to serve the province (HQ + sub-branch)",
            "hq": "head-office (สำนักงานใหญ่) registrations",
            "branch": "sub-branch (สำนักสาขา) registrations",
        },
        "honesty_caveat": ("Counts are LICENSED entities, not verified-active storefronts (a licence may "
                           "be dormant) — a licence-count upper bound on sub-scale competition. Province "
                           "granularity only; the registry's street addresses are not geocoded here."),
        "n_operators": n_total,
        "n_provinces_covered": n_covered,
        "n_provinces_zero": len(REGION) - n_covered,
        "n_hq": sum(hq.values()),
        "n_branch": sum(branch.values()),
        "n_unresolved_rows": n_unresolved,
        "region_totals": dict(sorted(region_totals.items())),
    }
    return {"meta": meta, "provinces": provinces}


def serialize(obj):
    # ensure_ascii=False, indent=2 + trailing newline — the platform/data convention (matches meta.json).
    return json.dumps(obj, ensure_ascii=False, indent=2) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:
            pass

    if not os.path.exists(CSV_PATH):
        if args.check:
            print("build_pico_operators.py --check: SKIP (source-data/datagoth/fpo_pico.csv absent — "
                  "run: python3 pull_datagoth.py --only fpo_pico)")
            sys.exit(3)
        sys.exit("fpo_pico.csv missing — run: python3 pull_datagoth.py --only fpo_pico (Thai IP or CI)")

    payload = serialize(build())
    if args.check:
        if not os.path.exists(OUT):
            print("build_pico_operators.py --check: SKIP (pico_operators.json not generated yet)")
            sys.exit(3)
        if open(OUT, encoding="utf-8").read() != payload:
            sys.exit("build_pico_operators.py --check: pico_operators.json drifted — run "
                     "python3 pipeline/build_pico_operators.py")
        print("build_pico_operators.py --check: OK (byte-exact)")
        return
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(payload)
    m = json.loads(payload)["meta"]
    print("wrote %s (%d operators; %d/%d provinces covered; %d HQ + %d branch)"
          % (OUT, m["n_operators"], m["n_provinces_covered"], len(REGION),
             m["n_hq"], m["n_branch"]))


if __name__ == "__main__":
    main()
