#!/usr/bin/env python3
"""
build_occupation_risk.py — OCCUPATION × RISK cross-read per branch (objective #1).

WHAT THIS DOES
--------------
Joins the MEASURED per-branch occupation mix (platform/data/branch_occupations.json,
written by build_occupations.py from the Overture Places pull) against the existing
risk signals to flag branches whose borrower base is CONCENTRATED in a sector that is
currently STRESSED.

The credit thesis (objective #1, portfolio risk): a title-loan book is repaid out of the
borrower's cash flow. If a branch's catchment is dominated by, say, factory/industrial
establishments during an industrial slowdown — or by agriculture during crop-stress — the
borrowers there are disproportionately exposed to that sector's downturn, so that branch's
book is riskier than its headline segment scores suggest. This layer surfaces exactly those
branches.

MEASURED vs ESTIMATED (the data-mandate — stated explicitly, also in meta)
-------------------------------------------------------------------------
  - occupation SHARES (share of a branch's ≤10km establishments in each bucket) are
    MEASURED — they come straight from Overture Maps Places (a sample / lower bound).
  - the STRESS WEIGHTING (which buckets count as "stressed" and how heavily) is ESTIMATED:
    an editorial, transparent judgement about which sectors are under macro pressure now.
    Two buckets carry a stress weight:
      * factory  — industrial/production. ESTIMATED stress = a fixed macro slowdown level
        (Thai manufacturing PMI / MPI softness). Same for every branch (a national lever).
      * agriculture — borrower exposure to the crop cycle. ESTIMATED stress = the branch's
        OWN PROVINCE crop-household stress from crop_stress.json (agri_stress 0..1), which
        is itself an estimated composite (price proxy × drought × crop dependence). So this
        term is province-varying and reuses an already-shipped, already-caveated signal.
    No other bucket is weighted (weight 0) — we only flag sectors we can defend as stressed.
  - the final occupation_risk SCORE is therefore an ESTIMATED composite: a MEASURED
    concentration multiplied by an ESTIMATED stress weight. Every input is exposed per
    branch (sector shares + the two stress weights + the raw terms) so the blend is auditable.

The score is NOT a measured default rate. It is a triage flag: "this branch's borrower base
leans on a sector that is under pressure — look here first."

FORMULA (per branch, all transparent)
-------------------------------------
  sector_share[k]   = o[k] / t            (MEASURED, 0..1; 0 when the catchment is empty)
  stressed_share    = Σ_k sector_share[k] · stress_weight[k]   (only k in STRESS_BUCKETS)
                      where stress_weight[factory]      = FACTORY_STRESS (national, ESTIMATED)
                            stress_weight[agriculture]  = province agri_stress (ESTIMATED, varies)
  occ_risk          = round(100 · stressed_share)             (0..100 ESTIMATED index)
  flag              = occ_risk >= FLAG_THRESHOLD AND t >= MIN_ESTAB
                      (only flag branches with a real, concentrated, stressed base — not noise)

DETERMINISTIC + NETWORK-FREE
----------------------------
No network. Given the same branch_occupations.json + branches.json + crop_stress.json it
reproduces byte-for-byte, so it carries --check (the QA gate runs it).

GRACEFUL ABSENT PATH (mandatory)
--------------------------------
branch_occupations.json is the MEASURED input and may be ABSENT in the sandbox (the Overture
pull runs from a normal/Thai network). Mirrors build_occupations.py exactly:
  - build() returns None when branch_occupations.json is absent.
  - `--check` then prints a skip line and exits 0 (so the gate stays green with no input).
  - a plain run exits non-zero with a clear "run build_occupations.py first" message.
The frontend lens hides itself when occupation_risk.json is absent, so the whole feature is
dark-until-data and lights up automatically once the Overture layer lands.

OUTPUT (platform/data/occupation_risk.json):
  { "meta": {... full provenance, MEASURED/ESTIMATED split, weights, thresholds ...},
    "stress_weights": {"factory": <national>, "agriculture": "per-province agri_stress"},
    "branches": [ {"s": occ_risk 0..100, "f": flag bool, "d": dominant_bucket_key,
                   "ds": dominant_share 0..1, "t": total_estab} , ... ] }
The "branches" array is INDEX-ALIGNED to platform/data/branches.json (entry i ↔ branch i),
matching branch_occupations.json so the frontend reads by branch index.

Usage:
  python3 build_occupation_risk.py            # build/refresh occupation_risk.json
  python3 build_occupation_risk.py --check    # verify byte-exact (skip-passes when the
                                              # MEASURED input is absent)
"""
import argparse, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OCC = os.path.join(ROOT, "platform", "data", "branch_occupations.json")
BRANCHES = os.path.join(ROOT, "platform", "data", "branches.json")
CROP = os.path.join(ROOT, "platform", "data", "crop_stress.json")
OUT = os.path.join(ROOT, "platform", "data", "occupation_risk.json")

# ── ESTIMATED stress weighting ───────────────────────────────────────────────
# A NATIONAL, fixed stress level for the factory/industrial borrower base. This is an
# editorial macro lever (Thai manufacturing softness: PMI/MPI sub-50 territory through
# 2025-26), NOT a measured per-branch quantity. Kept conservative and explicit; the value
# is recorded in meta so it can be revised when a real industrial index is wired in.
FACTORY_STRESS = 0.5     # 0..1 — "how stressed is the factory borrower base, nationally".

# The agriculture bucket's stress weight is NOT a constant — it is the branch's OWN province
# crop-household stress (crop_stress.json agri_stress, 0..1). Branches in a province with no
# crop_stress entry (e.g. Bueng Kan) get 0 agri stress (graceful).

# Flag thresholds — a branch is flagged only when its occupation_risk is high AND its
# catchment carries enough measured establishments to trust the share (not a 2-point fluke).
FLAG_THRESHOLD = 25.0    # 0..100 occ_risk
MIN_ESTAB = 20           # measured establishments ≤10km required to flag

# Stable bucket keys we attach a stress weight to. agriculture is province-resolved.
STRESS_BUCKETS = ("factory", "agriculture")


def _load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def build():
    if not os.path.exists(OCC):
        return None  # MEASURED input absent — caller decides (skip on --check)
    occ = _load(OCC)
    buckets = occ.get("buckets", [])
    bkeys = [b.get("key") for b in buckets]
    recs = occ.get("branches", [])

    branches = _load(BRANCHES)

    # province agri_stress (0..1), keyed by the SAME Thai province name branches use (b["v"]).
    prov_agri = {}
    if os.path.exists(CROP):
        for p in _load(CROP).get("provinces", []):
            prov_agri[p.get("th")] = float(p.get("agri_stress") or 0.0)

    # index of each stressed bucket in the bucket vector (-1 when the layer omits it).
    factory_i = bkeys.index("factory") if "factory" in bkeys else -1
    agri_i = bkeys.index("agriculture") if "agriculture" in bkeys else -1

    out = []
    n_flagged = 0
    for i, b in enumerate(branches):
        e = recs[i] if i < len(recs) else None
        t = (e.get("t") if isinstance(e, dict) else 0) or 0
        o = (e.get("o") if isinstance(e, dict) else None) or []

        # province agri stress for THIS branch (0 when the province has no crop_stress entry).
        agri_w = prov_agri.get(b.get("v"), 0.0)

        # MEASURED shares; ESTIMATED-weighted stressed share.
        if t > 0 and o:
            fac_share = (o[factory_i] / t) if 0 <= factory_i < len(o) else 0.0
            agri_share = (o[agri_i] / t) if 0 <= agri_i < len(o) else 0.0
            stressed_share = fac_share * FACTORY_STRESS + agri_share * agri_w
            # dominant bucket (measured) — argmax of the count vector, for the readout.
            dom_idx = max(range(len(o)), key=lambda j: o[j]) if any(o) else -1
            dom_key = bkeys[dom_idx] if 0 <= dom_idx < len(bkeys) else None
            dom_share = (o[dom_idx] / t) if dom_idx >= 0 else 0.0
        else:
            stressed_share = 0.0
            dom_key = None
            dom_share = 0.0

        score = round(100.0 * stressed_share, 1)
        flag = bool(score >= FLAG_THRESHOLD and t >= MIN_ESTAB)
        if flag:
            n_flagged += 1
        out.append({
            "s": score,
            "f": flag,
            "d": dom_key,
            "ds": round(dom_share, 3),
            "t": t,
        })

    meta = {
        "generated_with": "pipeline/build_occupation_risk.py",
        "objective": "Portfolio impact / risk (objective #1) — flag branches whose borrower "
                     "base is concentrated in a STRESSED sector.",
        "label": "ESTIMATED COMPOSITE — MEASURED occupation shares (Overture Maps Places, a "
                 "sample/lower bound) weighted by an ESTIMATED 'stressed sector' judgement. "
                 "A triage flag, NOT a measured default rate.",
        "measured": "occupation shares per branch (share of ≤10km establishments in each "
                    "Overture bucket) — from branch_occupations.json.",
        "estimated": "the stress weighting: factory borrower-base stress is a fixed national "
                     "macro lever (Thai manufacturing softness); agriculture borrower-base "
                     "stress is the branch's province crop-household stress (crop_stress.json "
                     "agri_stress, itself an estimated composite).",
        "stress_weights_note": {
            "factory": "FIXED national level (%.2f) — ESTIMATED macro slowdown lever, same for "
                       "every branch." % FACTORY_STRESS,
            "agriculture": "PER-PROVINCE — the branch's crop_stress.json agri_stress (0..1), "
                           "ESTIMATED; 0 where the province has no crop_stress entry.",
            "all_other_buckets": "weight 0 — not flagged (we only weight sectors we can defend "
                                 "as stressed).",
        },
        "formula": "occ_risk = 100 * sum_k share_k * stress_weight_k  (k in {factory, agriculture}); "
                   "flag = occ_risk >= %.0f AND total_estab >= %d." % (FLAG_THRESHOLD, MIN_ESTAB),
        "factory_stress": FACTORY_STRESS,
        "flag_threshold": FLAG_THRESHOLD,
        "min_estab": MIN_ESTAB,
        "source_occupations": occ.get("meta", {}).get("source", "Overture Maps Places"),
        "n_branches": len(out),
        "n_flagged": n_flagged,
        "index_note": "branches[] is INDEX-ALIGNED to platform/data/branches.json (entry i <-> "
                      "branch i), identical to branch_occupations.json.",
        "fields": {
            "s": "ESTIMATED occupation-stress score 0..100 (measured shares x estimated weights).",
            "f": "flag — true when s >= flag_threshold AND total establishments >= min_estab.",
            "d": "MEASURED dominant occupation bucket key for the branch's ≤10km catchment (or null).",
            "ds": "MEASURED dominant-bucket share 0..1.",
            "t": "MEASURED total establishments ≤10km (the denominator; 0 = empty/unknown catchment).",
        },
    }
    return {
        "meta": meta,
        "stress_weights": {"factory": FACTORY_STRESS, "agriculture": "per-province agri_stress"},
        "branches": out,
    }


def serialize(obj):
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true",
                    help="verify the committed output reproduces byte-exact (no write); "
                         "skip-passes when branch_occupations.json is absent")
    args = ap.parse_args()

    obj = build()
    if obj is None:
        msg = ("no platform/data/branch_occupations.json yet — run build_occupations.py "
               "(after pull_overture_places.py, from a normal/Thai network) first.")
        if args.check:
            print(f"build_occupation_risk.py --check: skip ({msg})")
            return
        sys.exit(f"build_occupation_risk.py: {msg}")

    payload = serialize(obj)

    if args.check:
        if not os.path.exists(OUT):
            sys.exit("build_occupation_risk.py --check: occupation_risk.json missing but "
                     "branch_occupations.json exists — run build_occupation_risk.py to generate it.")
        cur = open(OUT, encoding="utf-8").read()
        if cur != payload:
            sys.exit("build_occupation_risk.py --check: occupation_risk.json drifted from its "
                     "inputs — re-run build_occupation_risk.py.")
        print("build_occupation_risk.py --check: OK (byte-exact)")
        return

    with open(OUT, "w", encoding="utf-8") as f:
        f.write(payload)
    m = obj["meta"]
    kb = os.path.getsize(OUT) / 1024.0
    print(f"wrote {OUT}  ({kb:.1f} KB)")
    print(f"  {m['n_flagged']}/{m['n_branches']} branches flagged "
          f"(occ_risk >= {int(m['flag_threshold'])} & >= {m['min_estab']} estab ≤10km)")


if __name__ == "__main__":
    main()
