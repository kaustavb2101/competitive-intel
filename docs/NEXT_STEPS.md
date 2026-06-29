# NEXT STEPS — prioritized backlog

Ordered by value × unblocked-ness. Each has a concrete first action so Claude Code can just start.
**For the exact Thai-laptop pulls (copy-pasteable), see `docs/TONIGHT_CHECKLIST.md`.**

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

## 0b. Get a REAL loan tape  ⟶ highest-leverage data unlock for objective #1 (portfolio risk)
The loan-tape bridge is built and proven on SYNTHETIC data; it flips to measured the moment a real
export lands. Until then the four portfolio-risk outputs are stamped SYNTHETIC.
- ✅ **Done:** the no-PII contract (`pipeline/loan_tape_schema.md`), deterministic synthetic generator
  (`make_synthetic_tape.py`), and the validating ingest (`ingest_loan_tape.py`) that computes vintage
  90+ aging, branch ROI/payback, HHI concentration, and proxy-vs-actual PD calibration.
- **Next concrete step:** Kaustav exports two no-PII files from core banking per the schema
  (`loan_tape.json` + `branch_aum_monthly.json`, join on branch `code`), drops them in `source-data/`,
  and runs the one command in TONIGHT_CHECKLIST §loan-tape. The platform then stamps `measured`.

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
