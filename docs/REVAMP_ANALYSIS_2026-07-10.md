# Revamp Analysis — UX/UI + Data Enrichment
**For:** Kaustav, Corp Strategy Director · **Date:** 2026-07-10
**Basis:** three fresh recon sweeps this session (full UX/IA inventory of every route; a complete audit of all 303 data files / 72 layers; an enrichment-opportunity scan with live probes of reachable hosts) layered on the committee assessment's 13 adversarially verified findings (`docs/COMMITTEE_ASSESSMENT_2026-07-10.md`). Every count below was measured, not guessed; measured vs estimated is labelled throughout.

---

## 1. Bottom line

**UX:** the platform doesn't need a visual redesign — it needs *consolidation*. It has grown to 10 routes + 3 standalone 3D pages, ~180 render functions, and **11 boards that render the same fact in two or more places** from three competing "answer" models. The revamp is: one canonical answer per question, four destinations instead of ten, every fact rendered once, and the styling pulled out of JavaScript (431 inline styles) back into the stylesheet.

**Data:** the estate is large (72 layers: 29 measured, 37 estimated, 6 unlabelled, 1 synthetic) but under-exploited. Measured data is sitting on disk unsurfaced — peer NPLs, the national labour battery, 164 mirrored DLT files no builder reads — while several exec surfaces still run on GLOBAL price proxies although MEASURED Thai farm-gate prices are committed. The enrichment plan is: surface what we already have (zero network, days), pull the verified new taps (OAE second-rice-crop yields — the drought detector the committee said was missing; ThaiWater flood telemetry), then build the product-mix layer, with the real loan tape remaining the single highest-leverage owner-side unlock.

---

## 2. PART I — UX/UI revamp

### 2.1 Diagnosis (measured)

**a. Three competing answer models, surfaced simultaneously.**
"Where do we open next" is answered by `expansion_plan.json` (sequenced), `opportunity_score.json` (composite), and `amphoe.json` raw white-space — with identical "Open next:" wording for two of them on the same #acq screen (committee-CONFIRMED). "Which province is riskiest" is answered three ways on one Home screen (`province_stress_index` vs `household_risk` vs `province_risk`).

**b. Duplication instead of hierarchy.**
11 board families render on ≥2 routes from the same file: white-space tables (#home + #acq), commodity board (#home + #overview + #trend), opportunity score (#home + #acq), Road-to-3,000 (#home + #acq), risk readouts (#home + #exposure), crop stress (4 routes), collateral outlook, competitor coverage, contested ground, regional outlook, deltas. Every duplicate is a chance for the label/number drift the committee caught (MEASURED-vs-ESTIMATED on the same score; 87.5% vs 86.8% household debt side by side).

**c. Navigation shape doesn't match how the platform is used.**
The top nav has 7 tabs + a "More ▾" dropdown, with two entries pointing at the same route (`#provinces` appears as both "3D map" and "Provinces"), and the Simulator/Market/Branches buried in the dropdown. Standalone 3D pages have return-only navs. The exec path the platform is designed around (Home → answer → evidence) competes with a flat 10-tab layout.

**d. Weight concentrated in the wrong place.**
Home is the heaviest route (~20 data fetches through `renderHome`); #map lazy-fetches up to 15+ layer files across its 22 lenses. app.js is 5,606 lines / 374KB serving all routes. No single function is oversized (largest ~110 lines) — the sprawl is breadth, which is a *consolidation* problem, not a refactor problem.

**e. Style system has drifted into JS.**
431 `style=` occurrences in app.js template literals + 69 in index.html + two conflicting `:root` blocks in styles.css (legacy dark `#0a0e17` vs canonical `#121826`). And the site defaults to **light** theme while CLAUDE.md and the palette describe a dark instrument console — the light theme is the override that has already produced one user-reported bug (invisible grey text).

**f. Reliability and payload (committee-CONFIRMED).**
Leaflet + deck.gl load only from unpkg.com — one CDN hiccup kills the National map and blames the data files. 74 of 77 province 3D scenes stream ~35MB of uncompressed JSON from R2 with no compression and no cache headers, on what is now the PRIMARY click path from two tabs.

### 2.2 Target information architecture

Reshape ten routes into **four destinations plus evidence pages**, aligned one-to-one with how the platform is actually questioned:

| Destination | Question it answers | Absorbs (today's routes) |
|---|---|---|
| **Command center** (`#home`) | "What do I do this week?" | #home, slimmed: verdict + queue + ONE row per theme, each row a link — no full tables |
| **Risk** (objective #1) | "What's getting riskier, where, and what-if?" | #overview's risk half + #exposure + #trend + #sim as sub-sections of one page with a sticky section nav |
| **Expand** (objective #2) | "Where do we open, against whom?" | #acq + #market + the competitor boards; ONE canonical "Open next" (sequenced plan), other rankers renamed to lenses |
| **Map & Explore** | "Show me the ground truth" | #map + #provinces + #branches + the 3D pages, cross-linked as drill levels: national → district → province 3D → branch 3D |

Principles the IA enforces:

1. **One fact, one renderer.** Each board family gets a single render function and a single home; Home shows only the top line of each with a deep link. This removes the entire class of committee findings 2–7 (same fact, two labels/values) structurally, not by patching copy.
2. **One canonical model per question.** Sequenced plan = "open next"; composite + raw white-space become explicitly named *lenses* on the Expand page. The DTI+unemployment composite = "riskiest province"; raw DTI and branch-composite become labelled secondary reads.
3. **Objectives bookend every page.** Risk page leads with crop-household stress (objective #1's readout, currently buried at 91% page depth); Expand leads with the sequenced plan. Illustrative boards (recovery sensitivity) always last, always labelled.
4. **Provenance chips rendered from data, not copy.** One shared `tag(meta)` helper that reads each layer's own meta stamp — the label can't drift per-tab because it isn't hand-written per-tab.

### 2.3 Design-system consolidation

- **One `:root`.** Delete the legacy block; keep the canonical palette (accent `#5B7CFA`, agri `#E0574F`, merchant `#23A28F`, collateral `#8E63E8`, gold `#E6B450`).
- **Decide the default theme once.** Recommendation: keep light as default (Kaustav uses it; it produced the readability bug precisely because it's the less-tested override) but promote it to first-class: every color in app.js goes through a CSS var, no raw hex in JS.
- **Kill inline styles by class extraction.** The 431 inline styles collapse into ~15 utility classes (`.num`, `.pos`, `.neg`, `.est`, `.meas`, `.dim`, `.right`, …). Mechanical, and it makes theme correctness automatic.
- **Reliability:** vendor Leaflet (148KB) + deck.gl (~1.6MB) into `platform/vendor/`; split the `boot()` error message by cause. Pre-gzip the R2 catchments (~4MB each, 8–10× smaller) with `DecompressionStream`.

### 2.4 UX delivery phases

| Phase | Content | Effort | Visible change |
|---|---|---|---|
| **P0 — trust** | Committee fixes 1–8: vendor libs + error split, canonical "Open next", provenance flip, coverage copy, macro de-dupe + single source, gold-firming caption, zero-state cards, Home bridging clause | ~2 sessions | The contradictions a board member would catch are gone |
| **P1 — IA consolidation** | 4-destination nav; merge Risk (overview-risk/exposure/trend/sim) and Expand (acq/market); dedupe the 11 board families to single renderers; Home slims to verdict + queue + links | ~3–4 sessions | Ten tabs become four; Home loads fast; every fact appears once |
| **P2 — design system** | Single `:root`, utility-class extraction of inline styles, shared provenance-chip helper, favicon, empty-state copy sweep | ~2 sessions | Light/dark both provably correct; styling maintainable |
| **P3 — 3D performance** | Gzipped R2 catchments + cache headers; optional-layer manifest (stop the 404s); PMTiles path continues in parallel | ~1–2 sessions + desktop upload | Province 3D loads in seconds on Thai mobile, not tens of MB |

---

## 3. PART II — Data enrichment

### 3.1 Estate audit (what we have)

- **303 files → 72 layers: 29 MEASURED / 37 ESTIMATED / 6 unlabelled / 1 SYNTHETIC** (per the auto-generated provenance census). "Estimated" almost always means *derived score over measured inputs* — the honest pattern; the issue is coverage and freshness, not fabrication.
- **Granularity:** strong at branch (23 index-aligned layers) and district (8 layers over 928 amphoe); province layers carry the measured government backbone (SES income/debt 2566, DLT fuel/vehicles 2026-02, DIW factories 2026-07); time dimension is young (2 snapshots).
- **The one synthetic:** `loan_tape_derived.json` — clearly stamped, surfaced on #exposure/#trend, replaceable the day a real export lands (contract ready in `pipeline/loan_tape_schema.md`).
- **Hygiene gaps:** 6 unlabelled layers (`branches.json`, `meta.json`, `deltas.json`, `snapshots_index.json`, `provinces/index.json`, `rayong_province.json`) need meta stamps; `rayong_province.json` is legacy dead weight.

### 3.2 The waste: measured data we hold but don't use

1. **`peer_npl.json`** (MEASURED, 2026-06): three peer lenders' reported NPLs — the natural benchmark strip for the Risk page. Committed, surfaced nowhere.
2. **`ilostat_labour.json`** (MEASURED, pulled 2026-07-10): national employment by sector, informality 63.2%, unemployment — no builder consumes it, so the informal-worker borrower base (the core title-loan demographic) never reaches the UI, while `occupation_risk`/`macro_exposure` run on *estimated* sector weights it could anchor.
3. **DLT mirror, 9 of 14 datasets untouched** — 2 substantive: `stat_1_005` (driver licenses by province, 123 files) and `stat_1_010` (transport-operator licenses, 41 files). Plus `stat_1_009` (transport-vehicle registration actions, 50 files) is only partially distilled — the commercial-fleet flow (logistics-SME borrower pulse) is unbuilt.
4. **Thai farm-gate prices vs GLOBAL proxy:** `nabc_prices.json` + `crop_prices.json` (both MEASURED, Thai) are committed, but the Overview commodity board, `collateral_outlook`, and `macro_sensitivity` still run on World Bank GLOBAL prices. `branch_agri` already made the swap — finish the job for the other three surfaces.
5. **`gpp_by_province.json`** — quarantined (76/77 rows uncited); stays out until the NESDC pull (owner-side) replaces it.

### 3.3 New taps verified reachable this session (Wave 12, recorded in `docs/CKAN_SOURCES.md`)

| Tap | What it gives | Objective | Effort |
|---|---|---|---|
| **OAE per-province crop production/yield CSVs** (`dataoae1104` rice verified, incl. **second-crop นาปรัง 2568**; siblings for maize/cassava/rubber/palm) | The measured "did the irrigated second rice crop get cut" detector — exactly the gap in the committee's Central/West drought finding; also refreshes the stale crop-mix vintage and can extend crop_stress beyond 3 crops (the sugar-belt blind spot) | #1 | S/M |
| **ThaiWater water-level/flood telemetry** (`waterlevel_load` verified: storage %, flood tiers) | The flood-side twin of the live rain pulse; joins the existing 6-hourly CI job | #1 | S |
| **3 new ILOSTAT series** (self-employed counts, informality by sector, employees by sector — all verified returning THA data) | Deepens the labour battery; self-employed = the title-loan core segment | #1 | S |
| **DLT refresh** (when the intermittent window opens) | Feb-2026+ monthly brand file (current one is an upstream stub) + new vehicle-flow months | #1 | S |
| **OAE farmer-family registrations** (PDF, likely per-province) | The honest denominator: branches per 10k farm households | both | M |
| **DIW refresh + EEC class-3 factories** | Keeps the 67k-factory layer fresh; EEC exposure detail | #1/#2 | S/M |
| **Google Places pawnshop census** (needs key + quota) | The competitor-adjacent layer OSM can't provide (~4 pawnshops nationally in OSM) | #2 | M |

Dead ends re-confirmed and recorded (do not re-probe): OAE drought-warning is a PowerBI embed with no data resource; DLT operator licenses national-only; NSO hosts all sealed — ILOSTAT remains the only labour tap.

### 3.4 Owner-side unlocks (need your Thai IP / keys / exports), ranked

1. **Real loan tape** — contract ready; flips 4 SYNTHETIC outputs to MEASURED and, uniquely, **calibrates every estimated risk score on the site against actual arrears**. One export from your side; small pipeline effort. This is the single highest-leverage data action available to the project.
2. **NESDC per-province GPP** (data.nesdc.go.th, 502 from cloud) — un-quarantines GPP as a measured layer.
3. **NSO SES/LFS refresh** — the DTI backbone is SES 2566; a newer vintage moves every leverage read.
4. **BoT sub-scale lender registry** — turns exit-whitespace from inferred to measured ahead of the Q1-2026 registration deadline.
5. **DLD livestock / DOF fisheries** — province-precise livestock for agri-PD.
6. **OpenRouteService key** — true 15-min isochrones for the catchment scenes.

### 3.5 Enrichment delivery waves

| Wave | Content | Network | Effort |
|---|---|---|---|
| **E0 — use what we hold** | Surface peer_npl on Risk page; ILOSTAT builder + "informal-worker base" card; distill `stat_1_009` → commercial-fleet flow; swap NABC/OAE Thai prices into commodity board + collateral_outlook + macro_sensitivity; drought-watch flag; ex-gold collateral leg; inherit DTI into district risk_proxy; stamp the 6 unlabelled layers | none | ~2 sessions |
| **E1 — verified new taps** | OAE production/yield puller (second-crop detector + sugar/cassava extension of crop_stress); ThaiWater flood pulse into the 6-hourly CI; +3 ILOSTAT series; DIW refresh | reachable now | ~2 sessions |
| **E2 — product layer** | `branch_product_mix.json` (workforce est × fleet measured × SES income measured → per-branch "what to sell", with EV-income caveat); merchant/SME rec rule; crop calendar (static OAE months) → agri-season timing | mostly none | ~2–3 sessions |
| **E3 — owner-side** | Loan tape ingest `--real`; NESDC GPP; NSO refresh; sub-scale registry | your side | S each, once data lands |

---

## 4. PART III — One sequenced program

Interleaving the two tracks so every sprint ships something the exec can see:

1. **Sprint 1 (trust):** UX P0 + data-hygiene stamps. *Outcome: zero visible contradictions; every layer self-labelled.*
2. **Sprint 2 (consolidate + use-what-we-hold):** UX P1 (four destinations, dedupe) + E0. *Outcome: four-tab platform; Thai farm-gate prices behind every commodity number; peer NPL benchmark; drought-watch live.*
3. **Sprint 3 (new data + design system):** E1 + UX P2. *Outcome: second-rice-crop detector + flood pulse on the Risk page; styling provably correct in both themes.*
4. **Sprint 4 (product + 3D):** E2 + UX P3. *Outcome: "what should this branch sell" answered per branch — the committee's biggest identified gap — and province 3D usable on mobile data.*
5. **Continuous:** E3 whenever your exports land; DLT/DIW refresh crons already in CI.

**The two asks that only you can action:** (1) the loan-tape export per `pipeline/loan_tape_schema.md`; (2) merge PR #2 so the scheduled feeds (rain pulse cron, census refresh) run on master.
