# CLAUDE.md — AutoX / เงินไชโย Credit Intelligence

> This file is auto-loaded by Claude Code. Read it first. It tells you what this project is,
> what's already built, the hard environment constraints, and how to continue.

## Who this is for
**Kaustav**, Corp Strategy Director at **AutoX / บริษัท ออโต้ เอกซ์ จำกัด** (brand **เงินไชโย / Ngern Chaiyo**),
a Thai non-bank **title-loan lender** (SCBX subsidiary). Targets ~1M customers, ฿70bn loans,
25% ROE. There is NO IPO plan. Runs **~2,015 branches today and is now consolidating / rationalising the
network, not expanding it** — there is no branch-growth target.

Kaustav works from a laptop in **Thailand** and deploys to **Vercel**. He gets overwhelmed by
complexity — so: **lead with the answer, explain simply, keep outputs concrete (not abstract indices),
prefer something that visibly works over something clever.** He values honesty about data provenance
(measured vs estimated) and acknowledging gaps.

## The two standing objectives (everything serves these)
1. **Portfolio impact / risk** — which borrower segments and collateral are getting riskier.
2. **Competitive risk** — where the *existing* network faces competitive pressure / margin erosion:
   rival density, contested-market concentration, and per-branch / per-province competitor counts around
   the current branches. A risk lens on the footprint we already run — **not** branch expansion, and it
   makes **no** open / close / where-to-open recommendations.

## What this project is
A branch-intelligence platform over all **2,015 AutoX branches**, plus deep-dives. It is a
**static site deployed to Vercel** (no build step) backed by a **Python data pipeline**.

### The deployable app — `platform/` (deploy THIS subfolder)
One Vercel app, one nav bar, multiple routes (kept as separate pages on purpose — heavy
deck.gl/WebGL scenes in one DOM crashed on mobile; separate routes each get a fresh GL context):
- `index.html` + `app.js` — SPA with lazy-rendered tabs (hash routes):
  - **Command center** (`#home`) — exec front door: aggregates competitive risk + portfolio risk into one
    readout (rival pressure & contested ground, most-stressed segments/provinces, headline KPIs). Lead with the answer.
  - **Overview** (`#overview`) — macro + commodity board + collateral outlook + BoT rate-cap card + region signals.
  - **National** (`#map`) — Leaflet 2D map, 2,015 branches; branch lenses (coverage-gap / competitor-density /
    agri-PD / merchant / collateral) **and district (amphoe) lenses** (coverage / risk).
  - **Risk trend** (`#trend`) — the TIME dimension: snapshots + deltas (which segments/branches are
    getting riskier). Reads `data/snapshots_index.json` + `data/deltas.json`.
  - **Competition** (`#acq`) — competitive-risk readout on the existing network: competitor coverage &
    rival density, districts where AutoX is outnumbered, brand share-of-search vs rivals, and segment
    competitor-exposure tables. Makes **no** open / expand recommendations.
  - **Exposure** (`#exposure`) — portfolio concentration (segment × collateral) + coverage / competitor exposure.
  - **Simulator** (`#sim`) — client-side portfolio what-if (rate/price/drought levers → PD + exposure).
  - **Provinces** (`#provinces`) — selector into the 77-province deep-dive. **Market** (`#market`) —
    real-numbers market assessment. **Branches** (`#branches`) — search/sort.
    Both the Provinces and Market tables route the PRIMARY click to the 3D **building scene**
    (`rayong-catchment.html?city=<slug>`); a secondary "▦ district" link still opens the extruded-
    relief district view (`province.html?p=<slug>`).
- `rayong-catchment.html?city=<slug>` — the **fancy Overture 3D building scene** for ANY province
  (Rayong/Bangkok ship with their `data/<slug>_catchment.json`; others are pulled per-province from
  the desktop via `pull_overture_buildings.py --province <slug>`). When a province's catchment file
  is absent it shows a CALM "buildings haven't been pulled yet — open the district view" notice
  (links to `province.html?p=<slug>`); it never crashes into an empty scene. This is now the primary
  3D entry point for every province.
- `province.html?p=<slug>` — generalized deck.gl **3D district-polygon** deep-dive (extruded relief)
  for ANY of 77 provinces (Rayong = curated pilot). Loads `data/provinces/<slug>.json`. Now the
  SECONDARY "district view"; its strip carries a "🏙 3D buildings" link to the building scene.
- `branch-explorer.html?lat=&lng=&n=` — per-branch deck.gl **3D scene** (live OSM buildings, 10km
  rings, grouped establishments, who-works-nearby proxy, 3D POI columns).
- `rayong-catchment.html` — deck.gl **3D buildings** (3,631 extruded), Mueang Rayong core.
  Left = reachable-population card; right = acquisition leads + recommendations. Loads `data/rayong_catchment.json`.
- `rayong-province.html` — RETIRED redirect stub → `rayong-catchment` (kept for old bookmarks).
- `styles.css`, `vercel.json` (static, cleanUrls). Data served from `platform/data/`
  (`branches.json`, `meta.json`, `amphoe.json`, `crop_stress.json`, `deltas.json`,
  `snapshots_index.json`, `tape_real.json`, `tape_geo_occ.json`, `social_themes.json`,
  `provinces/`, `rayong_*.json`).

**Map tech split (deliberate):** National view = Leaflet (light, reliable on mobile for 2,015 pts).
Province / branch / Rayong views = deck.gl 8.9.35 (3D). Don't merge them into one page.

### The pipeline — `pipeline/`
*All derive/build scripts are deterministic + network-free and carry `--check` (byte-exact reproduce).
`bash tests/run.sh check` gates derive / build_province / build_amphoe / bake_catchment_heights /
timeseries `--check` plus `node --check` on every page's JS.*
- `autox_enrich_loop.py` — the re-runnable enrichment loop. Source registry (13 OSM POI layers,
  OAE crops, HDX pop/rainfall, World Bank Pink Sheet), freshness-TTL caching, recomputes per-branch
  features + segment scores into `source-data/branches_final.json`, then calls `derive.py` so the
  refresh lands in the app; writes `iteration_log.json`. `--watch --interval 86400` to self-refresh;
  `--derive-only` skips all network pulls and just re-projects the master (runnable offline).
- `derive.py` — **projects the master into the app**: regenerates `platform/data/branches.json` +
  `meta.json` from `source-data/`. `--check` verifies byte-for-byte. Livestock-buffered agri counts
  (`region.hi`, `n_agri`), segment coverage tables (`mws`/`cws`) and editorial macro are carried forward.
- `build_province.py` — generalizes the Rayong deep-dive to ALL 77 provinces via spatial join (amphoe
  polygons + branches PIP + gov layers) → `platform/data/provinces/<slug>.json` + index.
- `build_amphoe.py` — **district (amphoe) intelligence engine**: scores all 928 amphoe polygons
  (incl. 0-branch coverage gaps) → `platform/data/amphoe.json` (whitespace + risk_proxy + raw components).
- `build_crop_stress.py` — per-province crop-household stress (objective #1) → `platform/data/crop_stress.json`
  (crop mix, price_stress [GLOBAL proxy], drought, agri_stress + components).
- `build_exit_whitespace.py` — **competitor-fragility cue** (objective #2, regulatory-shakeout lens) →
  `platform/data/exit_whitespace.json`. ESTIMATED PROXY: per-amphoe read of where the surviving big-4
  rival field is thinnest / most exposed if marginal sub-scale operators exit under the Q1-2026 BoT
  registration deadline, inferred from big-4 competitor scarcity (PIP of `competitors_national.json`) ×
  local demand (`amphoe.json`). We do NOT census the sub-scale operators that would actually exit (only the
  4 big compliant brands), so the score is inferred, not measured — full caveat + regulatory citation in
  `meta`. Surfaces on `#acq` (Competition, labelled ESTIMATED) as a competitive-landscape signal. A true
  rival-fragility index needs a sub-scale-operator census (blocked Thai-IP registry pull).
- `build_expansion_plan.py` — **sequenced district-demand planning script**, now **RETAINED BUT DORMANT**
  → `platform/data/expansion_plan.json`. Since the network is consolidating (not growing), its output is
  **no longer surfaced in the UI**; the script + file are kept on disk for reversibility only. Places
  branches one at a time by greedy divisor allocation (D'Hondt) over risk-adjusted district demand with
  15km neighbor cannibalization (≤8/district). The app does not render it.
- `build_branch_density.py` — projects the already-committed `source-data/perimeter_counts.json`
  (MEASURED Overture building count within 10km of each branch, from the 77-province catchment
  pulls, previously unused since 2026-07-02) → `platform/data/branch_density.json`; one popup line
  ("Buildings ≤10km (Overture)"), no lens. Degrades to an honest ABSENT-state on a length mismatch
  against the current `branches.json` rather than guessing a projection.
- `build_branch_peers.py` — **peer-twin outlier benchmark** (objective #1) → `platform/data/branch_peers.json`.
  Benchmarks every branch against its 15 statistical twins (measured market fingerprint: 10km POI mix +
  DIW/workers + rain + own density + NSO province-DTI backdrop, ≥25km away) and flags branches whose
  ESTIMATED composite risk sits ≥2 robust-σ above the twin median — "risky vs its market twins" ≠ "risky
  market". Audit-first list on `#trend` (vintage-independent, labelled ESTIMATED).
- `timeseries.py` — captures a per-vintage SNAPSHOT (label from `meta.updated`, never wall clock) +
  diffs → `source-data/snapshots/`, `platform/data/snapshots_index.json` + `deltas.json` (Risk-trend tab).
- **Loan tape** (objective #1) — **THE REAL TAPE LANDED 2026-07-21. It is not synthetic any more.**
  382,735 real accounts. The raw xlsx never enters the repo; nothing published is below `MIN_CELL`
  accounts; no account or application number is read into any output.
  - `ingest_real_tape.py` — streams the owner-side xlsx (path via `--src` or `REAL_TAPE_XLSX`) into
    committed no-PII aggregates → `source-data/staging/real_tape_aggregates.json`. Owner-side only,
    NOT in the determinism gate (its input is off-repo). The months-on-book anchor is the newest
    disbursement year-month IN THE DATA, never wall clock.
  - `build_tape_layers.py` — the deterministic, `--check`-gated projection of that staging file into
    `platform/data/tape_real.json` + `tape_geo_occ.json`. Everything downstream of staging IS gated.
    Live on `#exposure`, `#trend` and `data.html`.
  - `loan_tape_schema.md` — the original no-PII export contract; kept as the spec the export follows.
  - `make_synthetic_tape.py` — the pre-2026-07-21 SYNTHETIC generator. Kept for reproducing old
    vintages only; its files are gitignored. **Do not build anything new on it.**
  - RETIRED 2026-07-31: `ingest_loan_tape.py` → `loan_tape_derived.json`. It was the synthetic-era
    bridge, superseded by the two scripts above; the 1.1MB output had zero consumers in the app
    (verified by grep across `app.js`/`index.html`/`data.html`) and it was still being maintained.
- `ingest_gov.py` — folds the data.go.th pull (`pipeline/dgt_out/` CSVs) into clean source-data layers
  (DIW factories etc.). `autox_dgt_ingest.py` — the data.go.th puller. **Both blocked from a foreign
  IP; must run from Kaustav's Thai network** (see `docs/TONIGHT_CHECKLIST.md`).
- `fix_provinces.py` — province/region key normalizer (116→77, 0 `Other`). `regionmap.py` —
  province→region + tier lookup (imported widely). `bake_catchment_heights.py` — bakes per-building
  type/height into `rayong_catchment.json`.
- **Rival pulse** (objective #2 — always-on promo + sentiment watch, on `#acq`):
  - `pull_rival_promos.py` — **THAI-IP** pull of the rivals' OWN sites (tidlor.com promo listing,
    sawad.co.th WP REST, muangthaicap.com news; Heng has no parseable promo page) →
    `source-data/rival_promos.json` with per-item `first_seen`/`last_seen`, so each re-run flags NEW.
  - `pull_app_reviews.py` — **any-IP** Google Play ratings + newest reviews for 5 title-lender apps
    incl. AutoX's own เงินไชโย (`th.co.autox.chaiyo`) → `source-data/app_reviews.json` (review store
    accumulates across runs, dedup by reviewId, 1,500/app cap).
  - `build_rival_pulse.py` — deterministic `--check`; sentiment ladder (score, 1★ share, 90-day
    trend anchored on newest review date IN the data, dev-reply rate, ESTIMATED Thai-lexicon
    detractor themes) + promo feed → `platform/data/rival_pulse.json`.
- `save_competitors.py` — writes `rayong_competitors.json` (hand-curated Google Places list).
- `pull_buildings.py`, `pull_wide.py` — Overpass building-footprint pulls. `build_platform.py` —
  assembles the Rayong HTML pages from head + app + loader, wires the nav.

### The data-quality committee — `committee/` (+ `deploy/`)
Brought over from the sibling **TMLI** effort (`kaustavb2101/watcher`). A standing, gated multi-agent
loop that generates the MEASURED data the derive/build pipeline consumes — one verifiable improvement
per cycle, never regressing a metric (see `committee/COMMITTEE.md`). Members:
- **Competitor Scout** (`scout.py`) — pulls rival title-lenders (Srisawad, Muangthai, Tidlor, Krungsri…)
  province-by-province via **Google Places** (`GOOGLE_MAPS_API_KEY`) → `source-data/competitor_census.json`
  + `competitors_national.json`, joins `competitors_prov` onto the master. **Runs from any IP incl.
  cloud/CI** (no Thai network needed) — this is the path to close the Rayong-only competitor gap
  nationally without the laptop.
- **Geocoder** (`geocoder.py`) — tambon/zip centroid → precise branch coordinates (Google/OSM).
- **Industry Census** (`census.py`) — DIW factory census per province/district.
- **Validator** (`validator.py`) — the acceptance gate; **Orchestrator** (`run_cycle.py`) picks the next
  smallest highest-value task; **daemon** (`daemon.py`) runs members continuously. `deploy/` (Dockerfile +
  Procfile + systemd unit) runs the daemon persistently. Keys come from env/`.env` — never committed.
- Not wired into the determinism gate yet (its outputs are network-pulled inputs, like `branches.json`).
  Next step: point `build_rival_pressure.py` at `competitor_census.json` once a national scout run lands.

### Master data — `source-data/`
- `branches_final.json` — **the master**, all 2,015 branches, 46 fields each (see DATA_SOURCES.md
  for the field dictionary). Everything in `platform/data/` is derived from this.
- `osm_layers.json` — 13 national OSM POI coordinate layers (~79k points; items are `[lng,lat]`).
- `estates.json` (35 industrial estates), `rayong_competitors.json` (30 live competitor branches),
  `commodity_board.json` / `commodities*.json` (Pink Sheet prices), `crop_prov_area.json` /
  `rice_prov_area.json` (province planting area), `bldg_wide.json` (3,633 Rayong buildings),
  `rayong_districts.geojson` (8 district polygons + rollups).
- `th_amphoe.geojson` — **nationwide 928 amphoe (district) polygons** (drives build_province/build_amphoe).
- `factories_by_district.json`, `vehicles_by_province.json`, `employment_by_province.json`,
  `crop_prices.json` — the gov fold-in (DIW / DLT / NSO / OAE) from `ingest_gov.py`.
- `province_narratives.json` — editorial "what impacts them" narratives (Rayong curated).
- `snapshots/` — per-vintage time-dimension snapshots (written by `timeseries.py`).
- `loan_tape_synthetic.json` / `branch_aum_monthly_synthetic.json` — **gitignored** SYNTHETIC loan tape.

## How to run things
```bash
# serve the app locally (must be http, not file://, or data fetch fails)
cd platform && python3 -m http.server 8000      # open http://localhost:8000

# deploy (Kaustav's Vercel; sets root to platform/)
cd platform && npx vercel --prod                  # prints live URL

# refresh data (national features + segment scores) — now writes straight to platform/data/
cd pipeline && python3 autox_enrich_loop.py       # recompute master + derive platform/data + log iteration
cd pipeline && python3 derive.py                  # just re-project master → platform/data (no network)

# rebuild the derived layers (all deterministic + network-free, all have --check)
cd pipeline && python3 build_province.py          # provinces/<slug>.json (77-province deep-dive)
cd pipeline && python3 build_amphoe.py            # amphoe.json (928-district coverage + risk)
cd pipeline && python3 build_crop_stress.py       # crop_stress.json (per-province agri stress)
cd pipeline && python3 timeseries.py              # snapshot the current vintage + rebuild deltas

# REAL loan tape (objective #1) — 382,735 accounts, landed 2026-07-21. Not synthetic.
cd pipeline && python3 ingest_real_tape.py --src <the xlsx>   # owner-side → no-PII staging aggregates
cd pipeline && python3 build_tape_layers.py       # staging → tape_real.json + tape_geo_occ.json (gated)

# QA gate (must pass before commit) — offline, deterministic
bash tests/run.sh check

# pull the BLOCKED gov data — ONLY works from a Thai/residential IP (see docs/TONIGHT_CHECKLIST.md)
cd pipeline && python3 autox_dgt_ingest.py        # DIW factories, DLT vehicles, NSO, OAE
```
`pip install --break-system-packages shapely openlocationcode openpyxl pdfplumber` if missing.

## Hard environment constraints (read DATA_SOURCES.md for the full list)
- **REACHABLE:** Overpass (mirror `https://maps.mail.ru/osm/tools/overpass/api/interpreter`),
  Google Places, HDX, OAE (`catalog.oae.go.th`), World Bank (`thedocs.worldbank.org`), NABC
  (`agriapi.nabc.go.th`), BIS (`stats.bis.org`).
- **✅ BREAKTHROUGH (verified 2026-07-09, both HTTP 200 from this sandbox — see docs/INSIGHTS.md §3):**
  the government DEPARTMENTS' OWN CKAN catalogs are NOT geoblocked, only the `data.go.th` aggregator is.
  So the authoritative factory + vehicle census refreshes from ANY cloud IP — **no Thai laptop needed:**
  - DIW factories — `diw-dataset.diw.go.th` (`factype3`, ~67k category-3 factories, all 77 provinces)
  - DLT vehicles — `gdcatalog.dlt.go.th` (`dataset_1_1_04`, registered vehicles by province+type; resource
    URLs rotate monthly — `committee/census.py` resolves the newest CSV via the API)
  Run via `committee/census.py` or the `.github/workflows/data-gov-census.yml` CI job.
- **STILL BLOCKED from the foreign IP (geo/Cloudflare):** the `data.go.th` aggregator itself, IMF, FRED,
  **competitor corporate sites** (muangthaicap/sawad/tidlor/hengleasing — the competitor census was
  already pulled; can't refresh from CI), dataforthai. A real loan-tape export is the only true
  laptop/owner-side unlock left.
- `DATA_GO_TH_TOKEN` lives in Vercel env (project `thailand-labor-intel`). It is valid but
  useless from a foreign IP. Treat as sensitive; rotate (it was exposed in chat).

## Conventions / theme
Dark instrument-console. Fonts IBM Plex Sans Thai + IBM Plex Mono. Accent `#5B7CFA`.
Segment colors: agri/PD `#C8433B`, merchant `#1C8C7D`, collateral `#7A4FE0`, coverage/gold `#E6B450`.
Always state whether a number is measured or estimated. Read the matching SKILL.md before generating
docx/pptx/xlsx/pdf.

## Operating model (how work happens here)
Three nested loops — see `docs/OPERATING_MODEL.md`: (1) agentic coding ~minutes (agent vs written
spec, evals = gate REAL exit + headless render, worktree branches, incremental commits on long
batches); (2) developer feedback ~hours (owner directive → committee → ranked waves → plain-language
digest back); (3) external feedback ~days (phone use / preview comments / nightly site-health →
`docs/FEEDBACK_LOG.md`; feedback outranks backlog; only this loop edits the vision).

## Where to go next
See `docs/NEXT_STEPS.md` (prioritized) and `docs/PROGRESS_LOG.md` (what's done + decisions).
The top three: (1) deploy and verify on Vercel, (2) run the blocked gov data from the Thai IP and
fold DLT vehicles + DIW factories into the loop, (3) replace the catchment's walk-radius estimate
with a true 15-min street-network isochrone (routing API).
