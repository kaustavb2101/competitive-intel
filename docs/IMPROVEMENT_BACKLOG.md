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
- [x] **`hhdti` (household DTI) lens is province-resolution but only paints branch dots — DONE
      2026-07-03 (7)** (`build_province_geo.py` groups the existing `amphoe_geo.json` polygons by
      province → `province_geo.json`; `hhdti`/`pstress` gained `prov:true` + a
      `drawProvinceChoropleth()` layer, same pattern as the district choropleth).

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
- [ ] **Vendor `numpy`/`shapely`/`rasterio` into the sandbox's default setup** (session-start hook or
      environment Dockerfile) so `build_branch_peers.py --check` and `build_branch_population.py
      --check` run for real on cycle 1 instead of hitting `[SKIP]` (2026-07-03/2026-07-03(6) fixes stop
      them being misreported as failures, but a `[SKIP]`'d check still isn't as good as one that
      actually ran). *(LOW, S)*
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
- [ ] **`province_stress_index.json`'s equal 50/50 DTI/unemployment weighting is an editorial
      choice** (documented honestly in `meta.caveats`, not calibrated to realized loss) — once the
      real loan tape lands (`docs/TONIGHT_CHECKLIST.md` §6), correlate `composite_stress` against
      actual branch-level 90+ delinquency by province and re-weight if one leg dominates. *(LOW, S,
      blocked until real loan tape)*
- [ ] **`build_province_stress.py` could add a 3rd leg** once DLT vehicle registrations (the
      highest-value blocked pull, `docs/TONIGHT_CHECKLIST.md` §1) land — collateral-supply stress
      (motorcycle share of the province vehicle stock is already a MEASURED lens, `motomix`) is a
      third structurally-relevant, already-sourced signal that isn't in the composite yet. *(LOW, S)*

## Queue — follow-ups noticed 2026-07-03 (4)
- [ ] **`renderHomeThesis()`'s one-sentence board thesis still doesn't cite `PSTRESS_LIST[0]`** —
      only the risk CARD got the new "structurally riskiest" row this cycle; the top-of-page
      sentence's "risk to watch" clause still only checks `HHRISK_LIST[0]`/`CSTRESS_LIST[0]`. Once
      `province_stress_index.json` is the more defensible read (it blends two NSO legs, not one),
      consider swapping the thesis clause to lead with the composite instead of raw DTI, or adding a
      4th clause — small, same lazy-load chain (`loadProvinceStress` is already warmed on Home).
      *(LOW, S)*
- [ ] **`PSTRESS_LIST[0]` and `HHRISK_LIST[0]` can point at different provinces** (composite blends
      DTI+unemployment, DTI alone is unemployment-blind) — today's data has them agree
      (อำนาจเจริญ/ขอนแก่น both Isan, no direct clash visible on the rendered card), but nothing
      guards against the two rows reading as contradictory "riskiest province" claims if the two
      legs diverge on a future NSO refresh. Worth a short explanatory caption distinguishing
      "composite structural stress" from "raw household leverage" if it ever looks confusing in
      review. *(LOW, S)*
- [ ] **Same rank-1-surfacing pattern could extend to the Exposure tab** (`#exposure`) — the
      backlog item this cycle closed named "Command Center hero / Exposure tab" but only Command
      Center got built (smaller, more central surface). Exposure's portfolio-concentration view has
      no province-level structural-stress context yet; a compact callout there would round out the
      original ask. *(LOW, S)*

## Queue — follow-ups noticed 2026-07-03 (5)
- [x] **`pstress` lens has the same "province-resolution but only branch dots" issue as `hhdti` —
      DONE 2026-07-03 (7), duplicate of the entry fixed above** (one `province_geo.json` +
      `drawProvinceChoropleth()` serves both lenses via the shared `prov:true` flag).
- [ ] **Stale comment at `platform/app.js`'s `initMap()` `deferForAmp` line ("the district lenses
      (dws/drisk) read d._amp") predates the `unemp` amp lens** and now also `isAmpLens()` — the
      comment still names only 2 of the (now 3, growing) amp lenses. Reword to describe the
      mechanism ("any amp:true lens") instead of enumerating keys, so it doesn't go stale again
      next time one is added. *(LOW, trivial)*

## Queue — follow-ups noticed 2026-07-03 (6)
- [ ] **`province_geo.json`'s province shapes are amphoe polygons GROUPED (not dissolved)** —
      internal amphoe boundary seams render as thin lines within a province (cosmetic only, the
      fill colour is uniform per province so it still reads as one shape at the National map's
      normal zoom). If `shapely` ever lands in the default sandbox setup (see the existing
      "vendor numpy/shapely/rasterio" backlog item), a true `unary_union` dissolve would produce
      cleaner single-ring province outlines — low priority, purely cosmetic. *(LOW, S,
      blocked-ish on shapely)*
- [ ] **`drawAmphoeChoropleth()` and `drawProvinceChoropleth()` are near-duplicate functions**
      (same canvas-layer lifecycle, colour-ramp, popup-binding shape, only the join key differs —
      amphoe `id` vs province name) — now that there are two resolutions of choropleth, a shared
      `drawChoropleth({features, keyFn, valFn, ...})` helper would remove the duplication before a
      3rd resolution (e.g. region-level) ever gets added. *(LOW, S, pure refactor)*
- [x] **The new province choropleth is effectively invisible at the National map's default
      country-wide zoom — DONE 2026-07-03 (9)** (`styleMarkers()` drops marker `fillOpacity` to 0.6
      specifically when `isProvLens(curLens)` is true; every other lens unchanged at 0.9).

## Queue — follow-ups noticed 2026-07-03 (7)
- [ ] **`household_debt_by_province.json` carries its OWN `debt_to_income` + `stress_index` (BOT
      Q4/2024 regional)** that is never surfaced — only `build_household_risk.py`'s own computed
      DTI (debt ÷ NSO SES annualized income) is. The two could disagree (different vintages/methods:
      BOT regional vs NSO SES-derived); worth an AUDIT pass comparing them and either reconciling or
      explicitly captioning "two independent DTI estimates" if they diverge materially. *(MED, S)*
- [ ] **The new `gov.income` per-occupation breakdown (2026-07-03 (8)) could feed the Simulator's
      occupation-sensitivity lever** — a sector shock that also discounts by the province's
      lowest-earning-occupation share would sharpen the existing ESTIMATED factory-slowdown lever
      with a real NSO income floor. *(LOW, M)*
- [ ] **`province.html`'s new "Income by occupation" panel has no equivalent on the Overview/Exposure
      tabs** — same rank-1-surfacing pattern used for `PSTRESS_LIST[0]`/`HHRISK_LIST[0]` on Home
      could add "lowest-paid occupation nationally" as a portfolio-risk callout. *(LOW, S)*

## Queue — follow-ups noticed 2026-07-03 (9)
- [x] **The same "opaque dots tile over a polygon fill" issue likely applies to the amphoe
      (district) choropleth too — DONE 2026-07-04** (`styleMarkers()`'s dot-opacity thinning now
      checks `isProvLens(curLens)||isAmpLens(curLens)`, so `dws`/`drisk`/`unemp` get the same 0.6
      thinning `hhdti`/`pstress` got in 2026-07-03 (9); confirmed via headless render of
      `?lens=drisk#map` that the district fill now reads through the dots).
- [ ] **0.6 opacity was picked from the backlog's suggested 0.55–0.65 range, not measured against a
      contrast/legibility bar** — worth a quick visual check that dot fill-color is still readable at
      0.6 against both the light basemap and the reddest end of the stress ramp before calling the
      choropleth-visibility problem fully closed. *(LOW, trivial)*
- [ ] **`drawAmphoeChoropleth()` and `drawProvinceChoropleth()` are near-duplicate functions** — see
      the existing 2026-07-03 (6) backlog entry above; now that dot-opacity handling has ALSO grown a
      parallel `isAmpLens`/`isProvLens` branch in `styleMarkers()`, a shared `isPolyLens(k)` +
      `drawChoropleth({...})` helper would collapse three duplicated call-sites at once instead of one.
      *(LOW, S, pure refactor)*

## Queue — follow-ups noticed 2026-07-04
- [ ] **`isProvLens(curLens)||isAmpLens(curLens)` in `styleMarkers()` is the third call-site that now
      distinguishes "polygon-backed lens" from a plain branch/estab/comp lens** (the choropleth-draw
      call already does `drawAmphoeChoropleth(); drawProvinceChoropleth();` unconditionally and each
      no-ops internally) — the existing backlog item proposing a shared `isPolyLens(k)` helper
      (2026-07-03 (6)/(9)) would now collapse three OR-chains into one; worth doing together with the
      `drawAmphoeChoropleth`/`drawProvinceChoropleth` duplicate-function merge already queued.
      *(LOW, S, pure refactor)*
- [ ] **No amp/prov lens currently combines BOTH a district fill and a province fill on the same
      view** — if a future lens ever wants district-level detail nested inside a province-level
      rollup (e.g. show province stress shading with district risk dots atop it), `styleMarkers()`'s
      binary `polyDots?0.6:0.9` would need a 3rd tier; not needed today, just a note for whoever adds
      the next choropleth resolution. *(LOW, trivial, speculative — no action needed yet)*
- [ ] **Verify the 0.6 dot-opacity thinning reads legibly on the `unemp` lens specifically** — this
      cycle's headless check only screenshotted `drisk`; `unemp`'s legend/color ramp is visually
      similar but wasn't independently screenshotted, so it inherits the fix by code-path but not by
      pixel-verification. *(LOW, trivial)*

## Done (most recent first)
- (loop will append here)
- **2026-07-04 — UX: district (amp) lenses get the same choropleth dot-thinning as province lenses.**
  `platform/app.js`'s `styleMarkers()` now thins dot `fillOpacity` to 0.6 for `isProvLens(curLens)||
  isAmpLens(curLens)` (was province-only) so `dws`/`drisk`/`unemp`'s district choropleth reads through
  the dots the same way `hhdti`/`pstress`'s province choropleth was fixed to in 2026-07-03 (9). Gate
  42/0 (`validate_data.py` 224/224, unchanged). Headless-rendered `?lens=drisk#map` confirms the fill
  now shows; control render of `opportunity` confirms no regression. Full writeup: `PROGRESS_LOG.md`.
- **2026-07-03 (9) — UX: thinned branch-dot opacity so the province choropleth reads through.**
  `platform/app.js`'s `styleMarkers()` drops marker `fillOpacity` to 0.6 specifically when
  `isProvLens(curLens)` is true (`hhdti`/`pstress`); every other lens keeps 0.9, unchanged. Two-line
  change, no new data/files. Gate 40/0 (`validate_data.py` 211/211, untouched). Headless-rendered
  `index.html?lens=pstress#map` confirms the province fill now reads through the dot layer; a control
  render of the default `opportunity` lens confirms no regression elsewhere. Full writeup:
  `docs/PROGRESS_LOG.md` (2026-07-03 (9) entry).
- **2026-07-03 (8) — ENRICH: NSO SES 2566 per-occupation income surfaced on the province deep-dive.**
  `source-data/household_income_by_province.json` (already vendored + MEASURED, previously only
  consumed as an unweighted mean by `build_household_risk.py`) is now joined into
  `build_province.py`'s `gov` block (`gov.income`, per-province, all 5 NSO occupation categories +
  the existing mean) and rendered in `province.html`'s "Who works nearby" panel: an "Avg household
  income" row + a new "Income by occupation" mini-chart, tagged `measured · NSO SES 2566`
  (deliberately not crossed against the Overture 14-bucket occupation-mix taxonomy — different
  categories, would require an editorial mapping this cycle avoided). No fabrication — byte-identical
  source values; `build_province.py --check` 0 drift; gate 40/0. Headless dump-dom on
  `province.html?p=rayong` confirms `data-errors="[]"` + real sorted THB values render (the WebGL
  screenshot pass hit the known pre-existing swiftshader flakiness, unrelated to this change — see
  the 2026-07-03 (7) render note below). Full writeup: `docs/DATA_REFRESH_LOG.md` (2026-07-03 (8)
  entry).
- **2026-07-03 (7) — ENRICH: province polygon choropleth for the hhdti/pstress lenses.** New
  `pipeline/build_province_geo.py` groups the already-committed `amphoe_geo.json` polygons by
  `amphoe.json` province_th (no dissolve, no re-simplification) → `platform/data/province_geo.json`
  (77 provinces, `--check`-gated, degrades to SKIP when inputs absent). `hhdti`/`pstress` gained a
  `prov:true` LENS flag + `isProvLens()`/`loadProvinceGeo()`/`drawProvinceChoropleth()` (mirrors the
  amphoe-choropleth pattern), wired into `initMap()`/`setLens()`/`styleMarkers()`. Purely additive,
  null-safe when the file is absent. `validate_data.py` gained `check_province_geo()` (193/193, was
  185/185); gate 37/0. Verified via headless Playwright load (not just a screenshot, since the
  dense opaque branch dots hide the polygon fill at country zoom): `PGEO` = 77 features and
  `provChoroLayer` attaches all 77 province polygons on both `?lens=hhdti` and `?lens=pstress`,
  zero JS errors. `tests/run.sh render` also surfaced a pre-existing, unrelated
  `rayong-catchment.html` render failure (3D page owned by a different in-flight workflow, not
  touched this cycle). Full writeup: `docs/PROGRESS_LOG.md` (2026-07-03 (7) entry).
- **2026-07-03 (6) — AUDIT: fixed a second false-red/false-green gate gap in
  `build_branch_population.py --check` (same bug class as the 2026-07-03 numpy fix, one level
  subtler).** The script has two valid build methods — MEASURED raster sum (needs `rasterio` + the
  committed WorldPop GeoTIFF) preferred, ESTIMATED area-weight (needs only `shapely`) as fallback —
  and only skip-passed `--check` when **both** were unavailable. With `shapely` installed but
  `rasterio` absent (a real sandbox state — `shapely` is a lighter, more commonly pre-installed
  dependency), `build()` silently succeeds via the areaweight fallback and produces a **different but
  valid** JSON than the raster-built file already committed, which `--check` then reported as
  `DRIFT` — a false failure that could have tempted a future cycle to "fix" it by overwriting the
  committed MEASURED file with an ESTIMATED one (exactly the kind of silent regression the
  no-fabrication mandate exists to prevent). Confirmed by installing `rasterio`
  (`pip install --break-system-packages rasterio`): `build_branch_population.py --check` then
  reproduces byte-exact (`method=raster`, 0 drift) — the committed data was never wrong, only the
  gate's partial-dependency handling was blind to a real environment configuration. Fix (code only,
  zero data changed): `run(check=True)` now compares the *committed* file's `meta.method` against
  what this environment can produce; on a method mismatch it prints a distinct `SKIP` (exit 3, same
  convention as the numpy fix) naming exactly which dependency to install to verify for real, instead
  of a `DRIFT` (exit 1); a genuine same-method byte mismatch still fails correctly (hand-corrupted the
  committed file with `rasterio` present and confirmed `--check` still reports `DRIFT`/exit 1, then
  restored from git). `tests/run.sh` now echoes the script's own `SKIP` reason instead of a hardcoded
  (now-inaccurate) "shapely not installed" message, since the missing dependency could be `rasterio`
  instead. Verified all three dependency states by hand (blocking `rasterio` only, blocking both,
  blocking neither) via `builtins.__import__` interception. Gate: 37/0 with `numpy`+`shapely`+
  `rasterio` all installed this cycle (both previously-`[SKIP]`'d checks — `build_branch_peers.py`
  and `build_branch_population.py` — ran for real and passed; was 35/0 with 2 `[SKIP]`s before).
  `validate_data.py` unaffected (181/181, no `platform/data`/`source-data` file touched). Full
  writeup: `docs/DATA_REFRESH_LOG.md` (2026-07-03 (6) entry).
- **2026-07-03 (5) — REFACTOR: amp-lens gating now reads `LENS[k].amp` instead of a 4-site
  hand-maintained OR-chain.** New `isAmpLens(k)` helper in `platform/app.js`; replaced the
  `curLens==='dws'||curLens==='drisk'||curLens==='unemp'` (and `k===` equivalent) checks in
  `drawAmphoeChoropleth()`, `initMap()`'s `deferForAmp`, and both lazy-load triggers in `setLens()`.
  Pure refactor, behaviour-identical (today's `amp:true` lens set already equals the old hardcoded
  list). Removes the whole "dots paint, polygon doesn't" bug class for future amp lenses. Gate:
  35/0 (validate_data 181/181). Headless-rendered `?lens=unemp#map` + `?lens=drisk#map` confirm the
  choropleth still paints, no JS errors. Full writeup: `docs/PROGRESS_LOG.md` (2026-07-03 (5) entry).
- **2026-07-03 (4) — UX: structurally-riskiest province surfaced on the Command Center hero.**
  Added a "Structurally riskiest · DTI + unemployment" row to `renderHomeRisk()`'s risk card
  (`platform/app.js`) using `province_stress_index.json`'s rank-1 province (`PSTRESS_LIST[0]`),
  the same pattern `HHRISK_LIST[0]` already uses for the household-leverage hero line. Wired
  `loadProvinceStress()` into Home's lazy-load chain so it's no longer only reachable via the
  National map's pstress lens. Purely additive, null-safe when the file is absent. Gate: 33/0.
  Headless-rendered `index.html#home` confirms the row (อำนาจเจริญ, composite 98) renders cleanly
  with no JS errors. Full writeup: `docs/PROGRESS_LOG.md` (2026-07-03 (4) entry).
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
