#!/usr/bin/env python3
"""
build_branch_pico.py — per-branch LICENSED-PICO rival exposure in the branch's district (MEASURED)
===================================================================================================
Attaches, to every one of the 2,015 AutoX branches, the count of LICENSED PICO-finance
(พิโกไฟแนนซ์) operators registered in that branch's OWN district (อำเภอ) — a distinct
small-ticket non-bank competitor class to AutoX, and the one the per-branch rival picture
was blind to. `build_rival_pressure.py` counts only the big-4 store-locator networks
(Muangthai / Srisawad / Tidlor / Heng, from competitors_census.json); the licensed PICO
operators — AutoX's most direct rural small-ticket rival — were only ever read at the
province/district AGGREGATE (pico_competitors.json / pico_district.json, on the #acq tab),
never attached to the individual branch. This layer closes that gap (objective #2,
competitive risk on the EXISTING footprint — it makes NO open/close/expand call).

CANONICAL JOIN (no fuzzy name matching — this is the point):
  - amphoe.json carries `branch_amphoe[]`, an INDEX-ALIGNED array (branch i -> index into
    amphoe.json's 928-district `amphoe[]`), the authoritative spatial (point-in-polygon)
    assignment of each branch to its district — the SAME 928-district identity that
    build_pico_district.py keys `pico_district.json` on ("province_th|amphoe").
  - So branch i's district count is exactly pico_district.by_district["<province_th>|<amphoe>"],
    with a MISS meaning that district genuinely has ZERO licensed PICO operators in the FPO
    registry (an honest zero — both sides share amphoe.json's identity, so a miss is never a
    name mismatch). 503 branches sit in a zero-PICO district; 1,512 in a district with >=1.

INPUTS (all committed, MEASURED, deterministic):
  platform/data/amphoe.json         — branch_amphoe[] (PIP assignment) + amphoe[] (928-district identity)
  platform/data/pico_district.json  — by_district{ "prov|amphoe": {total,head,branch,recent,recent_op} }
                                       (build_pico_district.py, from the FPO picofinanceoperate registry)
  platform/data/branches.json       — for the branch count + branches_fingerprint stamp

OUTPUT platform/data/branch_pico.json (index-aligned to branches.json, record i == branch i):
  branches[i] = { "pico": total, "head": head, "branch": branch, "recent": recent }
    pico   = licensed PICO operators registered to THIS branch's district (0 = honest zero)
    head   = of which head offices (สำนักงานใหญ่)
    branch = of which branch offices (สาขา)
    recent = of which licensed in the registry's most-recent window (pico_district's `recent`)
  meta carries full MEASURED provenance, the canonical-join note, a coverage summary
  (n_with_pico / n_zero / n_districts_covered), and branches_fingerprint.

Deterministic + network-free. Pure stdlib.
  python3 build_branch_pico.py            # write platform/data/branch_pico.json
  python3 build_branch_pico.py --check    # re-run, byte-compare (SKIP if an input is absent)
"""
import argparse
import json
import os
import sys

from lib.fingerprint import branches_fingerprint

ROOT = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(ROOT)
DATA = os.path.join(REPO, "platform", "data")
BRANCHES = os.path.join(DATA, "branches.json")
AMPHOE = os.path.join(DATA, "amphoe.json")
PICO_DISTRICT = os.path.join(DATA, "pico_district.json")
OUT = os.path.join(DATA, "branch_pico.json")


class JoinError(Exception):
    """A branch_amphoe index is out of range against amphoe[] — the two layers have desynced."""


def _load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def dumps(obj):
    return json.dumps(obj, ensure_ascii=False, indent=2) + "\n"


def build():
    # every input must be present; --check treats an absent input as SKIP, not FAIL.
    if not (os.path.exists(BRANCHES) and os.path.exists(AMPHOE) and os.path.exists(PICO_DISTRICT)):
        return None

    branches = _load(BRANCHES)
    amp = _load(AMPHOE)
    amphoe = amp.get("amphoe") or []
    branch_amphoe = amp.get("branch_amphoe") or []
    by_district = (_load(PICO_DISTRICT) or {}).get("by_district") or {}

    n = len(branches)

    # index-alignment guard: branch_amphoe must be one index per branch, or the join misattributes
    # every branch. Emit an honest ABSENT-state instead of a silently-misaligned MEASURED layer.
    if n == 0 or len(branch_amphoe) != n:
        return {
            "meta": {
                "generated_by": "build_branch_pico.py",
                "absent": True,
                "label": "MEASURED licensed-PICO rivals in each branch's district — UNAVAILABLE this run",
                "note": ("amphoe.json branch_amphoe has %d entries but branches.json has %d records — "
                         "length mismatch, cannot trust the district join; honest ABSENT-state emitted "
                         "instead of a misaligned projection." % (len(branch_amphoe), n)),
                "n_branches": n,
            },
            "branches": [],
        }

    recs = []
    districts_covered = set()
    n_with_pico = 0
    for i in range(n):
        idx = branch_amphoe[i]
        rec = {"pico": 0, "head": 0, "branch": 0, "recent": 0}
        if isinstance(idx, int) and 0 <= idx < len(amphoe):
            a = amphoe[idx]
            key = "%s|%s" % (a.get("province_th"), a.get("name"))
            p = by_district.get(key)
            if p:
                rec = {
                    "pico": int(p.get("total", 0)),
                    "head": int(p.get("head", 0)),
                    "branch": int(p.get("branch", 0)),
                    "recent": int(p.get("recent", 0)),
                }
                if rec["pico"] > 0:
                    n_with_pico += 1
                    districts_covered.add(key)
        elif idx is not None:
            # a present-but-out-of-range index means amphoe.json's two arrays have desynced —
            # fail loudly (like every other builder's CHECK FAIL) rather than ship a wrong join.
            raise JoinError(
                "branch_amphoe[%d]=%r is out of range for amphoe[] (len %d) — amphoe.json is "
                "internally inconsistent; rebuild it (build_amphoe.py) before this layer" %
                (i, idx, len(amphoe))
            )
        recs.append(rec)

    # self-check invariant: head + branch of every non-zero record must not exceed its total
    # (a parse/aggregation bug in pico_district would surface here, not silently in the app).
    bad = [i for i, r in enumerate(recs) if r["head"] + r["branch"] > r["pico"] and r["pico"] > 0]
    if bad:
        raise JoinError(
            "%d records have head+branch > total (e.g. index %d: %r) — pico_district head/branch "
            "split is inconsistent with total; fix build_pico_district.py before shipping" %
            (len(bad), bad[0], recs[bad[0]])
        )

    return {
        "meta": {
            "generated_by": "build_branch_pico.py",
            "label": ("MEASURED — licensed PICO-finance (พิโกไฟแนนซ์) operators registered in each "
                      "branch's OWN district (อำเภอ). A distinct small-ticket non-bank rival class, "
                      "counted per branch for the first time; the per-branch big-4 census "
                      "(rival_pressure.json) does not include PICO operators."),
            "source": ("MEASURED — FPO (Fiscal Policy Office) licensed-operator registry via "
                       "pico_district.json (build_pico_district.py), joined to each branch by "
                       "amphoe.json's branch_amphoe[] point-in-polygon district assignment."),
            "join": ("branch i -> amphoe.json branch_amphoe[i] -> amphoe[]['province_th'|'name'] -> "
                     "pico_district.by_district['province_th|amphoe']. A district absent from "
                     "by_district is an HONEST ZERO (both sides share amphoe.json's 928-district "
                     "identity — a miss is a real zero, never a name mismatch)."),
            "caveats": [
                "District grain, not catchment radius: this counts PICO operators registered in the "
                "branch's administrative อำเภอ, not within a fixed km radius (the FPO registry carries "
                "a service address, not coordinates). A large อำเภอ may place a rival several km away.",
                "Registry = LICENSED operators (service points), not live-storefront geocodes; a "
                "licensed head office may not run a walk-in branch. head/branch splits the two office "
                "types as the registry records them.",
            ],
            "fields": {
                "pico": "licensed PICO operators registered in this branch's district (total)",
                "head": "of which head offices (สำนักงานใหญ่)",
                "branch": "of which branch offices (สาขา)",
                "recent": "of which licensed in the registry's most-recent window (pico_district 'recent')",
            },
            "n_branches": n,
            "n_with_pico": n_with_pico,
            "n_zero": n - n_with_pico,
            "n_districts_covered": len(districts_covered),
            "branches_fingerprint": branches_fingerprint(branches),
            "index_aligned_to": "branches.json (record i == branch i)",
        },
        "branches": recs,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true",
                    help="re-run and byte-compare against the committed JSON; exit 1 on drift "
                         "(exit 3 / SKIP when an input layer is absent)")
    args = ap.parse_args()

    try:
        data = build()
    except JoinError as e:
        print("CHECK FAIL: %s" % e, file=sys.stderr)
        sys.exit(1)

    if args.check:
        if data is None:
            print("CHECK SKIP: an input layer (branches/amphoe/pico_district) is absent — "
                  "branch_pico not byte-checkable", file=sys.stderr)
            sys.exit(3)
        text = dumps(data)
        if not os.path.exists(OUT):
            print("CHECK FAIL: %s does not exist" % OUT)
            sys.exit(1)
        with open(OUT, encoding="utf-8") as f:
            existing = f.read()
        if existing == text:
            print("CHECK OK: %s reproduces byte-for-byte (%d branches, %d with PICO in-district)" %
                  (OUT, data["meta"]["n_branches"], data["meta"].get("n_with_pico", 0)))
            sys.exit(0)
        print("CHECK FAIL: %s differs from a fresh build" % OUT)
        sys.exit(1)

    if data is None:
        print("SKIP: an input layer (branches/amphoe/pico_district) is absent — nothing to build",
              file=sys.stderr)
        sys.exit(3)

    text = dumps(data)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(text)
    m = data["meta"]
    print("wrote %s (%d branches, %d with PICO in-district, %d zero, %d districts covered)" %
          (OUT, m["n_branches"], m.get("n_with_pico", 0), m.get("n_zero", 0),
           m.get("n_districts_covered", 0)))


if __name__ == "__main__":
    main()
