# DATA REFRESH LOG — dated entries from the data-enrichment & integrity cycle

> Appended by the recurring DATA-ENRICHMENT & INTEGRITY routine (one entry per cycle: what was
> refreshed/enriched/audited, with provenance + source). See `docs/IMPROVEMENT_BACKLOG.md` for the
> Rules this cycle follows (no-fabrication is absolute).

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
