# Blocked-source ledger — what CI can and cannot pull

> **Why this file exists.** The integration loop repeatedly rediscovers the same wall: the highest-value
> data unlocks left are all gated behind a network block or a missing key, so run after run burns its
> whole budget re-probing the same hosts before concluding "blocked, skip, log". This ledger captures
> that knowledge **with live HTTP evidence** so a future run (or Kaustav) can read the state in seconds
> instead of re-deriving it. It is the honest companion to `docs/DATAGOTH_CATALOG.md` (which lists what
> _was_ pulled from a Thai IP) — this file lists what **cannot** be pulled from CI **now**, and the exact
> owner-side action that unblocks each.
>
> **Provenance of the evidence below:** every status code was measured live from this GitHub-Actions /
> cloud sandbox on the date stamped. Re-verify any row in one paste with the probe block at the bottom —
> a `403`/`000` that flips to `200` means the block lifted and the integration is now doable.

_Last probed: **2026-09-10** (from the autonomous integration loop's network policy). Prior probe
2026-09-05 (from the cloud runner). Every `403`/`000` status below is **unchanged** since (nothing
flipped open, so no integration became CI-doable). The one refinement this pass (2026-09-10):
**`openapi.dbd.go.th` (DBD company-formation) returns `403` from a cloud IP** — measured on the exact
committed CSV (`.../registration/99_202606_1.csv`, the 2026-06 snapshot the app ships) and the two
newer months (`_202607_`, `_202608_`), **with and without a browser User-Agent**. So DBD is an
application-layer Cloudflare geo-block like the `data.go.th` aggregator, **not** a CI-reachable
department CKAN — its committed layer came from the Thai-IP pull (DATAGOTH_CATALOG: "pulled 2026-07-12
from a Bangkok IP"), and it was mis-grouped under "reachable from CI" below. Corrected in the summary +
a new frontier row. Also re-confirmed 2026-09-10: **MOT `datagov.mot.go.th` `200` but its cumulative
registry still tops out at BE 2568 (2025)** = the committed `vehicle_registry.json` vintage, so a
re-pull is byte-identical (do not "refresh" it). Prior refinement (2026-09-05): **NSO's own CKAN
`catalog.nso.go.th` is CI-reachable (`200`)** — reachable but **its household-debt vintage is staler
than what the app already ships** (so it is reachable but not a refresh source — see that note).
Earlier refinement (2026-09-04): the GISTDA row was probing the *landing* host, not the API host the
puller actually calls._

## The one-screen summary

- **Everything reachable from CI is already integrated.** DIW factories, DLT/MOT vehicles, NABC
  farm-gate prices, Overture/OSM, World Bank, ILOSTAT labour context, NSO SES/LFS (vendored) — all
  distilled into committed, `--check`-gated, provenance-stamped layers. See `docs/AUTONOMY_PLAN.md`
  (0 open) and `docs/DATAGOTH_CATALOG.md`. **NB (corrected 2026-09-10):** DBD company-formation and the
  FPO PICO competitor registry are integrated too, but they came from **Thai-IP pulls**, not CI —
  `openapi.dbd.go.th` is `403` from a cloud IP (re-probed 2026-09-10, see the DBD frontier row), and
  `fpo_pico.csv` is a gitignored Thai-IP pull (`build_pico_census.py` SKIP-passes when it is absent).
  Both refresh owner-side, not from this loop.
- **What's left is blocked, and the blocks are owner-side, not code-side.** No amount of CI work opens
  them; they need Kaustav's Thai residential IP, a real core-banking export, or a secret wired into the
  workflow env. They are listed below, most-valuable first.

## Blocked frontier sources (re-measured 2026-09-04; unchanged vs 2026-07-17 except the GISTDA host refinement)

| Source | Signal (objective) | Host probed | Status | Why blocked | Owner-side unblock |
|---|---|---|---|---|---|
| ~~**Real loan tape**~~ | vintage 90+ aging, branch ROI, PD calibration — **direct portfolio risk (#1)** | (core banking export, no host) | ✅ **UNBLOCKED 2026-07-21** | — | **DONE.** 382,735 real accounts landed via `ingest_real_tape.py` → `build_tape_layers.py` → `tape_real.json` + `tape_geo_occ.json`. This row is kept struck-through rather than deleted because it was named "the single highest-leverage unlock left" for months and its absence would read as an oversight. The open question is now refresh **cadence**, not existence. |
| **BAAC personal credit** by province | formal-credit **penetration** (inverse of title-loan demand, #1) | `data.go.th/api/3/action/package_show?id=baac02_2567` | **403** | data.go.th **aggregator** is Cloudflare geo-blocked to datacenter IPs. BAAC's own host (`catalog.baac.or.th`) is unreachable (`000`). Pulled once from a Bangkok IP 2026-07-12 (21 KB) but the raw cache is gitignored + **never distilled**, so nothing is committed and it cannot be rebuilt from CI. | Re-pull `baac_credit` via `pull_datagoth.py` from the Thai laptop, **commit the raw CSV** (or a distilled `baac_credit_by_province.json`), then a CI builder can distill it deterministically. |
| **SME-bank credit** outstanding by province | SME formal-credit penetration (#1) | `data.go.th/api/3/action/package_show?id=smedbank-outprovince` | **403** | Same aggregator geo-block; `opendata.smebank.co.th` unreachable (`000`). Same never-distilled state as BAAC. | Same as BAAC — Thai-IP pull + commit, then distill. |
| **GISTDA 40m satellite crop-area** | measured per-branch crop-area to **supersede the SPAM baseline** in `build_branch_cropland.py` (#1) | `api.sphere.gistda.or.th` (API host, what the puller calls); `sphere.gistda.or.th` (landing) | API host **000**; landing intermittent (**200/000**); **`GISTDA_SPHERE_KEY` still absent** | **Doubly blocked (2026-09-04).** The check-crop / isochrone **API host `api.sphere.gistda.or.th` is unreachable from CI (`000`, stable across re-probes)**, *and* the repo secret is not mapped into this run's env. NB: the 2026-07-17 "host **200**, reachable" read probed the *landing* page `sphere.gistda.or.th` (intermittent), not the API host — corrected here so a future run doesn't chase a CI path that dies at the host. | Run the puller from Kaustav's Thai machine (which reaches `api.sphere.gistda.or.th` directly), **and** map `GISTDA_SPHERE_KEY` into the env. Mapping the key alone will **not** unblock CI while the API host returns `000`. |
| **NESDC GPP** per province | economic vitality backdrop (#1) — currently ⚠ ESTIMATED (only 1/77 CKAN-verified, see NEXT_STEPS §0a) | `opendata.nesdc.go.th` | host **200**, but **no clean dataset** | The reachable `opendata.nesdc.go.th` is a government-wide **project** catalog; a keyword search (`GPP`, `ผลิตภัณฑ์มวลรวมจังหวัด`) returns 0 relevant datastores. GPP is published as Excel/PDF SNA tables on `www.nesdc.go.th`, not as a CKAN datastore. | Obtain the per-province GPP SNA table (Excel) and vendor it into `source-data/`, then a builder can replace the estimated `gpp_by_province.json`. Do **not** ship the current estimated file labelled MEASURED. |
| **Excise vehicle-tax** collections | motorcycle/car-sales proxy = collateral flow (#1) | `catalog.excise.go.th` | **000** | Host unreachable from CI (connection failure, not just geo-403). The vehicle **stock** signal is already covered by the committed DLT/MOT layers, so this is a nice-to-have, not a gap. | Thai-IP pull via `pull_datagoth.py --only excise_moto_tax excise_car_tax`, commit + distill. |
| **DBD company-formation** (newer month) | new-firm + capital formation = business-demand backdrop (both objectives) | `openapi.dbd.go.th/juristic_person/registration/99_YYYYMM_1.csv` | **403** | Application-layer Cloudflare geo-block to datacenter IPs (re-probed 2026-09-10 on the committed `202606` file and the newer `202607`/`202608` months, with and without a browser UA — all `403`). Despite the ledger's earlier "reachable from CI" grouping, DBD's own host is **not** CI-reachable; the committed `dbd_formation.json` (2026-06) came from the 2026-07-12 Thai-IP pull. The layer is integrated and only ~3 months stale, so a refresh is a nice-to-have, not a gap. | Thai-IP pull via `pull_datagoth.py --only dbd_newco` for the newer month, then `build_dbd_formation.py` distils it deterministically (already `--check`-gated). **Recheck trigger:** `99_202607_1.csv` (or later) returning `200` from a cloud IP flips this back to CI-doable. |
| **data.go.th aggregator** (general) | ~30 dataset families | `data.go.th/api/3/action/*` | **403** | Cloudflare geo-block to datacenter IPs. Department **own** CKANs (DIW, MOT) are the CI-reachable path and are already used. | Thai-IP pull for any family without a reachable department mirror. |
| **DLT own host** | vehicle registrations by district | `gdcatalog.dlt.go.th` | unreachable | Documented in `DATAGOTH_CATALOG.md`; MOT (`datagov.mot.go.th`, **200**) is the working substitute and is already distilled. | None needed — MOT substitute is live. |

## Reachable from CI (for contrast — all already integrated)

`datagov.mot.go.th` (200), `catalog.oae.go.th`, `agriapi.nabc.go.th`, `thedocs.worldbank.org`,
`stats.bis.org`, the Overpass mirror, DIW `diw-dataset.diw.go.th`, `catalog.nso.go.th` (200 — see the
NSO note directly below), and the department CKANs behind the committed vehicle/factory layers.
(**Not** DBD or PICO — those are Thai-IP pulls; see the corrected NB in the one-screen summary and the
DBD frontier row.) If a new run wants to _refresh_ these, note that most already have a scheduled
workflow (NABC prices, fuel prices) — check `.github/workflows/` before pulling by hand.

**NSO own CKAN `catalog.nso.go.th` — reachable from CI. ✅ RECHECK TRIGGER MET & ACTED ON
2026-09-12: household debt now pulls the authoritative SES-2566 per-province table from CI, and
doing so exposed that the vendored file it replaced was WRONG for 73 of 77 provinces.** NSO's own
catalog returns real JSON (`success:true`) exactly like the DIW/MOT department CKANs — the
"geo-blocked, Thai-IP-only" framing applied only to the `data.go.th` **aggregator**. The 2026-09-05
note said package `0705_08_0009` (`หนี้สินเฉลี่ยต่อครัวเรือน`) topped out at survey year **2564
(2021)**; since then NSO added two **SES 2566 (2023)** per-province resources (both `created`
2026-02-27): **`SFD_SPB0806`** (all households, resource id `89cc71ae-f596-4307-b38f-10d61d084801`)
and `SFD_SPB0807` (indebted-only). That is exactly the documented trigger, so it is now CI-doable.
- **`pipeline/pull_nso_ses_debt.py`** pulls `SFD_SPB0806` and reconstructs each province's average
  household debt (household-weighted mean over the 10 socioeconomic strata — the table has no
  pre-aggregated "all households" row). Its built-in correctness proof: the national weighted mean
  it produces is **197,255 THB, exactly NSO's published SES-2566 national headline**; the puller
  refuses to write if that drifts. Output committed to `source-data/nso_ses_debt_2566.json`.
- **`build_household_risk.py`** now consumes that authoritative layer (vendored file kept as a
  graceful-degrade fallback). This is the debt input to the `hhdti` / `pstress` National-map risk
  lenses and the whole province risk ranking.
- **The finding that made this more than a refresh:** the prior debt source
  (`source-data/household_debt_by_province.json`, TMLI-vendored) *claimed* in its own meta to be
  "MEASURED (NSO SES 2566), matches nso-ses-debt-2566.json". Audited against the authoritative CKAN,
  only **4 / 77** provinces matched; the rest diverged up to ~4.5x (Khon Kaen shipped 280,791 vs the
  authoritative 62,884; Bangkok 88,856 vs 161,050), and the two vendored files did not agree with each
  other either. So the shipped household-DTI risk ranking was materially wrong (75/77 provinces
  changed rank; the most-stressed province flipped from Khon Kaen to Amnat Charoen; Phuket rose #67→#5).
- **Income is now fixed too (2026-09-12).** The DTI denominator no longer uses the vendored
  `household_income_by_province.json` — whose `avg_monthly_income` was not a household income at all
  but an UNWEIGHTED mean across five occupation rows. `pipeline/pull_nso_ses_income.py` pulls the
  authoritative per-province average monthly household income from NSO's own CKAN (package
  `0705_08_0007`, table `SFD_SPB0802_66`, the income sibling of the debt package), reconstructs the
  province average by the SAME household-weighted method as the debt puller (weighting each
  socioeconomic leaf's total monthly income by that leaf's household count from `SFD_SPB0806`), and
  commits `source-data/nso_ses_income_2566.json`. Its built-in correctness proof: the national
  household-weighted mean it reconstructs is **29,030 THB/month, exactly NSO's published SES-2566
  national headline**; the puller refuses to write if that drifts. `build_household_risk.py` now
  consumes it (no vendored fallback, same discipline as the debt side). The correction re-ranked
  **67 of 77 provinces** on DTI and flipped the most-stressed province (Amnat Charoen → Surin);
  e.g. Sisaket's income was overstated 1.29x by the occupation mean (25,597 vs the authoritative
  19,858), hiding a DTI that is actually ~1.0. The vendored income file is retained only for the
  occupation-level income breakdowns that still legitimately read it (agri/factory/SME/occupation
  income builders). **Residual follow-up (lower priority):** the province-card `avg_monthly_income`
  surfaced by `build_province.py` / `build_regions.py` / `province.html` still shows the vendored
  occupation mean, not the authoritative household-weighted figure — a separate, larger rewire.

## Re-verify in one paste

```bash
for u in \
  "https://data.go.th/api/3/action/package_show?id=baac02_2567" \
  "https://data.go.th/api/3/action/package_show?id=smedbank-outprovince" \
  "https://catalog.excise.go.th/api/3/action/datastore_search?resource_id=a8d9115a-708d-420d-b796-e96b373ad1b8&limit=1" \
  "https://api.sphere.gistda.or.th/services/route/isochrone" \
  "https://opendata.nesdc.go.th/api/3/action/package_search?q=GPP&rows=1" \
  "https://openapi.dbd.go.th/juristic_person/registration/99_202607_1.csv" \
  "https://catalog.nso.go.th/api/3/action/package_show?id=0705_08_0009" \
  "https://datagov.mot.go.th/api/3/action/package_search?q=test&rows=1" ; do
  echo "$(curl -s -o /dev/null -w '%{http_code}' -m 8 -A 'Mozilla/5.0' "$u")  $u"
done
[ -n "$GISTDA_SPHERE_KEY" ] && echo "GISTDA key: present" || echo "GISTDA key: absent"
```

A row that flips `403`/`000` → `200` (or the GISTDA key appearing) means that integration is now doable
from CI — pick it up.
