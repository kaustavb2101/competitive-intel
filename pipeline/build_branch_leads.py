#!/usr/bin/env python3
"""
build_branch_leads.py — occupation LEAD BOARD per branch (local customer acquisition)
=====================================================================================
For each of the 2,015 branches: which occupations around THIS branch should the
branch manager go after first? This is a CUSTOMER-ACQUISITION layer for people
running an existing branch — NOT a branch-expansion layer (that's amphoe.json /
opportunity_score.json / expansion_plan.json).

What it fuses (all offline, all already shipped):
  - branch_occupations.json  MEASURED 14-bucket establishment mix within the ≤10km
                             catchment (Overture Maps Places — a sample/lower bound,
                             not a registry). This is the "who is actually nearby" count.
  - a TITLE-LOAN FIT MAP     ESTIMATED, editorial. For every occupation bucket, a
                             high/med/low product-fit rating + one-line rationale
                             grounded in the title-loan product: vehicle-owning
                             likelihood, cash-flow volatility, informal income that
                             banks don't serve. Fully embedded in the output (meta +
                             buckets[]) so the judgement is auditable, not hidden.
  - occupation_risk.json +   ESTIMATED risk flag on a lead: factory leads carry the
    crop_stress.json         national manufacturing-softness lever; agriculture leads
                             carry the branch's OWN province crop-household stress.
                             Risky leads are FLAGGED, never excluded — a stressed
                             farmer is still a customer; underwrite accordingly.
  - branches.json a/m/c      branch segment scores, used for the UNTAPPED read:
                             buckets with top-quartile nearby presence whose mapped
                             segment score sits in the network's bottom quartile —
                             "presence we are not yet monetizing" (ESTIMATED inference).
  - branch_labor.json        MEASURED context per branch: province informal-work share
                             (NSO) and district factory workers (DIW) — the two numbers
                             a manager quotes when pitching the top leads.

Ranking (documented, transparent):
  lead_score(bucket) = n_bucket (MEASURED count) x fit_weight (ESTIMATED: high 1.0 /
  med 0.6 / low 0.25). Top 5 buckets with n>0 per branch, sorted by score desc,
  then count desc, then bucket key asc (stable).

Output: platform/data/branch_leads.json  (compact; INDEX-ALIGNED to branches.json)
  { meta:   {... full provenance, fit map rationale, thresholds ...},
    buckets:[{k,label,fit,w,seg,why} x14]   # the auditable fit map
    branches:[{leads:[{k,n,f,rf?} up to 5], u:[{k,n,seg,sv} up to 3], inf, fw}] x2015 }
  Per-lead `label`/`why`/fit weight are joined from buckets[] by `k` (they are pure
  functions of the bucket) — embedding them 10,000x would triple the payload.

Deterministic + network-free. Pure stdlib.
    python3 build_branch_leads.py            # write the JSON
    python3 build_branch_leads.py --check    # verify byte-for-byte reproduce
"""
import os, json, argparse

from fingerprint import branches_fingerprint

ROOT = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(ROOT)
DATA = os.path.join(REPO, "platform", "data")
OUT  = os.path.join(DATA, "branch_leads.json")

# ── THE TITLE-LOAN FIT MAP (ESTIMATED, editorial — the whole point is that it is ──
#    written down and auditable). fit: high / med / low; w: the ranking weight;
#    seg: which branch segment score (a/m/c) monetizes this bucket (None = none);
#    why: one-line product rationale (vehicle ownership x cash-flow volatility x
#    informal income needing non-bank credit).
FIT_WEIGHT = {"high": 1.0, "med": 0.6, "low": 0.25}
FIT_MAP = {  # keyed by branch_occupations.json bucket key; order = bucket order
    "factory":      ("high", "c", "Shift/OT wage swings; motorcycle- and pickup-owning workers with thin bank files — the classic title-loan cash-gap borrower."),
    "auto":         ("high", "m", "Vehicle-rich trade: garages, dealers and parts shops hold titles and need fast working capital between jobs."),
    "retail":       ("high", "m", "Market vendors and small shops run on informal daily cash and own motorcycles/pickups for stock runs — restocking gaps fit title credit."),
    "food":         ("high", "m", "Street food and small eateries: informal daily cash income, motorcycle-owning, largely underbanked."),
    "hospitality":  ("med",  "m", "Seasonal tourism income swings create cash gaps, but wages are steadier than trade; staff commonly own motorcycles."),
    "finance":      ("low",  None, "Banked professionals and competing lenders — their presence signals local credit demand, not leads."),
    "health":       ("low",  None, "Salaried and bank-served; little need to pledge a vehicle."),
    "education":    ("low",  None, "Teacher/civil-service pay with savings-cooperative credit access; rarely title-loan customers."),
    "public":       ("low",  None, "Salaried with GSB/co-op access; low non-bank credit need."),
    "professional": ("low",  None, "Formal payroll and bank credit access; weak title-loan fit."),
    "agriculture":  ("high", "a", "Pickup- and tractor-owning farmers with harvest-cycle cash gaps and informal income — core title-loan demand."),
    "personal":     ("med",  "m", "Salons, repair and laundry micro-operators: informal income, motorcycle-owning, modest ticket sizes."),
    "logistics":    ("high", "c", "Drivers and riders own the truck, van or bike they work with; per-job income is volatile — the vehicle is both livelihood and collateral."),
    "construction": ("high", "c", "Pickup-owning contractors with lumpy project cash flow and informal subcontract income."),
}

# ── risk-flag rule (mirrors build_occupation_risk.py's stressed-sector weights): a
#    lead is FLAGGED (not dropped) when its bucket stress weight >= RISK_W_MIN.
#    factory = FIXED national manufacturing-softness lever (occupation_risk.json meta);
#    agriculture = the branch's OWN province crop-household stress (crop_stress.json).
RISK_W_MIN = 0.35

TOP_LEADS    = 5      # leads per branch (max)
TOP_UNTAPPED = 3      # untapped buckets per branch (max)
PRESENCE_Q   = 0.75   # "high nearby presence" = bucket count >= this quantile of the bucket across all branches
SEG_LOW_Q    = 0.25   # "low segment score" = at/below this quantile of that segment across all branches


def _load(name):
    with open(os.path.join(DATA, name), encoding="utf-8") as f:
        return json.load(f)


def _q(sorted_vals, q):
    """Deterministic quantile: value at floor(q*(n-1)) of the sorted list."""
    return sorted_vals[int(q * (len(sorted_vals) - 1))]


def build():
    occ      = _load("branch_occupations.json")
    branches = _load("branches.json")
    labor    = _load("branch_labor.json")["branches"]
    orisk    = _load("occupation_risk.json")
    crop     = _load("crop_stress.json")["provinces"]

    keys   = [b["key"] for b in occ["buckets"]]
    labels = {b["key"]: b["label"] for b in occ["buckets"]}
    assert set(keys) == set(FIT_MAP), "fit map out of sync with branch_occupations buckets"
    rows = occ["branches"]
    assert len(rows) == len(branches) == len(labor), "inputs not index-aligned"

    # per-province agri stress (same raw-Thai-name join build_occupation_risk.py uses)
    prov_agri = {p.get("th"): float(p.get("agri_stress") or 0.0) for p in crop}
    factory_stress = float(orisk.get("meta", {}).get("factory_stress", 0.5))

    # presence quantile per bucket (across all 2,015 branches) — for the untapped read
    cols = list(zip(*[r["o"] for r in rows]))
    p_hi = {k: _q(sorted(c), PRESENCE_Q) for k, c in zip(keys, cols)}
    # segment "low" cutoffs (bottom quartile of each segment score across the network)
    seg_lo = {s: _q(sorted(b[s] for b in branches), SEG_LOW_Q) for s in ("a", "m", "c")}

    out_rows, n_flagged, n_untapped = [], 0, 0
    for i, (r, br, lb) in enumerate(zip(rows, branches, labor)):
        counts = dict(zip(keys, r["o"]))
        agri_w = prov_agri.get(br.get("v"), 0.0)

        def stress_w(k):
            if k == "factory":     return factory_stress
            if k == "agriculture": return agri_w
            return 0.0

        # ── leads: measured count x estimated fit weight, top 5 ──────────────────
        scored = []
        for k in keys:
            n = counts[k]
            if n <= 0:
                continue
            fit, _seg, _why = FIT_MAP[k]
            scored.append((-n * FIT_WEIGHT[fit], -n, k))
        scored.sort()
        leads = []
        for negs, negn, k in scored[:TOP_LEADS]:
            fit, _seg, _why = FIT_MAP[k]
            lead = {"k": k, "n": counts[k], "f": fit[0]}   # f: h/m/l
            if stress_w(k) >= RISK_W_MIN:
                lead["rf"] = 1
                n_flagged += 1
            leads.append(lead)

        # ── untapped: top-quartile presence, bottom-quartile mapped segment score ──
        unt = []
        for k in keys:
            fit, seg, _why = FIT_MAP[k]
            if seg is None:
                continue
            n = counts[k]
            if n >= p_hi[k] and n > 0 and br[seg] <= seg_lo[seg]:
                unt.append({"k": k, "n": n, "seg": seg, "sv": br[seg]})
        unt.sort(key=lambda u: (-u["n"], u["k"]))
        unt = unt[:TOP_UNTAPPED]
        n_untapped += len(unt)

        row = {"leads": leads, "u": unt}
        # MEASURED context the manager quotes with the pitch (nullable, never fabricated)
        inf = lb.get("informal_pct")
        fw  = lb.get("factory_workers")
        row["inf"] = round(inf, 1) if inf is not None else None
        row["fw"]  = fw
        out_rows.append(row)

    buckets = [{"k": k, "label": labels[k], "fit": FIT_MAP[k][0],
                "w": FIT_WEIGHT[FIT_MAP[k][0]], "seg": FIT_MAP[k][1],
                "why": FIT_MAP[k][2]} for k in keys]

    meta = {
        "generated_by": "pipeline/build_branch_leads.py",
        "label": "OCCUPATION LEAD BOARD per branch — MEASURED nearby establishment counts ranked by an "
                 "ESTIMATED editorial title-loan fit map. For branch managers doing LOCAL CUSTOMER "
                 "ACQUISITION at an existing branch — NOT a branch-expansion layer.",
        "objective": "Acquisition (objective #2, local flavor): which occupations near THIS branch to court first.",
        "n_branches": len(out_rows),
        "branches_fingerprint": branches_fingerprint(branches),
        "index_note": "branches[] is INDEX-ALIGNED to platform/data/branches.json (entry i <-> branch i), "
                      "identical to branch_occupations.json / branch_labor.json / occupation_risk.json.",
        "ranking": "lead_score = n (MEASURED catchment establishment count, <=10km) x fit weight "
                   "(ESTIMATED editorial: high 1.0 / med 0.6 / low 0.25). Top %d buckets with n>0, "
                   "sorted score desc, count desc, key asc." % TOP_LEADS,
        "fit_map_provenance": "ESTIMATED / EDITORIAL. The high/med/low fit ratings and rationales in "
                              "buckets[] are product judgements (vehicle-owning likelihood x cash-flow "
                              "volatility x informal income needing non-bank credit), NOT measured "
                              "conversion rates. They are embedded in full so the judgement is auditable "
                              "and can be argued with. Counts (n) are MEASURED; the weighting is not.",
        "risk_flag": "rf:1 marks a lead in a STRESSED sector — flagged for careful underwriting, never "
                     "excluded. Rule (mirrors occupation_risk.json): bucket stress weight >= %.2f, where "
                     "factory = the national manufacturing-softness lever (%.2f, ESTIMATED, "
                     "occupation_risk.json meta) and agriculture = the branch's OWN province crop-household "
                     "stress (crop_stress.json agri_stress, ESTIMATED). All other buckets carry no stress "
                     "weight." % (RISK_W_MIN, factory_stress),
        "untapped": "u[] = ESTIMATED INFERENCE 'presence we are not yet monetizing': buckets whose nearby "
                    "count is in the network's TOP quartile for that bucket (>= q%.2f) while the mapped "
                    "branch segment score (seg: a=agri, m=merchant, c=collateral) sits in the network's "
                    "BOTTOM quartile (<= q%.2f). Max %d per branch, count desc. The presence is MEASURED; "
                    "the 'not monetizing' read is inferred from segment scores, not from loan books."
                    % (PRESENCE_Q, SEG_LOW_Q, TOP_UNTAPPED),
        "fields": {
            "leads[].k":  "occupation bucket key (join buckets[] for label/fit weight/why).",
            "leads[].n":  "MEASURED — establishments of this bucket within <=10km of the branch "
                          "(Overture Maps Places, a sample/lower bound, not a registry).",
            "leads[].f":  "ESTIMATED — fit rating initial (h/m/l) from the editorial fit map.",
            "leads[].rf": "ESTIMATED — present (1) only when the lead's sector is stressed (see risk_flag).",
            "u[]":        "ESTIMATED inference — high-presence bucket whose mapped segment score is low "
                          "(k, n MEASURED count, seg a/m/c, sv the branch's segment score).",
            "inf":        "MEASURED — province informal-work share %% (NSO, via branch_labor.json); "
                          "province-inherited; null where absent.",
            "fw":         "MEASURED — registered factory workers in the branch's district (DIW, via "
                          "branch_labor.json); null where the district is not measured.",
        },
        "inputs": [
            "branch_occupations.json (MEASURED counts — Overture Maps Places, sample/lower bound)",
            "branches.json (segment scores a/m/c + province; MEASURED features, scores are model outputs)",
            "branch_labor.json (MEASURED NSO informal share + DIW factory workers)",
            "occupation_risk.json (national factory stress lever, ESTIMATED)",
            "crop_stress.json (province agri stress, ESTIMATED composite)",
        ],
        "seg_low_cutoffs": seg_lo,
        "presence_p75": p_hi,
        "n_leads_flagged": n_flagged,
        "n_untapped_rows": n_untapped,
    }
    return {"meta": meta, "buckets": buckets, "branches": out_rows}


def run(check=False):
    obj = build()
    text = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    if check:
        if not os.path.exists(OUT) or open(OUT, encoding="utf-8").read() != text:
            print(f"DRIFT: {os.path.relpath(OUT, REPO)}"); return 1
        print(f"OK: branch_leads.json reproduces ({obj['meta']['n_branches']} branches)")
        return 0
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(text)
    m = obj["meta"]
    print(f"wrote {m['n_branches']} branches -> platform/data/branch_leads.json "
          f"({len(text)/1024:.0f} KB; {m['n_leads_flagged']} flagged leads, {m['n_untapped_rows']} untapped rows)")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="per-branch occupation lead board (local customer acquisition)")
    ap.add_argument("--check", action="store_true")
    raise SystemExit(run(check=ap.parse_args().check))
