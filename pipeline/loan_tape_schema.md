# Loan Tape Schema — the privacy-safe contract for AutoX / เงินไชโย

> **What this is.** The exact, minimal, **no-PII** data contract Kaustav exports from core banking
> so this platform can light up vintage cohorts, PD calibration, branch ROI, and concentration.
> Until a real export lands, the pipeline runs on a **clearly-labelled SYNTHETIC** tape so the
> machinery is proven and the value realizes the moment real data arrives.
>
> **Lead with the answer:** export two files (loans + a monthly branch-AUM series), no customer
> identities, join on the branch code we already use. Validate with one command (bottom of this doc).

---

## Why no PII
This is loan-portfolio *intelligence*, not servicing. We never need to know **who** a borrower is to
answer "which segments/collateral are getting riskier" or "which branches earn back their cost". So:

- **No names, no national ID, no phone, no address, no account number, no birth date.**
- `loan_id` is an **opaque** surrogate key (e.g. a salted hash or a sequential export key). It must be
  stable across exports (so we can track a loan over time) but must **not** be reversible to a customer
  or reused for another loan. It is the only per-loan identifier and it identifies a *loan*, not a person.
- Everything is aggregatable to branch × quarter × segment × collateral. That is all the platform reads.

This keeps the export safe to email/upload and clean for the **2027 IPO audit trail** — every number on
the platform is reproducible from these two files plus our branch master.

---

## File 1 — `loan_tape.json` : one row per loan

A JSON array of objects. One object = one loan. Required fields, exact names:

| field                | type    | required | description / rule |
|----------------------|---------|----------|--------------------|
| `loan_id`            | string  | yes      | Opaque, stable, unique per loan. No PII. (e.g. `"L0000001"` or a hash.) |
| `branch_id`          | string  | yes      | The originating branch. **Must equal our branch master `code`** (e.g. `"@chaiyo30415"`). See *Branch mapping* below. |
| `origination_quarter`| string  | yes      | Quarter the loan was booked, `YYYYQn` (e.g. `"2024Q3"`). `n` ∈ {1,2,3,4}. |
| `segment`            | string  | yes      | Enum: `agri` \| `merchant` \| `collateral` \| `other`. The credit segment we score. |
| `collateral_type`    | string  | yes      | Enum: `motorcycle` \| `car` \| `pickup` \| `gold` \| `land`. |
| `principal_thb`      | number  | yes      | Original disbursed principal, THB. > 0. |
| `balance_thb`        | number  | yes      | Current outstanding balance, THB. ≥ 0 and ≤ `principal_thb`. For `charged_off` this is the balance at charge-off. |
| `status`             | string  | yes      | Enum: `current` \| `30+` \| `90+` \| `charged_off`. Delinquency bucket (see *Status* below). |
| `opened_branch_date` | string  | yes      | The **branch's** opening date `YYYY-MM-DD` (or first-disbursement date for that branch). Same value for every loan at a branch. Used for branch ROI/payback. |

Notes:
- **Status semantics (worst-ever vs current).** We treat `status` as the loan's **current** delinquency
  bucket, ordered `current < 30+ < 90+ < charged_off`. The ingest does a *monotonicity sanity* check
  across exports only if `loan_id` is stable: a loan should not move from `charged_off` back to `current`.
  Within a single tape we just validate the enum.
- **`balance_thb ≤ principal_thb`** is enforced. If your core system can show balance > principal (capitalised
  fees/interest), cap it or add a note — the platform assumes amortising title loans.
- Extra fields are ignored (forward-compatible), but **do not add PII**.

### Minimal example row
```json
{
  "loan_id": "L0000001",
  "branch_id": "@chaiyo30415",
  "origination_quarter": "2024Q3",
  "segment": "collateral",
  "collateral_type": "motorcycle",
  "principal_thb": 42000,
  "balance_thb": 31500,
  "status": "current",
  "opened_branch_date": "2019-04-01"
}
```

---

## File 2 — `branch_aum_monthly.json` : monthly AUM per branch

A JSON array of objects. One object = one (branch, month). This is the time series behind branch ROI /
payback. Keep it separate from the loan file so it stays small and is easy to refresh monthly.

| field         | type   | required | description / rule |
|---------------|--------|----------|--------------------|
| `branch_id`   | string | yes      | Our branch master `code`. |
| `month`       | string | yes      | `YYYY-MM` (e.g. `"2025-06"`). |
| `aum_thb`     | number | yes      | Total outstanding loan balance booked at that branch at month-end, THB. ≥ 0. |

### Minimal example row
```json
{ "branch_id": "@chaiyo30415", "month": "2025-06", "aum_thb": 18450000 }
```

---

## Branch mapping (the join)
- Our branch master is `source-data/branches_final.json`; the join key is the **`code`** field, e.g.
  `@chaiyo30415`. There are **2,015 branches** (2,013 distinct codes — two codes legitimately repeat at
  different locations; for those the loan rolls up to the code, which is acceptable for portfolio rollups).
- `branch_id` in **both** files must be one of those `code` values, verbatim (including the leading `@`).
- The ingest reports the **join-rate** (% of tape `branch_id`s found in the master). Real data should be
  ~100%. Any unmatched ids are listed so a mapping fix is obvious. If core banking uses a different
  internal branch key, supply a one-time `branch_id → code` crosswalk and we'll add a remap step.

## Date / format conventions
- Quarters: `YYYYQn` (`2024Q3`). Months: `YYYY-MM` (`2025-06`). Dates: `YYYY-MM-DD` (`2019-04-01`).
- All money in **THB**, plain numbers (no commas, no ฿ symbol, no thousands separators).
- All files **UTF-8 JSON arrays**. (CSV with the same columns is fine too — tell us and we add a reader.)

## Data-handling note (for the export operator)
1. Strip every PII column **at the source query** — do not export then delete. The platform should never
   receive a name/ID/phone/address.
2. `loan_id` must be a surrogate (hash or export sequence), **not** the customer account number.
3. Treat the export as **internal-confidential**: it is portfolio data, even without PII.
4. Keep the export reproducible (same query → same numbers) so IPO auditors can re-derive every chart.
5. Mark the export with its as-of date; the platform stamps everything `measured` only once a **real**
   tape replaces the synthetic one (until then every derived number is stamped `SYNTHETIC`).

---

## What the platform computes from this (the four turnkey outputs)
Written to `platform/data/loan_tape_derived.json` by `ingest_loan_tape.py`:
1. **Vintage / cohort 90+ aging curves** by `origination_quarter` — cumulative 90+ rate as cohorts age.
2. **Per-branch ROI / payback proxy** — AUM trajectory vs `opened_branch_date` (months to AUM scale).
3. **Concentration HHI** by `segment × collateral` — portfolio concentration in [0,1].
4. **Calibration table** — joins our model proxies (`agri_pd`, `merchant_pd`, `collateral_density`) to the
   **actual** 90+ rate per branch, so you can see proxy-vs-reality once real data lands.

---

## Validating a REAL tape — the one command
When Kaustav has a real export, drop the two files in `source-data/` as
`loan_tape.json` and `branch_aum_monthly.json`, then run **from `pipeline/`**:

```bash
python3 ingest_loan_tape.py --tape ../source-data/loan_tape.json \
                            --aum  ../source-data/branch_aum_monthly.json \
                            --real
```

- It validates the schema (required fields, enums, ranges, join-rate, status sanity), **fails loudly**
  on problems, and on success writes `platform/data/loan_tape_derived.json` stamped `measured` (not
  `SYNTHETIC`). Drop `--real` (or run with no args) to regenerate from the synthetic tape instead.
