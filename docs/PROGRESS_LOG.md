# PROGRESS LOG — AutoX / เงินไชโย Credit Intelligence

Reverse-chronological. Most recent first. "Decision" entries explain *why* a path was taken so you
don't re-litigate settled choices.

---

## 2026-07-03 (5) — REFACTOR: amp-lens gating reads `LENS[k].amp` instead of a hand-maintained OR-chain

Loop cycle. Backlog follow-up (self-noted 2026-07-03 (2)): `drawAmphoeChoropleth()`'s district-lens
gate and `setLens()`'s amphoe-join/amphoe-geo lazy-load triggers all hardcoded
`curLens==='dws'||curLens==='drisk'||curLens==='unemp'` (or the `k===` equivalent) across 4 separate
call sites in `platform/app.js`. Every amphoe-keyed lens shipped so far (`drisk`, then `unemp`) had
needed this same 3-key OR-chain extended by hand in all 4 places — a bug class ("dots paint, polygon
doesn't") the backlog flagged as likely to bite a future amp lens if someone forgot one site.

Added `isAmpLens(k)` — reads the lens's own `amp:true` flag off the `LENS` registry (the flag already
exists and is used by the `dws`/`drisk`/`unemp` entries) — and replaced all 4 OR-chains with calls to
it: `drawAmphoeChoropleth()`'s `on` check, the branch-popup `deferForAmp` gate in `initMap()`, and both
the amphoe-join and amphoe-geo lazy-load triggers in `setLens()`. Pure refactor, behaviour-identical
(confirmed: the `amp:true` lens set is exactly `{dws, drisk, unemp}` today, matching the old hardcoded
list). A future `LENS.foo={amp:true,...}` now wires into the choropleth + join-warming automatically —
no 4-site OR-chain to remember.

Verification: `bash tests/run.sh check` → 35/0 (validate_data 181/181). Headless-rendered
`index.html?lens=unemp#map` and `index.html?lens=drisk#map` (`tests/lib/render.sh`) — both still paint
the district choropleth under the branch dots with no uncaught JS errors, pixel-identical in shape to
the pre-refactor renders (basemap raster blank headless, expected).

## 2026-07-03 (4) — UX: structurally-riskiest province surfaced on the Command Center hero

Loop cycle. Backlog follow-up (self-noted 2026-07-03 (3)): `province_stress_index.json`
(household DTI + unemployment composite, `build_province_stress.py`, already shipped) only lived
behind the National map's "Province stress" menu lens — it never reached the exec front door.
Added a "Structurally riskiest · DTI + unemployment" row to `renderHomeRisk()`'s "What is getting
riskier" card on Command Center (`platform/app.js`), directly under the existing composite-risk
verdict, using `PSTRESS_LIST[0]` (rank-1 by `composite_stress`) the same way `HHRISK_LIST[0]`
already seeds the household-leverage hero line. Shows province + region, the two MEASURED NSO
inputs (DTI ×, unemployment %) and the ESTIMATED composite score, correctly tagged `est`. Wired
`loadProvinceStress()` into the Home page's lazy-load chain (`homeBooted`) so it warms alongside
the other Home data sources instead of only loading when a user opens the National map's pstress
lens. Purely additive: 12-line render block + 2-line lazy-load wire; no data file changed, no
existing row touched, renders nothing when the file is absent (`pstressHasData()` guard, same
null-safe pattern as every other Home card).

Verification: `bash tests/run.sh check` → 33 passed, 0 failed. `node --check platform/app.js` OK.
Installed render deps and headless-rendered `index.html#home` (1400×1800) — screenshot confirms
the new row (อำนาจเจริญ, Isan, DTI 1.14× · unemployment 2.8%, composite ▲98) sits cleanly between
"Most stressed · composite risk" and "Riskiest single branch" with no layout shift elsewhere on
the page; DOM probe shows `data-errors="[]"` (no uncaught JS).

## 2026-07-03 (2) — UX: `unemp` lens gets its own district (amphoe) polygon choropleth

Loop cycle. Backlog item: the `unemp` lens (added earlier the same day) only painted branch dots —
`dws`/`drisk` also paint the underlying amphoe polygon itself via `drawAmphoeChoropleth()`, which is
sharper for sparsely-branched high-unemployment districts where dots under-represent the district area.
Added `unemp` to `drawAmphoeChoropleth()`'s `on` check and to the `ageoLoaded` lazy-load trigger in
`setLens()` (both previously only listed `dws`/`drisk`); the fill colour/scale is free — it reuses
`unemp`'s own `color`/`val` already registered in `LENS`, and the amphoe-geo polygon layer that dws/drisk
already warm. Two-line change in `platform/app.js`, no new data file, no pipeline change, fully
backward-compatible (dws/drisk behaviour untouched; other lenses still clear the layer as before).

Verification: `bash tests/run.sh check` → 30 passed, 0 failed (both before and after merging a concurrent
push from another session). Installed the render deps (`tests/.cache`) and headless-rendered
`index.html?lens=unemp#map` — the district polygons now paint alongside the branch dots (basemap tiles
blank headlessly, as expected; geometry/fill renders). No regression to `dws`/`drisk` (same code path,
just widened the lens-key check).

---

## 2026-07-03 — UX: dedicated "Unemployment ▲" National-map district lens

Loop cycle. `amphoe.json` has carried a province-inherited `unemployment_rate` (MEASURED · NSO Labour
Force Survey) since 2026-07-02, but it was only visible baked into the blended `risk_proxy` composite —
Kaustav couldn't see raw district unemployment on its own. Added a standalone `unemp` lens to
`platform/app.js`'s `LENS` registry (mirrors the household-DTI dot-lens pattern: reads `d._amp.unemployment_rate`
straight off the existing amphoe join, no new data file, no new pipeline step). Lives in the "More lenses ▾"
menu (not a hero pill — the 4 hero slots are reserved). Own legend branch renders the raw percentage to 1
decimal (`0.4% → 1.8% → 3.6% unemployment`) tagged "● measured · NSO LFS", rather than the generic legend's
integer rounding which would have collapsed most districts to "0%"/"1%"/"4%". Extended the existing
amphoe-join defer/repaint logic (`deferForAmp`, the `setLens` eager-load branch) to include `unemp` alongside
`dws`/`drisk` so a `?lens=unemp` deep-link repaints correctly once the join lands.

**Verification:** `node --check platform/app.js` clean. `bash tests/run.sh check` → 31 passed, 0 failed
(158/158 data-integrity checks). Note: the `numpy` package was missing from this sandbox, which made
`build_branch_peers.py --check` throw and report as a false "drift" — installed it
(`pip install --break-system-packages numpy`), confirmed the check then passes cleanly on an untouched
checkout (pre-existing environment gap, not a repo bug, not caused by this cycle's change). Rendered
`index.html?lens=unemp#map` headless (`tests/lib/render.sh`) — the "Unemployment" pill appears active with
its `M` badge, markers colour by district rate, and the legend/DOM dump confirms the exact expected
`0.4%/1.8%/3.6% unemployment … measured · NSO LFS` string. No regression on the default `#map` render.

---

## 2026-07-02 (3) — ENRICH: NSO unemployment_rate folded into build_amphoe.py's district risk_proxy

Loop cycle. `unemployment_by_province.json` (MEASURED · NSO Labour Force Survey, already vendored and
joined into `build_province.py`'s per-province `gov` block) was landed but only rendered as a fact —
not used as a risk input anywhere. Folded it into `build_amphoe.py`'s `risk_proxy` (objective #1, district
risk triage): every amphoe now carries a province-inherited `unemployment_rate` field, and risk_proxy is
`0.4*agri_stress + 0.25*collateral_density + 0.15*merchant_pd + 0.2*unemployment_stress` (unemployment
linearly scaled 0-3.0% -> 0-100, clipped; 3.0% chosen as a round cap above the observed national max of
3.59%), falling back to `2/3*agri_stress + 1/3*unemployment_stress` for zero-branch amphoe (no
collateral/merchant signal there). Regenerated `amphoe.json` + its two downstream `--check`'d consumers
(`expansion_plan.json` drifted and was rebuilt; `branch_peers.json` reproduced byte-identical — needed
`numpy` installed in the sandbox, unrelated to this change). Updated the Acquisition tab's district-risk
table (`platform/index.html` + `app.js`): new **Unemployment** column, updated formula tooltip/caption
copy, unemployment added to the district CSV export.

Verification: `bash tests/run.sh check` → **31 passed, 0 failed**. Rendered `index.html#acq` headless
(temporarily forced the collapsed `sec-segments` `<details>` open for the screenshot, then reverted before
committing) and confirmed the risk-readout table renders the new column with real values (e.g. Warin
Chamrap 0.16%, Mueang Buri Ram 1.87%) and no layout regression.

---

## 2026-06-29 — Decision layer: command center, time dimension, district engine, loan-tape bridge

Big session (~80 commits on `claude/new-session-wto26j`). The platform moved from "branch map +
Rayong pilot" to a full **decision layer** for the two standing objectives (portfolio risk +
acquisition), with the honesty conventions made explicit everywhere. QA (`bash tests/run.sh check`)
is green: 11/11 determinism + syntax gates pass.

**New SPA tabs (one nav, lazy-rendered, `index.html` + `app.js`):**
- **Command center** (`#home`) — the exec front door. Aggregates the expand + risk signals into a
  single readout (top white-space districts, most-stressed segments/provinces, headline KPIs) so
  Kaustav lands on the answer, not a map.
- **Risk trend** (`#trend`) — the **time dimension**. Snapshots + deltas (which segments/branches are
  getting riskier). Built to work with one vintage today ("baseline captured") and light up
  automatically on the next refresh. Reads `platform/data/snapshots_index.json` + `deltas.json`.
- **Exposure** (`#exposure`) — real portfolio concentration (segment × collateral), white-space v2.
- **Simulator** (`#sim`) — client-side portfolio what-if (move a rate/price/drought lever, see the
  segment PD + exposure response). All in-browser, no server.
- **Provinces** (`#provinces`) — selector into the generalized 77-province deep-dive (`province.html?p=`).
- National map gained **district (amphoe) lenses** (white-space + risk) on top of the branch lenses.
- Acquisition tab rebuilt: **district (amphoe) white-space leaderboard**, most-stressed **district
  risk** readout, and **Road to 3,000** regional headroom allocation (branch-count gap to the 3,000
  target, allocated by regional demand vs saturation). IA/a11y pass (role=tab, deep-link chips).

**New pipeline scripts (all deterministic + `--check`, all gated in `tests/run.sh check`):**
- `build_amphoe.py` → `platform/data/amphoe.json` — **district intelligence engine**. Spatial-joins
  national point layers onto all 928 amphoe polygons (`source-data/th_amphoe.geojson`), **including
  amphoe with zero AutoX branches** (the white-space targets). Per amphoe: branch count, POI counts,
  DIW factories/workers (where the Thai district name is resolvable), province-inherited vehicles/
  employment/agri-stress (clearly tagged province-inherited, NOT amphoe-measured), plus a
  `whitespace` score (demand minus saturation; works for 0-branch amphoe) and a `risk_proxy`.
- `build_crop_stress.py` → `platform/data/crop_stress.json` — **per-province crop-household stress**
  (objective #1). Joins planting area (`crop_prov_area.json`) + price board YoY (`commodity_board.json`,
  a GLOBAL World-Bank direction proxy, NOT Thai farm-gate) + branch drought anomaly. Emits crop mix,
  price_stress, drought, crop_dependence, a transparent `agri_stress` composite, and the raw
  components behind it so the UI shows reality, not just a score.
- `timeseries.py` → `source-data/snapshots/*` + `platform/data/snapshots_index.json` + `deltas.json` —
  captures a deterministic snapshot per data **vintage** (label derived from `meta.updated`, never the
  wall clock, so `--check` is byte-exact) and diffs it against the prior snapshot for the Risk-trend tab.
- `build_province.py` → `platform/data/provinces/<slug>.json` + index — **generalizes the Rayong
  deep-dive to all 77 provinces** from national data (amphoe PIP + gov layers). Competitors/facts
  carried only where curated (Rayong today); others get safe empties. Renders via `province.html?p=`.
- **Loan-tape bridge** (objective #1, synthetic until a real export lands):
  - `pipeline/loan_tape_schema.md` — the **no-PII data contract** Kaustav exports from core banking
    (loans + monthly branch-AUM, join on branch `code`). One-command validation at the bottom.
  - `make_synthetic_tape.py` → `source-data/loan_tape_synthetic.json` +
    `branch_aum_monthly_synthetic.json` — deterministic, clearly-labelled SYNTHETIC (every `loan_id`
    starts `SYNTH-`), proves the pipeline end-to-end.
  - `ingest_loan_tape.py` → `platform/data/loan_tape_derived.json` — validates against the contract
    (enums/ranges/join-rate/status sanity, **fails loudly**) and computes the four turnkey outputs:
    (a) vintage 90+ aging curves, (b) per-branch ROI/payback proxy, (c) HHI concentration by
    segment×collateral, (d) proxy-vs-actual PD **calibration**. `--real` drops the SYNTHETIC stamp.
    The synthetic tape is **gitignored** (only the schema + generators are committed).
- `ingest_gov.py` / `save_competitors.py` / `bake_catchment_heights.py` carried forward from prior
  sessions (the DIW fold-in, Rayong competitor list, catchment building-height bake).

**Honesty conventions (made MANDATORY and enforced in the UI):**
- Every number is labelled **measured / proxy / estimated / SYNTHETIC** at the point of display.
  Loan-tape outputs carry `meta.measured` + a `SYNTHETIC` flag; the app shows the stamp.
- Province-level data inherited down to amphoe is tagged "province-inherited, not amphoe-measured".
- Crop price stress is explicitly a **global price direction proxy**, not Thai farm-gate.
- Abstract indices were retired earlier; scores that remain (whitespace, agri_stress, risk_proxy)
  ship the **raw components** alongside the number so the exec sees reality, not just an index.

**Perf / a11y / IA:** payload trims, theme-aware colors, mobile grid fixes, Overview/Branches
re-render fix, SPA a11y pass (tab roles, deep-link chips into Acquisition sections).

## 2026-06-28 — Exhaustive gov pull + national fold-in (vehicles, employment, crops)

- **Exhaustive puller**: national pass + 77-province sweep + employment topic + resume → 1,925 files.
  National tables secured for every topic (vehicles `dataset_1_1_04` 77 prov; employment `skn_nso8`
  82 prov; crop area `newprovince_weekly` 78 prov; crop prices `35`).
- **`ingest_gov.py`** now distills four layers into `source-data/`: `factories_by_district.json`,
  `vehicles_by_province.json` (car/pickup/moto/EV), `employment_by_province.json` (formal/informal,
  latest year), `crop_prices.json` (95 commodities, latest + YoY). All `--check` byte-exact.
  - **Vehicles by region:** Central&BKK 17.9M · Isan 9.2M · North 7.5M · South 5.5M · East 4.3M.
  - **Formal workers by region:** Central&BKK 6.1M · Isan 2.4M · East 2.3M · South 2.2M · North 1.8M.
- **Rayong pilot** now shows measured DLT vehicles (878k; 58% motorcycles), NSO workers
  (467k formal / 903k informal) alongside DIW factories — KPI strip + `gov` block.
- regionmap: aliased the ฏ/ฎ Surat Thani spelling variant seen in NSO data.
- ⚠️ `pipeline/dgt_out/` is now ~491 MB of raw CSVs in the branch — distilled layers make it
  redundant in-repo; should be git-ignored / removed before merge (see NEXT_STEPS).

## 2026-06-28 — Gov data unblocked from the Thai IP + first real-data fold-in (factories)

**Milestone:** the data.go.th pull — impossible from the sandbox's foreign IP — ran from Kaustav's
Thai laptop (Claude Code in PowerShell). 277 CSVs / 57 MB landed in `pipeline/dgt_out/`.

- **Puller hardened** (`autox_dgt_ingest.py`): UTF-8 manifest (Windows cp1252 crash), crash-proof
  per-resource try/except, province-coverage reporting (★ at ≥20 provinces), depth 5→120 datasets/topic.
- **Coverage (honest):** one genuinely national table secured — **DIW `factype3` = 66,100 factories,
  all 77 provinces, district-level + worker counts**. Vehicles (DLT) and crops (OAE) are published
  per-province; we have ~20 vehicle provinces + many crop-province files (stitch later, partial).
- **First fold-in** (`ingest_gov.py` → `source-data/factories_by_district.json`): real factory & worker
  counts per province|district. 99% of branches (2,005/2,015) join by (province, district).
  **Factories by region (measured): Central&BKK 34,403 · East 9,607 · Isan 8,612 · North 7,196 ·
  South 6,282** — hard-number confirmation of the "worker lending = Central+East" thesis.
- **Surfaced in the Rayong pilot:** `build_rayong.py` attaches province totals (2,113 factories /
  132,733 workers) + per-district `real_fac`/`real_workers`; the province KPI strip now shows
  **Factories (DIW)** + **Factory workers** (measured, replacing the OSM `industrial` POI estimate).
- Both new builders have `--check` (byte-exact reproduce-from-source).

## 2026-06-28 — Province/region data hygiene (prerequisite for by-province/by-region rollout)

**Why:** Rayong is the deep-dive pilot; Kaustav wants it replicated **by province, then by
region**. Before that can be correct, the master's geography keys had to be clean — and they
weren't: 116 distinct province strings (should be 77), and **87 branches (4.3%) sat in a junk
region `Other`**, silently dropped from every by-region rollup (the committed `meta.json` only
ever summed 1,928 of 2,015 branches). Rayong itself was clean (`ระยอง`), which is why the pilot
looked perfect while the national base was not.

- `regionmap.py`: added `ISO` (full ISO 3166-2:TH → Thai name), `ALIAS` (English names), a
  `DISTRICT_PROV` fallback for blanks, and `canonical()` / `region_of()`.
- `fix_provinces.py`: normalizes `prov` + recomputes `region` on the master; `--check` dry-runs
  and fails if anything stays unresolved. Deterministic, offline, idempotent.
- Result: **116 → 77 provinces, 0 `Other`, all 2,015 branches now roll up.** Region counts:
  Isan 553→601, Central&BKK 561→580, South 241→250, East 265→273, North 308→311.
- Re-derived `platform/data/` (derive `--check` passes). NOTE: the carried-forward `meta`
  fields (`region.hi`, `n_agri`, `mws`, `cws`) were computed by the enrich loop under the old
  geography — they're stale until a full `autox_enrich_loop.py` run refreshes them.

## 2026-06-28 — One-command refresh: `derive.py` + wired enrichment loop (NEXT_STEPS #6)

**State now:** "Refresh the data" is one deterministic command, and the recursive loop is runnable
(and offline-testable) in this repo. Pushed to branch `claude/new-session-wto26j` (draft PR).

- Added `pipeline/derive.py` — projects the master `source-data/branches_final.json` into the
  deployable `platform/data/branches.json` + `meta.json`. Network-free and deterministic. `--check`
  rebuilds in memory and byte-compares against the committed files (exits 1 on drift) — verified it
  reproduces both files exactly.
- **Decision — derive only what `source-data/` actually determines; carry the rest forward.** Reverse-
  engineered the projection from the committed output: `branches.json` = compact records
  (`x=round(lng,4)`, `y=round(lat,4)`, `n=name[:34]`, `o=round(opportunity,1)`, + direct fields);
  `meta` region rollups = count + rounded mean; estate `own` = AutoX branches within 10 km. But
  `region.hi`/`n_agri` embed the regional **livestock-income buffer** (Isan 376→316 = the cattle-belt
  adjustment), and `mws`/`cws`/`macro` are analyst/editorial — none recoverable from `source-data/`
  alone, so `derive.py` carries them forward unchanged rather than silently inventing different numbers.
- Wired `autox_enrich_loop.py`: it now reads/writes the **real** master in `source-data/` (it previously
  pointed at a non-existent `pipeline/branches_final.json`, so it couldn't run here), calls `derive.py`
  every iteration, and gained `--derive-only` (skip all network, just re-project + log). Loop artifacts
  (`cache/`, `iteration_log.json`, the CSV) are now gitignored.
- **Bug fix carried from import:** Python 3.12-only f-string (backslash in expression) in
  `build_platform.py` now compiles on 3.11.

## 2026-06-28 — Unified Vercel platform + Rayong catchment explorer

**State now:** One deployable static app in `platform/` with a shared nav across all routes.
Validated locally (all routes serve 200). NOT yet deployed (Claude has read-only Vercel access;
Kaustav deploys).

- Built `rayong-catchment.html` — the "DataProteins-style" view Kaustav asked for: 3,631 real OSM
  building footprints extruded in deck.gl over the Mueang Rayong core, AutoX branches as gold labelled
  pins, 25 live competitors as brand-coloured dots, POI scatter, named landmarks as chips.
  - LEFT card = reachable population at 5/10/15-min walk (recomputes when you tap a branch) + catchment context.
  - RIGHT card = verdict (contested: 25 competitors vs 9 AutoX ≈ 2.8:1), top-5 gaps (tap to fly), 3 recommendations.
  - Top strip = brand counts (AutoX / Srisawad / Tidlor / Muangthai / 7-Eleven+ / vehicle / markets).
- **Decision — reachable population is a dasymetric ESTIMATE**, not a true isochrone: building floor-area
  within walk radii (400/800/1200 m) × local occupancy (~1 person / 45 m²). Honest, matches the reference's
  method family. A true street-network isochrone needs a routing API → see NEXT_STEPS.
- **Decision — buildings are urban-core only.** OSM building coverage is good in Mueang Rayong town but
  ~0 in the factory zones (Pluak Daeng returned 0 buildings). So the catchment view is the *urban* catchment;
  for factory zones fall back to the province district-polygon 3D view.
- **Decision — multi-page, not single-DOM SPA for the 3D scenes.** Three WebGL scenes in one page crashed
  on Kaustav's phone ("uncaught script error"). Each 3D view is its own route → fresh GL context → stable.
  Still one Vercel deployment, one nav bar. `build_platform.py` assembles the Rayong pages.
- Moved Rayong payloads into `platform/data/` and externalized them (pages `fetch()` their JSON instead of
  inlining), with a loading state + error message on fetch failure.
- Added shared `#nav` to `index.html` + hash deep-linking (`index.html#map` opens the Map tab) so the nav is
  consistent and the Rayong pages can link back into specific SPA tabs.

## 2026-06-28 (earlier) — Rayong province 3D deep-dive

- Built `rayong-province.html`: deck.gl extruded **district polygons** (8 Rayong amphoe), switchable
  elevation metric (Workers / Factories / Vehicles), 57 branches, 30 live competitors, estates, POI.
  Bottom-sheet intel panel with tabs: What impacts them / Workers & income / Districts / Competitors / Nearest.
- **Decision — dropped the abstract per-branch "agri_pd" PD score for Rayong.** Kaustav found it too
  far-fetched for a single province; he wanted concrete facts (nearest POI, worker counts, income, factories,
  competitors). The PD score still exists nationally (Overview/National), but Rayong leads with real numbers.
- Pulled real income/worker facts (cited): Rayong = EEC core, ฿400/day min wage (top tier ≈ ฿10,400/mo),
  EEC pay 10–25% above Bangkok, national avg ฿15,972/mo (Q3-25). Anchors: Map Ta Phut petrochemicals,
  automotive (Toyota/Ford/BMW/Mitsubishi) pivoting to **EV** (Chinese BYD/Great Wall plants). 475k skilled
  workers needed in EEC by ~2030. "For daily life you rely on a motorbike or car" → vehicle-dependent =
  title-loan relevant.
- **"What impacts these people" narrative:** EV transition is THE swing factor (threatens ICE auto-parts
  workers, creates EV jobs); plus US tariffs (18% exports to US), petrochemical cycle, ฿400 min wage,
  automation/Thailand 4.0, vehicle dependence.
- Per-district rollups: Mueang Rayong (17 br, 472k working-age, vehicle hub), **Pluak Daeng (factory core,
  ind10≈148, 4 estates — Amata/Eastern Seaboard)**, Nikhom Phatthana, Ban Chang (near Map Ta Phut),
  and rural east (Klaeng / Wang Chan / Khao Chamao / Ban Khai).
- Pulled 30 live competitors via Google Places: Srisawad ×10, Muangthai Capital ×10, Ngern Tid Lor ×9,
  Krungsri Auto ×1 — cluster hard in Mueang Rayong (Thapma/Choeng Noen/Noen Phra) + Map Ta Phut.

## Earlier sessions — national build (condensed)

- Geocoded all 2,015 branches from the Chaiyo locator API; 354 building-precise, rest tambon/zip centroid.
- Built `branches_final.json` master (46 fields): demand, industrial/bank/atm/cvs/etc. POI-within-10km,
  nearest industrial estate, district working-age pop (UNFPA/HDX), drought anomaly (WFP/HDX),
  and segment scores **agri_pd, merchant_demand, merchant_pd, collateral_density, tourism_score**.
- **Decision — segments diverge (core analytical insight).** "Farmers" aren't monolithic: CROP households
  (rice/rubber/sugar/palm) are stressed (double-digit price declines on the WB Pink Sheet), but
  LIVESTOCK/FISHERIES/FORESTRY households are resilient (chicken +25.6%, beef +18.4%, fishmeal +14.1%,
  logs +11.9%); gold +62.7%. agri_pd = crop-price stress × drought, urban-suppressed, minus a regional
  livestock-income buffer.
- **Decision — worker lending is structurally an East+Central play.** Real industrial density: East ind10≈71,
  Central&BKK≈67, vs Isan≈1, South≈2, North≈9. Separate from Isan agri risk.
- Built the national static platform (Overview / National map / Acquisition / Branches) after a heavy
  inline-data 3D engine threw "uncaught script error" on mobile → rearchitected to slim external data + Leaflet.
- White-space found: estates with ≤3 AutoX within 10km (WHA Eastern Seaboard IE 2 has own=0), merchant
  white-space (high vendor demand, few branches), collateral-rich white-space.

---

## Known-good checkpoints
- **`bash tests/run.sh check` passes 11/11** (determinism + syntax gate) — last verified 2026-06-29.
  Gated scripts: derive, build_province, build_amphoe, bake_catchment_heights, timeseries `--check`
  (byte-exact) + `node --check` on app.js and every page's inline JS.
- `platform/` serves 200 on all routes via `python3 -m http.server`.
- `branches_final.json` = 2,015 records, ~99% joined on district population.
- SPA tabs live: Command center, Overview, National, Risk trend, Acquisition, Exposure, Simulator,
  Provinces, Market, Branches.

## Open threads (see NEXT_STEPS.md for detail — and TONIGHT_CHECKLIST.md for the Thai-IP pulls)
1. Deploy to Vercel + verify production (Claude can read logs once it's live).
2. Run blocked gov data from the Thai IP → DLT vehicles, DIW factories, NSO occupations → fold in.
   Plus OSM roads/water/landuse/buildings, agri farm-gate/reservoir/flood, competitor census.
3. **Get a real loan tape** from core banking (schema = `pipeline/loan_tape_schema.md`); run
   `ingest_loan_tape.py --real` to flip the four portfolio-risk outputs from SYNTHETIC to measured.
4. True 15-min isochrone (routing API) to replace the catchment walk-radius estimate.
5. Widen the catchment view beyond Mueang Rayong where OSM building coverage allows.
6. Province-precise livestock/aquaculture mapping (DLD/DOF data not in OAE datastore).
