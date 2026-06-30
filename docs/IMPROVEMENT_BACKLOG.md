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

## Queue — enrichment / capabilities (serve the two objectives)
- [ ] **★ Household debt-to-income RISK LENS (National map) — objective #1, MEASURED, now unblocked.** The TMLI
      bridge landed `source-data/household_debt_by_province.json` + `household_income_by_province.json` (real NSO
      SES). Two steps: (1) project a province→{debt_to_income, stress_index} lookup into `platform/data/` (a small
      `household_risk_by_province.json` via a deterministic --check'd step, or fold into derive.py) with full
      provenance; (2) add a National map lens that colours each branch by its province household leverage,
      labelled MEASURED · NSO. Graceful when absent. The standout measured-risk view no competitor has. *(HIGH, M)*
- [ ] **★ Surface the opportunity score on the Acquisition tab — objective #2.** `platform/data/opportunity_score.json`
      (928 districts) is merged but not yet shown. Render the ranked where-to-open-next leaderboard (top districts +
      per-component breakdown: whitespace / competitor-gap / agri-stress) on #acq, labelled ESTIMATED COMPOSITE. *(HIGH, M)*
- [ ] **Composite expansion-opportunity score** per district — combine white-space + dominant occupation +
      competitor density + crop-stress into one rank for "where to open next". Graceful absent. *(high, M)*
- [ ] **Occupation × risk cross-read** — once `branch_occupations.json` is present, flag branches whose
      borrower base is concentrated in a stressed sector (factory-heavy + industrial slowdown). Graceful absent. *(high, M)*
- [ ] **Competitor coverage QA panel** — found-vs-expected per brand so the lower-bound caveat is explicit
      (Srisawad ~11%, MTC ~14%, Tidlor ~37%, Heng ~35%). *(med, S)*
- [ ] **NSO census occupation distiller** scaffolding in `ingest_gov.py` (code only; drop-in when the
      data.go.th pull lands) — improves data availability. *(med, M)*
- [ ] **Expand `validate_data.py`** coverage as new data layers land. *(med, S)*
- [ ] **Simulator: occupation-sensitivity lever** — model borrower-base exposure to a sector shock. *(med, M)*

## From the research digest (docs/RESEARCH_DIGEST.md — all cited)
- [ ] **★ Model the BoT 28% title-loan rate cap** in the Simulator (effective 2 Dec 2025). Add a lever/scenario
      showing book yield + which segments compress at 28%. Real regulatory constraint (obj #1). *(HIGH, M, sandbox)*
- [ ] **Competitor-exit white-space cue** — non-compliant operators must register by Q1 2026 or exit; surface
      districts where sub-scale rivals may exit as fresh white-space (obj #2). Uses existing competitor census. *(MED, M)*
- [ ] **Rice/rubber + drought "double-stress" flag** in crop_stress / district risk — research shows rice+rubber
      prices softening AND >80% El Niño drought prob mid-2026; flag districts with both (obj #1). Uses existing
      crop_stress signals, label estimated. *(MED, M, sandbox)*
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

## Done (most recent first)
- (loop will append here)
