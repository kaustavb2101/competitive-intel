#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_flood_hazard.py — per-district & per-branch repeated-flood hazard (MEASURED, GISTDA).

Projects the committed source-data/gistda_flood_hazard.json (GISTDA Repeated Flooding 2005-2016,
server-side MAX(flood_freq) per district — see pull_flood_hazard.py) into platform/data/flood_hazard.json:
a district-grain hazard map keyed on the app's canonical amphoe identity, a province rollup, and a
per-branch flood-frequency flag INDEX-ALIGNED to branches.json.

WHAT THE NUMBER MEANS (objective #1 — portfolio/collateral risk)
  flood_freq = the count of the 12 years 2005-2016 in which any ground in that district flooded (1-12).
  A high value marks a district whose collateral (vehicles under title, borrower cash-flow from farm/
  shop ground) sits on repeatedly-inundated land — a chronic PD / recovery hazard on the network we
  already run. This is a MEASURED government hazard census, NOT an estimate.

HONEST SCOPE
  - MAX(flood_freq), never SUM(area): the GISTDA polygons OVERLAP (per-event, not dissolved), so any
    flooded-AREA total off this service is a 3-9x overstatement artifact (docs/NEXT_STEPS.md §0). The
    per-district MAX is immune to that overlap; no area is claimed anywhere in the output.
  - Join is Thai-name-first, English-name fallback, onto amphoe.json's 928 canonical districts. The
    handful that resolve to neither are counted honestly in meta.n_unresolved (with samples), NOT
    silently dropped. Every unresolved district is a zero-branch amphoe (verified), so no AutoX branch
    loses a real flood flag to the naming gap — asserted at build time.

INPUT  source-data/gistda_flood_hazard.json  (committed; re-pullable via pull_flood_hazard.py)
       platform/data/amphoe.json              (928 canonical districts + branch_amphoe index)
       platform/data/branches.json            (identity/order for the fingerprint + per-branch join)
OUTPUT platform/data/flood_hazard.json
       { meta, by_province{prov:{maxfreq,n_chronic,n_districts}}, by_district{"prov|amphoe":freq},
         branches:[freq,...] }  — branches[i] index-aligned to branches.json (0 = district not in the
         repeated-flood registry).

DETERMINISTIC + NETWORK-FREE. Carries --check; SKIP-passes (exit 3) when the committed source or an
input layer is absent, same convention as build_branch_density.py / build_pico_district.py.

  python3 build_flood_hazard.py
  python3 build_flood_hazard.py --check
"""
import argparse, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.regionmap import canonical
from lib.fingerprint import branches_fingerprint

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, "source-data", "gistda_flood_hazard.json")
AMPHOE = os.path.join(ROOT, "platform", "data", "amphoe.json")
BRANCHES = os.path.join(ROOT, "platform", "data", "branches.json")
OUT = os.path.join(ROOT, "platform", "data", "flood_hazard.json")

CHRONIC = 7   # flooded in >=7 of 12 years — the "chronic hazard" band
# interpretation bands surfaced to the app (freq -> label); documented in meta.bands
BANDS = [(10, "chronic (10-12/12 yrs)"), (7, "frequent (7-9/12 yrs)"),
         (4, "recurrent (4-6/12 yrs)"), (1, "occasional (1-3/12 yrs)"), (0, "none on record")]


class UnresolvedBranchError(Exception):
    """A district that carries AutoX branches failed the amphoe join — the naming gap would silently
    drop a REAL per-branch flag. Fix the join (do not ship) rather than under-report branch hazard."""


def _load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def dumps(obj):
    return json.dumps(obj, ensure_ascii=False, indent=1) + "\n"


def band(freq):
    for lo, lab in BANDS:
        if freq >= lo:
            return lab
    return "none on record"


def build():
    if not (os.path.exists(SRC) and os.path.exists(AMPHOE) and os.path.exists(BRANCHES)):
        return None

    src = _load(SRC)
    districts = src.get("districts") or []
    smeta = src.get("meta") or {}

    ampdoc = _load(AMPHOE)
    amp = ampdoc["amphoe"]
    branch_amphoe = ampdoc.get("branch_amphoe") or []
    branches = _load(BRANCHES)
    n_branches = len(branches)

    # amphoe.json index -> stores by (province_th, thai_name) and (province_th, english_name),
    # so a GISTDA row can join on either its Thai ap_tn or its English ap_en.
    by_prov = {}
    for i, a in enumerate(amp):
        prov = a["province_th"]
        d = by_prov.setdefault(prov, {})
        d[a["name"].strip()] = i
        en = (a.get("name_en") or "").strip()
        if en:
            d.setdefault(en, i)
            d.setdefault(en.lower(), i)

    amp_freq = [0] * len(amp)          # amphoe-index -> max flood_freq (0 = not in registry)
    by_district = {}                    # "province_th|amphoe" -> freq
    prov_roll = {}                      # canonical province_th -> [maxfreq, n_chronic, n_districts]
    n_resolved = 0
    unresolved = []                     # (prov, ap_tn, ap_en, freq)

    for row in districts:
        prov = canonical((row.get("pv_tn") or "").strip())
        freq = int(row.get("maxfreq") or 0)
        # province rollup uses the SOURCE directly (province match is exact for all rows), so it is
        # complete over all flood-affected provinces regardless of amphoe-name resolution.
        pr = prov_roll.setdefault(prov, [0, 0, 0])
        pr[0] = max(pr[0], freq)
        pr[2] += 1
        if freq >= CHRONIC:
            pr[1] += 1

        m = by_prov.get(prov)
        idx = None
        if m is not None:
            ap_tn = (row.get("ap_tn") or "").strip()
            ap_en = (row.get("ap_en") or "").strip()
            idx = m.get(ap_tn)
            if idx is None and ap_en:
                idx = m.get(ap_en)
            if idx is None and ap_en:
                idx = m.get(ap_en.lower())
        if idx is None:
            unresolved.append((prov, row.get("ap_tn"), row.get("ap_en"), freq))
            continue
        n_resolved += 1
        # a district can appear once per group; keep the max defensively
        amp_freq[idx] = max(amp_freq[idx], freq)
        key = "%s|%s" % (amp[idx]["province_th"], amp[idx]["name"])
        by_district[key] = max(by_district.get(key, 0), freq)

    # per-branch flag via the branch_amphoe index join
    branch_freq = [0] * n_branches
    if len(branch_amphoe) == n_branches:
        for i, ai in enumerate(branch_amphoe):
            if isinstance(ai, int) and 0 <= ai < len(amp_freq):
                branch_freq[i] = amp_freq[ai]

    # SAFETY: no unresolved district may carry a branch. Count branches whose amphoe is an
    # unresolved GISTDA district — must be zero, else the naming gap is dropping a real flag.
    unresolved_amp_names = {(p, tn) for (p, tn, _en, _f) in unresolved}
    branches_in_unresolved = 0
    if len(branch_amphoe) == n_branches:
        for ai in branch_amphoe:
            if isinstance(ai, int) and 0 <= ai < len(amp):
                a = amp[ai]
                if (a["province_th"], a["name"]) in unresolved_amp_names:
                    branches_in_unresolved += 1
    if branches_in_unresolved:
        raise UnresolvedBranchError(
            "%d AutoX branches sit in a GISTDA flood district that failed the amphoe join — the "
            "join would drop a real per-branch flood flag; fix the crosswalk before shipping"
            % branches_in_unresolved)

    n_branches_flagged = sum(1 for f in branch_freq if f > 0)
    n_branches_chronic = sum(1 for f in branch_freq if f >= CHRONIC)

    by_province = {p: {"maxfreq": v[0], "n_chronic": v[1], "n_districts": v[2]}
                   for p, v in sorted(prov_roll.items())}
    by_district = {k: by_district[k] for k in sorted(by_district)}
    freq_hist = {}
    for f in branch_freq:
        freq_hist[f] = freq_hist.get(f, 0) + 1

    meta = {
        "generated_by": "build_flood_hazard.py",
        "label": ("MEASURED — repeated-flood hazard per district & branch: MAX flood_freq (count of "
                  "the 12 years 2005-2016 a district's ground flooded), GISTDA 50k census."),
        "source": smeta.get("source", ""),
        "service": smeta.get("service", ""),
        "data_vintage": smeta.get("data_vintage", ""),
        "pulled": smeta.get("pulled", ""),
        "method": ("Server-side MAX(flood_freq) per district (immune to the per-event polygon "
                   "overlap that makes area totals unreliable — no flooded AREA is claimed). Joined "
                   "onto amphoe.json (Thai name first, English name fallback); per-branch flag via "
                   "amphoe.json branch_amphoe index. flood_freq 1-12; chronic band = >=%d." % CHRONIC),
        "chronic_threshold": CHRONIC,
        "bands": [lab for _lo, lab in BANDS],
        "caveats": [
            "MEASURED government hazard census; the only inference is the district name-match, and "
            "every unresolved district is tallied honestly below (all are zero-branch amphoe).",
            "flood_freq is a 2005-2016 STRUCTURAL hazard (does the ground repeatedly flood), distinct "
            "from thaiwater_flood.json's LIVE water-level pulse (is it flooding right now).",
        ],
        "n_districts_flooded": len(districts),
        "n_resolved": n_resolved,
        "n_unresolved": len(unresolved),
        "n_provinces_flooded": len(by_province),
        "n_branches": n_branches,
        "n_branches_flagged": n_branches_flagged,
        "n_branches_chronic": n_branches_chronic,
        "branch_freq_hist": {str(k): freq_hist[k] for k in sorted(freq_hist)},
        "branches_fingerprint": branches_fingerprint(branches),
        "index_aligned_to": "branches.json (record i == branch i)",
    }
    if unresolved:
        meta["unresolved_samples"] = [
            {"province_th": p, "ap_tn": tn, "ap_en": en, "maxfreq": f}
            for (p, tn, en, f) in sorted(unresolved, key=lambda r: (-r[3], r[0], r[1] or ""))[:20]
        ]

    return {"meta": meta, "by_province": by_province, "by_district": by_district,
            "branches": branch_freq}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true",
                    help="re-run and byte-compare against the committed JSON; exit 1 on drift, "
                         "exit 3 / SKIP when the source or an input layer is absent")
    args = ap.parse_args()

    try:
        data = build()
    except UnresolvedBranchError as e:
        print("CHECK FAIL: %s" % e, file=sys.stderr)
        sys.exit(1)

    if args.check:
        if data is None:
            print("CHECK SKIP: source-data/gistda_flood_hazard.json (or an input layer) absent — "
                  "flood_hazard not byte-checkable", file=sys.stderr)
            sys.exit(3)
        text = dumps(data)
        if not os.path.exists(OUT):
            print("CHECK FAIL: %s does not exist" % OUT)
            sys.exit(1)
        with open(OUT, encoding="utf-8") as f:
            existing = f.read()
        if existing == text:
            print("CHECK OK: %s reproduces byte-for-byte (%d branches, %d/%d districts resolved)" %
                  (OUT, data["meta"]["n_branches"], data["meta"]["n_resolved"],
                   data["meta"]["n_districts_flooded"]))
            sys.exit(0)
        print("CHECK FAIL: %s differs from a fresh build" % OUT)
        sys.exit(1)

    if data is None:
        print("SKIP: source-data/gistda_flood_hazard.json (or an input layer) absent — nothing to "
              "build", file=sys.stderr)
        sys.exit(3)

    text = dumps(data)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(text)
    m = data["meta"]
    print("wrote %s (%d branches; %d flagged, %d chronic; %d/%d districts resolved, %d unresolved)"
          % (OUT, m["n_branches"], m["n_branches_flagged"], m["n_branches_chronic"],
             m["n_resolved"], m["n_districts_flooded"], m["n_unresolved"]))


if __name__ == "__main__":
    main()
