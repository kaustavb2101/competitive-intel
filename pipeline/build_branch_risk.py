#!/usr/bin/env python3
"""
build_branch_risk.py — PER-BRANCH COMPOSITE RISK (objective #1)
==============================================================
One ranked read of "which branches are getting riskier" by FUSING the risk
signals the platform already computes into a single 0-100 composite per branch.

It is deterministic + network-free + carries --check (byte-exact reproduce),
mirroring the other builders (build_amphoe / build_crop_stress / ...).

Output: platform/data/branch_risk.json — INDEX-ALIGNED to platform/data/branches.json
(entry i <-> branch i), identical alignment to branch_occupations.json /
occupation_risk.json. Each record:
    {code, composite_risk (0-100), components{...}, top_driver}

------------------------------------------------------------------------------
THE COMPOSITE (ESTIMATED — a triage ranking, NOT a measured default rate)
------------------------------------------------------------------------------
For each branch we combine up to FOUR component signals, each on a 0-100 scale,
each clearly tagged MEASURED or ESTIMATED in meta. A branch joins a province
component by its Thai province name (branches.json field "v"); the two
branch-own components use the branch's own features in branches.json.

  household  [MEASURED]   province household debt-stress: stress_index (0-100)
                          from household_risk_by_province.json (NSO SES via the
                          TMLI bridge). The single most direct borrower-balance-
                          sheet signal we have, so it carries the top weight.
  agri       [ESTIMATED]  province crop/agri stress: agri_stress (0..1, rescaled
                          to 0-100) from crop_stress.json, with a fixed BUMP when
                          the province is double_stress (rice/rubber price-soft +
                          drought). A GLOBAL-price proxy, hence estimated.
  occupation [MEASURED x  per-branch occupation-stress score 's' from
              ESTIMATED]  occupation_risk.json (measured Overture occupation
                          shares x an estimated stressed-sector weighting),
                          min-max normalized to 0-100 across the network.
  segment    [DERIVED]    the branch's OWN segment/collateral risk signals in
                          branches.json: agri_pd (a), collateral_density (c),
                          merchant_demand (m). Blended, then min-max normalized
                          to 0-100 across the network. (These are derive.py
                          features off the sourced master — see DATA_SOURCES.md.)

DEFAULT WEIGHTS (sum to 1.0 when all four are present):
  household 0.35, agri 0.25, occupation 0.20, segment 0.20

GRACEFUL DEGRADE (no fabrication): a component that is ABSENT for a branch — the
optional file isn't present, OR the branch's province isn't in that province
layer, OR the branch has no measured occupation catchment (t == 0) — is simply
DROPPED, and its weight is REDISTRIBUTED proportionally across the components the
branch DOES have. A missing signal is never invented or zero-filled. composite_risk
is the weight-renormalized blend of whatever is available; a branch with zero
available components (should not happen — segment is always present) gets null.

  composite_risk = round( sum_k(w_k_renorm * component_k) , 1)   over present k

top_driver = the present component with the single largest *weighted* contribution
(w_k_renorm * component_k), so it answers "what is pushing THIS branch up the list".

Run:
  python3 build_branch_risk.py            # write platform/data/branch_risk.json
  python3 build_branch_risk.py --check    # re-run, byte-compare against committed file
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, "source-data")
DATA = os.path.join(ROOT, "platform", "data")
OUT = os.path.join(DATA, "branch_risk.json")

# --- component default weights (sum to 1.0 when ALL present) ------------------
W = {
    "household": 0.35,   # MEASURED province debt-stress (NSO) — most direct signal
    "agri": 0.25,        # ESTIMATED province crop/agri stress (global-price proxy)
    "occupation": 0.20,  # MEASURED shares x ESTIMATED stressed-sector weight
    "segment": 0.20,     # DERIVED branch-own agri/collateral/merchant blend
}

# crop_stress agri_stress is 0..1 -> 0-100; double_stress provinces get a fixed
# additive bump (capped at 100) reflecting the 2026 rice/rubber double-hit.
DOUBLE_STRESS_BUMP = 12.0

# branch-own "segment" blend weights over branches.json features (each ~0-100):
#   a = agri_pd, c = collateral_density, m = merchant_demand.
# agri & collateral lead (the title-loan default-relevant axes); merchant is a
# lighter demand/liquidity signal. Blend is then min-max normalized network-wide.
SEG_W = {"a": 0.45, "c": 0.40, "m": 0.15}

# human labels for top_driver / meta
DRIVER_LABEL = {
    "household": "Household debt-stress (province, measured)",
    "agri": "Crop/agri stress (province, estimated)",
    "occupation": "Occupation-sector stress (branch, measured x estimated)",
    "segment": "Branch own segment/collateral risk (derived)",
}


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_opt(rel):
    """Load an OPTIONAL platform/data file; return None if absent (graceful degrade)."""
    p = os.path.join(DATA, rel)
    if not os.path.exists(p):
        return None
    try:
        return load(p)
    except Exception:
        return None


def minmax_to_100(values):
    """Min-max normalize a list of (index, value) onto 0-100. Returns {index: score}.
    Indices with value None are skipped. Degenerate (all equal / <2 points) -> 0.0
    for every present index (no spread to rank on)."""
    pres = [(i, v) for i, v in values if v is not None]
    if not pres:
        return {}
    lo = min(v for _, v in pres)
    hi = max(v for _, v in pres)
    rng = hi - lo
    if rng <= 0:
        return {i: 0.0 for i, _ in pres}
    return {i: round((v - lo) / rng * 100.0, 4) for i, v in pres}


def build():
    branches = load(os.path.join(DATA, "branches.json"))   # required, index-defining
    master = load(os.path.join(SRC, "branches_final.json"))  # for branch `code`
    n = len(branches)

    # code per branch (master is 1:1 with branches.json in the same order — derive.py).
    # If the master length ever drifts, fall back to None code (still index-aligned).
    codes = [b.get("code") for b in master] if len(master) == n else [None] * n

    # --- optional inputs (each may be wholly absent -> component dropped network-wide) ---
    hr = load_opt("household_risk_by_province.json")
    cs = load_opt("crop_stress.json")
    occ = load_opt("occupation_risk.json")

    hr_absent = not (hr and not (hr.get("meta") or {}).get("absent") and hr.get("provinces"))
    cs_present = bool(cs and cs.get("provinces"))
    # occupation layer must be present AND index-aligned to be usable
    occ_present = bool(occ and isinstance(occ.get("branches"), list)
                       and len(occ["branches"]) == n)

    # province lookups (Thai-name keyed — keys already match branches.json "v").
    hr_si = {}
    if not hr_absent:
        for p in hr["provinces"]:
            si = p.get("stress_index")
            if isinstance(si, (int, float)) and not isinstance(si, bool):
                hr_si[p.get("province")] = float(si)

    cs_agri = {}    # prov_th -> agri_stress component (0-100, incl. double-stress bump)
    if cs_present:
        for p in cs["provinces"]:
            ag = p.get("agri_stress")
            if isinstance(ag, (int, float)) and not isinstance(ag, bool):
                v = ag * 100.0
                if p.get("double_stress"):
                    v = min(100.0, v + DOUBLE_STRESS_BUMP)
                cs_agri[p.get("th")] = round(v, 4)

    # --- per-branch RAW component values (pre-normalization) ----------------------
    # household & agri are already on a 0-100 interpretable scale (use directly).
    # occupation & segment are raw -> network min-max normalized below.
    occ_raw = []   # (i, s) measured occupation-stress; None when no catchment (t==0)
    seg_raw = []   # (i, blended a/c/m); always present (branches.json always has them)
    for i, b in enumerate(branches):
        if occ_present:
            o = occ["branches"][i]
            t = o.get("t")
            s = o.get("s")
            # only count as a real signal when there's a measured catchment
            if isinstance(t, (int, float)) and t > 0 and isinstance(s, (int, float)):
                occ_raw.append((i, float(s)))
            else:
                occ_raw.append((i, None))
        seg = (SEG_W["a"] * (b.get("a") or 0)
               + SEG_W["c"] * (b.get("c") or 0)
               + SEG_W["m"] * (b.get("m") or 0))
        seg_raw.append((i, seg))

    occ_norm = minmax_to_100(occ_raw) if occ_present else {}
    seg_norm = minmax_to_100(seg_raw)

    # --- assemble per-branch composite -------------------------------------------
    recs = []
    used_counts = {"household": 0, "agri": 0, "occupation": 0, "segment": 0}
    for i, b in enumerate(branches):
        prov = b.get("v")
        comps = {}   # component_key -> 0-100 value (only those PRESENT for this branch)

        if not hr_absent and prov in hr_si:
            comps["household"] = round(hr_si[prov], 1)
        if cs_present and prov in cs_agri:
            comps["agri"] = round(cs_agri[prov], 1)
        if occ_present and i in occ_norm:
            comps["occupation"] = round(occ_norm[i], 1)
        if i in seg_norm:
            comps["segment"] = round(seg_norm[i], 1)

        for k in comps:
            used_counts[k] += 1

        if not comps:
            # should not happen (segment is always present), but degrade honestly.
            recs.append({"code": codes[i], "composite_risk": None,
                         "components": {}, "top_driver": None})
            continue

        # redistribute the absent components' weight across the present ones.
        wsum = sum(W[k] for k in comps)
        weighted = {k: (W[k] / wsum) * v for k, v in comps.items()}
        composite = round(sum(weighted.values()), 1)
        top_driver = max(weighted, key=lambda k: (weighted[k], k))

        recs.append({
            "code": codes[i],
            "composite_risk": composite,
            "components": comps,
            "top_driver": top_driver,
        })

    # --- meta --------------------------------------------------------------------
    scored = [r["composite_risk"] for r in recs if r["composite_risk"] is not None]
    driver_tally = {}
    for r in recs:
        if r["top_driver"]:
            driver_tally[r["top_driver"]] = driver_tally.get(r["top_driver"], 0) + 1

    meta = {
        "title": "Per-branch composite risk (portfolio impact / risk, objective #1)",
        "generated_by": "pipeline/build_branch_risk.py",
        "deterministic": True,
        "network_free": True,
        "label": "ESTIMATED COMPOSITE — fuses measured + estimated risk signals into one "
                 "0-100 triage ranking of 'which branches are getting riskier'. NOT a "
                 "measured default rate. Each input's provenance is stated per component.",
        "n_branches": n,
        "n_scored": len(scored),
        "index_note": "branches[] is INDEX-ALIGNED to platform/data/branches.json "
                      "(entry i <-> branch i), identical to branch_occupations.json / "
                      "occupation_risk.json. `code` is the AutoX branch code from the master.",
        "components": {
            "household": {
                "weight": W["household"],
                "provenance": "MEASURED — province household stress_index (0-100) from "
                              "household_risk_by_province.json (NSO SES debt/income via the "
                              "TMLI bridge). Branch inherits its province value.",
                "scale": "used directly (already 0-100).",
            },
            "agri": {
                "weight": W["agri"],
                "provenance": "ESTIMATED — province agri_stress (0..1) from crop_stress.json "
                              "(World Bank GLOBAL price proxy x measured rainfall anomaly, "
                              "scaled by crop_dependence), rescaled to 0-100, +%g when the "
                              "province is double_stress (rice/rubber). Branch inherits province."
                              % DOUBLE_STRESS_BUMP,
                "scale": "agri_stress*100 (+%g double-stress bump, capped 100)." % DOUBLE_STRESS_BUMP,
                "double_stress_bump": DOUBLE_STRESS_BUMP,
            },
            "occupation": {
                "weight": W["occupation"],
                "provenance": "MEASURED x ESTIMATED — per-branch occupation-stress score 's' "
                              "from occupation_risk.json (measured Overture occupation shares x "
                              "an estimated stressed-sector weighting). Dropped for branches "
                              "with no measured catchment (occupation_risk t == 0).",
                "scale": "min-max normalized to 0-100 across the network (raw 's' has a small "
                         "absolute range, so it is rank-normalized to be comparable).",
            },
            "segment": {
                "weight": W["segment"],
                "provenance": "DERIVED — the branch's OWN segment/collateral signals in "
                              "branches.json: a=agri_pd, c=collateral_density, m=merchant_demand "
                              "(derive.py features off the sourced master, see DATA_SOURCES.md).",
                "scale": "blend %s then min-max normalized to 0-100 across the network."
                         % json.dumps(SEG_W),
                "blend_weights": SEG_W,
            },
        },
        "formula": {
            "composite_risk": "round( sum_k( (w_k / sum_present w) * component_k ), 1 ) over the "
                              "components PRESENT for the branch (absent components' weight is "
                              "redistributed proportionally — never zero-filled or fabricated).",
            "default_weights": W,
            "top_driver": "the present component with the largest weighted contribution "
                          "(w_k_renorm * component_k); ties broken by component name.",
        },
        "graceful_degrade": "Any absent input (file missing, province not in a province layer, "
                            "or branch with no measured occupation catchment) is dropped and its "
                            "weight redistributed across present components. --check passes even "
                            "when optional inputs are absent. composite_risk is null only if a "
                            "branch has zero available components.",
        "inputs_used": {
            "branches.json": "REQUIRED — defines index order and the segment component (a/c/m).",
            "branches_final.json": "REQUIRED (source-data) — branch `code`.",
            "household_risk_by_province.json": "present" if not hr_absent else "ABSENT/empty (household component skipped)",
            "crop_stress.json": "present" if cs_present else "ABSENT (agri component skipped)",
            "occupation_risk.json": "present (index-aligned)" if occ_present else "ABSENT/misaligned (occupation component skipped)",
        },
        "component_coverage": {k: used_counts[k] for k in W},
        "top_driver_tally": dict(sorted(driver_tally.items(), key=lambda kv: -kv[1])),
        "stats": {
            "composite_min": round(min(scored), 1) if scored else None,
            "composite_max": round(max(scored), 1) if scored else None,
            "composite_mean": round(sum(scored) / len(scored), 1) if scored else None,
        },
        "sort": "branches[] kept in index order (NOT sorted) to preserve alignment; rank by "
                "composite_risk in the consumer.",
        "caveats": [
            "ESTIMATED composite — a triage ranking, not a measured default rate.",
            "household + agri are PROVINCE-level signals inherited by every branch in the "
            "province; they do not vary within a province.",
            "occupation 's' has a small raw range and is rank-normalized, so its component is a "
            "relative (within-network) signal, not an absolute stress level.",
            "weights are an editorial judgement (household weighted highest as the most direct "
            "balance-sheet signal); see meta.components for each input's provenance.",
        ],
    }

    return {"meta": meta, "branches": recs}


def dumps(obj):
    return json.dumps(obj, ensure_ascii=False, indent=2) + "\n"


def main():
    ap = argparse.ArgumentParser(description="per-branch composite risk (objective #1)")
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
            print("CHECK OK: branch_risk.json reproduces byte-for-byte (%d branches, %d scored)"
                  % (data["meta"]["n_branches"], data["meta"]["n_scored"]))
            sys.exit(0)
        print("CHECK FAIL: branch_risk.json differs from a fresh build")
        sys.exit(1)

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    # newline="\n": the Windows default turns every \n into \r\n, inflating the byte sizes
    # build_provenance.py censuses and diverging the local tree from the LF blob CI reads.
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    m = data["meta"]
    print("wrote %s (%d branches, %d scored)" % (OUT, m["n_branches"], m["n_scored"]))
    print("  component coverage:", m["component_coverage"])
    print("  composite stats:", m["stats"])
    ranked = sorted(
        [r for r in data["branches"] if r["composite_risk"] is not None],
        key=lambda r: -r["composite_risk"])
    print("  top-10 riskiest:")
    for r in ranked[:10]:
        print("    %-14s %5.1f  driver=%s" % (r["code"], r["composite_risk"], r["top_driver"]))


if __name__ == "__main__":
    main()
