# PROGRESS LOG — AutoX / เงินไชโย Credit Intelligence

Reverse-chronological. Most recent first. "Decision" entries explain *why* a path was taken so you
don't re-litigate settled choices.

---

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
- `platform/` serves 200 on all routes via `python3 -m http.server` (last verified 2026-06-28).
- All embedded JS passes `node --check`.
- `branches_final.json` = 2,015 records, 46 fields, ~99% joined on district population.

## Open threads (see NEXT_STEPS.md for detail)
1. Deploy to Vercel + verify production (Claude can read logs once it's live).
2. Run blocked gov data from Thai IP → DLT vehicles, DIW factories → fold into the loop.
3. True 15-min isochrone (routing API) to replace the catchment walk-radius estimate.
4. Widen the catchment view beyond Mueang Rayong where OSM building coverage allows.
5. Province-precise livestock/aquaculture mapping (DLD/DOF data not in OAE datastore).
