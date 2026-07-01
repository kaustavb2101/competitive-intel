#!/usr/bin/env python3
"""
build_branch_labor.py — PORTFOLIO / ACQUISITION context: per-branch EMPLOYMENT & LABOUR mix.

Network-free, deterministic. Assembles ALREADY-MEASURED source layers into ONE per-branch,
INDEX-ALIGNED layer (entry i <-> branches.json branch i, 2015 entries) so the app can show,
for each branch, WHO WORKS in its catchment and the health of the province labour market.

It joins four LOCAL layers (no fabrication — any field that can't be sourced is null):
  - branch_occupations.json          MEASURED Overture occupation mix <=10km per branch
                                     (index-aligned). -> occ_top (top-3 buckets by share) + estab_total.
  - amphoe.json (.branch_amphoe[])   MEASURED DIW factory workers in the branch's DISTRICT
                                     (only where that district is fac_measured) -> factory_workers.
  - employment_by_province.json      MEASURED NSO workers-by-province (formal/informal counts)
                                     joined by the branch's province -> informal_pct.
  - unemployment_by_province.json    MEASURED NSO Labour Force Survey provincial summary
                                     joined by the branch's province -> prov_employed_k,
                                     prov_labor_force_k, prov_unemployment_rate.

Branch->province join key: branches_final.json `prov` (Thai province name), which is 1:1 with
branches.json by index and matches all 77 keys in both NSO province files exactly.

Per branch:
  occ_top                [{label, share_pct} x up to 3]  MEASURED (Overture). Empty list if estab_total=0.
  estab_total            int total establishments in catchment (Overture sample/lower bound). MEASURED.
  factory_workers        int DIW factory workers in the branch's district, else null. MEASURED (where fac_measured).
  informal_pct           informal/(informal+formal) x100, province ratio, else null. MEASURED (NSO, province-inherited).
  prov_employed_k        NSO LFS employed (thousands), province, else null. MEASURED.
  prov_labor_force_k     NSO LFS labour force (thousands), province, else null. MEASURED.
  prov_unemployment_rate NSO LFS unemployment rate (%), province, else null. MEASURED.

Run:
  python3 build_branch_labor.py            # write platform/data/branch_labor.json
  python3 build_branch_labor.py --check    # re-run, byte-compare against committed file
"""
import json
import os
import sys
import argparse

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, "source-data")
PDATA = os.path.join(ROOT, "platform", "data")
OUT = os.path.join(PDATA, "branch_labor.json")


def _load(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def build():
    master = _load(os.path.join(SRC, "branches_final.json"))          # list, 2015, has `prov`
    occ = _load(os.path.join(PDATA, "branch_occupations.json"))       # index-aligned occupation mix
    amphoe = _load(os.path.join(PDATA, "amphoe.json"))                # .amphoe[] + .branch_amphoe[]
    emp = _load(os.path.join(SRC, "employment_by_province.json"))     # NSO formal/informal by province
    unemp = _load(os.path.join(SRC, "unemployment_by_province.json")) # NSO LFS province summary

    n = len(master)

    buckets = occ.get("buckets", [])                 # [{key,label} x14]
    bucket_labels = [b.get("label") for b in buckets]
    occ_recs = occ.get("branches", [])
    if len(occ_recs) != n:
        raise SystemExit("branch_occupations length %d != branches %d (not index-aligned)"
                         % (len(occ_recs), n))

    A = amphoe.get("amphoe", [])
    BAMP = amphoe.get("branch_amphoe", [])
    if len(BAMP) != n:
        raise SystemExit("amphoe.branch_amphoe length %d != branches %d" % (len(BAMP), n))

    emp_prov = emp.get("provinces", {})
    unemp_prov = unemp.get("provinces", {})

    branches = []
    n_fac = 0
    n_informal = 0
    n_lfs = 0
    n_occ = 0
    for i in range(n):
        prov = master[i].get("prov")

        # --- occupation mix (MEASURED, Overture) ---
        rec = occ_recs[i]
        t = rec.get("t") or 0
        o = rec.get("o") or []
        occ_top = []
        if t and t > 0 and o:
            # rank buckets by count desc; deterministic tie-break by bucket index (stable sort)
            order = sorted(range(len(o)), key=lambda j: (-o[j], j))
            for j in order[:3]:
                if o[j] <= 0:
                    continue
                occ_top.append({
                    "label": bucket_labels[j] if j < len(bucket_labels) else None,
                    "share_pct": round(100.0 * o[j] / t, 1),
                })
        if occ_top:
            n_occ += 1

        # --- district factory workers (MEASURED, DIW, only where fac_measured) ---
        factory_workers = None
        ai = BAMP[i]
        if isinstance(ai, int) and 0 <= ai < len(A):
            a = A[ai]
            if a.get("fac_measured") and a.get("workers") is not None:
                factory_workers = a.get("workers")
        if factory_workers is not None:
            n_fac += 1

        # --- informal share (MEASURED NSO, province-inherited ratio) ---
        informal_pct = None
        ep = emp_prov.get(prov)
        if isinstance(ep, dict):
            inf = ep.get("informal")
            frm = ep.get("formal")
            if isinstance(inf, (int, float)) and isinstance(frm, (int, float)) and (inf + frm) > 0:
                informal_pct = round(100.0 * inf / (inf + frm), 1)
        if informal_pct is not None:
            n_informal += 1

        # --- province labour-force summary (MEASURED NSO LFS) ---
        prov_employed_k = None
        prov_labor_force_k = None
        prov_unemployment_rate = None
        up = unemp_prov.get(prov)
        if isinstance(up, dict):
            prov_employed_k = up.get("employed_k")
            prov_labor_force_k = up.get("labor_force_k")
            prov_unemployment_rate = up.get("unemployment_rate")
        if prov_employed_k is not None:
            n_lfs += 1

        branches.append({
            "occ_top": occ_top,
            "estab_total": t,
            "factory_workers": factory_workers,
            "informal_pct": informal_pct,
            "prov_employed_k": prov_employed_k,
            "prov_labor_force_k": prov_labor_force_k,
            "prov_unemployment_rate": prov_unemployment_rate,
        })

    meta = {
        "generated_by": "pipeline/build_branch_labor.py",
        "n_branches": n,
        "index_aligned_to": "platform/data/branches.json (entry i <-> branch i)",
        "join_key_province": "branches_final.json `prov` (Thai province name); matches all 77 "
                             "keys in employment_by_province.json and unemployment_by_province.json.",
        "fields": {
            "occ_top": {
                "label": "MEASURED",
                "source": occ.get("meta", {}).get("source",
                          "Overture Maps Places — measured establishment points (sample/lower bound)"),
                "note": "Top-3 catchment occupation buckets by establishment share (count/total, <=%s km). "
                        "A workforce-composition proxy from where businesses are, not a payroll census."
                        % occ.get("meta", {}).get("radius_km", 10.0),
            },
            "estab_total": {
                "label": "MEASURED",
                "source": occ.get("meta", {}).get("source", "Overture Maps Places"),
                "note": "Total establishments in the branch catchment (Overture sample/lower bound).",
            },
            "factory_workers": {
                "label": "MEASURED",
                "source": "DIW factories_by_district (Department of Industrial Works), via amphoe.json workers",
                "note": "Registered factory workers in the branch's DISTRICT (amphoe), only where the "
                        "district is fac_measured; null otherwise (never fabricated).",
            },
            "informal_pct": {
                "label": "MEASURED",
                "source": emp.get("source", "NSO ภาวะการทำงานของประชากร (data.go.th) — workers by province"),
                "note": "informal / (informal + formal) x100. A province-level MEASURED ratio "
                        "(province-inherited to every branch in the province); null where the province is absent.",
                "year_be": emp.get("year_be"),
            },
            "prov_employed_k / prov_labor_force_k / prov_unemployment_rate": {
                "label": "MEASURED",
                "source": unemp.get("meta", {}).get("source",
                          "NSO Labour Force Survey — provincial summary"),
                "provenance": unemp.get("meta", {}).get("provenance"),
                "unit": unemp.get("meta", {}).get("unit",
                        "*_k fields are thousands of persons; unemployment_rate is percent"),
                "note": "Province labour-force health, joined by the branch's province; null where absent.",
            },
        },
        "coverage": {
            "branches_with_occ_top": n_occ,
            "branches_with_factory_workers": n_fac,
            "branches_with_informal_pct": n_informal,
            "branches_with_province_lfs": n_lfs,
        },
        "provenance": "MEASURED assembly. No index or synthetic value is introduced here — this layer "
                      "only re-projects existing MEASURED source layers (Overture Places, DIW factory "
                      "workers, NSO employment & Labour Force Survey) onto each branch by index/province. "
                      "Any field that cannot be sourced for a branch is null.",
    }

    return {"meta": meta, "buckets": buckets, "branches": branches}


def dumps(obj):
    return json.dumps(obj, ensure_ascii=False, indent=2) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true",
                    help="re-run and byte-compare against the committed JSON; exit 1 on drift")
    args = ap.parse_args()

    data = build()
    text = dumps(data)

    if args.check:
        if not os.path.exists(OUT):
            print("CHECK FAIL: %s does not exist" % OUT)
            sys.exit(1)
        with open(OUT, encoding="utf-8") as f:
            existing = f.read()
        if existing == text:
            print("CHECK OK: %s reproduces byte-for-byte (%d branches)" %
                  (OUT, data["meta"]["n_branches"]))
            sys.exit(0)
        print("CHECK FAIL: %s differs from a fresh build" % OUT)
        sys.exit(1)

    with open(OUT, "w", encoding="utf-8") as f:
        f.write(text)
    cov = data["meta"]["coverage"]
    print("wrote %s (%d branches)" % (OUT, data["meta"]["n_branches"]))
    print("  measured factory_workers: %d / %d  |  province LFS: %d  |  informal_pct: %d  |  occ_top: %d"
          % (cov["branches_with_factory_workers"], data["meta"]["n_branches"],
             cov["branches_with_province_lfs"], cov["branches_with_informal_pct"],
             cov["branches_with_occ_top"]))


if __name__ == "__main__":
    main()
