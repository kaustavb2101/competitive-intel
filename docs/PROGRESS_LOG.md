# PROGRESS LOG — AutoX / เงินไชโย Credit Intelligence

Reverse-chronological. Most recent first. "Decision" entries explain *why* a path was taken so you
don't re-litigate settled choices.

---

## 2026-07-06 (2) — UX: "Most contested ground" rank-1 fact ported to the Home command center (objective #2)

Loop cycle. Audited the standing "any other Exposure-only rank-1 callout still missing from Home?"
follow-up (2026-07-05 (8)/2026-07-06 backlog note) by comparing `renderRiskReadouts()` (`#exposure`)
against `renderHomeRisk()`/`renderHomeWhitespace()` (`#home`) block-by-block. Found Home's risk card
already has parity or a superset on every objective-#1 (risk) callout — but on the objective-#2
(expand) side, Exposure's "Most contested ground" table (`renderContestedGround()`, MEASURED WorldPop
2020 × merged rival census, `data/contested_pop.json`) had no equivalent anywhere on Home: the
whitespace card only ever named *where there's open space*, never *where we already fight a rival for
the same catchment population* — the natural flip side of the same signal, and a real portfolio/
expansion-risk fact (a branch that is "open" but heavily contested is a weaker opening than the
white-space score alone suggests).

`renderHomeWhitespace()` (`platform/app.js`) gained a "Most contested ground" row (rank-1 branch off
`CPOP.top[0]`, same measured tag/pattern as the existing competitor-coverage row right above it);
wired `loadContestedPop()` into Home's lazy-load chain (`renderHome()`'s `homeBooted` block, calling
the existing `reHome` re-render helper already used for the other white-space-card loaders) — null-safe,
renders nothing until/unless `contested_pop.json` loads. Zero new data file, zero new pipeline script,
pure reuse of plumbing that's been live on Exposure since the file shipped. `node --check app.js` clean;
gate `bash tests/run.sh check` 53/0 (`validate_data.py` 433/433, unaffected — UI-only change).
Headless-rendered `index.html#home`: `data-errors="[]"`, DOM dump confirms the new row renders with
real measured data (เงินไชโยสาขาอินทามระ ซอย 4, Bangkok, 100% of a 4.59M-person catchment contested) right
after "Competitor coverage" in the white-space card, no layout regression. Full diff: `platform/app.js`
(+13 lines, 2 call sites).

## 2026-07-06 — UX: lowest-paid-occupation-nationally fact ported to the Home command center (objective #1)

Loop cycle. Closed the 2026-07-05 (8) backlog follow-up: `#exposure`'s "Lowest-paid occupation
nationally" callout (`occupation_income.json`, NSO SES 2566, measured) had no equivalent on `#home`,
even though Home's risk card already follows the exact same rank-1-surfacing convention used for
`PSTRESS_LIST[0]`/`HHRISK_LIST[0]`. `renderHomeRisk()` (`platform/app.js`) gained the identical row
(Transport ฿18,547/mo avg, worst แม่ฮ่องสอน ฿6,713/mo) placed right after the "Structurally riskiest ·
DTI + unemployment" row; wired `loadOccupationIncome()` into Home's lazy-load chain
(`renderHome()`'s `homeBooted` block) so it re-renders once the file lands, null-safe when absent
(`occincHasData()` guard, matches the pattern already used everywhere else on this page). Zero new
data file, zero new pipeline script — pure reuse of already-shipped plumbing. `node --check app.js`
clean; gate `bash tests/run.sh check` 53/0 (`validate_data.py` 433/433, unaffected — UI-only change).
Headless-rendered `index.html#home`: `data-errors="[]"`, new row renders with the real measured
values under "What is getting riskier", no layout regression (screenshot confirmed). Full diff:
`platform/app.js` (+12 lines).

## 2026-07-05 (7) — ENRICH: national lowest-paid-occupation callout on Exposure (objective #1)

Loop cycle. Closed the 2026-07-03 (7) backlog follow-up: `province.html`'s "Income by occupation"
panel (NSO SES 2566, per-province) had no national-level read — a reader had to open all 77
province pages to notice which occupation category is structurally the lowest-paid nationally.

New `pipeline/build_occupation_income.py` projects the already-committed, already-MEASURED
`source-data/household_income_by_province.json` into `platform/data/occupation_income.json`: for
each of the 5 occupation categories, the unweighted national average monthly income plus the
single lowest/highest-paying province (a concrete worst case, not just the mean), sorted
worst-first. Pure aggregation of already-MEASURED data — no modeling, no new source. Absent-state
degrades gracefully (empty `categories`, `meta.absent=true`) if the source file is ever missing.

`renderRiskReadouts()` on `#exposure` (`platform/app.js`) gained a "Lowest-paid occupation
nationally" callout right after the existing DTI+unemployment "Structurally riskiest" block, same
rank-1-surfacing pattern, lazy-loaded via `loadOccupationIncome()`/`OCCINC_LIST`, null-safe. Live
data: **Transport** is the lowest-paid occupation nationally, ฿18,547/mo average — worst case
แม่ฮ่องสอน (Mae Hong Son) at just ฿6,713/mo. A concrete fact, not an abstract index, per CLAUDE.md's
"concrete not abstract" preference.

`--check`-gated in `tests/run.sh` (new `build_occupation_income.py --check` line, SKIP-pass if the
source is absent); `tests/validate_data.py` gained `check_occupation_income()` (positive values,
min≤avg≤max, sorted worst-first, meta/provenance present). `build_provenance.py` regenerated to
pick up the new file (auto-discovered via its `platform/data/*.json` glob — no manual registration
needed). Gate: 53/0 (was 52/0), `validate_data.py` 433/433 (was 428/428, +5 checks). Headless-
rendered `index.html#exposure`: settled-DOM probe shows `data-errors="[]"`, the new callout renders
with the real Transport/แม่ฮ่องสอน numbers right where expected, no regression to the existing
"Structurally riskiest" block above it (verified via DOM text search, not just a viewport
screenshot, since the callout sits below the first ~1600px of a taller tab).

## 2026-07-05 (6) — UX: Acquisition tab now leads with Road to 3,000, not the leaderboard

Loop cycle. Backlog follow-up (noted 2026-07-04 (9), still open): the "★ Rebuild dense tabs as 2-col
dashboards" bigger bet's own spec says Acquisition should "lead with the full-width Road to 3,000 bar
+ the leaderboard under it", but `platform/index.html` rendered `sec-opp` (the composite
opportunity-score leaderboard) BEFORE `sec-r3k` (Road to 3,000) — the opposite order, confirmed by
reading the live markup before touching anything (`sec-opp` at the old line 235, `sec-r3k` at 243).

Swapped the two `<details>` blocks (and their preceding comment numbering, "1 ·"/"2 ·") so Road to
3,000 (the regional headroom bar + the sequenced 985-branch plan nested inside it) now renders first,
with the opportunity-score leaderboard directly underneath; also swapped the `#acqjump` chip-nav order
to match the new visual order. Zero JS/data touched — pure markup reorder, both sections keep their
existing ids (`sec-r3k`/`sec-opp`) and `open` attribute, so every `app.js` call site
(`renderAcq()`/`renderAcqBoard()`/CSV buttons/jump-nav click handler) is unaffected by DOM position.
Moved the (already CSS-inert — grepped `platform/styles.css`, zero rules reference it) `.acq-lead`
class onto the new hero section for correctness.

Verified: `bash tests/run.sh check` 52/0 (`validate_data.py` 429/429, unchanged — no data file
touched). Headless-rendered `index.html#acq` (`tests/lib/render.sh`, 1400×3200): `data-errors="[]"`,
screenshot confirms Road to 3,000 now renders first (headroom table + sequenced-plan callout), the
composite-opportunity leaderboard directly below it, no layout regression to either table/CSV button.

## 2026-07-05 (5) — VALIDATOR: provinces/*.json now gated for meta.provenance completeness

Loop cycle. Backlog follow-up (2026-07-05 audit): `provinces/<slug>.json` gained a real
`meta.generated_by` + `meta.provenance.{measured,editorial,estimated}` block for all 77 provinces
earlier this same day, but the generic `check_provenance()` gate exempts the whole `provinces/`
subtree by prefix (a pre-existing exemption from before that block existed), so nothing actually
asserted the new block stays populated. Added a dedicated `check_province_provenance()` to
`tests/validate_data.py`: reads every slug off `provinces/index.json`, loads each deep-dive file, and
fails loudly if `meta.generated_by` is missing/blank or `meta.provenance.measured` / `.editorial` /
`.estimated` is missing, empty, or not a list of non-blank strings. Verified the check actually
catches drift (not just a happy-path pass-through): hand-deleted `rayong.json`'s
`provenance.editorial`, re-ran, got a real `FAIL` naming the exact file/field, then restored the file
(confirmed 0 diff via `git status`). Also investigated (before picking this item) whether the
CKAN-discoverable OAE outlook re-verification backlog item (flagged 3 cycles running) was tractable —
confirmed `catalog.oae.go.th` IS reachable from this sandbox (200 OK, unlike the `data-oae-prices.yml`
workflow's comment suggesting it 403s from a cloud runner), but a `package_list`/`group_list` sweep of
all 57 datasets in the catalog found no discoverable "outlook"/forecast document — the cited "OAE
Dec-2025 outlook" sentence almost certainly traces to a www.oae.go.th news page, not a CKAN dataset, so
confirming it needs a different (website-scraping) approach; logged this finding below instead of
guessing at an update with no real source to cite. Zero `platform/data`/`pipeline` files touched —
pure test-file addition. Gate 52/0, `validate_data.py` 429/429 (was 428/428, +1 check).

## 2026-07-05 (4) — UX: Home board-thesis sentence now cites the DTI+unemployment composite

Loop cycle. Backlog follow-up (self-noted 2026-07-03 (4), re-flagged 2026-07-05): `renderHomeThesis()`'s
one-sentence board thesis ("risk to watch is …") only ever checked `HHRISK_LIST[0]` (raw household
DTI) or `CSTRESS_LIST[0]` (crop stress) — never the more defensible `PSTRESS_LIST[0]` composite
(`province_stress_index.json`, 0.5×DTI-percentile + 0.5×unemployment-percentile) that the Home risk
CARD and the Exposure tab's rank-1 callout already lead with. The one-sentence hero and the detailed
card below it could name different "riskiest" provinces if the two legs ever diverged.

`platform/app.js`: the thesis clause now prefers `PSTRESS_LIST[0]` (states DTI + unemployment +
composite score together, e.g. "อำนาจเจริญ household stress (DTI 1.14× + unemployment 2.8%, composite
▲98, measured)"), falling back to raw DTI then crop-stress exactly as before when the composite layer
hasn't loaded. Also wired `loadProvinceStress().then()` (already warmed on Home for the risk card) to
call `renderHomeThesis()` too, so the sentence re-renders once the composite lands instead of staying
on the DTI-only fallback. Purely additive UI, no new data file/pipeline script.

Verified: `node --check platform/app.js` clean; `bash tests/run.sh check` 50/0 (`validate_data.py`
426/426, unchanged — no data file touched). Headless-rendered `index.html#home` (`tests/lib/render.sh`,
1400×3000): `data-errors="[]"`, thesis sentence renders the composite clause verbatim as above, no
layout regression to the card/Road-to-3,000 bar below it.

## 2026-07-05 — UX: structural household-leverage callout on the Exposure tab

Loop cycle. Backlog follow-up (self-noted 2026-07-03 (4)): the rank-1-surfacing pattern already
used on the Home command-center risk card (`PSTRESS_LIST[0]`, the MEASURED NSO household-DTI +
unemployment composite from `province_stress_index.json`) had no equivalent on `#exposure`, which
otherwise only surfaces the blended `province_risk.json` composite ("Most-stressed provinces" —
agri/collateral/merchant/unemployment mix). The two signals answer different questions (pure
borrower-leverage vs a broader multi-factor composite) and the backlog explicitly flagged the gap.

`renderRiskReadouts()` in `platform/app.js` gained a small "Structurally riskiest · household DTI +
unemployment" block, inserted between the existing "Most-stressed provinces" and "Riskiest branches"
sections. Reuses the already-defined `ccRow()`/`TAG_E` helpers (same markup Home uses) and the
existing `pstressHasData()`/`PSTRESS_LIST`/`loadProvinceStress()` plumbing — no new data file, no
new pipeline script, purely additive UI. Lazy-loads `province_stress_index.json` on first Exposure
visit (mirrors the existing `priskLoaded`/`briskLoaded` pattern in the same function) and renders
nothing when the layer is absent (graceful degrade, no fabrication).

Verified: `node --check platform/app.js` clean; `bash tests/run.sh check` 47/0 (`validate_data.py`
421/421, unchanged — no data file touched). Headless-rendered `index.html#exposure`
(`tests/lib/render.sh`, 1400×3000): `data-errors="[]"`, new block renders real data (อำนาจเจริญ,
DTI 1.14×, unemployment 2.8% NSO-measured, composite ▲98) directly under "Most-stressed provinces",
no layout regression to the surrounding cards/tables.

## 2026-07-04 (9) — AUDIT: reconciled the stale "Queue — UX / polish" backlog section against the live app

Loop cycle. Before picking a build item, spot-checked the committee-ranked quick-wins/bigger-bets
list in `docs/IMPROVEMENT_BACKLOG.md` against what's actually shipped — a hunch prompted by
`docs/PROGRESS_LOG.md`'s own 2026-06-30/07-01 entries already describing several of those exact
items as done. Confirmed via `git log -S"<label>"` on `platform/styles.css`/`app.js` (finding the
exact shipping commit + date for each) and fresh headless renders of `index.html#home`, `#map`,
`#overview`, `#exposure`, `#acq` (`bash tests/lib/render.sh`, screenshots read back).

**Found stale:** QW1 (map = hero, `ff2e9af`), QW2 (full-bleed canvas, `f142cd0`/`5d006d6`), QW3 (nav
fix, `738c28b`), QW5 (home leads with the verdict, `af05be8` — now grown well past its original
2–3-sentence spec into a full ranked "THIS WEEK" defend/audit/tighten/expand decision queue), QW8
(Risk-trend baseline, `44ca12d`), and the "★ Rebuild dense tabs as 2-col dashboards" bigger bet
(`af05be8` again) — all six were still listed `[ ]` open in the backlog despite shipping weeks ago.
Separately, the "Composite expansion-opportunity score per district" enrichment-queue item turned
out to be a stale duplicate of the already-shipped `pipeline/build_opportunity_score.py` →
`platform/data/opportunity_score.json` (fuses white-space + competitor-gap + agri-stress +
optional occupation-pull into one composite, already surfacing on `#acq`'s "Where to open next"
leaderboard).

**Left genuinely open** (verified, not just assumed): QW4 (unify theme — `platform/styles.css`
still literally has two `:root{}` blocks, lines 1 and 119) and QW6 (3D fails gracefully —
`rayong-catchment.html`'s data-load `.catch()` still shows a raw "Could not load … 3D data:
{msg}" string) — both correctly stay open and correctly stay out of the loop's scope (owned by
`viz-richness-bangkok`/`design-system-polish`). Noted for that workflow: `branch-explorer.html`
already ships QW6's exact target string (`'Building footprints unavailable — showing branch + POI
layer'`) — reusable verbatim instead of re-designing. "Reduce prose" wasn't independently
re-checked (no commit title claims it done) — left open rather than guessing.

**Why this matters:** a stale backlog is a real cost to this standing loop — a future cycle (or a
human skimming it) could burn a cycle "fixing" something already fixed, or worse, build a second,
divergent implementation alongside the shipped one. Docs-only change, zero `platform/`/`pipeline/`
files touched. Gate: `bash tests/run.sh check` 47/0 before and after (unaffected, as expected for a
backlog-doc correction). Full detail + evidence trail in `docs/IMPROVEMENT_BACKLOG.md`'s Done log
(2026-07-04 (9) entry) and inline against each corrected item.

## 2026-07-04 (8) — VALIDATOR: doc/data vintage-drift tripwire in `validate_data.py`

Loop cycle. Backlog follow-up (self-noted 2026-07-04 (7)): the AUDIT that same day found
`docs/DATA_SOURCES.md` + `docs/DATA_PROVENANCE.md` had silently drifted stale (still quoting the
pre-refresh Dec-2025 Pink Sheet vintage two days after `platform/data/meta.json` had already moved to
2026M06), caught only by a manual pass — no automated tripwire existed for that class of doc-drift.

New `check_doc_vintage()` in `tests/validate_data.py`: reads the live vintage off
`meta.json.updated` (regex `\d{4}M\d{2}`), then greps each doc's own "live read" anchor — the
`## World Bank Pink Sheet — current read (VINTAGE prices)` header in `DATA_SOURCES.md` and the
`` currently `VINTAGE prices ...` `` phrase in `DATA_PROVENANCE.md` (both docs already carried a
"keep this in sync with meta.json" comment next to these exact spots) — and fails the gate if either
doc's cited vintage disagrees with the live one. Deliberately scoped to these two specific anchors
rather than every `\d{4}M\d{2}` substring in the docs tree: `docs/DATA_REFRESH_LOG.md`,
`docs/QA_FINDINGS.md` and `IMPROVEMENT_BACKLOG.md`'s own Done log legitimately *mention* the old
stale vintage as history (audit write-ups), and a naive whole-doc scan would false-positive on those
every cycle.

Verified it actually catches drift: hand-edited `DATA_SOURCES.md`'s header back to `2025M12`, reran
`validate_data.py` — new check correctly `FAIL`s with the doc/live vintages named; restored the file
and reran — clean `PASS`. Zero `platform/data`/`source-data` files touched. Gate: `bash tests/run.sh
check` 47/0 (`validate_data.py` 421/421, was 418/418).

## 2026-07-04 (6) — HYGIENE: `build_national_places.py`/`build_scene_places.py` no longer bare-`assert` on malformed committed data

Loop cycle. Backlog follow-up (self-noted 2026-07-04 (5)): both scripts' SKIP-pass path (bulk
`occupation_places_named.json` input absent — the normal CI/sandbox state) re-validated the
already-committed output file with a bare `assert "places" in d, ...`. A corrupted committed JSON
would have raised an uncaught `AssertionError` traceback under `tests/run.sh check` instead of the
clean `CHECK FAIL: ...` / exit-1 convention every other builder follows — the same class of gap
`build_branch_density.py`'s `BucketDriftError` fixed last cycle (2026-07-04 (5) entry above).

Fix: both scripts now check the condition explicitly and print `CHECK FAIL: ... malformed (missing
'places'/'bbox')` to stderr + `sys.exit(1)` instead of asserting. Zero behavior change on the happy
path (source still absent in this sandbox → both scripts still SKIP/exit-3 exactly as before,
verified by hand). Pure `pipeline/` change, no `platform/data` file touched.

Gate: `tests/run.sh check` 46/0, `validate_data.py` 265/265 (both unchanged — no data file
modified). Verified `build_national_places.py --check` and `build_scene_places.py --check` both
still print their original SKIP message and exit 3 in this sandbox (bulk source absent, as always).

## 2026-07-04 (5) — HYGIENE: `build_branch_density.py`'s bucket-tally self-check now fails clean

Loop cycle. Backlog follow-up (self-noted 2026-07-04 (4)): the drift check added when
`branch_density.json` was wired in raised a bare `AssertionError` (uncaught Python traceback) on a
bucket-threshold mismatch, instead of the `CHECK FAIL: ...` / exit-1 convention every other builder
in `pipeline/` follows when `tests/run.sh check` calls it with `--check`. Functionally the gate still
failed either way (an uncaught exception also exits nonzero), but a future cycle diagnosing a real
failure would have had to read a raw traceback instead of a one-line message.

Fix: introduced a `BucketDriftError` exception; `main()` now catches it and prints `CHECK FAIL: ...`
to stderr + `sys.exit(1)`, matching `build_branch_density.py`'s own existing convention for every
other failure path (missing `OUT` file, byte-mismatch) and the pattern used across
`build_branch_peers.py`/`build_branch_population.py`'s `ImportError`→exit-3 `[SKIP]` handling. Zero
behavior change on the happy path.

Verified by hand: (1) normal `--check` still reproduces byte-exact (2,015 branches, exit 0); (2)
hand-corrupted `source-data/perimeter_counts.json`'s `meta.buckets.empty_0` by +999 and re-ran both
`--check` and the plain build — both now print a clean one-line `CHECK FAIL: ...` message (no
traceback) and exit 1; (3) restored the source file via `git checkout --` and confirmed `git status`
shows no diff before committing. Pure `pipeline/` change, no `platform/data`/`source-data` files
touched. Gate: `tests/run.sh check` 46/0 (unchanged `validate_data.py` 265/265).

## 2026-07-04 (3) — VALIDATOR: coverage for the new Overture "dense POI" layers

Loop cycle. Backlog item: "Expand `validate_data.py` coverage as new data layers land." The recent
concurrent 3D-lane workflows shipped `national_places.json` (`build_national_places.py`, nationwide
grid-thinned Overture places, the fallback density layer for every province's 3D scene) and per-city
`<city>_places.json` (`build_scene_places.py`, bbox-clipped full-density Overture places for
Rayong/Bangkok/Chiang Mai) with a determinism gate in `tests/run.sh` but **zero data-integrity check**
in `validate_data.py` — a bucket-taxonomy typo, a `[lat,lng]` order slip, or a `meta.count` drift over
those ~340k committed points could have shipped silently.

Added `check_national_places()` + `check_scene_places()` (shared `_check_places_payload()` helper) to
`tests/validate_data.py`: validates `meta.label`/`meta.buckets` against the known 14-bucket Overture
taxonomy, per-city `bbox` presence, every point is `[lng,lat]` inside a Thailand+border-buffer bbox
(97–106°E, 5–21°N — the same tolerance already used by `check_catchment_poi`/`check_lead_sites`, not
the tighter branches-only `TH_LAT_MIN/MAX` consts, since the Overture bulk pull genuinely reaches
points near the deep-south border e.g. Betong ≈5.4°N that the tighter bbox would have false-failed),
and `meta.count` matches the actual point total. Both new checks SKIP-pass (not fail) when the
optional file is absent, matching every other optional-layer check in the file.

Caught and fixed one real false-positive during development: my first draft used the module-level
`TH_LAT_MIN=5.5` constant and failed on ~1,800 genuine near-border factory points at lat 5.40–5.47;
confirmed these are real Overture coordinates (not an order bug) and switched to the wider 5.0–21.0
bound the codebase already uses for POI-shaped (as opposed to branch-shaped) checks.

Pure test-file change — no `platform/data`/`pipeline` files touched, zero risk of shared-tree
conflicts with the concurrent 3D-lane workflows. Gate: `tests/run.sh check` 45 passed/0 failed,
`validate_data.py` 259/259 (2 new checks added this cycle).

## 2026-07-04 — UX: district (amp) lenses get the same choropleth dot-thinning as province lenses

Loop cycle. Backlog follow-up (self-noted 2026-07-03 (9)): `styleMarkers()`'s dot-opacity thinning
(landed 2026-07-03 (9) for `hhdti`/`pstress`) only checked `isProvLens(curLens)`, but the three
district (amphoe) `amp:true` lenses — `dws`, `drisk`, `unemp` — paint the exact same
`drawAmphoeChoropleth()` polygon fill under the dots and were left at the full 0.9 opacity, tiling
over their own choropleth just as badly (worse, per the backlog note, since district polygons are
smaller than province ones).

`platform/app.js`'s `styleMarkers()` now computes `polyDots = isProvLens(curLens) || isAmpLens(curLens)`
and thins to 0.6 opacity for either; every branch/estab/comp-style lens is untouched at 0.9. Two-line
logic change (plus an updated comment), no new data, no new files. Gate: `tests/run.sh check` 42/0
(`validate_data.py` 224/224, unchanged — no data touched). Headless-rendered
`index.html?lens=drisk#map`: the district risk-proxy choropleth fill now reads clearly through the
dot layer in the denser clusters; a control render of the default `opportunity` lens confirms it's
still pixel-unchanged at full 0.9 opacity.

## 2026-07-03 (10) — Exec decision queue: "This week — do these first" leads the Command Center

New synthesis layer + first card on `#home`. `pipeline/build_decision_queue.py` →
`platform/data/decision_queue.json`: 8 ranked weekly actions built ONLY from existing committed
layers — defend (rival_pressure besieged, MEASURED), audit (branch_peers twin outliers, EST),
tighten/watch (macro_sensitivity headwind province + crop_stress worst province, EST), expand/scout
(opportunity_score + exit_whitespace top districts, EST). Every sentence carries the real numbers
copied from the source layer; each row shows its measured/estimated tag, source file and detail-tab
link. **Decision:** ranking is an openly stated EDITORIAL rule (defend 40 > audit 30 > tighten 20 >
expand 10, + 10× the layer's own normalized magnitude) because cross-layer scores are not
commensurable — we never pretend an opportunity score and a rival count live on one measured scale.
Deterministic, network-free, `--check`; gated in `tests/run.sh` + `check_decision_queue()` in
`tests/validate_data.py` (ranks 1..n, known type/basis/go, numbers inline, priority desc). UI:
numbered rows + type-color chips (defend red / expand gold / tighten orange / audit purple) with
explicit light-theme contrast overrides.

Loop cycle. Backlog follow-up (self-noted 2026-07-03 (6)): the `hhdti`/`pstress` province-resolution
lenses paint a polygon fill under the branch dots (`drawProvinceChoropleth()`, landed 2026-07-03 (7)),
but the dots' fixed 0.9 fill-opacity fully tiled over that fill in denser provinces (Bangkok, the
East), making the new choropleth invisible at the National map's default zoom.

`platform/app.js`'s `styleMarkers()` now checks `isProvLens(curLens)` and drops dot `fillOpacity` to
0.6 specifically on `hhdti`/`pstress`; every other lens is untouched at 0.9. Two-line change, no new
data, no new files. Gate: 40/0 (`validate_data.py` 211/211, unchanged — no data touched). Headless-
rendered `index.html?lens=pstress#map`: the grey/pink province fill now reads clearly through the
dot layer, including in the dense Bangkok/East cluster; a control render of the default `opportunity`
lens confirms the other lenses are pixel-behaviour-unchanged at full 0.9 opacity.

## 2026-07-03 (7) — ENRICH: province polygon choropleth for the hhdti/pstress lenses

Loop cycle. Backlog follow-up (self-noted 2026-07-03 (2)/(5)): the two PROVINCE-resolution map
lenses — `hhdti` (household debt-to-income) and `pstress` (province structural stress) — key off
`d.v` (the branch's province name), so every branch in a province shared one colour and painted as
many same-coloured overlapping dots instead of one clean province shape, unlike the district
(amphoe) lenses (`dws`/`drisk`/`unemp`) which already paint a polygon choropleth via
`drawAmphoeChoropleth()`.

New `pipeline/build_province_geo.py` → `platform/data/province_geo.json` (77 provinces). Avoids a
second Douglas–Peucker simplification pass or a `shapely` polygon dissolve: it GROUPS the
already-simplified, already-committed `amphoe_geo.json` polygons by `amphoe.json`'s
`province_th`, re-emitting each province's constituent amphoe rings as one `MultiPolygon` feature
(no new geometry invented, no vertices changed — same convention as `build_amphoe_geo.py`, which
this reuses as input instead of re-touching `th_amphoe.geojson`). Deterministic + network-free,
`--check`-gated (byte-exact reproduce), degrades gracefully (`SKIP`, exit 0) if `amphoe_geo.json`/
`amphoe.json` are absent.

Wired into `platform/app.js`: `hhdti`/`pstress` gained a `prov:true` flag on the `LENS` registry
(mirrors the existing `amp:true` pattern); new `isProvLens(k)` + `loadProvinceGeo()` +
`drawProvinceChoropleth()` (parallel to `isAmpLens`/`loadAmphoeGeo`/`drawAmphoeChoropleth`, painted
UNDER the branch dots, same canvas-renderer / colour-ramp / legend conventions) — reads the lens's
own `val()` against `{v: province}` so it needs no new join logic. Wired into `initMap()`'s warm-up
and `setLens()`'s lazy-load triggers, and into `styleMarkers()` alongside the existing amphoe-draw
call. Purely additive: every other lens is untouched, and the file degrades to dots-only if
`province_geo.json` is absent (same optional-layer convention as `amphoe_geo.json`).

`tests/validate_data.py` gained `check_province_geo()` (FeatureCollection shape, provenance, valid
closed rings, Thailand-bbox sanity, unique province names, and a join check against real branch
provinces — mirrors `check_amphoe_geo()`); `tests/run.sh` gates `build_province_geo.py --check`.
Gate: 37/0 (`validate_data.py` 193/193, was 185/185). Verified with a headless Playwright load of
`index.html?lens=hhdti#map` and `?lens=pstress#map` against the local vendored bundles: `PGEO`
resolves to 77 features and `provChoroLayer` attaches all 77 province polygons on both lenses, zero
JS errors (only the expected blocked basemap-tile/Google-Fonts network calls). A full-country
screenshot at branch-dot zoom can't visually distinguish the polygons under the dense, opaque dot
layer — confirmed via direct DOM/JS inspection instead. `bash tests/run.sh render` also caught a
pre-existing, unrelated `rayong-catchment.html` render failure (deck.gl 3D page owned by a
different in-flight workflow; untouched by this change).

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
