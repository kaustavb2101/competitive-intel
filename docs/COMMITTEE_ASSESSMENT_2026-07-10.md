# Platform Assessment — Committee Chair Report
**For:** Kaustav, Corp Strategy Director · **Date:** 2026-07-10 · **Basis:** 13 adversarially verified (CONFIRMED) findings + 7 unverified low-severity notes. Every number below was read from the committed data or a live headless render; measured vs estimated is labelled throughout.

---

## 1. Bottom line

The platform's data and logic are healthy — all 10 routes render clean, the simulator math checks out, and the three big risk stories (Isan leverage+drought, the Central drought pocket, the pickup-collateral squeeze) stand on measured government data. The problem is trust presentation: the site currently gives **two different "open next" answers on the same page**, labels the **same white-space score MEASURED on one tab and ESTIMATED on another**, and shows **"141% coverage" on a card that calls itself a lower bound** — exactly the contradictions that erode confidence with a board audience. One reliability hole needs fixing before anything else: the entire National map dies if one third-party CDN (unpkg.com) hiccups, and the error message blames your own data files.

---

## 2. UX / coherence fixes, ranked by impact (all CONFIRMED)

| # | Problem | Concrete fix |
|---|---|---|
| **1** | **One flaky CDN kills the National map and blames the wrong thing.** Leaflet and deck.gl load only from unpkg.com (index.html:11, 617; rayong-catchment.html:10). With the CDN blocked, #map shows "Couldn't load data files… (ReferenceError: L is not defined)" — the data loaded fine. Verified both ways: CDN blocked = dead map; CDN served = all 2,015 markers render. | Vendor the two libraries into `platform/vendor/` (leaflet 148KB + deck.gl ~1.6MB, static-deploy friendly), and split the `boot()` catch in app.js (~1104) so a library failure says "map library failed to load", not "data files missing". |
| **2** | **Two contradictory "Open next" verdicts on one screen (objective #2, the core question).** #acq shows "Open next: วัฒนา — 83/100" (opportunity_score.json, top = Vadhana 82.5) at the top and "Open next: Ko Pha-Ngan is placement #1 of 985" (expansion_plan.json) below. Home hero also says Ko Pha-Ngan. | Make the sequenced plan canonical (it models cannibalization + risk; the code's own comment at app.js:5203 calls it "purpose-built"). Rename the composite card to "Highest-composite district: วัฒนา — different lens, see method" so it can't be read as a placement instruction. |
| **3** | **Same score, opposite provenance labels.** amphoe white-space is tagged MEASURED on the map lens and branch popup (app.js:14, 4506-4509) but ESTIMATED on Home, #acq, and both CSV exports (`whitespace_score_est`). Ground truth: it's a derived 0–100 score over measured inputs — ESTIMATED is the honest call. | Flip LENS.dws tag 'm'→'e' and reword the popup rows to "est (measured inputs)". One-line change in two places. |
| **4** | **"141% coverage" on a "lower-bound" card.** Home says "Located 16,503 of ~11,684 rival branches — lower-bound census — 141%". Cause: Srisawad's expected 1,138 is the listed entity only; the locator found the whole group (5,203, 457%). The explanation exists only on #market, and even there the header still says "a lower bound". | Fix the Srisawad expected figure (or null it) in `build_competitor_coverage.py`; when coverage ≥100%, switch Home copy to "network fully located for 3 of 4 brands — Heng still a sample"; drop "lower-bound" wording wherever >100% shows. |
| **5** | **Two household-debt and two inflation numbers on one Overview page** — 87.5%/-0.13% (BIS/WB) vs 86.8%/~0.3% (editorial meta.json), rendered into the same grid. Verification also caught a bug: the BIS cards get **appended twice** (idempotency bug in renderMacroIndicators, app.js:1121-1136). | De-dupe the append (guard before insertAdjacentHTML), then source META.macro from the same regional_outlook feed or drop the editorial cards. |
| **6** | **"Recovery value firming" directly above "vehicle-title collateral under pressure."** The firming index (+0.14, 71/77 provinces) is gold-driven (+26.1% YoY global gold applied nationally); strip the gold term and the same index reads **-0.125 = softening** — matching the ↓ rows below. AutoX lends against vehicle titles, not gold; the code comment says so. | Show the ex-gold vehicle-title leg on Home (it computes to softening), or caption the firming row "gold-pawn tailwind dominates the index — vehicle-title legs below still point down". |
| **7** | **Home shows three different #1s with no bridge** — thesis/hero: Ko Pha-Ngan (sequenced plan); underserved-districts card: Vadhana ★64 (raw white-space); and on #acq the two Road-to-3,000 models disagree on regional totals (headroom: Isan +247 biggest; sequenced: North +300 biggest). | Add one clause to the Home white-space card: "sequenced plan opens Ko Pha-Ngan first — raw white-space ranks Vadhana; different lenses, see Acquisition." |
| **8** | **Red "0.0%" high-stress cards that carry no signal.** Worst province this vintage is 20.8/100 vs the 45/100 line, so #exposure shows "High agri-PD proxy 0.0% — 0 of 2,015" in risk-red and #sim's baseline says "0 provinces". Verification found **two** independent always-zero thresholds (branch a≥60 on #exposure; province ≥45 on #sim). Sim logic itself is fine (worst-case drive → 7 provinces, 311 branches, 15.4%). | Zero-state copy for both spots: "No province above the 45/100 line today — worst is Ubon at 21/100", coloured neutral/green, or switch to a per-vintage percentile threshold. |
| **9** | **Every un-shipped province 3D scene pulls ~35MB of uncompressed JSON** from R2 (nan = 36,837,296 bytes, no Content-Encoding even when the browser asks, no Cache-Control). 74 of 77 provinces hit this path, and it's the PRIMARY 3D click from Provinces and Market. | Store pre-gzipped `.json.gz` in R2 (~4MB each) + DecompressionStream, or front the bucket with a real Cloudflare zone. PMTiles supersedes this long-term. |
| **10** | **Overview is 14 boards / ~18 phone screens (15,116px at 390px)**, with the objective-#1 crop-stress readout at 91% of page depth, below an illustrative board. | Group the 3 vehicle/EV boards under one "Collateral & the EV wave" heading with `<details>` expanders (pattern already on #acq); move Crop-household stress above the collateral cluster. |

**Unverified low-severity (not adversarially checked; quick wins):** rewrite the 8 empty states that name Python scripts to the compliant app.js:1748 pattern; add a favicon and stop the two expected-404 optional-layer fetches; reconcile the 15 branches dropped by the amphoe join (2,000 vs 2,015) in build_amphoe.py; align Home's three "riskiest province" verdicts (DTI 1.14× Amnat Charoen vs 1.15× Khon Kaen three cards apart reads like a typo). One positive on record: all 10 routes clean in light+dark at 390px, no overflow, all 58 data fetch targets present.

---

## 3. OBJECTIVE A — Where the economy hits the book (ranked, verified)

**Area 1 — Isan leverage + drought double bind (~192–231 branches, HIGH).**
The highest MEASURED household debt-to-income in the country is all Isan (NSO SES 2566): Khon Kaen 1.15, Amnat Charoen 1.14, Udon Thani 1.05, Ubon 1.00, Maha Sarakham 0.99 — debt exceeds annual income outright in three provinces. The same region holds the top crop-stress provinces: Ubon #1 (agri_stress 20.8/100, rain 79.2% of normal, 46 branches), Roi Et #2 (19.8, rain 70.5%, 39 branches). Amnat Charoen is #1 on the composite structural-stress index (98.05) and puts 3 districts in the national top-10 riskiest amphoe. Ubon+Roi Et+Surin+Sisaket+Buriram+Maha Sarakham = 231 branches. The only cushion is rice at +17.9% YoY (MEASURED, NABC): with debt ≥ income, any yield shortfall goes straight to collections. Verifier caveats: the overlap is directional, not literal (Khon Kaen tops DTI but not crop stress), and the six-province branch count depends on which six you pick. **Action: collections-watch tier — tighter LTV on agri-income borrowers, earliest-contact collections, monitored against Risk-trend deltas each vintage.**

**Area 2 — Central/West drought pocket: the driest measured belt is NOT Isan (HIGH).**
Worst 3-month rainfall anomalies: Ratchaburi 56.3% of normal (drought 1.0, 27 branches), Samut Songkhram 56.6%, Samut Sakhon 56.9%, Samut Prakan 59.0% (40 branches), Suphanburi 61.9% (99% rice mix, 22 branches), Bangkok 65.1% (170 branches), Chonburi 67.1% (103 branches). These are also the most rice-price-sensitive clusters nationally (macro-sensitivity: Suphanburi 11.0, Chainat 10.7, Ratchaburi 9.0 — top 3; ESTIMATED proxy over measured inputs). Today's read: water-stressed but income-cushioned by the rice-price tailwind — the risk crystallizes if the irrigated second rice crop is cut. The gap: drought currently only feeds the province agri_stress blend, so a tailwind price hides a 56%-of-normal rain reading (Suphanburi's stress score is just 10/100 despite drought 0.95). **Action: the drought-watch flag in section 5.**

**Area 3 — National collateral: the pickup squeeze (HIGH, forward-looking).**
MEASURED DLT first registrations: pickups 234,909 (2022) → 99,984 (2025), **-57%**; Isuzu pickups -71%. Pure-EV share of new registrations 0.2% → 3.8% → 10.4% YTD Jan 2026 (ESTIMATED brand classification over measured counts; BYD is the #4 brand). The registered fleet is still only 0.95% BEV (MEASURED, 2026-02), so this is a **forward resale-value squeeze on used diesel pickups** — the higher-recovery title collateral — not a current default event. Most resale beta where fleets are diesel-heavy: Nong Bua Lamphu 37.7%, Chaiyaphum 35.7%, Khon Kaen 32.3% (all Isan — compounding Area 1). **Action: the diesel-pickup LTV lever in section 5.**

---

## 4. OBJECTIVE B — Demographics → product mix by region

Inputs and labels: workforce mix = ESTIMATED (branch_workforce.json's own meta: "reflective mix, not a census"); vehicle fleet mix = MEASURED (DLT stock by province); DTI = MEASURED (NSO SES 2566). Debt-to-income and stress_index in the older household_debt file are self-flagged UNVERIFIED — use only the SES-sourced file.

| Region (branches) | Who's around the branch (est. workforce) | What they drive (MEASURED fleet) | Leverage (MEASURED median DTI) | Product read |
|---|---|---|---|---|
| **Isan (601)** | Agriculture 41.2%, factory 14.4% | Moto 57.0%, pickup 19.0% (highest pickup share) | **0.92** (max 1.15) | Agri-cycle moto-title + pickup-title core. Highest leverage + highest diesel fleet = both Area 1 and Area 3 land here. Underwrite to crop calendar; collections-watch tier. |
| **East (273)** | **Factory 46.4%** — the factory-worker region | Moto 60.3%, car 24.7% | 0.62 | Salaried factory-worker moto- and car-title. Caveat (unverified but sourced): auto-sector workers concentrate here and peri-BKK (Samut Prakan 46,672, Rayong 11,299, Chonburi 9,131 — MEASURED DIW); if ICE-parts employment contracts, this borrower base weakens **before** the collateral does. |
| **Central&BKK (580)** | Food service 17.1%, factory 16.7%, retail 10.0% — merchant-tilted | **Car 42.2%** (vs ~24% elsewhere), moto 43.8% | **0.47** (lowest) | Merchant lending + car-title. Lowest household leverage but heaviest competitor density (Vadhana: 7 rivals ≤5km) — a margin/competition play, not a risk play. Also sits in the Area-2 drought belt for its rice fringe. |
| **North (311)** | Agriculture 22.2%, hospitality 11.9% — most mixed | Moto 58.3%, pickup 18.0% | 0.69 | Blended agri/tourism moto-title. Note the sequenced Road-to-3,000 plan allocates its biggest headroom here (+300). |
| **South (250)** | Agriculture 36.6% (rubber/palm), hospitality 9.6% | **Moto 61.2%** (highest), car 23.8% | 0.61 | Agri-moto core plus the tourism expansion frontier (Ko Pha-Ngan is sequenced placement #1). Moto-title-heavy = most exposed to the used-motorcycle price leg already flagged ↓ on Home. |

Standing rule for any product-mix layer built from this: carry per-input provenance in meta (vehicle mix MEASURED-province / workforce ESTIMATED-10km / income MEASURED-SES / debt = debt_per_household only).

---

## 5. Build recommendations, smallest first

1. **Copy-only fixes (hours):** provenance flip (fix #3), "Open next" rename + Home bridging clause (#2, #7), coverage ≥100% copy (#4), zero-state high-stress cards (#8), gold-firming caption (#6), the 8 script-naming empty states, favicon.
2. **Two small bugs:** de-dupe the double-appended BIS macro cards (app.js:1121-1136) and fix Srisawad's expected count in `build_competitor_coverage.py` (#4, #5).
3. **Vendor Leaflet + deck.gl into `platform/vendor/` and split the boot() error message** (#1) — the single biggest reliability fix; ~1.7MB of static files.
4. **Overview restructure** (#10): one "Collateral & the EV wave" group with `<details>` expanders, crop stress moved above it — layout only, no data change.
5. **Drought-watch flag** (Area 2): new field in build_crop_stress.py — crop mix >90% rice AND rain <65% of normal — surfaced as a branch-popup line and a #trend list. Small, uses committed data only.
6. **Ex-gold vehicle-title outlook leg** (fix #6): one extra field in build_collateral_outlook (the formula already isolates it; nationally it computes to -0.125 softening), rendered on Home.
7. **Gzip the R2 catchments** (#9): pre-compress to `.json.gz` (~4MB/province) + DecompressionStream in rayong-catchment.html; interim until PMTiles.
8. **Diesel-pickup LTV lever in #sim** (Area 3): key a recovery-haircut slider to each province's MEASURED diesel_pct (ev_penetration.json is already loaded for #overview, never for #sim).
9. **`branch_product_mix.json`** (Objective B): join workforce mix (est) × fleet mix (measured) × SES income/debt (measured) into a per-branch product recommendation layer, with the EV-transition income caveat tagged on factory-dominant branches in top-decile auto-worker provinces — the largest build, and the one that turns section 4 into a shippable tab.
