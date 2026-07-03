#!/usr/bin/env python3
"""
build_province_risk.py — PORTFOLIO RISK (objective #1): per-PROVINCE rollup of the per-branch
composite risk, so the map/exec views can read "which provinces are getting riskier" at a glance.

Network-free, deterministic. Aggregates two LOCAL files:
  platform/data/branch_risk.json   per-branch composite_risk (0–100) + top_driver, INDEX-ALIGNED
                                   to branches.json (built by pipeline/build_branch_risk.py).
  platform/data/branches.json      the master branch list (province `v`, region `r`).

Per province it computes:
  n_branches      count of AutoX branches in the province.                 [MEASURED count]
  mean_risk       mean composite_risk over the province's branches.        [ESTIMATED composite —
                  it is a mean of the ESTIMATED branch composite.]
  p90_risk        90th-percentile (nearest-rank) composite_risk.           [ESTIMATED composite]
  top_driver_mix  count of branches by their top_driver in the province.   [from the branch composite]

The branch composite is itself an ESTIMATED blend (household DTI [MEASURED · NSO] + crop/drought
double-stress [ESTIMATED] + occupation concentration [MEASURED mix × ESTIMATED weight] + the
branch's own segment/collateral mix). This rollup inherits that provenance — see branch_risk.json
meta. NOTHING is fabricated: a province with no branch-risk records is simply omitted.

GRACEFUL DEGRADE: if branch_risk.json is absent, the projector STILL writes the output with an empty
provinces list and meta.absent=true, so any consumer can hide itself without erroring. --check
byte-compares against whatever was last committed.

Run:
  python3 build_province_risk.py            # write platform/data/province_risk.json
  python3 build_province_risk.py --check    # re-run, byte-compare against the committed file
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "platform", "data")
BRANCHES = os.path.join(DATA, "branches.json")
BRANCH_RISK = os.path.join(DATA, "branch_risk.json")
OUT = os.path.join(DATA, "province_risk.json")


def _load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _p90(values_sorted):
    # nearest-rank 90th percentile of an ascending-sorted list (>=1 element).
    if not values_sorted:
        return 0.0
    k = max(0, min(len(values_sorted) - 1, int(round(0.90 * (len(values_sorted) - 1)))))
    return values_sorted[k]


def build():
    absent = not (os.path.exists(BRANCHES) and os.path.exists(BRANCH_RISK))
    rows = []
    if not absent:
        branches = _load(BRANCHES)
        br = _load(BRANCH_RISK)
        recs = br.get("branches") if isinstance(br, dict) else br
        if not isinstance(recs, list) or len(recs) != len(branches):
            # length drift means the index-alignment guarantee is broken — refuse to guess.
            absent = True
        else:
            agg = {}  # province -> {"region":..., "vals":[...], "drivers":{...}}
            for b, r in zip(branches, recs):
                prov = b.get("v")
                if not prov or not isinstance(r, dict):
                    continue
                cr = r.get("composite_risk")
                if cr is None:
                    continue
                a = agg.setdefault(prov, {"region": b.get("r"), "vals": [], "drivers": {}})
                a["vals"].append(float(cr))
                drv = r.get("top_driver")
                if drv:
                    a["drivers"][drv] = a["drivers"].get(drv, 0) + 1
            for prov, a in agg.items():
                vals = sorted(a["vals"])
                n = len(vals)
                mean = round(sum(vals) / n, 1) if n else 0.0
                rows.append({
                    "province": prov,
                    "region": a["region"],
                    "n_branches": n,
                    "mean_risk": mean,
                    "p90_risk": round(_p90(vals), 1),
                    "top_driver_mix": dict(sorted(a["drivers"].items(),
                                                  key=lambda kv: (-kv[1], kv[0]))),
                })
            # worst-first by mean_risk (desc); tie-break by province for determinism.
            rows.sort(key=lambda r: (-r["mean_risk"], r["province"]))

    meta = {
        "title": "Per-province composite-risk rollup (portfolio risk, objective #1)",
        "generated_by": "pipeline/build_province_risk.py",
        "deterministic": True,
        "network_free": True,
        "absent": absent,
        "n_provinces": len(rows),
        "sort": "worst-first by mean_risk (desc)",
        "source": "Rollup of platform/data/branch_risk.json (per-branch composite) over "
                  "platform/data/branches.json provinces.",
        "provenance": "The branch composite is an ESTIMATED blend (household DTI [MEASURED · NSO] + "
                      "crop/drought double-stress [ESTIMATED] + occupation concentration [MEASURED "
                      "mix × ESTIMATED weight] + branch segment/collateral mix). This province "
                      "rollup inherits that provenance — see branch_risk.json meta. n_branches is "
                      "a MEASURED count; mean_risk / p90_risk are aggregates of the ESTIMATED "
                      "composite, NOT measured default rates.",
        "fields": {
            "n_branches": "MEASURED — AutoX branches in the province.",
            "mean_risk": "ESTIMATED — mean per-branch composite_risk (0–100).",
            "p90_risk": "ESTIMATED — 90th-percentile (nearest-rank) per-branch composite_risk.",
            "top_driver_mix": "count of branches by their composite top_driver in the province.",
        },
        "measured_vs_estimated": "n_branches MEASURED; mean_risk / p90_risk are ESTIMATED composites.",
    }
    return {"meta": meta, "provinces": rows}


def dumps(obj):
    return json.dumps(obj, ensure_ascii=False, indent=2) + "\n"


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true",
                    help="re-run and byte-compare against the committed JSON; exit 1 on drift")
    args = ap.parse_args()

    data = build()
    text = dumps(data)

    if args.check:
        if not os.path.exists(OUT):
            # absent-state is allowed to be uncommitted; only fail if branch_risk EXISTS but the
            # rollup is missing (a real drift). When inputs are absent, skip-pass.
            if data["meta"]["absent"]:
                print("build_province_risk.py --check: skip (inputs absent, no output expected)")
                sys.exit(0)
            print("CHECK FAIL: %s does not exist" % OUT)
            sys.exit(1)
        with open(OUT, encoding="utf-8") as f:
            existing = f.read()
        if existing == text:
            print("CHECK OK: %s reproduces byte-for-byte (%d provinces%s)" % (
                OUT, data["meta"]["n_provinces"],
                ", ABSENT-state" if data["meta"].get("absent") else ""))
            sys.exit(0)
        print("CHECK FAIL: %s drifted — re-run build_province_risk.py" % OUT)
        sys.exit(1)

    with open(OUT, "w", encoding="utf-8") as f:
        f.write(text)
    print("wrote %s (%d provinces%s)" % (
        OUT, data["meta"]["n_provinces"],
        ", ABSENT-state" if data["meta"].get("absent") else ""))


if __name__ == "__main__":
    main()
