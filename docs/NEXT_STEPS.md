# NEXT STEPS — prioritized backlog

Ordered by value × unblocked-ness. Each has a concrete first action so Claude Code can just start.
**For the exact Thai-laptop pulls (copy-pasteable), see `docs/TONIGHT_CHECKLIST.md`.**

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
