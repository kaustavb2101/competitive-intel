#!/usr/bin/env python3
"""
make_synthetic_tape.py — deterministic SYNTHETIC loan-tape generator for AutoX / เงินไชโย.

WHAT: produces two clearly-labelled SYNTHETIC files that conform to pipeline/loan_tape_schema.md:
  - source-data/loan_tape_synthetic.json        (one row per loan, NO PII)
  - source-data/branch_aum_monthly_synthetic.json (monthly AUM per branch)

WHY: until Kaustav exports a real loan tape, this fake-but-plausible data proves the whole
     ingest -> derive pipeline end to end, so the four turnkey outputs light up immediately.

NOT REAL. Every loan_id starts with "SYNTH-". The ingest stamps all derived numbers SYNTHETIC.

Deterministic: fixed seed + sorted iteration => byte-identical output every run.

Run from pipeline/:
    python3 make_synthetic_tape.py
"""
import hashlib
import json
import os
import random


def stable_hash(s):
    """Deterministic across processes (unlike built-in hash())."""
    return int(hashlib.md5(s.encode("utf-8")).hexdigest(), 16)

SEED = 20260629
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
MASTER = os.path.join(ROOT, "source-data", "branches_final.json")
OUT_TAPE = os.path.join(ROOT, "source-data", "loan_tape_synthetic.json")
OUT_AUM = os.path.join(ROOT, "source-data", "branch_aum_monthly_synthetic.json")

# Origination quarters covered (oldest -> newest). 3 years of vintages.
QUARTERS = [f"{y}Q{q}" for y in (2023, 2024, 2025) for q in (1, 2, 3, 4)]
# AUM monthly series spans the same window through 2025-12.
AUM_MONTHS = [f"{y}-{m:02d}" for y in (2023, 2024, 2025) for m in range(1, 13)]

SEGMENTS = ["agri", "merchant", "collateral", "other"]
# Target portfolio segment mix (title lender: collateral-heavy).
SEGMENT_MIX = {"agri": 0.30, "merchant": 0.22, "collateral": 0.40, "other": 0.08}

COLLATERAL = ["motorcycle", "car", "pickup", "gold", "land"]
# ~50% motorcycle as specified; rest plausible for a Thai title lender.
COLLATERAL_MIX = {"motorcycle": 0.50, "car": 0.16, "pickup": 0.18, "gold": 0.12, "land": 0.04}

# Typical principal (THB) by collateral type: (mean, spread). Title-loan scale.
PRINCIPAL = {
    "motorcycle": (28000, 9000),
    "car": (180000, 70000),
    "pickup": (220000, 80000),
    "gold": (35000, 15000),
    "land": (450000, 180000),
}

STATUSES = ["current", "30+", "90+", "charged_off"]


def weighted_choice(rng, mix):
    """Deterministic weighted pick from {key: weight}. Keys sorted for stability."""
    items = sorted(mix.items())
    r = rng.random() * sum(w for _, w in items)
    acc = 0.0
    for k, w in items:
        acc += w
        if r <= acc:
            return k
    return items[-1][0]


def quarter_age(orig_q, latest_q=QUARTERS[-1]):
    """How many quarters old the cohort is (0 = booked in the latest quarter)."""
    return QUARTERS.index(latest_q) - QUARTERS.index(orig_q)


def synth_open_date(rng, branch):
    """A stable, plausible branch opening date. Derived from branch demand_decile so it's
    sticky per branch and not pure noise. YYYY-MM-DD."""
    # higher-demand branches opened earlier (more established); spread 2016..2022.
    dec = branch.get("demand_decile", 5) or 5
    base_year = 2016 + (10 - int(dec)) % 7  # 2016..2022
    month = 1 + (stable_hash(branch["code"]) % 12)
    return f"{base_year}-{month:02d}-01"


def status_for(rng, segment, branch, age_q):
    """Pick a delinquency status. Aging: older cohorts have had more time to go 90+/charged_off.
    Riskier proxies (agri_pd / merchant_pd / low collateral) lift the bad-rate. Deterministic
    via rng. Returns one of STATUSES."""
    # base hazard scales with cohort age (more seasoning => more defaults)
    seasoning = min(age_q, 12) / 12.0  # 0..1
    # risk lift from segment proxies on the branch (0..1-ish)
    if segment == "agri":
        risk = (branch.get("agri_pd", 30) or 30) / 100.0
    elif segment == "merchant":
        risk = (branch.get("merchant_pd", 50) or 50) / 100.0
    elif segment == "collateral":
        # higher collateral_density = healthier market => lower risk; invert
        risk = 1.0 - (branch.get("collateral_density", 70) or 70) / 100.0
    else:
        risk = 0.25
    # final probability of *ever* being delinquent
    p_bad = 0.04 + 0.30 * seasoning * (0.5 + risk)
    p_bad = min(p_bad, 0.75)
    if rng.random() > p_bad:
        return "current"
    # conditional on bad, split across buckets; deeper buckets need more seasoning
    r = rng.random()
    p_co = 0.20 * seasoning + 0.05          # charged off
    p_90 = 0.35 * seasoning + 0.15          # 90+
    if r < p_co:
        return "charged_off"
    if r < p_co + p_90:
        return "90+"
    return "30+"


def balance_for(rng, principal, status, age_q):
    """Outstanding balance <= principal. Amortises with age; charged-off freezes at a remaining
    balance; defaulted loans amortise less."""
    if status == "charged_off":
        frac = 0.35 + 0.40 * rng.random()      # froze with sizable balance
    elif status == "90+":
        frac = 0.45 + 0.35 * rng.random()
    elif status == "30+":
        frac = 0.40 + 0.40 * rng.random()
    else:
        # current: amortises down with age
        frac = max(0.05, 0.95 - 0.07 * age_q - 0.10 * rng.random())
    return round(principal * min(frac, 1.0), -2)  # round to nearest 100 THB


def main():
    rng = random.Random(SEED)
    with open(MASTER, encoding="utf-8") as f:
        branches = json.load(f)

    loans = []
    # per-branch end-of-window AUM accumulator (sum of current balances)
    branch_balance = {}
    branch_open = {}
    seq = 0

    # Iterate branches in stable order. Loan count scales with demand_decile.
    for branch in sorted(branches, key=lambda b: (b["code"], b.get("prov", ""))):
        code = branch["code"]
        open_date = synth_open_date(rng, branch)
        branch_open[code] = min(branch_open.get(code, open_date), open_date)
        dec = int(branch.get("demand_decile", 5) or 5)
        n_loans = 30 + dec * 12 + rng.randint(0, 20)   # ~42..170 loans/branch
        for _ in range(n_loans):
            seq += 1
            seg = weighted_choice(rng, SEGMENT_MIX)
            coll = weighted_choice(rng, COLLATERAL_MIX)
            orig_q = QUARTERS[rng.randint(0, len(QUARTERS) - 1)]
            age_q = quarter_age(orig_q)
            mean, spread = PRINCIPAL[coll]
            principal = max(3000, round(rng.gauss(mean, spread), -2))
            status = status_for(rng, seg, branch, age_q)
            balance = balance_for(rng, principal, status, age_q)
            balance = min(balance, principal)
            loans.append({
                "loan_id": f"SYNTH-{seq:07d}",
                "branch_id": code,
                "origination_quarter": orig_q,
                "segment": seg,
                "collateral_type": coll,
                "principal_thb": int(principal),
                "balance_thb": int(balance),
                "status": status,
                "opened_branch_date": branch_open[code],
            })
            branch_balance[code] = branch_balance.get(code, 0.0) + balance

    # Monthly AUM series: build a deterministic ramp per branch from open to end-of-window,
    # landing at the end-window balance computed above. Branches opening later start at 0.
    aum_rows = []
    for code in sorted(branch_balance):
        final_aum = branch_balance[code]
        open_m = branch_open[code][:7]  # YYYY-MM
        # find index where the branch is "live"
        for i, m in enumerate(AUM_MONTHS):
            if m < open_m:
                aum = 0.0
            else:
                # ramp: months since open / total live months, with a gentle S-ish curve
                live_total = sum(1 for mm in AUM_MONTHS if mm >= open_m)
                live_now = sum(1 for mm in AUM_MONTHS[: i + 1] if mm >= open_m)
                frac = live_now / max(live_total, 1)
                aum = final_aum * (0.15 + 0.85 * frac)
            aum_rows.append({"branch_id": code, "month": m, "aum_thb": int(round(aum, -2))})

    # Stable sort for byte-determinism
    loans.sort(key=lambda r: r["loan_id"])
    aum_rows.sort(key=lambda r: (r["branch_id"], r["month"]))

    tape = {
        "_meta": {
            "SYNTHETIC": True,
            "note": "SYNTHETIC loan tape — NOT real customer data. Generated by make_synthetic_tape.py.",
            "seed": SEED,
            "n_loans": len(loans),
            "n_branches": len(branch_balance),
            "schema": "pipeline/loan_tape_schema.md",
        },
        "loans": loans,
    }
    aum = {
        "_meta": {
            "SYNTHETIC": True,
            "note": "SYNTHETIC monthly branch AUM — NOT real. Generated by make_synthetic_tape.py.",
            "seed": SEED,
            "n_rows": len(aum_rows),
        },
        "series": aum_rows,
    }

    with open(OUT_TAPE, "w", encoding="utf-8") as f:
        json.dump(tape, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")
    with open(OUT_AUM, "w", encoding="utf-8") as f:
        json.dump(aum, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")

    print(f"SYNTHETIC tape: {len(loans)} loans across {len(branch_balance)} branches -> {OUT_TAPE}")
    print(f"SYNTHETIC AUM : {len(aum_rows)} rows -> {OUT_AUM}")


if __name__ == "__main__":
    main()
