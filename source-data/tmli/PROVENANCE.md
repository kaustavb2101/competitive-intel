# source-data/tmli/ — vendored MEASURED data.go.th datasets

These are **measured** Thai government datasets (NSO, NESDC, BOT) sourced through
data.go.th. They were pulled from a **Thai network** by the user's separate
**Thailand Macro Labor Intelligence (TMLI)** platform — the `kaustavb2101/watcher`
repo — and are vendored here verbatim because the competitive-intel sandbox is
blocked from data.go.th / DLT / NSO from its foreign IP.

Vendoring them lets `pipeline/ingest_tmli.py` emit clean province-keyed measured
layers into `source-data/` **with no desktop pull needed**, so the app can replace
ESTIMATED proxies with MEASURED data.

## Source
- repo: `kaustavb2101/watcher` (TMLI platform)
- commit (of `/workspace/watcher` at vendor time): `27172d4776dac905893e1d88942dc24f8339f3e4`
- These files are copies of `watcher/data/*` — unmodified.

## Files
> Most fields here are MEASURED. Two exceptions are called out explicitly below (not blanket-MEASURED):
> `household-debt.js`'s `debtToIncome`/`stressIndex` (2026-07-04 audit) and `provincial-gpp.js` (2026-07-02 audit).
| file | source authority | reference period (as stamped in the TMLI source) | drives |
|---|---|---|---|
| `household-debt.js` | **MIXED (corrected 2026-07-04 audit).** `debtPerHousehold`: NSO SES 2566 (debt/household, THB) — MEASURED, matches the co-vendored `nso-ses-debt-2566.json`. `debtToIncome`/`stressIndex`: attributed to "BOT Household Debt Regional Q4/2024" but **no CKAN/BOT resource id is cited anywhere in the file** — the values are grouped under hand-written narrative headers ("CENTRAL (High leverage)", "NORTHEASTERN (Agri-Stress Hubs)"...), the same fabrication smell caught in `provincial-gpp.js` below, and diverge 10-20x from the independently-computed ratio the app actually uses. **UNVERIFIED — treat as not-real; not consumed by any builder.** | NSO SES 2566 (2023 CE); BOT Q4/2024 (unverified); TMLI `updated_at` 2026-04-05 | `household_debt_by_province.json` (only `debt_per_household` is used downstream — `build_household_risk.py` recomputes its own `debt_to_income`) |
| `nso-ses-debt-2566.json` | NSO SES 2566 raw debt-per-household (THB) | 2566 B.E. (2023 CE) | (raw reference; superseded by household-debt.js corrected values) |
| `nso-ses-income-2566.json` | NSO SES 2566 monthly income by occupation (THB/month) | 2566 B.E. (2023 CE) | `household_income_by_province.json` |
| `nso-lfs-provincial-summary.json` | NSO Labour Force Survey provincial summary (thousands of persons) | ไตรมาสที่ 3/2568 (Q3/2025); TMLI downloaded 2026-03-29 | `unemployment_by_province.json` |
| `provincial-gpp.js` | NESDC Provincial Accounts (GPP, million THB; sector shares) | 2566 B.E. (2023 CE) NESDC estimate | `gpp_by_province.json` |
| `provinces.js` | TMLI province name map (Thai ⇄ English), matches competitive-intel canonical 77 | n/a (reference map) | English→Thai key normalization in ingest_tmli.py |

Dates above are carried from the TMLI source metadata. No wall-clock date is invented here.

## Notes
- DLT vehicles and NSO employment from TMLI were intentionally **not** bridged:
  competitive-intel's existing `vehicles_by_province.json` (vehicle *stock*, 44.3M,
  with car/pickup/moto/ev breakdown) and `employment_by_province.json` (formal/informal)
  are richer than TMLI's `dlt-vehicles.json` (vehicles *processed/registered* flow, 3.48M)
  and the National-only `nso-unemployment.js`. TMLI's LFS summary IS used, for provincial
  unemployment rate (which the existing layers lacked).
