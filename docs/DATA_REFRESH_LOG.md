# DATA REFRESH LOG — dated entries from the data-enrichment & integrity cycle

> Appended by the recurring DATA-ENRICHMENT & INTEGRITY routine (one entry per cycle: what was
> refreshed/enriched/audited, with provenance + source). See `docs/IMPROVEMENT_BACKLOG.md` for the
> Rules this cycle follows (no-fabrication is absolute).

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
