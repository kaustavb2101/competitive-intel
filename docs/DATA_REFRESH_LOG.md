# DATA REFRESH LOG — dated entries from the data-enrichment & integrity cycle

> Appended by the recurring DATA-ENRICHMENT & INTEGRITY routine (one entry per cycle: what was
> refreshed/enriched/audited, with provenance + source). See `docs/IMPROVEMENT_BACKLOG.md` for the
> Rules this cycle follows (no-fabrication is absolute).

## 2026-07-04 (4) — ENRICH: MEASURED building-density-within-10km layer, sitting unused since 2026-07-02, wired into the branch popup

**Task type:** ENRICH. `/workspace/watcher` [TMLI blueprint] was not present this cycle, so no
cross-repo pull was possible. Started with a RE-DERIVE pass: `bash tests/run.sh check` on a clean
pull of `claude/new-session-wto26j` — 45 passed, 0 failed, `validate_data.py` 259/259, no drift.
With the tree already fully in sync, moved to an ENRICH pass per the rule to prefer folding in a
real, already-available, not-yet-integrated layer over auditing files already scrutinized in the
last several cycles (all four TMLI-vendored sources in `source-data/tmli/` have each already been
audited — `household-debt.js` 2026-07-04, `provincial-gpp.js` 2026-07-02 — and the gov fold-in files
from `ingest_gov.py` all carry non-round, province-distinct values consistent with a genuine pull).

**What was found.** `source-data/perimeter_counts.json` — written in a single commit (`dda7816`,
2026-07-02, "Perimeter 3D audit: measured building counts for all 2,015 branch perimeters") — is a
real, sourced, MEASURED layer (per-branch Overture building-footprint count within 10km, counted
from the 77 real per-province catchment pulls: 3 in-repo + 74 on the operator R2 CDN, capped
180k/province) that has never been consumed by any pipeline script or `platform/app.js` (confirmed
via `grep -rn perimeter_counts` across `pipeline/*.py` and `platform/` — zero hits before this
cycle). It carries full provenance in its own `meta` (`generated_by`, `label` with the honest
"a zero means the CAPPED file has no buildings there" caveat, `method`, `buckets` tally) and is
`counts[]` index-aligned to `platform/data/branches.json` (2,015 entries) — a genuinely useful,
already-real signal (urban/commercial density context for both objectives) sitting orphaned.

**Alignment safety check (before wiring in as index-aligned).** `perimeter_counts.json` predates the
`branches_fingerprint` convention and carries no per-record identity field, so it cannot be
re-verified byte-for-byte the way a stamped layer can — an index-aligned projection is only honest
if `branches.json`'s ORDER has not changed since the counts were generated. Checked explicitly:
`branches.json` at commit `dda7816` (2026-07-02, when the counts were written) has the identical
`branches_fingerprint` (`e25867ab0c76d888…`) as the `branches.json` committed with this cycle's
change, despite two intervening commits that touched `branches.json` (`d9cc82f` adding a population
field, `00196c5` a full data refresh) — both changed field VALUES, neither reordered/added/removed
branches (length stable at 2,015 throughout; fingerprint recomputed independently, matches exactly).
Wiring the layer in as index-aligned was safe.

**What changed (zero fabrication — pure projection of an already-committed, already-sourced
MEASURED source into its first consumer):**
- New `pipeline/build_branch_density.py` (network-free, deterministic, `--check` byte-exact):
  loads `source-data/perimeter_counts.json`, carries `buildings_10km` verbatim per branch (no
  transform), and assigns a `bucket` label using the EXACT same cutpoints as the source's own
  `meta.buckets` tally — self-checked at build time (`AssertionError` if the recomputed tally ever
  disagrees with the source's, so a threshold typo fails loudly instead of shipping quietly wrong).
  Degrades to an honest ABSENT-state (empty `branches: []`, `meta.absent=true`) rather than guessing
  a projection if a future `branches.json` length ever stops matching `perimeter_counts.json`'s
  2,015 counts. `--check` SKIPs (exit 3, not a `--check` failure) when the source file is absent.
  → `platform/data/branch_density.json` (2,015 branches; buckets rich_1000plus 1,803 /
  good_200_999 73 / thin_50_199 1 / sparse_1_49 4 / empty_0 134 — matches the source exactly).
- `platform/app.js`: new `loadBranchDensity()`/`bldgDensityRec()` (mirrors the existing
  `poi_relevance.json` lazy-load pattern), warmed alongside the other popup-only layers in
  `initMap()`+`selectBranch()`. New `bldgDensityPopupHTML()` appends ONE line — "Buildings ≤10km
  (Overture) · measured — N (bucket-label)" — to the existing "Within 10 km" popup section. No new
  map lens (kept small per the loop's scope-discipline rule — a single popup-only metric doesn't
  warrant a whole lens/legend). Fully null-guarded: absent file → the line is simply omitted.
- `tests/validate_data.py`: new `check_branch_density()` (meta/provenance present, ABSENT-state
  handling, length == branches.json, `buildings_10km` a non-negative int, `bucket` one of the 5
  known labels); registered in the index-alignment gate and the branches-fingerprint gate (own
  `branches_fingerprint` stamp, so any FUTURE `branches.json` reorder that isn't matched by a rebuild
  of this layer will be caught by the existing fingerprint-mismatch check going forward).
- `tests/run.sh`: gates `build_branch_density.py --check` (SKIP, not FAIL, if the source is absent —
  same convention as the `numpy`/`build_branch_peers.py` fix).
- `pipeline/build_provenance.py` re-run (its census of all `platform/data/*.json` picked up the new
  file) — `platform/data/provenance.json` regenerated to match (pure count/list update, no logic
  changed).
- `CLAUDE.md` pipeline listing gained a one-line entry for the new builder.

**Verification.**
- `bash tests/run.sh check` — 46 passed, 0 failed (`validate_data.py`: 265/265, up from 259/259 — 6
  new checks). `node --check platform/app.js` clean.
- `python3 build_branch_density.py --check` reproduces byte-exact (0 drift); bucket tally
  self-check passes (recomputed tally == source's own `meta.buckets`, exactly).
- Headless-rendered `index.html#map` (Playwright, `/opt/pw-browsers/chromium-1194`) and evaluated
  the real in-page functions directly (`loadBranchDensity()`, `bldgDensityRec()`, `popupHTML()`) for
  branch #0: returned `{buildings_10km: 8, bucket: "sparse_1_49"}`, matching
  `platform/data/branch_density.json`'s own record exactly; the rendered popup HTML contains
  `Buildings ≤10km (Overture) · measured … 8 (sparse)`. Zero uncaught page errors (`pageerror`
  listener empty); the only console errors were the known-expected basemap-tile CDN blocks (see
  `tests/lib/render.sh`'s own comments — cartocdn is proxy-blocked in this sandbox).

**Source:** `source-data/perimeter_counts.json` `meta.generated_by` — "perimeter 3D audit workflow
(wf_127c1b1e-038), counts computed from the 77 real Overture catchment files (3 in-repo + 74 on the
operator R2 CDN)". No external pull performed this cycle — this is a first-use projection of an
already-committed, already-sourced MEASURED layer that had sat unconsumed for two days.

---

## 2026-07-04 (2) — AUDIT: `household-debt.js`'s `debtToIncome`/`stressIndex` mislabelled MEASURED, actually UNVERIFIED (BOT figure with no citable resource)

**Task type:** AUDIT (provenance sweep, per the backlog's own 2026-07-03 (7) follow-up: "the two
independent DTI estimates could disagree — worth an AUDIT pass"). `/workspace/watcher` was not
present this cycle, so no fresh cross-repo TMLI pull was possible; a RE-DERIVE pass first confirmed
the working tree was already fully in sync (`bash tests/run.sh check` — 42 passed, 0 failed, no
drift) before picking this AUDIT task.

**What was found.** `source-data/household_debt_by_province.json` (built by
`pipeline/ingest_tmli.py`'s `build_household_debt()` from the vendored
`source-data/tmli/household-debt.js`) carries three fields per province — `debt_to_income`,
`stress_index`, `debt_per_household` — and its `meta.provenance` blanket-claimed all three
"MEASURED... NSO SES 2566... BOT Q4/2024." Inspecting the vendored source:
- `debt_per_household` traces cleanly to the co-vendored `nso-ses-debt-2566.json` (NSO SES 2566,
  `catalog.nso.go.th/dataset/0705_08_0009`) — genuinely MEASURED, values non-round and
  province-distinct.
- `debt_to_income`/`stress_index` are attributed only to "BOT Household Debt Regional Q4/2024" —
  **no CKAN/BOT dataset or resource id is cited anywhere in the vendored file or its own
  `PROVENANCE.md` entry**, unlike every other TMLI-vendored layer (NSO SES debt/income, NSO LFS —
  all cite a real table/resource id). The values in `household-debt.js` are grouped under
  hand-written narrative section headers (`// --- CENTRAL (High leverage) ---`, `// --- NORTHEASTERN
  (Agri-Stress Hubs) ---`, etc.) — the exact same fabrication smell already caught and corrected in
  `provincial-gpp.js` on 2026-07-02 (round numbers, hand-assigned per editorial category, no
  verifiable resource).
- Magnitude check: the file's `debt_to_income` ranges 9.5x–18.2x across provinces — i.e. it claims
  the average Thai household owes 9.5 to 18.2 times its ANNUAL income, which is implausible (Thai
  household debt-to-GDP nationally runs under 1.0x per BOT's own published aggregate figures). By
  contrast, `platform/data/household_risk_by_province.json` (`build_household_risk.py`, independently
  computed as `debt_per_household ÷ (avg_monthly_income × 12)` from two fully-cited NSO SES layers)
  gives the *same* provinces a debt_to_income of 0.2x–1.2x — a 10-20x divergence from the
  BOT-attributed figures in `household-debt.js` for the identical province set (e.g. Krabi: file says
  10.5x, recomputed says 0.70x; Bangkok: file says 14.2x, recomputed says 0.22x).

**Blast radius: contained.** Traced every consumer of `household_debt_by_province.json` — only
`build_household_risk.py` reads it, and only its `debt_per_household` field (the genuinely-MEASURED
one); `debt_to_income`/`stress_index` from this file are never read by any builder or app code
(`grep` across `pipeline/*.py` and `platform/app.js` confirms every downstream consumer —
`build_branch_peers.py`, `build_branch_risk.py`, `build_macro_exposure.py`,
`build_province_stress.py`, `app.js`'s `HHRISK`/`PSTRESS` — reads exclusively from
`platform/data/household_risk_by_province.json`'s own recomputed ratio, never the raw source file).
The unverified BOT figure never reached a user-facing screen.

**Fix applied (no fabrication — corrected labels/docs only, zero data values changed):**
- `pipeline/ingest_tmli.py`'s `build_household_debt()`: `meta.provenance`/`fields`/new `meta.caveats`
  now split MEASURED (`debt_per_household`) from UNVERIFIED (`debt_to_income`, `stress_index`), name
  the exact divergence and the missing-resource-id issue, and state plainly "do NOT surface
  debt_to_income/stress_index from THIS file as MEASURED anywhere."
- Regenerated `source-data/household_debt_by_province.json` (`python3 ingest_tmli.py`) — diffed
  before committing: **only the `meta` block changed; every per-province numeric value is
  byte-identical.** `ingest_tmli.py --check` reproduces byte-exact.
- Corrected the blanket "MEASURED" claims in `source-data/tmli/PROVENANCE.md` (file-level table +
  header), `docs/NEXT_STEPS.md` §0a (also removed a stale "next concrete step: join into
  build_province.py/build_amphoe.py" instruction that would have wired the unverified BOT figures
  into the app had a future cycle followed it literally — replaced with a note that the measured path
  is already shipped via the recomputed ratio), and `docs/DATA_PROVENANCE.md`'s `tmli/` row.
- `bash tests/run.sh check` — 42 passed, 0 failed (`validate_data.py`: 224/224, unchanged — this
  layer isn't itself a `platform/data` file, so the data-integrity gate was never touching it).

**Follow-up (logged, not attempted — low priority since the figure is unused and there's no live BOT
access from this sandbox):** if a real per-province BOT Household Debt Regional dataset with a
citable resource id is ever pulled, it would be a genuinely independent second measure of household
leverage worth comparing against the recomputed NSO-ratio — but should not simply replace it without
that verification, given the current file's numbers don't check out even as a plausible unit
mismatch (e.g. debt ÷ monthly income doesn't reconcile either).

**Source:** `source-data/tmli/household-debt.js` (self-disclosed structure — narrative section
headers, no resource id) + cross-check against `source-data/tmli/nso-ses-debt-2566.json` and
`platform/data/household_risk_by_province.json`. No external pull performed this cycle.

---

## 2026-07-03 (8) — ENRICH: NSO SES 2566 per-occupation income folded into the province deep-dive

**Task type:** ENRICH. `/workspace/watcher` was not present this cycle, so no cross-repo TMLI pull
was possible. A RE-DERIVE pass first confirmed the working tree was already fully in sync (`bash
tests/run.sh check` — 40 passed, 0 failed, no drift) before picking this task.

**What was found.** `source-data/household_income_by_province.json` — already vendored, MEASURED,
provenance-documented (NSO SES 2566, via `kaustavb2101/watcher`/`ingest_tmli.py`, all 77 provinces
carry non-round per-occupation figures) — has been in the repo since at least the 2026-07-02 GPP
audit, but only its **unweighted mean** (`avg_monthly_income`) is consumed, by
`build_household_risk.py`, to form the province debt-to-income ratio. The underlying **per-occupation
breakdown** (`Agriculture` / `FactoryWorkers` / `OfficeStaff` / `SMEOwners` / `Transport`, THB/month)
was never surfaced anywhere in the app — a real, already-sourced, already-audited layer sitting
unused. These are NSO's own five occupation categories (not an invented crosswalk against the
Overture 14-bucket occupation mix, which uses a different taxonomy and would require an editorial
mapping this cycle avoided).

**What changed (zero fabrication — pure projection of an already-MEASURED, already-provenance-labelled
source):**
- `pipeline/build_province.py`: loads `household_income_by_province.json` and adds
  `gov.income = {Agriculture, FactoryWorkers, OfficeStaff, SMEOwners, Transport, avg_monthly_income}`
  per province (graceful `{}` fallback if the source file is ever absent, matching the existing
  `unemployment` pattern), and updated `gov.src` to name the new input. Regenerated all 77
  `platform/data/provinces/<slug>.json` (+`index.json`) via `python3 build_province.py` — only the
  new `gov.income` block was added; every other field byte-identical (spot-checked via diff).
- `platform/province.html`: "Who works nearby" panel gained (a) an "Avg household income" row next to
  the existing informal/formal/unemployment rows, and (b) a new "Income by occupation" mini-chart
  (NSO's 5 categories, sorted highest-first, THB/month), both tagged `measured · NSO SES 2566` (not
  `estimated` — distinct from the existing OSM-proxy "Occupation mix" section directly below it,
  which stays labelled `estimated · proxy`).
- Serves objective #1 (portfolio risk): which occupations in a province earn least (Transport,
  Agriculture in most provinces) is a direct affordability signal for the title-loan borrower base,
  now visible per-province instead of buried in an unused source file.

**Verification.** `bash tests/run.sh check` — 40 passed, 0 failed (`validate_data.py` 211/211, no
schema assumption broken — `check_provinces()` only spot-checks slug/branches/k10/NaN, no rigid field
list). Headless-rendered `province.html?p=rayong`: the WebGL **screenshot** pass failed (known
pre-existing swiftshader/3D flakiness in this sandbox, unrelated — logged in `IMPROVEMENT_BACKLOG.md`
2026-07-03 (7)'s render note), but the **DOM dump** pass succeeded and confirms `data-errors="[]"`
(zero JS errors) + `data-deck="1"` (deck.gl initialized) + the new panel rendering real, correctly
THB-sorted values (Agriculture ฿44,041/mo > Factory workers ฿36,970/mo > Office staff ฿35,831/mo >
SME owners ฿27,677/mo > Transport ฿18,929/mo for Rayong — matches the source file exactly).

**Source:** `source-data/household_income_by_province.json` `meta` — "NSO SES 2566 — monthly income
by occupation (THB/month), via data.go.th / TMLI"; vendored from `kaustavb2101/watcher
source-data/tmli/nso-ses-income-2566.json`. No external pull performed this cycle — this is a
re-projection of an already-committed, already-audited MEASURED source into a second (previously
unserved) view.

---

## 2026-07-03 (6) — AUDIT: fixed a second false-drift gate gap (`build_branch_population.py --check`)

**Task type:** AUDIT (gate integrity, not a data value change — no `platform/data` or `source-data`
file content was touched). `/workspace/watcher` [TMLI blueprint] was not present in this sandbox this
cycle, so no cross-repo ENRICH pull was possible; started with a RE-DERIVE pass instead (re-running
`bash tests/run.sh check` on a clean pull) and it surfaced a real gate bug worth fixing over forcing a
new data layer.

**What was found.** `bash tests/run.sh check` on a clean checkout reported 35 passed / 0 failed but
with 2 `[SKIP]`s: `build_branch_peers.py --check` (needs `numpy`) and `build_branch_population.py
--check` (needs `shapely`/`rasterio`) — both already-known sandbox dependency gaps
(`docs/IMPROVEMENT_BACKLOG.md`). Installing `numpy` + `shapely` + `rasterio`
(`pip install --break-system-packages numpy shapely rasterio`) to actually exercise both skipped
checks turned up a **real bug**, not just a missing package: with `shapely` installed but `rasterio`
absent, `bash tests/run.sh check` went to **36 passed, 1 FAILED** —
`build_branch_population.py --check` reported `DRIFT: platform/data/branch_population.json`.

Root cause: `build_branch_population.py` has two valid build methods — MEASURED raster sum (needs
`rasterio` + the committed `source-data/worldpop_tha_2020_1km.tif`), preferred; ESTIMATED
area-weight (needs only `shapely`), fallback. `run(check=True)` only returned the distinct "can't
verify" exit code (3) when **both** methods' dependencies were absent (`build()` returns `None`). With
only `shapely` present, `build()` **succeeds** via the areaweight fallback and produces a different
but internally-valid JSON, which the byte-compare against the committed **raster**-built file then
reported as `DRIFT` — a false failure. Installing `rasterio` too confirmed the committed file was
never wrong: `build_branch_population.py --check` then reproduces byte-exact (`method=raster`, 0
drift). This is the same bug class the 2026-07-03 numpy/`build_branch_peers.py` fix addressed, one
level subtler — that fix only needed "both-deps-absent → SKIP"; this script needed "committed method
≠ locally-producible method → SKIP" because it has two independently-satisfiable dependency paths, not
one all-or-nothing import.

**Why this matters for the no-fabrication mandate:** an unexplained `DRIFT` on a MEASURED file is
exactly the kind of red herring that could tempt a future cycle to "fix" the gate by regenerating
`branch_population.json` from whatever pipeline path the local environment happens to support —
which here would silently **downgrade a MEASURED raster-sum population count to an ESTIMATED
area-weight proxy** and commit it as if nothing changed. Catching this before that happens is the
point of the audit.

**Fix applied (code only, zero data changes):**
- `pipeline/build_branch_population.py` `run(check=True)`: now reads the *committed* file's
  `meta.method` and compares it against what this environment's `build()` actually produced. On a
  mismatch it prints `SKIP: committed ... was built with method=X but this environment can only
  produce method=Y (install <dep> to verify byte-for-byte)` and exits `3` (same convention as the
  numpy fix) instead of `DRIFT`/exit `1`. A genuine same-method byte mismatch still fails correctly —
  the byte-compare only runs once methods are confirmed equal.
- `tests/run.sh`: the `build_branch_population.py --check` phase now echoes the script's own `SKIP`
  message instead of a hardcoded "shapely not installed" string (which would have been actively wrong
  in the rasterio-missing-only case — shapely IS installed, rasterio isn't).

**Verification:**
- Hand-verified all three dependency states via `builtins.__import__` interception (no real
  uninstall, to avoid disturbing the shared sandbox): (1) `rasterio` blocked, `shapely` present →
  new `SKIP` naming `rasterio + worldpop_tha_2020_1km.tif`, exit 3 (previously: `DRIFT`, exit 1 —
  the bug). (2) both blocked → original `SKIP` path, exit 3 (unchanged). (3) neither blocked → `OK ...
  method=raster`, exit 0 (unchanged).
- Regression check: hand-corrupted one value in the committed `platform/data/branch_population.json`
  with `rasterio` present (real import, not mocked) → correctly printed `DRIFT:
  platform/data/branch_population.json`, exit 1 (not swallowed by the new skip path); restored from
  git (`git status` clean before committing).
- `bash tests/run.sh check` with `numpy`+`shapely`+`rasterio` all installed this cycle: **37 passed, 0
  failed** — both previously-`[SKIP]`'d checks (`build_branch_peers.py`, `build_branch_population.py`)
  now ran for real and passed (`validate_data.py`: 181/181, unaffected — no `platform/data` or
  `source-data` file touched by this diff).

**Source:** no external data pulled this cycle; pipeline/tooling integrity fix per the AUDIT task
type, same pattern as the already-logged 2026-07-03 numpy fix. `docs/IMPROVEMENT_BACKLOG.md` updated
(existing "vendor numpy" item broadened to also name shapely/rasterio; new Done entry added).

---

## 2026-07-03 (3) — ENRICH: combined province structural-stress index (household DTI + unemployment)

**Task type:** ENRICH (fold two already-vendored MEASURED layers into a single new composite view;
no external data pulled — `/workspace/watcher` [TMLI blueprint] was not present in this sandbox this
cycle, so no cross-repo pull was possible; this task was picked from the sandbox-safe backlog
instead, per the rule to prefer keeping existing real data provably-sourced over adding new things).

**What was found.** The backlog (`docs/IMPROVEMENT_BACKLOG.md`) carried two near-duplicate open
items asking for the same thing: combine `household_risk_by_province.json` (NSO SES 2566
debt-to-income) and `source-data/unemployment_by_province.json` (NSO Labour Force Survey) — both
already-committed, already-audited MEASURED province-level risk signals — into ONE "which provinces
are structurally riskiest" number. Today they feed two separate mechanisms: `hhdti` (a direct
province-keyed National-map lens) and `unemp` (an amphoe-join lens, province-inherited), with no
single combined read.

**What changed:**
- New `pipeline/build_province_stress.py` (network-free, deterministic, `--check` byte-exact) loads
  `platform/data/household_risk_by_province.json` (itself `build_household_risk.py`'s MEASURED-input
  output — `debt_to_income` + its 0–100 percentile `stress_index`) and
  `source-data/unemployment_by_province.json` (`unemployment_rate`, MEASURED). Computes an
  `unemployment_percentile` using the exact same percentile-rank method as the existing DTI
  percentile (for comparability), then `composite_stress = 0.5*dti_percentile +
  0.5*unemployment_percentile`, 0–100, ranked worst-first. All 77 provinces joined cleanly (both
  sources already use the canonical 77 Thai-name key) — 0 provinces dropped.
- Every field is labelled MEASURED or ESTIMATED in `meta.fields`; `meta.caveats` states plainly that
  the 50/50 weighting is an editorial triage choice, NOT calibrated against realized AutoX default
  data (no loan tape exists yet to calibrate against — see `docs/TONIGHT_CHECKLIST.md` §6).
  Top of the list: อำนาจเจริญ (Amnat Charoen) composite 98.05 (DTI 1.14×, unemployment 2.84% — both
  already-known Isan stress leaders from the individual `hhdti`/`unemp` lenses), นครพนม 90.58,
  กำแพงเพชร 83.12.
- `platform/app.js`: new National-map menu lens `pstress` ("Province stress ▲ est") in the `LENS`
  registry, following the exact `hhdti` pattern — own lazy loader (`loadProvinceStress`), own
  `lensAbsent` branch (hides the pill if the file is absent/empty), own legend block honestly tagged
  "▲ estimated · NSO SES + NSO LFS blend" (unlike `hhdti`/`unemp`'s plain "measured" tags, since this
  one blends two percentiles into a composite), warmed unconditionally in `initMap()` (not just on
  `setLens`) so a `?lens=pstress` deep link resolves on first load.
- `tests/validate_data.py`: new `check_province_stress()` — meta/provenance present, honest
  ABSENT-state handling, `debt_to_income`/`unemployment_rate` ≥0, all three of
  `dti_percentile`/`unemployment_percentile`/`composite_stress` in [0,100], `composite_stress`
  recomputed from the two percentiles and compared (±0.01 tolerance), `rank` is a unique 1..N
  sequence. `tests/run.sh` gates `build_province_stress.py --check`.

**Verification:**
- `bash tests/run.sh check` — 32 passed, 0 failed (`validate_data.py`: 166/166, up from 162/162 —
  4 new checks for the new file). `node --check platform/app.js` clean.
- `python3 build_province_stress.py --check` reproduces byte-exact (0 drift).
- Headless-rendered `index.html?lens=pstress#map` (`tests/lib/render.sh`, screenshot + settled DOM):
  **first pass caught a real bug** — the `?lens=` deep-link handler in `initMap()` only sets
  `curLens` and re-renders the pill row; it does not itself trigger a lens's lazy loader (that's
  normally `setLens()`'s job, which only fires on a user click). Every other data-gated lens
  (`hhdti`, `occrisk`, `brisk`, `poirel`, `peerdev`) has its own unconditional warm-load line inside
  `initMap()` to cover exactly this deep-link case; the new `pstress` lens was missing the
  equivalent line, so a `?lens=pstress` deep-link render left the legend stuck on its loading
  skeleton forever (branch dots never colored/sized). Added the matching
  `if(!pstressLoaded) loadProvinceStress().then(...)` line in `initMap()` (mirroring `hhdti`'s at
  the same call site) and re-rendered: the fix confirmed — dots now colour/size by
  `composite_stress`, legend reads "12 / 49 / 98 stress (0–100, est) · estimated · NSO SES + NSO LFS
  blend", pill shows the honest `E` provenance badge, `data-errors="[]"` in the QA probe (no
  uncaught JS). Re-ran `tests/run.sh check` after the fix — still 32/0.

**Source:** `platform/data/household_risk_by_province.json` (NSO SES 2566, via `build_household_risk.py`,
already-audited MEASURED) + `source-data/unemployment_by_province.json` (NSO Labour Force Survey,
via the TMLI bridge / `ingest_tmli.py`, already-audited MEASURED). No external pull performed this
cycle — this is a re-projection/composite of two already-committed, already-sourced MEASURED layers.
Two near-duplicate `docs/IMPROVEMENT_BACKLOG.md` entries for this idea checked off; 3 follow-up ideas
logged (surface on Command Center hero; re-weight once a real loan tape exists to calibrate against;
add a 3rd DLT-collateral leg once that blocked pull lands).

---

## 2026-07-03 — AUDIT: fixed a false-red gate (missing `numpy` misreported as data drift)

**Task type:** AUDIT (gate integrity, not a data value change — no `platform/data` or `source-data`
file content was touched).

**Finding:** `bash tests/run.sh check` reported `build_branch_peers.py --check` as **FAIL** ("drifted
from branches.json/branch_risk.json/household_risk") on a clean checkout with no data changes. Root
cause: `pipeline/build_branch_peers.py` does `import numpy as np` unconditionally; `numpy` is not
installed by default in this sandbox, so the script raised `ModuleNotFoundError` before it could even
attempt the byte-comparison, and `tests/run.sh` treated the non-zero exit as "drifted". This is the
gap already flagged (unactioned) in `docs/IMPROVEMENT_BACKLOG.md`: *"Sandbox setup gap: numpy isn't
installed by default... a fresh loop session hits a false-red gate on cycle 1."* Confirmed by
installing `numpy` (`pip install --break-system-packages numpy`) — the same script then reproduces
`platform/data/branch_peers.json` byte-exact (0 drift), proving the data itself was never wrong; only
the gate's error reporting was misleading.

**Why this matters for the no-fabrication mandate:** a false "drift" failure is exactly the kind of
signal that could tempt a future cycle to "fix" the gate by regenerating/overwriting
`branch_peers.json` from whatever inputs happen to be lying around — which would risk silently
changing a MEASURED-input-derived file for a reason that has nothing to do with the actual data. Fixing
the gate to fail for the right reason (or not fail at all when the reason is a missing dependency)
protects against that.

**Fix applied (code only, zero data changes):**
- `pipeline/build_branch_peers.py`: wrapped `import numpy as np` in `try/except ImportError`; on
  failure it now prints `SKIP: numpy not installed ... — dependency missing, NOT data drift` to
  stderr and exits `3` (a distinct code from the `1` used for genuine `--check` drift).
- `tests/run.sh` `phase_check()`: added a `skip()` reporter (yellow `[SKIP]`, not counted in
  `failc`) and special-cased the `build_branch_peers.py --check` call to read its exit code — `0` →
  `[PASS]`, `3` → `[SKIP]` (numpy missing, gate stays green), anything else → `[FAIL]` (real drift).

**Verification (this sandbox has no numpy by default):**
- With `numpy` absent: `bash tests/run.sh check` → `30 passed, 0 failed` with a `[SKIP]` line for
  `build_branch_peers.py --check` (previously: `1 failed`).
- With `numpy` installed (`pip install --break-system-packages numpy`): `31 passed, 0 failed`,
  `build_branch_peers.py --check` reports `[PASS]` — confirms the real gate still runs and passes
  when the dependency is present.
- Regression check: hand-corrupted one field in the committed `platform/data/branch_peers.json` and
  reran `build_branch_peers.py --check` with numpy installed → correctly printed `DRIFT:
  platform/data/branch_peers.json` and exited `1` (still `[FAIL]`, not swallowed by the new skip
  path); restored the file from git afterward (verified `git status` clean before committing).
- `validate_data.py`: 158/158 (unaffected — this cycle touched no `platform/data` or `source-data`
  file).

**Source:** no external data pulled this cycle; this was a pipeline/tooling integrity fix per the
AUDIT task type, addressing an already-logged backlog gap. `docs/IMPROVEMENT_BACKLOG.md` item checked
off below.

---

## 2026-07-02 (2) — ENRICH: NSO Labour Force Survey unemployment rate wired into the province deep-dive

**Task type:** ENRICH (fold an already-vendored MEASURED layer into a view that didn't use it yet).
No new data value was invented — `source-data/unemployment_by_province.json` (NSO Labour Force
Survey, ไตรมาสที่ 3/2568, table `ST_02_2005005_4`, vendored via the TMLI bridge + `ingest_tmli.py`,
already gated in `tests/run.sh check`) was, until this cycle, only surfaced per-**branch** in
`platform/data/branch_labor.json` (the branch-explorer "who works nearby" card). It was never joined
into `pipeline/build_province.py`, so the 77 per-province deep-dive pages (`province.html?p=<slug>`)
had no labour-force-health readout at all — only the informal/formal employment split
(`employment_by_province.json`, a different NSO release).

**What changed:**
- `pipeline/build_province.py`: loads `source-data/unemployment_by_province.json` (graceful:
  `{}` per province if the file or the row is absent — no fabricated fill) and adds a new
  `gov.unemployment = {employed_k, unemployed_k, labor_force_k, unemployment_rate}` block to every
  province JSON, alongside the existing `gov.employment` (informal/formal). `gov.src` provenance
  string updated to name both NSO releases. Regenerated all 77 `platform/data/provinces/<slug>.json`
  + `index.json` — verified `build_province.py --check` reproduces byte-exact (0 drift) after the
  regen; `index.json` itself is untouched (no schema change there).
- `platform/province.html`: the "Who works nearby" panel now reads `RY.gov.unemployment` and, when
  `unemployment_rate` is present, appends one line — `Unemployment rate (province, NSO LFS) — X%` —
  directly under the existing DIW-factory-workers line, tagged the same `measured · NSO` style
  already used for the informal-share stat immediately above it. Renders nothing extra when the
  source is absent for a province (graceful).

**Verification:**
- `bash tests/run.sh check` — 28 passed, 0 failed (`validate_data.py`: 125/125 — the `provinces/`
  subtree is provenance-exempt at the schema level since it carries no top-level `meta` block, but
  every number added here traces to the cited MEASURED source file via `gov.src`).
- Rendered `province.html?p=rayong` (headless Chrome, `tests/run.sh render`) and read the PNG +
  settled DOM: page renders clean, no uncaught JS errors, deck.gl initialises; DOM dump confirms
  `Unemployment rate (province, NSO LFS)` → `0.72%` for Rayong, correctly positioned after the DIW
  factory-workers row. `province.html?p=chon-buri` also rendered clean.
- One unrelated, pre-existing render failure: `rayong-catchment.html` (the 3,631-building 3D scene)
  failed the headless-render pass in this sandbox — `tests/lib/render.sh`'s own comments document
  this exact page as intermittently producing an empty screenshot under software WebGL even with its
  built-in 4x retry. Confirmed unrelated to this change: `rayong-catchment.html` and its data
  dependency (`provinces/index.json`) are untouched by this diff (`git diff` shows 0 changes to
  `index.json`), and the mandatory `tests/run.sh check` gate — which is what CLAUDE.md requires green
  — passed cleanly.

**Source:** `source-data/unemployment_by_province.json` `meta` — "NSO Labour Force Survey —
provincial summary, via data.go.th / TMLI"; "NSO LFS ไตรมาสที่ 3/2568 (table ST_02_2005005_4)". No
external pull performed this cycle — this is a re-projection of an already-committed, already-audited
MEASURED source into a second view.

---

## 2026-07-02 — AUDIT: `gpp_by_province.json` mislabelled MEASURED, actually a 76/77-row estimate

**Task type:** AUDIT (provenance sweep). No new data value was invented or shipped; a false
"measured" claim already sitting in the repo was corrected.

**What was found.** `source-data/tmli/provincial-gpp.js` (vendored from `kaustavb2101/watcher` in
commit `b203eb6`) titles itself `PROVINCIAL GPP KNOWLEDGE BASE — NESDC OFFICIAL DATA` and its own
`GPP_META` block cites exactly **one** CKAN-verified resource
(`ffabdf4f-b326-4d2d-8ede-a4514bf20339`, Mukdahan only). Inspecting all 82 rows:
- Only **Mukdahan** carries `source: 'CKAN-NESDC-2566'` and `confidence: 0.95` — genuinely tied to a
  named CKAN resource.
- The other **76 provinces** carry a generic `source: 'NESDC-2566'` tag, GPP figures that are all
  round multiples of 1,000–5,000 (million THB) — a strong fabrication smell for a real economic
  statistic — and confidence scores (0.75–0.97) that look hand-assigned per region rather than
  measured. `GPP_META.downloaded_at` is `new Date().toISOString()` (evaluates at *load* time), which
  is inconsistent with a genuine timestamped API pull.
- `pipeline/ingest_tmli.py` (`build_gpp()`) had copied this straight through into
  `source-data/gpp_by_province.json` with `"provenance": "MEASURED. ... NESDC 2566 B.E. (2023 CE)
  estimate."` — an incorrect blanket claim. `docs/NEXT_STEPS.md` and `docs/DATA_PROVENANCE.md` both
  repeated the MEASURED label.
- **Contrast:** the other three TMLI-vendored files (`nso-ses-debt-2566.json`,
  `nso-ses-income-2566.json`, `nso-lfs-provincial-summary.json`) have non-round, per-province-distinct
  values and (for the LFS file) an explicit `catalogapi.nso.go.th` table id + `downloaded_at`
  timestamp — consistent with real pulls. Those remain labelled MEASURED; only the GPP layer is
  affected.

**Blast radius:** contained. `gpp_by_province.json` is **not yet wired into any `platform/data`
layer** — no view or score in the live app currently uses it — so this was caught before a fabricated
number reached a user-facing screen.

**Fix applied (no fabrication — corrected the label, did not invent a number):**
- `pipeline/ingest_tmli.py` `build_gpp()`: regex now also captures the per-row `source` tag; emits it
  in each province record; rewrote `meta.provenance` to state plainly that only 1/77 rows is
  CKAN-verified and the rest are an ESTIMATED knowledge base, with an explicit "do not surface as
  MEASURED" instruction; added `meta.n_ckan_verified`.
- Regenerated `source-data/gpp_by_province.json` (`python3 ingest_tmli.py`) — **only meta + the new
  per-row `source` field changed; every `gpp_million_thb`/share/hub_type value is byte-identical to
  before** (verified via diff before committing). `ingest_tmli.py --check` reproduces byte-exact.
- Corrected the MEASURED claims in `docs/NEXT_STEPS.md` (§0a) and `docs/DATA_PROVENANCE.md` (§2
  table) to match.
- `bash tests/run.sh check` — 28 passed, 0 failed (`validate_data.py`: 125/125). (Sandbox note: this
  run required `pip install numpy==2.4.6` per `.github/workflows/qa.yml`'s pin — not present by
  default in this container; installed to mirror CI exactly.)

**Follow-up (logged, not attempted — needs a real per-province pull):** a genuine fix requires
pulling NESDC Provincial Accounts per-province from `data.go.th` (same CKAN dataset family as the
verified Mukdahan resource, `package_search?q=GPP`, 44 datasets) from a Thai IP — blocked from this
sandbox. Added to `docs/TONIGHT_CHECKLIST.md`. Until then, `gpp_by_province.json` should **not** be
wired into any `platform/data` layer or app view labelled MEASURED.

**Source:** `source-data/tmli/provincial-gpp.js` (self-disclosed provenance in its own header/`GPP_META`) — no external pull performed this cycle.

---
