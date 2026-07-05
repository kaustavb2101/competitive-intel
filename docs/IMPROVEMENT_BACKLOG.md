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
> ⚠ **2026-07-04 (9) audit note:** this whole quick-wins list had gone stale — 6 of 8 items below were
> already shipped in commits dated 2026-06-30/07-01 but never checked off. Before picking a "new" UX
> item from this section, spot-check it against the live app (`bash tests/lib/render.sh 'index.html#<tab>'
> ...`) — a `git log -S"<label>"` on `platform/styles.css`/`app.js` is a fast way to confirm.
- [x] **QW2 — Fill the canvas — DONE 2026-06-30/07-01** (`f142cd0` fullbleed 2D + `5d006d6` consolidated
      the conflicting `main{max-width}` rules into one `--maxw`/`--maxw-wide` source of truth). Re-confirmed
      2026-07-04 (9): headless render of `index.html#map`/`#home` shows content edge-to-edge, no narrow column.
- [x] **QW3 — Fix the nav — DONE 2026-06-30** (`738c28b`: shortened labels — Home/Overview/National/Acquire/
      Exposure/Trend/3D map — tucked under a "More ▾", no fade mask). Re-confirmed 2026-07-04 (9): headless
      render shows all 8 top-level items fit on one row, nothing clipped.
- [x] **QW1 — Map = hero — DONE 2026-06-30** (`ff2e9af`: full-bleed 78vh Leaflet map, lens cards collapsed
      into one segmented pill row docked over the map with "ⓘ" info tooltips, "More lenses ▾" for the rest).
      Re-confirmed 2026-07-04 (9): headless render of `index.html#map` matches the spec exactly.
- [x] **QW5 — Home leads with the verdict — DONE 2026-06-30, since grown well past spec** (`af05be8`).
      Re-confirmed 2026-07-04 (9): Home now opens with a plain-language board-thesis line + Road-to-3,000
      bar + a ranked "THIS WEEK — do these first" defend/audit/tighten/expand queue (`decision_queue.json`),
      each row source-tagged — well beyond the original 2–3-sentence hero ask.
- [ ] **QW6 — 3D fails gracefully.** Replace the raw "Could not load buildings (Overpass blocked?) — all
      mirrors failed" with a calm styled status ("Building footprints unavailable — showing branch + POI layer")
      and keep rings + branch pin + POI dots rendered so the scene is never blank. *(HIGH, S)* **Still open on
      `rayong-catchment.html`** (owned by `viz-richness-bangkok`, not touched by the loop) — confirmed
      2026-07-04 (9): that page's data-load `.catch()` still shows a raw "Could not load … 3D data: {msg}"
      string. `branch-explorer.html` already ships the target pattern verbatim
      (`status('Building footprints unavailable — showing branch + POI layer', 'info')`) — the owning
      workflow can likely port that exact string/pattern instead of designing a new one.
- [x] **QW8 — Seed or hide Risk-trend — DONE 2026-06-30** (`44ca12d`: designed "baseline captured" state —
      flat sparkline skeletons + "Δ at next refresh" chip — renders whenever `deltas.json` is single-vintage
      or absent, never a blank apology). Re-confirmed 2026-07-04 (9) by reading the live `renderTrend()`/
      `renderTrendBaseline()` code path (a 2nd vintage hasn't landed yet, so this is still the active state).
- [ ] **QW4 (shared w/ design team) — Unify on ONE theme.** Make the indigo-console tokens canonical, delete
      the legacy `:root`/nav/`.mcard` block (~styles.css lines 1–98), confirm the SPA inherits it, use
      identical nav markup on every page so deck.gl pages feel in-product. *(HIGH, M — coordinate w/ design-sys)*
      Confirmed 2026-07-04 (9) still open: `platform/styles.css` still has two `:root{}` blocks (line 1 and
      line 119) — owned by `design-system-polish`, not touched by the loop.
- [ ] **Reduce prose** — explanatory sentences → captions; numbers + colour carry meaning. *(med, S)*
      Not independently re-checked 2026-07-04 (9) — unlike the QW items above, no single commit title
      claims this one done; leaving open rather than guessing.

### Bigger bets (from committee — schedule after quick wins)
- [ ] Promote a deck.gl 3D scene to a **landing hero** (clickable thumbnail/loop on Home + province headers). *(HIGH, M)*
- [ ] **Dock the floating 3D controls** into a designed frame (legend rail, basemap segmented top-right named
      Streets/Satellite/Dark, action pills grouped bottom-right, proper header band, kill the stuck loader crescent). *(HIGH, M)*
- [ ] **Standardize provenance** as one quiet chip (filled dot = measured, hollow = estimated, ≥11px AA),
      one legend per page; move caveats into a consistent "Method & caveats" expander everywhere. *(MED, M)*
- [x] **★ Rebuild dense tabs as 2-col dashboards — DONE 2026-06-30** (`af05be8` "UX wow layer: 2-col
      dashboards + home leads with the verdict"). Re-confirmed 2026-07-04 (9) via headless render: Home,
      Overview and Exposure all lay out as KPI-card column beside a lead table/board that fills the widened
      canvas. Acquisition intentionally stayed single-column full-width (matches this item's own spec — "leads
      with the full-width Road to 3,000 bar + leaderboard"), though today the opportunity-score leaderboard
      renders ABOVE the Road-to-3,000 section rather than after it — cosmetic ordering only, logged below.
- [ ] **Touch-target pass** behind `@media (pointer:coarse)` (not a 600px phone breakpoint) for the touch laptop. *(MED, S)*
- [ ] **Acquisition tab section order** doesn't quite match the "2-col dashboards" bigger bet's own text
      ("Acquisition leads with the full-width Road to 3,000 bar + the leaderboard under it") — today "Where
      to open next" (the opportunity leaderboard) renders before the "Road to 3,000" section, not after.
      Purely cosmetic re-ordering, noticed during the 2026-07-04 (9) backlog audit. *(LOW, trivial)*

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
- [x] **Composite expansion-opportunity score per district — DONE (pre-existing, found stale during the
      2026-07-04 (9) audit)** (`pipeline/build_opportunity_score.py` → `platform/data/opportunity_score.json`
      already fuses white-space + competitor-gap + province-inherited agri-stress + optional occupation-pull
      into one 0–100 composite, renormalizing weights over whichever optional inputs are present; surfaced
      on `#acq`'s "Where to open next" leaderboard, re-confirmed live via headless render 2026-07-04 (9)).
      This queue entry was a duplicate of already-shipped work — corrected instead of re-built.
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
- [x] **Expand `validate_data.py`** coverage as new data layers land — DONE 2026-07-04 (3) (see below).
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
- [x] **Same rank-1-surfacing pattern could extend to the Exposure tab — DONE 2026-07-05**
      (`#exposure`'s `renderRiskReadouts()` gained a "Structurally riskiest · household DTI +
      unemployment" callout sourced from `PSTRESS_LIST[0]`, reusing the existing `ccRow()`/`TAG_E`
      helpers and `province_stress_index.json` plumbing — no new data/pipeline. Headless-rendered,
      no JS errors, gate 47/0).

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
- [x] **`household_debt_by_province.json` carries its OWN `debt_to_income` + `stress_index` (BOT
      Q4/2024 regional)** that is never surfaced — DONE 2026-07-04 (2), audit found this isn't just
      "disagreement" — the BOT-attributed fields have no citable resource id, look editorially
      hand-grouped (same smell as the GPP file), and diverge 10-20x from the recomputed ratio the app
      actually uses. Relabelled UNVERIFIED in `ingest_tmli.py`/`PROVENANCE.md`/`NEXT_STEPS.md`
      /`DATA_PROVENANCE.md`; zero data values changed; confirmed no code path ever consumed the
      unverified fields. See `docs/DATA_REFRESH_LOG.md` (2026-07-04 (2)).
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

## Queue — follow-ups noticed 2026-07-04 (3)
- [ ] **The Overture 14-bucket taxonomy (`factory`/`auto`/`retail`/…) is now hand-copied in at least
      three places** — `build_national_places.py`/`build_scene_places.py` (via their shared
      `source-data/occupation_places_named.json` `buckets` list), `build_occupations.py`/
      `build_amphoe_occupations.py`'s branch/amphoe occupation shares, and now
      `tests/validate_data.py`'s new `KNOWN_PLACE_BUCKETS` constant. Nothing currently asserts these
      three copies stay in sync — a future taxonomy change (a 15th bucket, a rename) in the source
      Overture pull could silently diverge from what the validator expects vs. what
      `occupation_leads.json`/`branch_occupations.json` actually carry. Worth a single shared
      bucket-list constant (or a cross-check in `validate_data.py` comparing `KNOWN_PLACE_BUCKETS`
      against whatever bucket list `branch_occupations.json`'s meta declares) next time either
      taxonomy is touched. *(LOW, S)*
- [ ] **`_check_places_payload()` (new this cycle, `tests/validate_data.py`) and the existing
      `check_catchment_poi()` validate near-identical shapes** (meta+label+points-in-bbox) but with a
      swapped point order (`[lng,lat]` vs `[lat,lng]`) and slightly different meta-key names — same
      duplicate-helper smell already queued for `drawAmphoeChoropleth`/`drawProvinceChoropleth` on the
      frontend side (2026-07-03 (6)/(9)); a shared `_check_point_layer(payload, order=...)` could
      collapse both. *(LOW, S, pure refactor)*

## Queue — follow-ups noticed 2026-07-04 (4)
- [ ] **`branch_density.json`'s 134 `empty_0` branches are ALL in Bangkok/Rayong** (per the source
      `perimeter_counts.json` commit message) — a genuine capped-pull artifact, not a real "no
      buildings" reading. Once Bangkok/Rayong get true province-wide Overture catchments (the
      "more tiles" ask in `docs/TONIGHT_CHECKLIST.md` §A), re-run
      `pipeline/build_branch_density.py` — those 134 zeros should mostly clear. *(LOW, S, blocked
      until the Thai-laptop tile pull lands)*.
- [ ] **`bldgDensityPopupHTML()`'s bucket color/label ramp was picked to visually match the existing
      `poiRelevancePopupHTML()` palette, not independently contrast-checked** — same low-priority
      "not measured against a contrast bar" smell already logged for the 0.6 dot-opacity choice
      (2026-07-03 (9)). *(LOW, trivial)*
- [x] **`build_branch_density.py`'s bucket-tally self-check (`AssertionError` on drift) is the only
      builder in the pipeline that hard-crashes instead of failing `--check` cleanly — DONE
      2026-07-04 (5)** (new `BucketDriftError`, caught in `main()` → clean `CHECK FAIL: ...` +
      exit 1, same convention as every other builder; verified via a hand-corrupted-then-restored
      `perimeter_counts.json`. Gate 46/0.)

## Queue — follow-ups noticed 2026-07-04 (5)
- [x] **The bare-`assert`-on-malformed-data pattern fixed in `build_branch_density.py` this cycle
      also exists in `build_national_places.py`/`build_scene_places.py` — DONE 2026-07-04 (6)**
      (both now print `CHECK FAIL: ... malformed` + exit 1 instead of an uncaught `AssertionError`;
      zero behavior change on the happy/SKIP paths, verified by hand. Gate 46/0.)
- [ ] **The "vendor numpy/shapely/rasterio into the sandbox's default setup" backlog item (below,
      still open) cannot be done FROM the improvement loop itself** — a session-start-hook /
      `.claude/hooks` change is agent self-configuration, out of scope for a platform-improvement
      cycle and blocked by the auto-mode policy (confirmed this cycle: creating `.claude/hooks/`
      was denied as "self-modification... not user-authorized"). This needs Kaustav (or a session
      with explicit hook-authoring intent) to set it up once outside the standing loop, e.g. via the
      `session-start-hook` skill or the environment's Dockerfile/setup config — not a future loop
      cycle retrying the same path. *(LOW, S, needs a human/out-of-loop session, not blocked-data)*
- [ ] **`docs/PROGRESS_LOG.md` and `docs/DATA_REFRESH_LOG.md` have diverging numbering for the same
      day** (e.g. today's cycles are `(2)`–`(5)` in one file and `(2)`/`(4)` in the other, tracking
      independent counters) — not a bug, but a reader cross-referencing "2026-07-04 (4)" has to know
      which file it lives in. Worth a one-line convention note in `CLAUDE.md` (or a shared per-day
      counter) if this ever causes real confusion; no action needed today. *(LOW, trivial,
      speculative)*

## Queue — follow-ups noticed 2026-07-04 (6)
- [ ] **`_check_places_payload()`/`check_catchment_poi()` in `tests/validate_data.py` still validate
      near-identical shapes with swapped point order and different meta-key names** (this is the
      2026-07-04 (3) duplicate-helper note, still open) — now that BOTH `build_national_places.py`
      and `build_scene_places.py` share the identical "malformed → CHECK FAIL" one-liner added this
      cycle, a small shared `_fail_if_malformed(d, required_keys, label)` pipeline helper could also
      collapse that duplication alongside the validator-side one. *(LOW, trivial, pure refactor)*
- [ ] **`build_national_places.py`'s `GRID=0.02` national fallback density has never been visually
      compared against a per-city `_places.json` at the same zoom** — worth a quick headless render
      of a province WITHOUT a committed catchment file (relies on the national fallback) to confirm
      the POI mat still reads as "dense" and not visibly sparser than Rayong/Bangkok/Chiang Mai's
      per-city files, now that both builders share hardened malformed-data handling. *(LOW, S)*
- [ ] **Vendor `numpy`/`shapely`/`rasterio` into the sandbox's default setup** remains the single
      highest-value low-effort infra gap (see the existing entry above) — still needs a human/
      out-of-loop session (session-start-hook or environment Dockerfile), not another loop cycle
      retrying the same blocked path. *(LOW, S, needs a human/out-of-loop session)*

## Queue — follow-ups noticed 2026-07-04 (7)
- [ ] **`docs/DATA_SOURCES.md`'s OAE "Dec-2025 outlook" sentence (rice+rubber=2026 RISK crops;
      cassava/palm/chicken/durian firmer) is now the oldest un-re-verified citation in that file** —
      unlike the Pink Sheet block above it (just corrected to 2026M06), this line has never been
      checked against a fresher OAE pull. OAE (`catalog.oae.go.th`) is REACHABLE from this sandbox
      per the same doc's own reachability matrix — a future ENRICH cycle could pull the current OAE
      outlook note and either confirm or update this sentence with a real citation. *(LOW, S)*
- [x] **Add a lightweight doc/data consistency check to `tests/validate_data.py` — DONE 2026-07-04
      (8)** (new `check_doc_vintage()`: reads the live vintage off `meta.json.updated`, greps
      `DATA_SOURCES.md`'s "current read (VINTAGE prices)" header + `DATA_PROVENANCE.md`'s "currently
      `VINTAGE prices`" phrase, fails on mismatch; scoped to those two live-claim anchors, not a
      whole-doc scan, so it doesn't false-positive on the audit logs' legitimate historical mentions
      of the old stale vintage. Verified against a hand-corrupted vintage. Gate 47/0, validate_data
      421/421).

## Queue — follow-ups noticed 2026-07-04 (8)
- [ ] **`check_doc_vintage()`'s two anchors are hand-picked regexes tied to exact current phrasing**
      ("current read (...)" / "currently `...`") — if either doc's live-claim sentence is ever
      reworded (not just re-vintaged), the check fails loudly with a clear message telling the editor
      to update `_DOC_VINTAGE_ANCHORS`, which is the intended fail-safe behaviour, but it's worth
      knowing this is a deliberate trade-off (brittle-but-loud beats silent) if a future doc rewrite
      trips it for a non-drift reason. *(LOW, trivial, informational)*
- [ ] **The same vintage-drift class could recur for other cited-vintage docs** beyond the Pink
      Sheet (e.g. NSO SES/LFS vintages quoted in `docs/DATA_SOURCES.md`'s household-debt/unemployment
      sections, or the OAE "Dec-2025 outlook" line flagged as unverified in the 2026-07-04 (7)
      follow-up) — once one of those layers gets a real refresh, the same anchor-and-compare pattern
      (`check_doc_vintage()`) could extend to a 2nd vintage family. Not needed until a refresh
      actually happens. *(LOW, S, speculative)*
- [ ] **OAE outlook re-verification (from 2026-07-04 (7), still open)** — pull the current OAE
      (`catalog.oae.go.th`, REACHABLE) outlook note and confirm/update `docs/DATA_SOURCES.md`'s
      "OAE Dec-2025 outlook" sentence (rice+rubber=2026 RISK; cassava/palm/chicken/durian firmer),
      the oldest un-re-verified citation in that file. *(LOW, S)*

## Queue — follow-ups noticed 2026-07-05
- [x] **`renderHomeThesis()`'s board-thesis sentence still doesn't cite `PSTRESS_LIST[0]` — DONE
      2026-07-05 (4)** (thesis clause now prefers the DTI+unemployment composite, falling back to raw
      DTI then crop-stress as before; `loadProvinceStress().then()` now also re-renders the thesis so
      it updates once the composite lands. See `docs/PROGRESS_LOG.md` 2026-07-05 (4) entry).
- [ ] **`drawAmphoeChoropleth()`/`drawProvinceChoropleth()` near-duplicate functions** (flagged
      2026-07-03 (6)/(9), still open) — a shared `drawChoropleth({features,keyFn,valFn,...})` helper
      would remove the duplication before a 3rd choropleth resolution is added; this cycle's Exposure
      change reused `ccRow()` rather than duplicating markup, which is the same instinct applied
      preemptively — worth doing the equivalent consolidation on the choropleth pair. *(LOW, S, pure
      refactor)*
- [x] **A parallel "structurally riskiest" callout for objective #2 (expansion) — ALREADY SHIPPED,
      stale duplicate found during the 2026-07-05 (4) audit.** This entry asked for a rank-1
      "where is the clearest expansion signal right now" callout on `#acq` — but `renderAcqVerdict()`
      (`platform/app.js`, gold `#acq-verdict` card, shipped in commit `7fb5d5f`, well before this
      backlog note was written) already renders exactly that: "🏆 Open next: `<top district>` —
      `<score>`/100 opportunity · `<rivals>` rivals ≤5km" sourced from `opportunity_score.json`'s
      rank-1 district. Confirmed live via `grep`+`git log -S` before touching anything; no code
      changed, left checked rather than rebuilding duplicate UI.
- [ ] **`provinces/<slug>.json`'s new `meta.provenance` block (2026-07-05) doesn't yet get its own
      `validate_data.py` check** — the provenance GATE already passes it (via the generic
      `meta.provenance` signal check), but there's no dedicated assertion that every one of the 77
      files' `meta.generated_by`/`meta.provenance.{measured,editorial,estimated}` sub-keys are present
      and non-empty (the way `check_province_stress()` does for `province_stress_index.json`). Would
      catch a future regression where `build_province.py` silently drops the block. *(LOW, S)*
- [ ] **Headless render of `province.html`/`rayong-catchment.html` is unreliable in this sandbox under
      software WebGL** (3 consecutive attempts this cycle all failed with `ERR_CONNECTION_REFUSED` or
      an empty screenshot, even after killing stray chrome/http.server processes between tries) — this
      echoes the already-documented `rayong-catchment.html` flakiness (2026-07-02 (2) log entry) but
      now also affects the plain-Leaflet-adjacent `province.html`. Worth a `tests/lib/render.sh`
      retry-loop (it already has a 4x retry per its own header comment — confirm it's actually being
      exercised) or a longer settle budget before concluding a render genuinely regressed vs. the
      harness just being flaky in this container. *(MED, S — blocks a fast confidence check on future
      province-page cycles)*

## Queue — follow-ups noticed 2026-07-05 (2)
- [ ] **`fuel_prices.json` only ever carries a single day's snapshot** (the Bangchak API has no
      in-API history) — `delta_tomorrow` is wired into the source file but not yet surfaced anywhere
      in the UI, and there's no YoY/trend read until the daily workflow (`data-fuel-prices.yml`,
      running since 2026-07-05) has accumulated enough committed snapshots to diff. Once ≥2 dated
      pulls exist, worth surfacing "diesel +X% since <date>" the same way `deltas.json` drives the
      Risk-trend card's sparklines. *(LOW, S, blocked on time — needs 2+ vintages)*
- [ ] **`renderHomeMacro()`'s new Fuel-prices row sits in the same card as "Key commodity moves"
      (World Bank) but has a structurally different vintage model** (daily point pull vs. monthly
      Pink Sheet) — today this is disambiguated only by the "Bangchak retail, daily" sub-label; if a
      3rd differently-cadenced macro source is ever added to this card, worth a shared "as of <date>"
      chip per sub-section instead of relying on prose alone. *(LOW, trivial, speculative)*

## Queue — follow-ups noticed 2026-07-05 (4)
- [ ] **Before picking a "stale UX gap" item from this backlog, `grep`/`git log -S` the claimed
      function name FIRST** — this cycle's audit found a 2nd instance (after the 2026-07-04 (9)
      audit found six) of a backlog entry describing a UI gap that was already shipped
      (`renderAcqVerdict()` for the objective-#2 rank-1 callout, live since `7fb5d5f`). A ~30-second
      grep before implementing would have caught it immediately; worth internalizing as a standing
      first-step for "UX gap noticed" items specifically, not just full backlog-hygiene passes.
      *(LOW, trivial, process note)*
- [ ] **`renderHomeThesis()`'s "strongest single opening" clause still doesn't distinguish the
      sequenced Road-to-3,000 plan (`EXPLAN.sequence[0]`) from the opportunity-score fallback
      (`OPPSCORE`) in its wording** — both render as "the strongest single opening is `<name>`" with
      no tag telling the reader which method produced it, unlike the "risk to watch" clause (now
      correctly distinguishes composite/DTI/crop-stress by construction). A small win once someone's
      touching this function again: only add the distinguishing word if a real ambiguity is reported
      — the two rarely disagree today. *(LOW, trivial, speculative)*
- [ ] **OAE outlook re-verification (from 2026-07-04 (7)/(8), still open)** — pull the current OAE
      (`catalog.oae.go.th`, REACHABLE per the reachability matrix) outlook note and confirm/update
      `docs/DATA_SOURCES.md`'s "OAE Dec-2025 outlook" sentence (rice+rubber=2026 RISK; cassava/palm/
      chicken/durian firmer) — now the oldest un-re-verified citation in that file across 3 cycles.
      Good next-cycle candidate: real network pull (no Thai-IP needed), small, closes a real audit
      gap rather than another cosmetic pass. *(LOW, S)*

## Done (most recent first)
- (loop will append here)
- **2026-07-05 (3) — ENRICH: live Bangchak fuel prices wired into the Home macro card.** New
  `pipeline/build_fuel_prices.py` projects the already-committed `source-data/fuel_prices.json`
  (real Bangchak retail pull, unwired since commit `ea93b96` this morning) verbatim into
  `platform/data/fuel_prices.json`; `renderHomeMacro()` gained a measured "Fuel prices" row (diesel
  = pickup/farm collateral, gasohol95 = motorcycle collateral). `--check`-gated (SKIP when the pull
  is absent), `validate_data.py`/`build_provenance.py` extended. Gate 50/0, `validate_data.py`
  426/426. Headless-rendered `index.html#home`: `data-errors="[]"`, live diesel ฿37.5/L + gasohol
  ฿37.45/L render under "Key commodity moves". Full writeup: `docs/DATA_REFRESH_LOG.md` (2026-07-05
  (3) entry).
- **2026-07-05 (2) — AUDIT: closed `docs/DATA_PROVENANCE.md`'s R1 provenance gap.** Every
  `platform/data/provinces/<slug>.json` (77 files) now carries its own `meta.generated_by` +
  `meta.provenance.{measured,editorial,estimated}` block naming every field's real source (PIP
  branches/POI, DIW factories, DLT vehicles, NSO workers/unemployment/income, deduped competitor
  census, editorial narratives) — mirrors `build_amphoe.py`'s existing pattern. `index.json`
  deliberately left a bare array (6+ frontend call sites fetch it directly as an array; wrapping it
  would be a breaking change for a docs-only gain). Zero data values changed — byte-diff confirms only
  the new `meta` key was added; `build_province.py --check` reproduces byte-exact. Gate: 47/0,
  validate_data 421/421. Headless-render of `province.html?p=rayong` was attempted 3x and failed each
  time under this sandbox's software WebGL (new follow-up logged above) — unrelated to this change
  (zero HTML/JS touched); the mandated `bash tests/run.sh check` gate is green. Full writeup:
  `docs/DATA_REFRESH_LOG.md` (2026-07-05 entry).
- **2026-07-05 — UX: structural household-leverage callout on the Exposure tab.** `renderRiskReadouts()`
  in `platform/app.js` gained a "Structurally riskiest · household DTI + unemployment" block (rank-1
  `PSTRESS_LIST[0]` from the already-MEASURED `province_stress_index.json`), inserted between "Most-
  stressed provinces" and "Riskiest branches". Reused existing `ccRow()`/`TAG_E` helpers and the
  existing `pstressHasData()`/`loadProvinceStress()` plumbing — no new data file, no new pipeline
  script, purely additive. Closes the 2026-07-03 (4)/(9) follow-up asking for this pattern on
  Exposure. Gate 47/0 (`validate_data.py` 421/421, unaffected — UI-only change). Headless-rendered
  `index.html#exposure`: `data-errors="[]"`, block renders real data (อำนาจเจริญ, DTI 1.14×,
  unemployment 2.8% NSO-measured, composite ▲98), no layout regression. Full writeup:
  `docs/PROGRESS_LOG.md` (2026-07-05 entry).
- **2026-07-04 (9) — AUDIT: backlog reconciliation, "Queue — UX / polish" had gone stale.** No code
  changed. Spot-checked the committee's quick-wins/bigger-bets list against the live app (headless
  renders of `#home`/`#map`/`#overview`/`#exposure`/`#acq` + `git log -S` on the claimed labels) and
  found 6 items already shipped in commits dated 2026-06-30/07-01 but never checked off: QW1 (map
  hero), QW2 (full-bleed canvas), QW3 (nav fix), QW5 (home verdict — since grown well past its
  original spec into a ranked decision queue), QW8 (Risk-trend baseline), and the "★ 2-col dashboards"
  bigger bet. Also found the separate "Composite expansion-opportunity score" enrichment item was a
  stale duplicate of the already-shipped `build_opportunity_score.py`/`opportunity_score.json`. Left
  genuinely-open items open (QW4/QW6 — both confirmed still outstanding and correctly owned by other
  workflows; "Reduce prose" — not independently verifiable either way, left as-is rather than
  guessing). A stale backlog risks a future cycle re-analyzing or re-building work that already
  shipped — this keeps the standing loop's queue trustworthy. `bash tests/run.sh check` unaffected
  (docs-only change): 47/0 before and after.
- **2026-07-04 (8) — AUDIT: closed the two remaining unsourced-catchment provenance gaps
  (`docs/DATA_PROVENANCE.md` R2/R3).** `rayong_catchment.json` and `chiang-mai_catchment.json`
  (180,000 real Overture building footprints each, commits `9482b0e`/`373b4f0`) shipped with
  **zero embedded `meta`** — source was known (git history) but a reader of the file couldn't tell.
  Added a real `meta` block to both (city/n_bldg/source/note/committed_in, same style as the
  already-provenanced `bangkok_catchment.json`) — zero building/geometry values changed, no
  fabrication (`n_bldg`/commit facts verified against `git log` before writing). Also caught that
  `bangkok_catchment.json`'s register row was itself stale (claimed "no source" when the file
  already has `meta.source`) — corrected the doc instead of the data. `PROVENANCE_EXEMPT` in
  `tests/validate_data.py` tightened (removed 2 entries that no longer need a blanket exemption);
  provenance gate now reads 276 sourced / 90 exempt (was 274/92). Gate: 47/0, `validate_data.py`
  421/421 (unchanged pass count — provenance-label fix, not a new check). `slim_catchment.py --check`
  confirmed unaffected. Full writeup: `docs/DATA_REFRESH_LOG.md` (2026-07-04 (8) entry).
- **2026-07-04 (7) — AUDIT: `docs/DATA_SOURCES.md` + `docs/DATA_PROVENANCE.md` quoting the
  pre-refresh (stale) World Bank Pink Sheet vintage, corrected to the already-committed 2026M06
  data.** No data value changed — both docs were still asserting Dec-2025 figures (rice −19.5%, gold
  +62.7%, vintage label `2025M12`) two days after commit `adf5494` had already regenerated
  `source-data/commodities*.json` / `platform/data/meta.json` to the real 2026M06 values. Every
  replacement number was copied verbatim from the already-committed source files (no external pull,
  no fabrication). Gate: `bash tests/run.sh check` 46/0 before and after (docs-only change,
  `validate_data.py` 265/265 unaffected). Full writeup: `docs/DATA_REFRESH_LOG.md` (2026-07-04 (7)
  entry).
- **2026-07-04 (4) — ENRICH: MEASURED building-density-within-10km layer (Overture, sitting unused
  since 2026-07-02) wired into the branch popup.** New `pipeline/build_branch_density.py` projects
  `source-data/perimeter_counts.json` (orphaned since commit `dda7816`, never consumed by any
  builder or `app.js`) → `platform/data/branch_density.json`; one new popup line, no new lens
  (scope discipline). Alignment safety verified by hand: `branches.json`'s `branches_fingerprint`
  at `dda7816` (2026-07-02) matches the fingerprint of today's `branches.json` exactly, despite two
  intervening data refreshes — the index alignment was never at risk. `validate_data.py` gained
  `check_branch_density()` (265/265, was 259/259); gate 46/0. Headless Playwright evaluation of the
  real in-page popup functions confirms branch #0 renders `buildings_10km=8, bucket=sparse_1_49`
  matching the data file exactly, zero JS errors. Full writeup: `docs/DATA_REFRESH_LOG.md` (2026-07-04
  (4) entry).
- **2026-07-04 (3) — VALIDATOR: `national_places.json` + `<city>_places.json` Overture "dense POI"
  layers gained data-integrity coverage.** These files (`build_national_places.py`/
  `build_scene_places.py`, shipped by concurrent 3D-lane workflows) had a determinism gate in
  `tests/run.sh` but zero sanity check in `validate_data.py`. New `check_national_places()` /
  `check_scene_places()` validate meta/bucket-taxonomy/bbox/point-order/point-count, SKIP-pass when
  absent. Caught a false-positive in development (module's tighter `TH_LAT_MIN=5.5` bbox constant
  wrongly flagged ~1,800 genuine near-border factory points at lat 5.40–5.47 as "wrong order"; fixed
  by using the same wider 5.0–21.0 bbox already used by `check_catchment_poi`/`check_lead_sites`).
  Pure test-file change, no `platform/data`/`pipeline` touched. Gate 45/0, `validate_data.py` 259/259
  (+2 checks). Full writeup: `docs/PROGRESS_LOG.md` (2026-07-04 (3) entry).
- **2026-07-04 (2) — AUDIT: `household-debt.js`'s `debtToIncome`/`stressIndex` mislabelled MEASURED,
  actually UNVERIFIED.** No CKAN/BOT resource id cited (unlike every other TMLI-vendored layer);
  values hand-grouped under narrative headers (same smell as the 2026-07-02 GPP catch); diverges
  10-20x from the fully-cited ratio the app already computes and ships
  (`household_risk_by_province.json`). Confirmed the unverified fields were never consumed downstream
  — caught before any fabricated-looking number reached the app. Corrected provenance in
  `ingest_tmli.py`/`source-data/tmli/PROVENANCE.md`/`docs/NEXT_STEPS.md`/`docs/DATA_PROVENANCE.md`;
  zero data values changed (diffed: meta-only). Gate 42/0, `validate_data.py` 224/224 (unchanged —
  this source layer sits upstream of the gated `platform/data` tree). Full writeup:
  `docs/DATA_REFRESH_LOG.md` (2026-07-04 (2) entry).
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
