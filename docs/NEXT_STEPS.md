# NEXT STEPS — prioritized backlog

Ordered by value × unblocked-ness. Each has a concrete first action so Claude Code can just start.
**For the exact Thai-laptop pulls (copy-pasteable), see `docs/TONIGHT_CHECKLIST.md`.**

## 0. GISTDA repeated-flooding — ✅ SHIPPED (MAX-freq hazard flag, 2026-08-02); area still needs a dissolve (objective #1)
**DONE (the defensible part):** `pull_flood_hazard.py` pulls the server-side MAX(flood_freq) per
district and `build_flood_hazard.py` (deterministic, `--check`-gated) projects it into
`platform/data/flood_hazard.json` — a per-district & per-branch repeated-flood-hazard flag
(count of the 12 years 2005-2016 the ground flooded, 1-12). 838 flood-affected districts, 825
joined onto `amphoe.json` (13 unresolved, all zero-branch — asserted at build time); 1,848/2,015
branches sit in a repeat-flood district, 685 in a CHRONIC one (≥7/12 yrs). Surfaced as a MEASURED
branch-popup line on `#map`, censused in `provenance.json`. NO area is claimed (see the trap below).
The remaining open work is purely the flooded-AREA number, which still needs a geometry dissolve.

Probed 2026-08-01. GISTDA's ArcGIS server is **open from this machine, no key**:
`https://gistdaportal.gistda.or.th/data/rest/services?f=json` lists ~40 folders (FL_Flood, GFlood,
FR_Fire hotspots + air quality, GWater, Industrial, EEC...).

The one worth having is a **FeatureServer**, so it can be aggregated server-side with no geometry
download:

    FL_Flood/FL_RepeatedFlooding_GISTDA_50k_Y2005_Y2016/FeatureServer/0

It carries `flood_freq` (how many of the 12 years that ground flooded), `area_rai`, and full
admin keys — `pv_tn`/`pv_code`, `ap_tn`/`ap_code`, `tb_tn`/`tb_code` — so it joins straight onto
`amphoe.json`'s 928 districts. `supportsStatistics: true`; a `groupByFieldsForStatistics=pv_tn`
query returns all 75 flood-affected provinces in one call.

**THE TRAP — do not skip this.** `area_rai` is genuinely each polygon's own area
(`area_m / 1600` checks out exactly), but the polygons **OVERLAP**: they appear to be per-event,
not dissolved by frequency. Sukhothai returns 202,744 polygons summing to 13.2m rai against a
province that is only ~4.1m rai; the tambon of วังลึก alone sums to 364,649 rai from 410 polygons.
A naive `SUM(area_rai)` therefore overstates flooded area by roughly 3-9x, and the national total
it produces (129.9m rai = 40% of Thailand) is an artifact, not a finding. **Any flooded-AREA number
off this service needs a real spatial dissolve first** — that is a geometry job (shapely over the
downloaded polygons per district), not a query parameter.

What IS defensible without any dissolve, because it is immune to overlap:
- `MAX(flood_freq)` per district — "this district contains ground that flooded in 11 of 12 years".
  A clean branch-hazard flag, one grouped query, no area claim.
- the count of districts at each max-frequency band.

Deliberately NOT built on 2026-08-01 rather than shipped with a suspect area number. ✅ The
MAX(flood_freq) group-by (joined onto `amphoe.json` via Thai/English name, NOT `ap_code` — the app's
amphoe identity is name-keyed) shipped 2026-08-02 as `build_flood_hazard.py`. **Area is still left
for a later pass that dissolves geometry** (shapely over the downloaded polygons per district).

## 0a. Fold the MEASURED TMLI province layers into the risk read  ⟶ NOW UNBLOCKED (objective #1)
The data.go.th / NSO / NESDC datasets that the sandbox is BLOCKED from pulling are now vendored
(measured, from the Thai-network TMLI platform) and projected into clean province-keyed layers — no
desktop pull needed. `pipeline/ingest_tmli.py` (deterministic, network-free, `--check`-gated in
`tests/run.sh check`) reads `source-data/tmli/` and writes, keyed by the canonical 77 Thai names:
- `source-data/household_debt_by_province.json` — `debt_per_household` THB (NSO SES 2566) is
  **MEASURED**. `debt_to_income`/`stress_index` (attributed to BOT Q4/2024) are **⚠ UNVERIFIED
  (corrected 2026-07-04 audit)** — no CKAN/BOT resource id is cited for them anywhere in the vendored
  source, the values are grouped under hand-written narrative headers (same fabrication smell as the
  GPP file below), and they diverge 10-20x from the debt-to-income the app actually computes and
  ships (`household_risk_by_province.json`, `build_household_risk.py`: `debt_per_household ÷` NSO SES
  annual income). **Do not use this file's `debt_to_income`/`stress_index` for anything** — the app
  already only ever consumes the recomputed ratio. See `source-data/tmli/PROVENANCE.md`.
- `source-data/household_income_by_province.json` — monthly income by occupation + `avg_monthly_income`
  (NSO SES 2566). **MEASURED.**
- `source-data/unemployment_by_province.json` — employed/unemployed/labor-force (thousands) +
  `unemployment_rate` (NSO LFS Q3/2025). **MEASURED.**
- `source-data/gpp_by_province.json` — GPP (million THB) + sector shares + hub type (NESDC 2566).
  **⚠ NOT MEASURED (corrected 2026-07-02 audit).** The vendored `provincial-gpp.js` labels itself
  "NESDC OFFICIAL DATA" but its own header/`GPP_META` admit only **1 of 77** provinces (Mukdahan,
  `source: 'CKAN-NESDC-2566'`) is actually CKAN-verified against a real NESDC dataset; the other 76
  rows are round-number figures (multiples of 1,000–5,000 THB million) with generic `source:
  'NESDC-2566'` and hand-assigned confidence 0.75–0.97 — an ESTIMATED plausibility knowledge base,
  not a per-province pull. `ingest_tmli.py` now carries the corrected provenance + a per-row `source`
  field and `n_ckan_verified`. **Do not wire this into `platform/data` labelled MEASURED** — it is
  not yet integrated into any `platform/data` layer, which is why this was caught before it reached
  the app. A real fix needs a per-province NESDC CKAN pull (see `docs/DATA_REFRESH_LOG.md`).

- **Why this matters (objective #1):** household **debt-to-income is a direct portfolio-risk signal**.
  This is already DONE, via the app's own recomputed ratio, not the unverified BOT-attributed figures
  above — see `household_risk_by_province.json` (`hhdti`/`pstress` National-map lenses; e.g. Khon Kaen
  1.15x, Amnat Charoen 1.14x, both NSO SES-derived and fully cited). Pairing debt with
  `household_income_by_province` (esp. the Agriculture occupation row) and `unemployment_by_province`
  is also already wired (province deep-dive, `province_stress_index.json`).
- **Next concrete step:** none outstanding for this layer — the measured path (recomputed DTI) is
  already shipped. If a real per-province BOT Household Debt Regional pull is ever obtained (with a
  citable resource id), it could be compared against the recomputed ratio as a second independent
  measure, but do not substitute it in without that verification.

## 0. Replicate the Rayong deep-dive by province, then by region  ⟶ DONE (engine), refine with data
Rayong was the pilot template; the goal was the same deep-dive for every province, rolled up by region.

| Piece | Source | Status |
|---|---|---|
| branches (filter master by prov) | `source-data/branches_final.json` | ✅ all 77 provinces |
| POI-within-province (10 layers) | `source-data/osm_layers.json` (national) | ✅ |
| nationwide amphoe (district) polygons | `source-data/th_amphoe.geojson` (928 amphoe) | ✅ acquired |
| per-district rollups (all 77 prov) | `build_province.py` / `build_amphoe.py` (spatial join) | ✅ done |
| competitors | hand-curated Google Places, **Rayong only** (30) | ⚠️ automate per province |
| "what impacts them" narrative | editorial, **Rayong only** | ⚠️ template by region |
| catchment 3D buildings | OSM footprints, urban cores only | ⚠️ opportunistic |

- ✅ **Done:** province/region keys normalized (116→77, 0 `Other`); nationwide amphoe polygons
  acquired; `build_province.py` reproduces Rayong's shape for all 77 provinces; `build_amphoe.py`
  scores all 928 districts (incl. 0-branch white-space). Rendered via `province.html?p=<slug>` and
  the National-map amphoe lenses + Acquisition district leaderboard.
- **Remaining (data-gated, see TONIGHT_CHECKLIST §competitors):** automate competitor pulls per
  province (Places, brand × province) so the deep-dive isn't competitor-blind outside Rayong; then
  template the "what impacts them" narrative by region (EEC-East, agri-Isan, tourism-South…).

## 0b. ✅ CLOSED 2026-07-21 — the REAL loan tape landed
Was "the highest-leverage data unlock for objective #1". It is done: **382,735 real accounts**
ingested. Nothing here is synthetic any more.
- `ingest_real_tape.py` streams the owner-side xlsx into no-PII aggregates
  (`source-data/staging/real_tape_aggregates.json`); the raw file never enters the repo and every
  published cell is suppressed below `MIN_CELL` accounts.
- `build_tape_layers.py` (deterministic, `--check`-gated) projects staging into
  `platform/data/tape_real.json` + `tape_geo_occ.json`, live on `#exposure`, `#trend`, `data.html`.
- The synthetic-era bridge (`ingest_loan_tape.py` → `loan_tape_derived.json`) was **retired
  2026-07-31** — superseded, zero consumers in the app.

**The remaining owner-side unlock is now a refresh cadence, not an unlock:** the tape is a
point-in-time export, so the question is how often a new one lands, not whether one exists.

## 0c. Social listening — which channels we watch, and which we decided NOT to  (objective #2)

The voice-of-customer corpus behind `#acq` (`social_themes.json`, `rival_pulse.json`). Settled
2026-08-01 so the channel list stops being re-litigated.

**Watched, working, and on the weekly job** (`.github/workflows/data-social-listening.yml`):
- Google Play reviews (`pull_app_reviews.py`) — any IP, no key. 10 apps.
- Apple App Store reviews (`pull_apple_reviews.py`) — any IP, no key. 10 apps.
- YouTube comments (`pull_youtube_comments.py`) — any IP, **needs the `YOUTUBE_API_KEY` repo secret**;
  the job warns loudly and skips without it. **← still unset; this is the one owner action left here.**
- Pantip forum threads (`pull_pantip.py`) — proven from a Thai residential IP. Whether it works from a
  GitHub runner is answered automatically by the first scheduled run (the job captures the exit code
  into the PR body). Exits 3 and writes nothing when the response is not the Thai-IP response, so a
  block can never be laundered into "the market went quiet".
- The rivals' own promo pages (`pull_rival_promos.py`) — **THAI IP ONLY**, deliberately excluded from
  CI; Cloudflare blocks datacenter IPs. Run from the laptop; the committed snapshot is reused meanwhile.

**Decided AGAINST — do not build these:**
- **TikTok — DROPPED (owner decision, 2026-08-01).** Not a gap to close later; a closed question. It
  has no key-free public API, the scrapers that exist break constantly and read as bot traffic, and
  the content is video whose text layer is captions and comments — the same material YouTube already
  gives us through a supported, keyed API. The cost is recurring maintenance for a channel that
  largely duplicates one we have.
- **LINE — permanent blind spot.** Closed messaging; no public corpus exists at any price. Where a
  rival's LINE OA promotion matters, it surfaces on their own promo page, which we already pull.
- **Meta Ad Library — proven useless for this market.** No Thai commercial/credit ad coverage; tested
  against a live token. See the `meta-ad-library-no-thailand` note. Google Ads Transparency is the
  working paid-media channel instead (`pull_google_ads.py`).

**Open item — Sabuy Cash.** Added to the Pantip watchlist 2026-08-01 with the LATIN string only
(`pipeline/pull_pantip.py`, key `SABUY`). It is deliberately absent from the app-sentiment ladders and
the ad-transparency pull, because each needs an id that cannot be looked up from this network and must
not be guessed: **Play package name**, **Apple app id**, **Google ATC advertiser id** (`AR…`). Verify
all three from the Thai IP, then extend `pull_app_reviews.py` `APPS`, `pull_apple_reviews.py` `APPS`,
`pull_google_ads.py` `ADVERTISERS`, and the Thai search term in `pull_pantip.py` `BRANDS["SABUY"]`.

## 0d. Macro-tab owner review follow-ups (2026-08-02) — six open items, ahead of the 2026-08-05 MCOM deck
The 17-point markup + stale-data audit landed (see `docs/PROGRESS_LOG.md`, 2026-08-02) but is **not
yet committed or merged** — working tree only, branch `feat/macro-review-17pt`. Six items came out of
that review still open:
1. Persist a trailing-12-month current-account aggregate in `build_macro_indicators.py` so the chip
   can ship without reading as a crisis (April 2026 alone is -7,591 USD million; the trailing 12
   months net to roughly +847M).
2. Government debt has no Thai replacement pulled (PDMO not investigated) — the row still shows IMF.
3. Unemployment's vintage was not re-verified this session (`labour_context.json` → `unemployment`,
   still 2025).
4. Co-pay ฿44bn: source and period unconfirmed. Candidate lead is "ไทยช่วยไทย พลัส" (cabinet-approved
   2026-05-19, government portion ~ ฿49.6bn at its two-month mark) but it doesn't cleanly match
   ฿44bn, so it was left rather than guessed.
5. ~~`tests/visual_overflow.js` is not yet wired into `tests/run.sh` or CI — run by hand only.~~
   **DONE 2026-08-03** — `tests/run.sh overflow` (also in `all`), and a line in qa.yml's
   "Render + health + visual" step. Wired the day after PR #259 shipped a Risk-tab panel that pushed
   a 390px phone to 494px of horizontal page scroll with every gate green. It sits in the
   **non-blocking** step for now, so a finding is visible in the log but does not red-gate a merge;
   promoting it to the blocking gate is a deliberate follow-up once it has a few clean runs behind it
   (it also fails on any uncaught console error, which is a wider net than layout alone).
6. The TH/EN language switch was deferred by the owner to Thursday 2026-08-06 (lower priority than
   the 2026-08-05 deck).
7. **OPEN — the three heavy 3D pages fail their headless render in CI.** `province-rayong`,
   `province-chonburi` and `rayong-catchment` (all deck.gl/WebGL) each burn ~4 minutes on the runner
   and then FAIL, on both master and PR runs — confirmed on the #262 master run (8 passed, 3 failed)
   and the #266 branch run (9 passed, 2 failed). This is what exposed the qa.yml bug fixed alongside
   it: the step's `bash -e` shell aborted at `render`, so `health` and `visual` had not been running
   in CI at all, and the step still reported green because it is `continue-on-error`. Each phase now
   runs independently, so the render failures are visible as warning annotations — **but they are not
   fixed**. They render fine locally, so the suspect is the runner's software GL under the QA_BUDGET
   timeout, not the pages. Diagnose from the uploaded `qa-renders` artifact before touching the pages.
8. ~~**OPEN — the page-health manifest hooks are stale.**~~ **DONE 2026-08-03.** Re-derived the hook
   column against the live settled DOM. Only two rows were actually wrong: `index` asserted `#region`
   (the "Segment signals by region" table removed 2026-08-01) → repointed to `#macro` (the JS-populated
   macro strip); `risk-trend` asserted `#trendbaseline` (the single-vintage placeholder, empty in the
   shipped multi-vintage state) → repointed to `#trendregions` (the region-mover list). The other 8 rows
   (national/`map`, acquisition/`amptbl,amprtbl`, branch-explorer/`map`, both data-book/`db-root`, the
   three 3D pages) were verified already-correct against rendered output and left unchanged. `health`
   now passes on all 7 non-3D pages (was 0/10, all false `missing #<hook>`). Test-config only — no app
   change. NOTE the earlier list here (`#map` national/branch-explorer, `#amprtbl` acquisition) was from
   an older render-failing state; those hooks were confirmed fine this pass.
9. **OPEN — the visual-regression baselines are stale to the point of being noise.** Now that
   `visual` runs it reports 0/10: five pages at `mean_diff` 175-212 against a tolerance of 12 (the
   app has been rebuilt several times over since the PNGs were taken) and three with no baseline at
   all (`acquisition`, `data-book`, `data-book-province`). Either refresh with
   `tests/run.sh baseline` after a deliberate review of each PNG, or retire the phase — as written it
   cannot tell a regression from the accumulated intended change.

## 1. Deploy to Vercel and verify production  ⟶ do first
- `cd platform && npx vercel --prod` (link to team "Kaustav Bagchi's projects"
  `team_pYNrbLMZobN80m4jD7WPWybD`; set Root Directory = current folder).
- Open the URL on a phone; click every nav item, rotate the 3D scenes.
- Then check production health (Claude Code or Claude with Vercel tools can read these):
  runtime errors + logs for the project. Existing projects incl. `autox-calibration`
  (`prj_IJwZXYYrdhobOSR2phIvf5uXHNap`).
- **Decision needed from Kaustav:** branch-level PD is sensitive → consider Vercel access protection
  (password / SSO) on the deployment.

## 2. Unblock the gov data from the Thai IP  ⟶ biggest data win, only possible locally
The whole reason to be in Claude Code on Kaustav's laptop. **Exact copy-pasteable commands live in
`docs/TONIGHT_CHECKLIST.md`** — this is the summary of what and why.

> **SETTLED 2026-08-04 — two CI "openings" verified as dead ends (stop re-flagging them; this is what
> was re-checked so the autonomous loop doesn't re-probe every run).** A negative-space sweep kept
> surfacing (a) refreshing the DLT vehicle/collateral layers and (b) probing a BAAC department CKAN as
> live openings. Both were probed from CI this date and are **not actionable from a cloud IP** — not
> because of a geoblock we can route around, but because the upstream data itself is frozen / absent:
> - **DLT collateral layers are already at DLT's newest genuinely-complete vintage — NOT stale by
>   neglect.** `gdcatalog.dlt.go.th` IS reachable from CI (HTTP 200), but: `dataset_1_1_04` (cumulative
>   stock → `ev_penetration.json`, `vehicle_collateral.json`, `vehicle_mix.json` stock) serves a single
>   resource `stt_car_fuel_at_25690228.csv` = **28 Feb 2026**, exactly the committed `vintage`;
>   `stat_1_1_01_first_regis_vehicles_car`'s `sttt_car_new_reg_mm_2569_02.csv` (Feb-2026) is a **permanent
>   ~6-row stub** (1KB vs Jan's 151KB/~1,421 rows) — re-verified still-a-stub 4 months after its
>   2026-03-17 last-modified — so `vehicle_models.json`'s `latest_month: 2026-01` is CORRECT, not a
>   laggard; the monthly-action datasets `dataset_stat_1_008/009` top out at Feb-2569. A DLT refresh is
>   worthwhile ONLY once newer files land. **Precise recheck trigger:** a `stt_car_fuel_at_2569MMDD.csv`
>   dated after 2569-02-28 on `dataset_1_1_04`, OR a `sttt_car_new_reg_mm_2569_03.csv` (or later) that is
>   **>20 rows** (not a stub) on `stat_1_1_01_first_regis_vehicles_car`. Until then, re-pulling produces
>   byte-identical output — do not "refresh" it.
> - **BAAC personal-credit (`build_baac_credit.py`) has NO CI-reachable source.** Its only source is the
>   data.go.th aggregator (`package_show?id=baac02_2567`, HTTP **403** from CI), and BAAC has **no own
>   department CKAN** — `catalog/data/opendata/…baac.or.th` all resolve **HTTP 000** (unlike the DIW/DLT
>   dept-CKAN breakthrough, there is no BAAC equivalent to bypass to). The builder stays correctly
>   SKIP-gated; the xlsx is **Thai-IP / owner-side only**. Do not re-probe a BAAC CKAN from CI.
>
> Net: the CI-doable, offline-deterministic data backlog is genuinely **exhausted** as of this date —
> the remaining unlocks are all Thai-IP/owner-side (below) or wait on the upstream publishing newer data.

- ✅ **Partly done (prior session):** DIW factories (66,100, all 77 prov) + a first DLT vehicle / NSO
  employment fold-in landed via `autox_dgt_ingest.py` → `ingest_gov.py`. Vehicles/crops are still only
  partial-province; widen them.
- **Still to pull (TONIGHT_CHECKLIST):**
  - **DLT vehicle registrations** all-province/district → replace `collateral_density` proxy + the
    catchment "vehicle" layer with real counts (motorcycle title ≈ 50% of the book, car/pickup ≈ 25%).
  - **DIW factories** — widen coverage to factory zones (Pluak Daeng/Nikhom) where OSM has ~nothing.
  - **NSO Census Table 6 occupations** → real who-works-here per district (replaces the OSM workforce proxy).
  - **OSM roads / water / landuse / buildings** (Overpass mirror) → catchment widening + isochrones.
  - **Agri farm-gate prices / reservoir / flood** → replace the GLOBAL price-direction proxy in
    `build_crop_stress.py` with real Thai farm-gate.
- **Rotate `DATA_GO_TH_TOKEN`** (it was exposed in chat) before running.
- Then merge into `source-data/branches_final.json` and re-derive (`derive.py` + `build_*` + `timeseries.py`).

## 3. True 15-minute isochrone (catchment view)
Replace the walk-radius dasymetric estimate with a real street-network reach polygon.
- Options: OpenRouteService (`api.openrouteservice.org`, free key, `/v2/isochrones/foot-walking`),
  or self-host Valhalla. Both fine to call from Kaustav's machine.
- Swap the circle layer in `rayong-catchment.html` for the returned isochrone polygon; recompute reachable
  population by summing building floor-area **inside the polygon** (same occupancy assumption, now honest geometry).
- Update the card footnote to say "street-network isochrone (foot-walking)".

## 4. Widen the catchment explorer beyond Mueang Rayong
- `pull_wide.py` for other urban boxes with OSM coverage (Ban Chang town, Klaeng town; check Chonburi/EEC if
  expanding). Where OSM buildings are absent (factory zones), keep the province district-polygon 3D view.
- Consider a province/area selector so the catchment view isn't hard-coded to Mueang.

## 5. Province-precise livestock & aquaculture
- DLD (livestock) and DOF (fisheries) data are **not** in the OAE datastore; currently regional-share only.
- This sharpens the agri-PD livestock buffer (the resilient-segment story). Look for DLD/DOF open data
  (likely via data.go.th from the Thai IP) or provincial statistical yearbooks.

## 6. Wire the enrichment loop straight into `platform/data/`  ⟶ DONE for national data
- ✅ `derive.py` projects `source-data/branches_final.json` → `platform/data/branches.json` + `meta.json`,
  deterministic + network-free, with `--check` (byte-exact verification of the committed output).
- ✅ `autox_enrich_loop.py` now reads/writes the real master in `source-data/`, calls `derive.py` each
  iteration, and has `--derive-only` (offline re-project). Refresh now reaches the app in one command.
- ⚠️ The livestock-buffered agri counts (`region.hi`, `n_agri`), white-space tables (`mws`/`cws`) and the
  editorial macro board are still **carried forward** by `derive.py` — they aren't recoverable from
  `source-data/` alone. To make them refresh too, have `autox_enrich_loop.py`'s scoring stage emit them
  into the master (or a sidecar) and extend `derive.py` to read them instead of carrying them.
- ⏳ Still to do: have `derive.py` also rebuild `rayong_*.json` from `bldg_wide.json` /
  `rayong_competitors.json` / `rayong_districts.geojson`; and surface the iteration log on the Overview
  tab (last-refreshed + per-source freshness).

## 7. Nice-to-haves
- Search-protection / role gating if this goes to a wider internal audience.
- A national 3D mode only where it performs (keep the 2D Leaflet default).
- Export buttons (CSV of leads per catchment) for the field team.

---

### Quick reference — IDs
- Vercel team: `team_pYNrbLMZobN80m4jD7WPWybD` ("Kaustav Bagchi's projects")
- Projects: autox-calibration `prj_IJwZXYYrdhobOSR2phIvf5uXHNap`,
  thailand-labor-intel `prj_VLpR8SIHOSwe5NXuqMjQaTBwwJFc` (holds `DATA_GO_TH_TOKEN`).
- Overpass mirror: `https://maps.mail.ru/osm/tools/overpass/api/interpreter`
