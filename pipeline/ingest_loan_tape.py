#!/usr/bin/env python3
"""
ingest_loan_tape.py — validate a loan tape against the contract and compute the four turnkey
portfolio-risk outputs for AutoX / เงินไชโย.

Reads (defaults = the SYNTHETIC tape):
  --tape  source-data/loan_tape_synthetic.json        (or a real loan_tape.json)
  --aum   source-data/branch_aum_monthly_synthetic.json (or a real branch_aum_monthly.json)
  --real  : drop the SYNTHETIC stamp; treat inputs as a real measured export.
  --check : regenerate from the synthetic tape and assert the committed derived file is
            byte-for-byte identical (deterministic reproduce gate).

Writes:
  platform/data/loan_tape_derived.json

The four outputs (see pipeline/loan_tape_schema.md):
  (a) vintage / cohort 90+ aging curves by origination_quarter
  (b) per-branch ROI / payback proxy (AUM trajectory vs opened date)
  (c) concentration HHI by segment x collateral
  (d) calibration table: model proxies (agri_pd/merchant_pd/collateral_density) vs actual 90+ rate

Validation FAILS LOUDLY (non-zero exit) on schema problems. Honesty about provenance is mandatory:
the output carries a `meta.measured` flag and a `SYNTHETIC` flag.

Run from pipeline/:
    python3 make_synthetic_tape.py        # build the synthetic inputs first
    python3 ingest_loan_tape.py           # ingest synthetic -> derived
    python3 ingest_loan_tape.py --check   # deterministic reproduce gate
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
MASTER = os.path.join(ROOT, "source-data", "branches_final.json")
DEF_TAPE = os.path.join(ROOT, "source-data", "loan_tape_synthetic.json")
DEF_AUM = os.path.join(ROOT, "source-data", "branch_aum_monthly_synthetic.json")
OUT = os.path.join(ROOT, "platform", "data", "loan_tape_derived.json")

SEGMENTS = {"agri", "merchant", "collateral", "other"}
COLLATERAL = {"motorcycle", "car", "pickup", "gold", "land"}
STATUSES = {"current", "30+", "90+", "charged_off"}
STATUS_ORDER = {"current": 0, "30+": 1, "90+": 2, "charged_off": 3}
QUARTERS = [f"{y}Q{q}" for y in range(2018, 2031) for q in (1, 2, 3, 4)]
# A loan is "bad / 90+" for cohort and calibration purposes if it has reached 90+ or charged off.
BAD_STATUSES = {"90+", "charged_off"}

LOAN_REQUIRED = [
    "loan_id", "branch_id", "origination_quarter", "segment",
    "collateral_type", "principal_thb", "balance_thb", "status", "opened_branch_date",
]
AUM_REQUIRED = ["branch_id", "month", "aum_thb"]


class ValidationError(Exception):
    pass


def _load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _rows(obj, key):
    """Accept either a bare array or {_meta, <key>: [...]}."""
    if isinstance(obj, list):
        return obj, {}
    if isinstance(obj, dict) and key in obj:
        return obj[key], obj.get("_meta", {})
    raise ValidationError(f"expected a JSON array or an object with '{key}' list")


def validate(loans, aum_rows, master_codes):
    """Validate against the contract. Returns a dict of validation stats; raises on hard errors."""
    errors = []
    # ---- loan rows ----
    seen_ids = set()
    for i, r in enumerate(loans):
        for fld in LOAN_REQUIRED:
            if fld not in r:
                errors.append(f"loan[{i}] missing required field '{fld}'")
        if errors and len(errors) > 50:
            break
        if not errors:
            pass
        lid = r.get("loan_id")
        if lid in seen_ids:
            errors.append(f"loan[{i}] duplicate loan_id '{lid}'")
        seen_ids.add(lid)
        if r.get("segment") not in SEGMENTS:
            errors.append(f"loan[{i}] bad segment '{r.get('segment')}'")
        if r.get("collateral_type") not in COLLATERAL:
            errors.append(f"loan[{i}] bad collateral_type '{r.get('collateral_type')}'")
        if r.get("status") not in STATUSES:
            errors.append(f"loan[{i}] bad status '{r.get('status')}'")
        if r.get("origination_quarter") not in QUARTERS:
            errors.append(f"loan[{i}] bad origination_quarter '{r.get('origination_quarter')}'")
        p = r.get("principal_thb")
        b = r.get("balance_thb")
        if not isinstance(p, (int, float)) or p <= 0:
            errors.append(f"loan[{i}] principal_thb must be > 0 (got {p})")
        if not isinstance(b, (int, float)) or b < 0:
            errors.append(f"loan[{i}] balance_thb must be >= 0 (got {b})")
        if isinstance(p, (int, float)) and isinstance(b, (int, float)) and b > p + 0.5:
            errors.append(f"loan[{i}] balance_thb ({b}) > principal_thb ({p})")
        od = r.get("opened_branch_date", "")
        if not (isinstance(od, str) and len(od) == 10 and od[4] == "-" and od[7] == "-"):
            errors.append(f"loan[{i}] opened_branch_date must be YYYY-MM-DD (got '{od}')")
        if len(errors) > 50:
            errors.append("... (truncated)")
            break

    # ---- aum rows ----
    for i, r in enumerate(aum_rows):
        for fld in AUM_REQUIRED:
            if fld not in r:
                errors.append(f"aum[{i}] missing required field '{fld}'")
        m = r.get("month", "")
        if not (isinstance(m, str) and len(m) == 7 and m[4] == "-"):
            errors.append(f"aum[{i}] month must be YYYY-MM (got '{m}')")
        a = r.get("aum_thb")
        if not isinstance(a, (int, float)) or a < 0:
            errors.append(f"aum[{i}] aum_thb must be >= 0 (got {a})")
        if len(errors) > 80:
            errors.append("... (truncated)")
            break

    if errors:
        raise ValidationError(
            "Loan tape FAILED validation:\n  - " + "\n  - ".join(errors[:80])
        )

    # ---- join-rate (warn-level, reported not raised) ----
    tape_codes = {r["branch_id"] for r in loans}
    matched = tape_codes & master_codes
    unmatched = sorted(tape_codes - master_codes)
    join_rate = round(100.0 * len(matched) / max(len(tape_codes), 1), 2)

    aum_codes = {r["branch_id"] for r in aum_rows}
    aum_unmatched = sorted(aum_codes - master_codes)

    return {
        "n_loans": len(loans),
        "n_aum_rows": len(aum_rows),
        "n_tape_branches": len(tape_codes),
        "branch_join_rate_pct": join_rate,
        "unmatched_branch_ids": unmatched[:50],
        "n_unmatched_branch_ids": len(unmatched),
        "aum_unmatched_branch_ids": aum_unmatched[:50],
    }


# ----------------------- the four outputs -----------------------

def cohort_aging(loans):
    """(a) Vintage 90+ aging curves. For each origination_quarter cohort, the cumulative
    90+ (=90+/charged_off) rate, alongside how seasoned the cohort is. Single-snapshot tape =>
    we report the *current* 90+ rate per cohort; as cohorts age the rate rises (the aging curve)."""
    by_q = {}
    for r in loans:
        q = r["origination_quarter"]
        d = by_q.setdefault(q, {"n": 0, "bad": 0, "principal": 0.0, "bad_principal": 0.0})
        d["n"] += 1
        d["principal"] += r["principal_thb"]
        if r["status"] in BAD_STATUSES:
            d["bad"] += 1
            d["bad_principal"] += r["principal_thb"]
    out = []
    present = [q for q in QUARTERS if q in by_q]
    latest = present[-1] if present else None
    for q in present:
        d = by_q[q]
        age = QUARTERS.index(latest) - QUARTERS.index(q) if latest else 0
        out.append({
            "origination_quarter": q,
            "age_quarters": age,
            "n_loans": d["n"],
            "rate_90plus_pct": round(100.0 * d["bad"] / d["n"], 2) if d["n"] else 0.0,
            "rate_90plus_by_principal_pct": round(100.0 * d["bad_principal"] / d["principal"], 2) if d["principal"] else 0.0,
        })
    return out


def branch_roi(loans, aum_rows, master_by_code):
    """(b) Per-branch ROI / payback proxy. Uses the monthly AUM series vs the branch open date:
    months since open, latest AUM, peak AUM, and a simple payback proxy = months to reach 50%
    of the branch's peak AUM (a 'scale-up speed' read). No cost data in the tape, so this is a
    *proxy*, clearly labelled."""
    # group aum by branch, sorted by month
    by_branch = {}
    for r in aum_rows:
        by_branch.setdefault(r["branch_id"], []).append((r["month"], r["aum_thb"]))
    # open date per branch from loans
    open_by_branch = {}
    for r in loans:
        open_by_branch.setdefault(r["branch_id"], r["opened_branch_date"])

    out = []
    for code in sorted(by_branch):
        series = sorted(by_branch[code])
        months = [m for m, _ in series]
        vals = [v for _, v in series]
        peak = max(vals) if vals else 0
        latest = vals[-1] if vals else 0
        first_month = months[0] if months else None
        last_month = months[-1] if months else None
        open_date = open_by_branch.get(code)
        open_m = open_date[:7] if open_date else None
        # months since open within the observed window
        months_since_open = None
        if open_m and last_month:
            live = [m for m in months if m >= open_m]
            months_since_open = len(live)
        # payback proxy: first month index (from open) where AUM >= 50% of peak
        payback_months = None
        if peak > 0 and open_m:
            half = 0.5 * peak
            live = [(m, v) for m, v in series if m >= open_m]
            for idx, (m, v) in enumerate(live):
                if v >= half:
                    payback_months = idx
                    break
        out.append({
            "branch_id": code,
            "region": (master_by_code.get(code) or {}).get("region"),
            "prov": (master_by_code.get(code) or {}).get("prov"),
            "open_date": open_date,
            "months_observed": len(series),
            "months_since_open": months_since_open,
            "latest_aum_thb": int(latest),
            "peak_aum_thb": int(peak),
            "ramp_to_half_peak_months": payback_months,
        })
    return out


def concentration_hhi(loans):
    """(c) Concentration HHI by segment x collateral, weighted by current balance. HHI in [0,1]:
    sum of squared market shares. Also returns the share table for transparency."""
    cells = {}
    total = 0.0
    seg_tot = {}
    coll_tot = {}
    for r in loans:
        w = r["balance_thb"]
        key = (r["segment"], r["collateral_type"])
        cells[key] = cells.get(key, 0.0) + w
        total += w
        seg_tot[r["segment"]] = seg_tot.get(r["segment"], 0.0) + w
        coll_tot[r["collateral_type"]] = coll_tot.get(r["collateral_type"], 0.0) + w

    def hhi(d, tot):
        if tot <= 0:
            return 0.0
        return round(sum((v / tot) ** 2 for v in d.values()), 4)

    shares = []
    for (seg, coll) in sorted(cells):
        v = cells[(seg, coll)]
        shares.append({
            "segment": seg, "collateral_type": coll,
            "balance_thb": int(v),
            "share_pct": round(100.0 * v / total, 2) if total else 0.0,
        })
    return {
        "hhi_segment_x_collateral": hhi(cells, total),
        "hhi_by_segment": hhi(seg_tot, total),
        "hhi_by_collateral": hhi(coll_tot, total),
        "interpretation": "HHI in [0,1]; higher = more concentrated. ~0.10 diversified, >0.25 concentrated.",
        "shares": shares,
    }


def calibration_table(loans, master_by_code):
    """(d) Calibration stub: per branch, join our model proxies to the ACTUAL 90+ rate from the
    tape. When real data lands this is the proxy-vs-reality scoreboard. Also rolls up by proxy
    decile so the relationship is readable at a glance."""
    by_branch = {}
    for r in loans:
        code = r["branch_id"]
        d = by_branch.setdefault(code, {"n": 0, "bad": 0})
        d["n"] += 1
        if r["status"] in BAD_STATUSES:
            d["bad"] += 1
    rows = []
    for code in sorted(by_branch):
        d = by_branch[code]
        m = master_by_code.get(code) or {}
        actual = round(100.0 * d["bad"] / d["n"], 2) if d["n"] else 0.0
        rows.append({
            "branch_id": code,
            "region": m.get("region"),
            "n_loans": d["n"],
            "actual_90plus_pct": actual,
            "proxy_agri_pd": m.get("agri_pd"),
            "proxy_merchant_pd": m.get("merchant_pd"),
            "proxy_collateral_density": m.get("collateral_density"),
        })
    # decile rollup on agri_pd proxy vs actual (Spearman-ish readability)
    have = [r for r in rows if isinstance(r["proxy_agri_pd"], (int, float))]
    have.sort(key=lambda r: r["proxy_agri_pd"])
    buckets = []
    if have:
        n = len(have)
        for d in range(10):
            lo = d * n // 10
            hi = (d + 1) * n // 10
            chunk = have[lo:hi]
            if not chunk:
                continue
            buckets.append({
                "decile": d + 1,
                "n_branches": len(chunk),
                "avg_proxy_agri_pd": round(sum(c["proxy_agri_pd"] for c in chunk) / len(chunk), 2),
                "avg_actual_90plus_pct": round(sum(c["actual_90plus_pct"] for c in chunk) / len(chunk), 2),
            })
    return {
        "note": "Joins model proxies to ACTUAL 90+ per branch. Compare avg_proxy vs avg_actual per decile.",
        "by_agri_pd_decile": buckets,
        "per_branch": rows,
    }


def build(loans, aum_rows, master, real):
    master_by_code = {}
    for b in master:
        master_by_code.setdefault(b["code"], b)  # first wins for dup codes
    master_codes = set(master_by_code)
    stats = validate(loans, aum_rows, master_codes)

    synthetic = (not real) and any(
        str(r.get("loan_id", "")).startswith("SYNTH-") for r in loans[:5]
    )
    derived = {
        "meta": {
            "SYNTHETIC": bool(synthetic),
            "measured": bool(real),
            "provenance": ("MEASURED real loan tape" if real else
                           "SYNTHETIC placeholder — NOT real customer data. Replace with a real export."),
            "schema": "pipeline/loan_tape_schema.md",
            "generated_by": "pipeline/ingest_loan_tape.py",
            "validation": stats,
        },
        "cohort_aging_90plus": cohort_aging(loans),
        "branch_roi_proxy": branch_roi(loans, aum_rows, master_by_code),
        "concentration": concentration_hhi(loans),
        "calibration": calibration_table(loans, master_by_code),
    }
    return derived, stats


def serialize(derived):
    return json.dumps(derived, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def main():
    ap = argparse.ArgumentParser(description="Validate + derive the AutoX loan tape.")
    ap.add_argument("--tape", default=DEF_TAPE)
    ap.add_argument("--aum", default=DEF_AUM)
    ap.add_argument("--real", action="store_true", help="treat inputs as a real measured export")
    ap.add_argument("--check", action="store_true",
                    help="reproduce from the synthetic tape and assert byte-identical to committed output")
    args = ap.parse_args()

    master = _load(MASTER)

    if args.check:
        # always check against the synthetic defaults
        loans, _ = _rows(_load(DEF_TAPE), "loans")
        aum_rows, _ = _rows(_load(DEF_AUM), "series")
        derived, _ = build(loans, aum_rows, master, real=False)
        fresh = serialize(derived)
        if not os.path.exists(OUT):
            print("CHECK FAILED: committed output does not exist:", OUT)
            sys.exit(1)
        with open(OUT, encoding="utf-8") as f:
            committed = f.read()
        if fresh != committed:
            print("CHECK FAILED: regenerated derived output differs from committed file.")
            sys.exit(1)
        print("CHECK OK: derived output byte-reproduces from the synthetic tape.")
        return

    try:
        loans, _ = _rows(_load(args.tape), "loans")
        aum_rows, _ = _rows(_load(args.aum), "series")
        derived, stats = build(loans, aum_rows, master, real=args.real)
    except ValidationError as e:
        print(str(e))
        sys.exit(2)

    with open(OUT, "w", encoding="utf-8") as f:
        f.write(serialize(derived))

    prov = "MEASURED" if args.real else "SYNTHETIC"
    print(f"[{prov}] ingested {stats['n_loans']} loans, {stats['n_aum_rows']} AUM rows.")
    print(f"  branch join-rate: {stats['branch_join_rate_pct']}% "
          f"({stats['n_unmatched_branch_ids']} unmatched ids)")
    print(f"  HHI seg x coll : {derived['concentration']['hhi_segment_x_collateral']}")
    print(f"  cohorts        : {len(derived['cohort_aging_90plus'])}")
    print(f"  wrote -> {OUT}")


if __name__ == "__main__":
    main()
