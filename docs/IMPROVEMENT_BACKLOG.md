# IMPROVEMENT BACKLOG — the standing continuous-improvement loop

> This file is the queue for the **standing improvement loop** (a scheduled trigger that fires a
> fresh session every 4 hours). Each cycle: read this file → pick the single highest-value
> **UNBLOCKED, sandbox-safe** item → build it small + graceful → `bash tests/run.sh check` must pass
> → commit/push to `claude/new-session-wto26j` → log to `PROGRESS_LOG.md` → check the item off here and
> add 1–3 new ideas (self-enriching). One substantive improvement per cycle.

## Rules for each cycle (read before picking)
- **Sandbox-only.** No item that needs a desktop/Thai-IP data pull (those live in `TONIGHT_CHECKLIST.md`).
  Anything that consumes pulled data must **degrade gracefully** when the data is absent.
- **Gate-gated.** If you can't get `tests/run.sh check` to 0 failed, revert ONLY the files you changed and
  pick a smaller item.
- **Shared working tree.** Other sessions may share this checkout — NEVER run `git clean -fd` or
  `git checkout -- .` (they destroy others' uncommitted work). Revert only files you yourself modified.
- **⛔ NO FABRICATION (absolute).** Never invent, guess, hallucinate, or synthesize a data value. Every
  number in `platform/data` must trace to a real source (committed `source-data/`, a real gov/OSM/Overture/TMLI
  pull) OR be explicitly labelled an ESTIMATED proxy/model with its method in the file's `meta`. If a value
  can't be sourced, leave it absent and log it — never fill a gap with a made-up number. When unsure if
  something is real, treat it as not-real and flag it rather than ship it.
- **Honest provenance.** Always label measured vs estimated (see CLAUDE.md).
- **Never** commit secrets or synthetic/generated geographic data; **only** push `claude/new-session-wto26j`.
- **Scope discipline.** Large/architectural/ambiguous ideas → write them here as a recommendation
  instead of building them. Prefer high-impact / low-effort.
- Serve the two standing objectives: **(1) portfolio risk**, **(2) where to expand**.

## Queue — UX / polish (from the UX committee; goal: beat DataProteins)
> Ranked by the committee. NOTE: some are IN FLIGHT in dedicated workflows — do not duplicate:
> `viz-richness-bangkok` owns rayong-catchment.html + index.html nav-3D; `design-system-polish` owns
> styles.css type/spacing. Loop should take the **app.js / page-structure / pipeline** items below.
- [ ] **QW2 — Fill the canvas (likely a centering BUG).** Content is pinned to a narrow left column
      (~770–1000px) wasting widescreen. Verify `main` centers at runtime; raise max-width to ~1280–1360px;
      let map/3D/board views go edge-to-edge. Investigate the dual `max-width` (1000 vs 1180). *(HIGH, S–M)*
- [ ] **QW3 — Fix the nav.** 11-item nav clips mid-word ("Exposu…") and hides tabs behind a fade. Fit all
      tabs (smaller padding/wrap), shorten labels (Command center→Home, Risk trend→Trend, Acquisition→Acquire),
      tuck Simulator/Market/Branches/Provinces under a "More ▾". Remove the silent fade mask. *(HIGH, S–M)*
- [ ] **QW1 — Map = hero (National #map).** Render the Leaflet map full-bleed at top (~78vh); collapse the
      ~10 lens cards into a single horizontal segmented pill row (colour dot + 2-word label) docked over the
      map; default to Opportunity lens; methodology → "ⓘ" tooltip; never show pipeline script names in UI. *(HIGH, M)*
- [ ] **QW5 — Home leads with the verdict.** Command center opens with 2–3 big plain-language hero
      statements (e.g. "Open next in Vadhana & Bang Na; watching Isan rice + Samut Sakhon moto-title");
      demote the measured/estimated legend to one quiet bottom line; ranked items click through to detail. *(HIGH, M)*
- [ ] **QW6 — 3D fails gracefully.** Replace the raw "Could not load buildings (Overpass blocked?) — all
      mirrors failed" with a calm styled status ("Building footprints unavailable — showing branch + POI layer")
      and keep rings + branch pin + POI dots rendered so the scene is never blank. *(HIGH, S)*
- [ ] **QW8 — Seed or hide Risk-trend.** Until a 2nd vintage exists, render today's snapshot as a designed
      "baseline captured" state (top stressed segments/provinces now + flat sparkline skeletons + "deltas next
      refresh" chip), or hide the tab. No blank apology page. *(MED/HIGH, S)*
- [ ] **QW4 (shared w/ design team) — Unify on ONE theme.** Make the indigo-console tokens canonical, delete
      the legacy `:root`/nav/`.mcard` block (~styles.css lines 1–98), confirm the SPA inherits it, use
      identical nav markup on every page so deck.gl pages feel in-product. *(HIGH, M — coordinate w/ design-sys)*
- [ ] **Reduce prose** — explanatory sentences → captions; numbers + colour carry meaning. *(med, S)*

### Bigger bets (from committee — schedule after quick wins)
- [ ] Promote a deck.gl 3D scene to a **landing hero** (clickable thumbnail/loop on Home + province headers). *(HIGH, M)*
- [ ] **Dock the floating 3D controls** into a designed frame (legend rail, basemap segmented top-right named
      Streets/Satellite/Dark, action pills grouped bottom-right, proper header band, kill the stuck loader crescent). *(HIGH, M)*
- [ ] **Standardize provenance** as one quiet chip (filled dot = measured, hollow = estimated, ≥11px AA),
      one legend per page; move caveats into a consistent "Method & caveats" expander everywhere. *(MED, M)*
- [ ] **★ Rebuild dense tabs as 2-col dashboards — NOW THE TOP LAYOUT ITEM.** The full-bleed fix widened the
      container (1180→1320/1680) but the KPI card ROWS still don't stretch, so Exposure/Overview/Acquisition
      still look left-weighted with an empty right half. Real fix: lay each tab out as KPI strip BESIDE the lead
      table/chart (2-col grid that fills the widened canvas), cards that grow, lead table to the right. Acquisition
      leads with the full-width "Road to 3,000" headroom bar + the opportunity-score leaderboard under it. *(HIGH, M)*
- [ ] **Touch-target pass** behind `@media (pointer:coarse)` (not a 600px phone breakpoint) for the touch laptop. *(MED, S)*

## Queue — UX follow-ups noticed 2026-07-03 (2)
- [ ] **Derive `drawAmphoeChoropleth()`'s `on` check from `LENS[curLens].amp` instead of a hardcoded
      `curLens==='dws'||curLens==='drisk'||curLens==='unemp'` OR-chain.** Same for the `ageoLoaded`/
      `ampJoinAttached` lazy-load triggers in `setLens()`. Every amphoe-keyed lens (`amp:true` in the
      `LENS` registry) has now needed this same 3-line wiring added by hand twice (drisk, then unemp);
      a future amp lens will hit the identical "dots paint, polygon doesn't" bug until someone remembers
      to extend 3 separate OR-chains. Refactoring to read the flag off `LENS` removes the whole bug
      class. Pure refactor, behaviour-identical — verify via `?lens=dws|drisk|unemp` renders unchanged. *(LOW, S)*
- [ ] **`hhdti` (household DTI) lens is province-resolution but only paints branch dots** — every branch
      in a province shares one DTI value, so today's map shows many same-coloured dots per province
      instead of one clean shape. A province-polygon choropleth (dissolve `th_amphoe.geojson` amphoe →
      province, or add a lightweight province boundary layer) would read as sharply as the district
      lenses and better communicate "this is a province-level signal, not a per-branch one" — ties into
      the existing backlog idea to combine DTI+unemployment into one province stress score. *(MED, M)*

## Queue — enrichment / capabilities (serve the two objectives)
- [x] **★ Household debt-to-income RISK LENS (National map) — objective #1, MEASURED. DONE 2026-06-30** (build_household_risk.py
      → household_risk_by_province.json + National lens "MEASURED · NSO"; top DTI all Isan: Khon Kaen 1.15×, Amnat Charoen 1.14×).
- [x] **★ Surface the opportunity score on the Acquisition tab — objective #2. DONE 2026-06-30** (#acq "Where to open next"
      leaderboard: top-20 districts + whitespace/competitor-gap/agri-stress component bars; Vadhana 82, Bang Na 80).
- [ ] **Composite expansion-opportunity score** per district — combine white-space + dominant occupation +
      competitor density + crop-stress into one rank for "where to open next". Graceful absent. *(high, M)*
- [x] **Occupation × risk cross-read — DONE 2026-06-30** (`build_occupation_risk.py` → `occupation_risk.json`,
      index-aligned to branches.json: per-branch ESTIMATED occ-stress = MEASURED Overture occupation shares ×
      ESTIMATED stressed-sector weighting [factory national slowdown lever + agriculture = province crop-stress],
      flag when score≥25 & ≥20 estab≤10km. National-map lens `Occupation × stress ◆▲` + branch-popup flag, both
      hide/omit gracefully when absent. Skip-pass `--check` when `branch_occupations.json` absent; validate_data.py
      check + tests/run.sh gated. Dark-until-data — lights up when the Overture pull lands.)
- [x] **Competitor coverage QA panel — DONE 2026-06-30** (#acq found-vs-expected per brand, cited expected; total coverage
      21.9% — MTC 11.3% (978/8673), Tidlor 39%, Srisawad 49%, Heng expected uncited/null. build_competitor_coverage.py gated).
- [ ] **Competitor coverage QA panel** — found-vs-expected per brand so the lower-bound caveat is explicit
      (Srisawad ~11%, MTC ~14%, Tidlor ~37%, Heng ~35%). *(med, S)*
- [ ] **NSO census occupation distiller** scaffolding in `ingest_gov.py` (code only; drop-in when the
      data.go.th pull lands) — improves data availability. *(med, M)*
- [ ] **Expand `validate_data.py`** coverage as new data layers land. *(med, S)*
- [x] **National map: dedicated "Unemployment ▲" district lens — DONE 2026-07-03** (new `unemp` lens
      in `platform/app.js`'s `LENS` registry, mirrors the household-DTI dot-lens pattern; reads
      `d._amp.unemployment_rate` off the existing amphoe join, own 1-decimal-percent legend tagged
      measured · NSO LFS, lives in "More lenses ▾"; gate 31/0, headless-rendered + DOM-verified).
- [x] **Combine household DTI + unemployment into one province portfolio-stress index — DONE
      2026-07-03 (3)** (`build_province_stress.py` → `province_stress_index.json`: 0.5×DTI-percentile
      + 0.5×unemployment-percentile composite over the two already-MEASURED NSO layers; new National
      map lens "Province stress ▲ est" — #1 อำนาจเจริญ composite 98.05, #2 นครพนม 90.58).
- [x] **Backlog hygiene pass — DONE 2026-07-03** (deduped the stale `[ ]` Household-DTI-lens and
      `[ ]` opportunity-score entries that were describing work already shipped `[x]`; removed the
      stale `[ ]` P2 Road-to-3,000 rounding item at the bottom of this file, already fixed per the
      2026-07-01 Done entry).
- [ ] **Vendor `numpy` into the sandbox's default setup** (session-start hook or environment Dockerfile)
      so `build_branch_peers.py --check` runs for real on cycle 1 instead of hitting the new `[SKIP]`
      path (2026-07-03 fix stops it being misreported as a failure, but a `[SKIP]`'d check still isn't
      as good as one that actually ran). *(LOW, S)*
- [ ] **Document the "optional heavy dependency" pattern** (try/except ImportError → distinct exit code
      → `tests/run.sh` reports `[SKIP]` not `[FAIL]`) in `CLAUDE.md`'s pipeline conventions, so if a
      future script adds `scipy`/`pandas`/etc. it follows `build_branch_peers.py`'s 2026-07-03 fix
      instead of reintroducing a false-red gate. *(LOW, S)*
- [ ] **Simulator: occupation-sensitivity lever** — model borrower-base exposure to a sector shock. *(med, M)*
- [x] **`unemp` lens: add a district (amphoe) polygon choropleth — DONE 2026-07-03 (2)** (added `unemp`
      to `drawAmphoeChoropleth()`'s `on` check + the `ageoLoaded` lazy-load trigger in `setLens()`;
      reuses `unemp`'s existing color/val from `LENS` and the amphoe-geo layer already warmed for
      dws/drisk — 2-line change, no new data. Gate 30/0; headless-rendered `?lens=unemp` confirms the
      district polygons now paint alongside branch dots).
- [x] **Sandbox setup gap: `numpy` isn't installed by default — DONE 2026-07-03** (`build_branch_peers.py`
      now catches `ImportError` and exits `3` with a clear "dependency missing, NOT data drift" message;
      `tests/run.sh` reads that exit code and reports `[SKIP]` instead of `[FAIL]`, so a fresh loop
      session without `numpy` no longer hits a false-red gate on cycle 1. Real drift still fails
      correctly — verified by hand-corrupting `branch_peers.json` and re-running with `numpy` installed.
      Vendoring `numpy` into the environment's default setup itself is still open — see below.)
- [x] **Combine household DTI + unemployment into a single province stress score for the National
      map — DONE 2026-07-03 (3), duplicate of the entry above** (same delivery: `pstress` lens).
- [x] **Fold NSO LFS `unemployment_rate` into `build_amphoe.py`'s `risk_proxy` — DONE 2026-07-02 (3)**
      (province-inherited `unemployment_rate` field + risk_proxy now 0.4·agri_stress + 0.25·collateral +
      0.15·merchant + 0.2·unemployment_stress [scaled 0-3.0%->0-100, clipped]; #acq risk table gained an
      Unemployment column; expansion_plan.json regenerated to match; gate 31/0).

## From the research digest (docs/RESEARCH_DIGEST.md — all cited)
- [x] **★ Model the BoT 28% title-loan rate cap — DONE 2026-06-30** (Simulator lever: book yield 28.2%→26.2% under the cap,
      −2.0 pts; moto/agri-vehicle/top-up compress; product mix labelled ESTIMATED, 28% cited; default OFF).
- [ ] **★ Model the BoT 28% title-loan rate cap** in the Simulator (effective 2 Dec 2025). Add a lever/scenario
      showing book yield + which segments compress at 28%. Real regulatory constraint (obj #1). *(HIGH, M, sandbox)*
- [x] **Competitor-exit white-space cue — DONE 2026-06-30** (#acq regulatory-tailwind card + ESTIMATED proxy: districts with
      AutoX demand but thin big-4 footprint; honest caveat that a true rival-fragility index needs a sub-scale-operator census).
- [ ] **Competitor-exit white-space cue** — non-compliant operators must register by Q1 2026 or exit; surface
      districts where sub-scale rivals may exit as fresh white-space (obj #2). Uses existing competitor census. *(MED, M)*
- [x] **Rice/rubber + drought "double-stress" flag — DONE 2026-06-30** (crop_stress.json double_stress flag + score, 20 provinces
      flagged; Overview badge; uses only existing signals, ESTIMATED-labelled, drought is the discriminating leg).
- [ ] **Rice/rubber + drought "double-stress" flag** in crop_stress / district risk — research shows rice+rubber
      prices softening AND >80% El Niño drought prob mid-2026; flag districts with both (obj #1). Uses existing
      crop_stress signals, label estimated. *(MED, M, sandbox)*
- [x] **Collateral-NPL context — DONE 2026-06-30** (Exposure peer-NPL benchmark: Tidlor 1.5% < MTC 2.53% < SAWAD 3.5–3.6%,
      cited, labelled PEER-reported / not an AutoX number; peer_npl.json).
- [ ] **Collateral-NPL context** — peer NPL ladder (Tidlor 1.5% < MTC 2.53% < SAWAD 3.5–3.6%) tracks collateral
      mix; annotate our collateral/segment views with this measured peer context (cited). *(LOW, S)*

## Blocked (need a desktop / Thai-IP pull — do NOT attempt in the loop)
- **★ DLT vehicle registrations by province — gdcatalog.dlt.go.th/en/dataset/** (separate from data.go.th). Highest-
  value new pull: replaces ESTIMATED collateral-supply/TAM per district with MEASURED data (both objectives).
- **OAE farm-gate crop prices** — replace the GLOBAL World Bank price proxy in build_crop_stress.py with real Thai
  farm-gate prices (sharpens obj #1).
- Occupation/competitor **deltas over time** — needs ≥2 vintage snapshots with the new layers.
- **NSO 2022 Business & Industrial Census** ingest — data is data.go.th (blocked from sandbox).
- More **cities** for the 3D showcase (Overture/Overpass pull) — Bangkok already pulled; others need a pull.
- Real **farm-gate** prices, isochrones (ORS/GISTDA), DLT/DIW gov refresh.

## Queue — follow-ups noticed 2026-07-03 (3)
- [ ] **Surface `province_stress_index.json`'s rank-1 province (composite_stress) on the Command
      Center hero / Exposure tab**, the same way `HHRISK_LIST[0]` already seeds the DTI headline —
      today the new composite only lives on the National map's "Province stress" menu lens; a
      one-line "structurally riskiest: <province>, composite NN (DTI+unemployment)" would put it in
      front of the exec front door too. *(MED, S)*
- [ ] **`province_stress_index.json`'s equal 50/50 DTI/unemployment weighting is an editorial
      choice** (documented honestly in `meta.caveats`, not calibrated to realized loss) — once the
      real loan tape lands (`docs/TONIGHT_CHECKLIST.md` §6), correlate `composite_stress` against
      actual branch-level 90+ delinquency by province and re-weight if one leg dominates. *(LOW, S,
      blocked until real loan tape)*
- [ ] **`build_province_stress.py` could add a 3rd leg** once DLT vehicle registrations (the
      highest-value blocked pull, `docs/TONIGHT_CHECKLIST.md` §1) land — collateral-supply stress
      (motorcycle share of the province vehicle stock is already a MEASURED lens, `motomix`) is a
      third structurally-relevant, already-sourced signal that isn't in the composite yet. *(LOW, S)*

## Done (most recent first)
- (loop will append here)
- **2026-07-03 (3) — ENRICH: combined province structural-stress index (household DTI +
  unemployment).** New `pipeline/build_province_stress.py` joins two already-committed MEASURED
  layers — `household_risk_by_province.json` (NSO SES 2566 debt-to-income, itself
  `build_household_risk.py`'s output) and `source-data/unemployment_by_province.json` (NSO Labour
  Force Survey) — into `platform/data/province_stress_index.json`: per province, `composite_stress`
  = 0.5×(DTI percentile) + 0.5×(unemployment percentile), 0–100, worst-first + ranked. All 77
  provinces joined cleanly (both sources already share the canonical 77 Thai-name key). Every
  MEASURED vs ESTIMATED distinction is explicit in `meta` (debt_to_income/unemployment_rate
  MEASURED; both percentiles + the composite ESTIMATED, equal-weighting called out as an editorial
  choice in `meta.caveats`, not calibrated to realized loss). Wired into the National map as a new
  "Province stress ▲ est" menu lens (`pstress` key in `app.js`'s `LENS` registry), following the
  exact `hhdti` lazy-load/legend/absent-guard pattern (own loader, own `lensAbsent` branch, own
  legend block honestly tagged "estimated · NSO SES + NSO LFS blend", warmed unconditionally in
  `initMap()` so `?lens=pstress` deep-links resolve — caught and fixed a first-pass bug via headless
  render where the deep-link path set `curLens` but never called the loader, leaving the legend
  stuck on its loading skeleton). `tests/validate_data.py` gained `check_province_stress()` (meta
  provenance, DTI/unemployment ≥0, percentiles+composite in [0,100], composite formula recomputed
  and compared, rank is a unique 1..77 sequence); `tests/run.sh` gates `build_province_stress.py
  --check`. Headless-rendered `index.html?lens=pstress#map` (screenshot + DOM) confirms the lens
  paints branch dots by composite score and the legend reads correctly — no uncaught JS errors.
  Gate: 32/0, `validate_data.py` 166/166 (was 162/162). Two near-duplicate backlog entries for this
  same idea both checked off. Full writeup: `docs/DATA_REFRESH_LOG.md` (2026-07-03 (3) entry).
- **2026-07-03 (2) — AUDIT: fixed the `numpy`-missing false-red gate.** `build_branch_peers.py` now
  catches `ImportError` on `numpy` and exits `3` with a "dependency missing, not data drift" message
  instead of an uncaught traceback; `tests/run.sh` reads that code and reports `[SKIP]` (not
  `[FAIL]`), so a fresh sandbox session without `numpy` no longer misreports `branch_peers.json` as
  drifted on cycle 1. Zero data values changed (verified: hand-corrupting `branch_peers.json` and
  re-running with `numpy` installed still correctly fails as `DRIFT`/exit 1). Gate: 30/0 without
  `numpy`, 31/0 with it. Full writeup: `docs/DATA_REFRESH_LOG.md` (2026-07-03 entry).
- **2026-07-02 (3) — ENRICH: NSO unemployment_rate folded into `build_amphoe.py`'s `risk_proxy`.**
  Province-inherited `unemployment_rate` field added to every amphoe record; risk_proxy reweighted to
  0.4·agri_stress + 0.25·collateral + 0.15·merchant + 0.2·unemployment_stress (unemployment scaled
  0-3.0%→0-100, clipped), falling back to 2/3·agri + 1/3·unemployment for zero-branch amphoe.
  `expansion_plan.json` regenerated to match (drift); `branch_peers.json` reproduced byte-identical.
  #acq district-risk table gained an Unemployment column + updated formula copy. Gate: 31/0. Full
  writeup: `docs/PROGRESS_LOG.md` (2026-07-02 (3) entry).
- **2026-07-02 (2) — ENRICH: NSO Labour Force Survey unemployment rate → province deep-dive.**
  `unemployment_by_province.json` (already vendored + MEASURED, previously only surfaced per-branch
  in `branch_labor.json`) is now joined into `build_province.py`'s `gov` block for all 77 provinces
  and rendered in `province.html`'s "Who works nearby" panel (measured · NSO LFS tag). No fabrication
  — byte-identical source values, `build_province.py --check` 0 drift. Gate: 28/0, validate_data
  125/125. Rendered + DOM-verified `province.html?p=rayong` (0.72% Rayong). Full writeup:
  `docs/DATA_REFRESH_LOG.md` (2026-07-02 (2) entry).
- **2026-07-02 — AUDIT: corrected a mislabelled-MEASURED layer before it reached the app.**
  `source-data/gpp_by_province.json` (TMLI-vendored NESDC GPP) claimed MEASURED but only 1/77 rows
  (Mukdahan) is actually CKAN-verified; the other 76 are round-number estimates. Fixed
  `ingest_tmli.py` provenance + added per-row `source` field (values unchanged, byte-diff confirms
  only meta/source changed); corrected `docs/NEXT_STEPS.md` + `docs/DATA_PROVENANCE.md`; logged real
  per-province NESDC pull command in `docs/TONIGHT_CHECKLIST.md` §8. Full writeup:
  `docs/DATA_REFRESH_LOG.md` (2026-07-02 entry). Gate: 28/0, validate_data 125/125.
- **2026-07-01 — Recursive-loop wave (3 concurrent agents, disjoint files, all gate 24/0):**
  (1) **QW2 canvas-fill cleanup** — removed two redundant/conflicting `main{max-width}` rules so the
  already-present full-bleed block (line ~807, `--maxw:1320`) is the single source of truth (behaviour-preserving).
  (2) **Simulator factory-slowdown lever** — new severity slider on `#sim` driving an ESTIMATED occupation-stress
  uplift on manufacturing-dominant branches off the MEASURED `occupation_risk.json` (honest: only 2 branches are
  factory-dominant today; null-safe hide when absent). (3) **P2 Road-to-3,000 rounding** — Total now sums the
  rounded rows (984↔985 fixed). (4) **validate_data +12 checks** for opportunity_score / exit_whitespace / peer_npl
  (98 data checks now). (5) **NSO occupation-distiller** scaffold log-line aligned (inert until the pull lands).
- **2026-07-01 — 3D beauty round (reverted → root-caused):** an in-GL `PostProcessEffect` cinematic grade
  blanked the canvas on real GPU (compiled clean but failed at render) → reverted all 3 pages. Real cause of the
  "white" scene was the DEFAULT basemap being LIGHT (near-white) with pale light-mode building fills washing into
  it → switched all 3 3D pages to the DARK basemap by default (gold buildings pop on black; no white surface).
  LESSON: never ship an in-GL shader change without live visual verification (gate/node --check can't catch a
  runtime shader-compile blank).
- **2026-07-01 — Exec-narrative + interaction + perf:** Home board-thesis sentence + Road-to-3,000 bar; district
  white-space/risk leaderboard rows drill into the National map (fly-to + gold ping); O(1) branch-index for map
  lens repaints (killed O(n²)); print one-pager coverage for the thesis strip; lens help-icon contrast bump.
- **2026-06-30 — White blow-out ROOT-CAUSED & fixed.** The diffuse cap wasn't enough: the culprit was the
  view-dependent SPECULAR term, spiked by auto-orbit sweeping through the sun's reflection angle. Zeroed specular on
  every extruded building/relief/peg across rayong-catchment/branch-explorer/province (lighting now angle-independent
  → no orbit position can clamp to white) + defaulted auto-orbit OFF.
- **2026-06-30 — Competitor store-locator puller** (pipeline/pull_competitor_branches.py) — --discover/--pull/--merge,
  run-from-Thai-IP, harvests the COMPLETE census from operators' own branch-finders (the ~2.5k Google/Overture sets
  cover only ~22% of reality). NO fabrication: brands yielding 0 omitted, coords sanity-checked.
- **2026-06-30 — Streaming Overture building tiles (architecture).** pipeline/build_building_tiles.py (union of 10km buffers
  around all 2,015 branches + 2,556 competitors → Overture pull → tippecanoe → PMTiles/MVT; docs/BUILDING_TILES.md runbook),
  + deck.gl MVTLayer streaming-building layer in rayong-catchment/branch-explorer/province (reads platform/data/tiles_config.json;
  province SWAPS extruded relief for real building scenes when tiles present). Graceful no-op until operator hosts tiles. NEXT
  (desktop, Thai-IP): run RUN_TILES.sh, host the .pmtiles/MVT on a CDN, paste the URL into tiles_config.json.
- **2026-06-30 — White blow-out fixed on ALL 3D pages.** branch-explorer (sun 3.0→0.85, material diffuse 0.95→0.34) and
  province (sun 2.4→0.85, diffuse 0.95→0.34) still had the un-capped lighting that clamps light building colours to white on a
  GPU; applied the rayong-catchment cap everywhere (max lit ≈0.83×).
