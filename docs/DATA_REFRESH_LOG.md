# DATA REFRESH LOG — dated entries from the data-enrichment & integrity cycle

> Appended by the recurring DATA-ENRICHMENT & INTEGRITY routine (one entry per cycle: what was
> refreshed/enriched/audited, with provenance + source). See `docs/IMPROVEMENT_BACKLOG.md` for the
> Rules this cycle follows (no-fabrication is absolute).

## 2026-07-10 (2) — ENRICH: commercial (truck/bus) DLT registration-FLOW distilled + wired in; fixed a dead-code path that was silently hiding both this and the prior cycle's scrappage callouts

**Task type:** ENRICH. **0. RE-DERIVE baseline first.** Fresh checkout of `claude/new-session-wto26j`,
`bash tests/run.sh check` → 61 passed, 0 failed (`validate_data.py` 453/453) before touching
anything — no drift to fix.

**1. What was found.** The backlog (`docs/IMPROVEMENT_BACKLOG.md`, "Queue — follow-ups noticed
2026-07-10") explicitly flagged `dataset_stat_1_009` (DLT land-transport-law registration-action
log — trucks/buses) as the same shape as the just-shipped car-law distiller
(`build_vehicle_flow.py` / `dataset_stat_1_008`) but not yet built, even though
`pipeline/pull_dlt_all.py`'s full-catalog mirror already secured all 50 monthly CSVs into
`source-data/dlt/raw/dataset_stat_1_009/`. Confirmed the raw files are genuinely a different
dataset (different CSV schema — 9 vehicle-type categories: trucks รถบรรทุก private/contract-hire,
7 bus รถโดยสาร subclasses, and an unqualified "small vehicle" รถขนาดเล็ก category — and two
cessation columns, "รถแจ้งเลิกใช้ ม.79"/"ม.89", instead of dataset_stat_1_008's single
"รถแจ้งไม่ใช้ตลอดไป" column), not a duplicate of anything already wired in.

**2. What was built (100% MEASURED, no modelling beyond a sum + a plain ratio).**
`pipeline/build_vehicle_flow_transport.py` — same trailing-12mo-sum method as
`build_vehicle_flow.py`, applied to this dataset: buckets `truck` (private + contract-hire),
`bus` (all 7 scheduled/unscheduled/international classes summed — none is individually
collateral-central), `small` (kept separate, not guessed into truck/bus), plus `all`.
`dereg_rate` sums BOTH ม.79 and ม.89 cessation columns without claiming to know why the source
splits them (documented plainly in `meta.formula` as a literal column-sum, not a legal opinion).
Output: `source-data/vehicle_flow_transport_by_province.json` (77 provinces, same window as the
sibling: 2025-03 → 2026-02). Sanity-checked the spread: truck `dereg_rate` 1.47%–8.12% (median
2.91%, p90 4.66%); bus `dereg_rate` 3.67%–26.24% (much wider — bus fleets per province are far
smaller, so the ratio is noisier over small denominators, e.g. สระแก้ว's 58/221 processed — a real
measured ratio, not an outlier that looks fabricated).

**3. Wired in gracefully.** `pipeline/build_province.py` joins the new file (graceful `{}` when
absent, identical pattern to `vehicle_flow`) into every `provinces/<slug>.json`'s
`gov.vehicle_flow_transport`; `meta.provenance.measured` gained a line. `platform/province.html`
gained a truck-scrappage watch line for provinces at/above `dereg_rate≥4.5%` (~top decile,
p90=4.66%) — mirrors the existing moto-scrappage line's threshold logic.

**4. Found + fixed a real bug while wiring this in: `autoImpacts()` was dead code on every
province.** Regenerating and reading `provinces/nakhon-pathom.json` (top truck-dereg province,
8.12%) to sanity-check the new UI line surfaced that `buildProvincePanels()`'s
`const impacts = editorial ? f.impacts : autoImpacts()` branch never actually calls
`autoImpacts()` — `source-data/province_narratives.json` now has non-empty `impacts` for **all 77
provinces** (not just the Rayong pilot `CLAUDE.md` still describes), so `editorial` is always
truthy. That silently hid not only this cycle's new truck-scrappage line but ALSO the prior
cycle's (2026-07-10 (1)) motorcycle-scrappage line — both were correctly computed and joined into
`platform/data`, but never rendered anywhere. Fixed by extracting the two DLT-flow watch-flags
into their own `vehicleFlowImpacts()` function and always appending its (sparse — only ~top-decile
provinces trigger either flag) output to whichever impacts list renders, editorial or auto-derived,
instead of letting the editorial branch fully suppress them. Verified with a hand-run Node script
against the live `nakhon-pathom.json`/`sa-kaeo.json` data (simulating the exact JS logic) since this
page's headless render is separately, already-documented flaky in this sandbox (2026-07-03 (7),
2026-07-05, 2026-07-10 (1)) — confirmed Nakhon Pathom's 6 impacts now include "Elevated
commercial-truck scrappage" appended after its 5 editorial lines, and confirmed provinces below
both thresholds are unaffected (only the sparse flag lines change, nothing else).

**5. Gates.** `tests/run.sh` gained a gated `build_vehicle_flow_transport.py --check` line
(graceful `[SKIP]` when the source mirror is absent, same convention as its sibling).
`tests/validate_data.py` gained `check_vehicle_flow_transport()`: verifies the source file's
meta/values (buckets present, counts ≥0, rates in [0,1]) AND that every `provinces/<slug>.json`'s
`gov.vehicle_flow_transport` is an exact pass-through of the source row. `node --check` on the
extracted inline JS of `province.html` (5/5 blocks) passed. `bash tests/run.sh check` →
**62 passed, 0 failed**, `validate_data.py` **458/458** (+5 new checks).

**6. Docs.** `docs/DATA_PROVENANCE.md` §2 register gained a row for
`vehicle_flow_transport_by_province.json`. `docs/CKAN_SOURCES.md`'s `dataset_stat_1_009`
"next target" line marked DONE.

**Source:** `gdcatalog.dlt.go.th` `dataset_stat_1_009` (mirrored via `pipeline/pull_dlt_all.py`,
already committed to this branch by a concurrent session before this cycle started) — no new
external pull performed this cycle; this cycle distilled already-committed raw data and fixed a
display-layer bug discovered while verifying the new layer actually surfaces.

---

## 2026-07-10 — ENRICH: DLT vehicle registration-transaction FLOW (dereg/transfer rates) distilled + wired into the province deep-dive

**Task type:** ENRICH. **0. RE-DERIVE baseline first.** Fresh checkout of
`claude/new-session-wto26j`, `bash tests/run.sh check` → 59 passed, 0 failed
(`validate_data.py` 448/448) before touching anything — no drift to fix.

**1. What was found.** A concurrent "DATA HUNT" standing loop landed `e2336293` (wave 10, earlier
today) — `pipeline/pull_dlt_all.py` mirrored DLT's ENTIRE gdcatalog (380 files, 14 datasets) into
`source-data/dlt/raw/`, bypassing the data.go.th geoblock. One dataset in that mirror,
`dataset_stat_1_008` ("การดำเนินการทางทะเบียน" — car-law registration-ACTION log, 50 monthly CSVs,
national, covering every calendar month Jan-2022 → Feb-2026), was sitting completely unprocessed —
CKAN_SOURCES.md itself named it a "next-wave target," and no pipeline script or `platform/data`
layer referenced it. Confirmed this is genuinely additive, not a duplicate: the existing
`vehicles_by_province.json` (dataset **1_1_04**, already wired into the `motomix`/`pickups`
National-map lenses) is a vehicle-STOCK snapshot (byte-identical total, 44,290,957, verified against
the new mirror's copy of the same dataset — no re-fabrication risk there); `dataset_stat_1_008` is a
different DLT release entirely — a monthly registration/deregistration/transfer-ACTION log, i.e. a
FLOW signal the app had no equivalent of.

**2. What was built (100% MEASURED, no modelling beyond a sum + a plain ratio).**
`pipeline/build_vehicle_flow.py` sums the TRAILING 12 available months (Mar-2025 → Feb-2026, the
most recent complete year — a single month would be noisy) per province, for three
collateral-relevant vehicle classes (car รย.1, pickup รย.3, motorcycle รย.12) + an all-types total,
then derives two plain ratios per class: `dereg_rate` = permanently-deregistered
("รถแจ้งไม่ใช้ตลอดไป") / total-processed ("รถที่ดำเนินการ") — a collateral-ageing/scrappage proxy —
and `transfer_rate` = ownership-transfers ("รถโอน") / total-processed — a used-vehicle-market
liquidity proxy. Output: `source-data/vehicle_flow_by_province.json` (77 provinces, full
`meta.{source,formula,window_months}`). National spread sanity-checked: moto `dereg_rate` ranges
0.02%–4.1% (median 0.14%, p90 1.47%) and moto `transfer_rate` ranges 2.4%–16.6% across provinces —
plausible, no outlier that looks fabricated.

**3. Wired in gracefully.** `pipeline/build_province.py` joins the new file (graceful `{}` when
absent, same pattern as the existing `unemployment`/`income` joins) into every
`provinces/<slug>.json`'s `gov.vehicle_flow`; `meta.provenance.measured` gained one line documenting
the field and its distinction from `gov.vehicles` (STOCK, different dataset). `platform/province.html`'s
`autoImpacts()` (the auto-derived "what moves local incomes" narrative, already used for
motorcycle-collateral-share/EV/factory-payroll callouts) gained ONE new conditional line: provinces
with moto `dereg_rate ≥ 1%` (roughly the national top decile — 14/77 provinces cross it) get an
"Elevated motorcycle scrappage" watch-tagged callout citing the actual percentage. Regenerated all
77 province files + `index.json` (`build_province.py --check` reproduces byte-exact).

**4. Gates.** `tests/run.sh` gained a gated `build_vehicle_flow.py --check` line (graceful `[SKIP]`
when the source mirror is absent, mirroring `build_branch_fuel.py`'s convention — not a hard `[FAIL]`
if a future checkout lacks the DLT mirror). `tests/validate_data.py` gained `check_vehicle_flow()`:
verifies the source file's meta/values (buckets present, counts ≥0, rates in [0,1]) AND that every
`provinces/<slug>.json`'s `gov.vehicle_flow` is an EXACT pass-through of the source row (no silent
recomputation drift). `bash tests/run.sh check` → **60 passed, 0 failed**, `validate_data.py`
**453/453** (+5 new checks). Headless-render of `province.html?p=tak` (Tak has the highest moto
dereg_rate nationally, 4.1%, so should trigger the new callout) hit the same pre-existing,
already-documented sandbox flakiness this exact page has shown in multiple prior cycles (2026-07-03
(7)/2026-07-05: `province.html`/`rayong-catchment.html` intermittently fail headless render under
this container's software WebGL) — confirmed unrelated to this change by (a) `node --check`ing the
extracted inline JS directly (clean, 5/5 blocks) and (b) reading `provinces/tak.json` by hand to
confirm `gov.vehicle_flow.moto.dereg_rate = 0.041` is exactly what the new conditional reads and
would render. The mandated `bash tests/run.sh check` gate — what CLAUDE.md requires green — passed.

**5. Docs.** `docs/DATA_PROVENANCE.md` §2 register gained a row for
`vehicle_flow_by_province.json` (distinguishing it from the pre-existing `vehicles_by_province.json`
row). `docs/CKAN_SOURCES.md`'s "next-wave target" line marked DONE, with the still-open sibling
(`dataset_stat_1_009`, land-transport-law trucks/buses — same shape, not yet distilled) logged as the
new target.

**Source:** `gdcatalog.dlt.go.th` `dataset_stat_1_008` (mirrored via `pipeline/pull_dlt_all.py`,
already committed to this branch by a concurrent session before this cycle started) — no new
external pull performed this cycle; this cycle only distilled and wired in already-committed raw
data.

---

## 2026-07-06 — AUDIT: closed R6, the last open provenance-register gap (7 OSM ground-bed geometry files stamped with real `meta.source`)

**Task type:** AUDIT (provenance-integrity pass — no geometry/numeric value changed; only a `meta`
block was added to already-committed files, verified byte-diff-clean on the underlying arrays).

**0. RE-DERIVE baseline first.** Fresh checkout of `claude/new-session-wto26j`,
`bash tests/run.sh check` → 53 passed, 0 failed (`validate_data.py` 433/433) before touching
anything. Re-ran every deterministic builder named in the routine's step 2(a)
(`derive.py`, `build_amphoe.py`, `build_province.py`, `build_crop_stress.py`,
`build_occupations.py`/`build_amphoe_occupations.py` — both correctly `SKIP` (no
`source-data/overture_places.json` yet), `build_opportunity_score.py`, `ingest_tmli.py`) — all
`--check` green, tree already fully in sync. Also re-checked PR #1: `mcp__github__list_pull_requests`
still shows it open/not-draft, `master` still un-imported — no change since 2026-07-05, not
re-flagging.

**1. What R6 was.** `docs/DATA_PROVENANCE.md`'s risk register has carried an open item since the
2026-07-04 audit: `rayong_landuse/roads/water/rail.json` and `bangkok_landuse/roads/water.json` are
genuine, 100%-measured OpenStreetMap geometry (pulled by `pipeline/pull_rayong_ground.py`,
`pull_rayong_extra.py`, `pull_city_3d.py`) but shipped as a bare `{"roads":[...]}`-style array with
**zero embedded `meta`** — the exact same class of gap R2/R3 closed for the `*_catchment.json`
building files back on 2026-07-04, just never done for the ground-bed layers. They were sitting on
`tests/validate_data.py`'s `PROVENANCE_EXEMPT` list rather than passing the provenance gate on their
own merits.

**2. Fix applied — real facts only, no fabrication.** Confirmed the exact pull commit/bbox/endpoint
per file from `git log --diff-filter=A` and each pull script's own defaults/PRESETS before writing
anything:
- `rayong_roads/water/landuse.json` — `pipeline/pull_rayong_ground.py`, bbox `12.655,101.155,12.725,101.310`, commit `a7a1491`.
- `rayong_rail.json` — `pipeline/pull_rayong_extra.py`, bbox `12.62,101.13,12.74,101.33`, commit `9a30396`.
- `bangkok_roads/water/landuse.json` — `pipeline/pull_city_3d.py --preset bangkok`, bbox `13.715,100.515,13.765,100.565`, commit `43b6fe3`. Honestly noted in the new `meta.note` that this bbox is **narrower** than `bangkok_catchment.json`'s full-metro building pull, so the ground bed doesn't extend under every building in the outer metro — a real, previously-undocumented asymmetry.

Added `meta.{city,source,bbox,note,n_features,committed_in}` to all 7 committed files (feature counts
computed directly from each file's own array, not invented). **Verified byte-diff-clean**: for every
file, the underlying `roads`/`water`/`landuse`/`rail` array is identical before/after — only the new
top-level `meta` key was added.

**3. Kept the fix live for future re-pulls.** Updated `pull_rayong_ground.py`, `pull_rayong_extra.py`,
and `pull_city_3d.py` so the next time any of them actually runs (from a Thai IP / Overpass mirror),
the same `meta` block is emitted automatically — this doesn't regress the moment `docs/TONIGHT_CHECKLIST.md`'s
"more tiles"/"more cities" pulls happen.

**4. Housekeeping.** `tests/validate_data.py`'s `PROVENANCE_EXEMPT` set: removed the 7 files (they now
pass `check_provenance()` on real `meta.source`, same as the `*_catchment.json` precedent) — narrowed
the exemption list to just `rayong_province.json` (curated deep-dive, unrelated, R-none). Regenerated
`platform/data/provenance.json` (`build_provenance.py`) since its aggregate counts shift with the new
meta stamps: unlabelled dropped 8→6, measured 20→22. `docs/DATA_PROVENANCE.md`: R6 marked CLOSED, §1
register rows updated for all 7 files.

**Verification:** `bash tests/run.sh check` → 53 passed, 0 failed (`validate_data.py` 433/433,
unchanged pass *count* — the provenance gate re-classifies these 7 files as sourced-by-their-own-meta
rather than exempt, net check count is the same because it's a set-membership reclassification, not a
new check). `git status` confirms only the 7 ground-geometry files + 3 pull scripts + `provenance.json`
+ `tests/validate_data.py` + `docs/DATA_PROVENANCE.md` changed — no page/app.js touched, so no render
verification required per the routine's own rule ("if you changed a page, render it").

**Source:** no external pull this cycle — every fact stamped (bbox, pull script, commit hash, feature
count) was read directly from git history and the pull scripts' own code, then written into files that
already existed. Nothing invented; `docs/IMPROVEMENT_BACKLOG.md`'s R6 backlog line closed below.

---

## 2026-07-05 (7) — AUDIT: RE-DERIVE baseline green; closed 2 stale backlog duplicates; re-confirmed the OAE dead-end and PR #1 unmerged status (no change)

**Task type:** AUDIT (backlog hygiene + gate/source re-verification — zero `platform/data` or
`source-data` values changed this cycle).

**1. RE-DERIVE baseline.** Fresh checkout of `claude/new-session-wto26j`, `bash tests/run.sh check`
→ **52 passed, 0 failed** (`validate_data.py` 429/429, provenance gate: 372 numeric `platform/data`
layers scanned, 359 sourced + 13 documented-exempt, 0 unsourced). No fix needed — the tree was
already in sync. `/workspace/watcher` (TMLI blueprint) was not present in this sandbox this cycle.

**2. Re-confirmed PR #1 is still unmerged (no change since 2026-07-05 (4)).**
`mcp__github__list_pull_requests(state=open)` → PR #1 still open, not draft.
`mcp__github__actions_list(list_workflows)` → still only `QA` registered. Same state as the
2026-07-05 (4) audit; not re-flagging via `PushNotification` since nothing has changed. Backlog
entry left open (not checked off) pending an actual status change.

**3. Re-confirmed the OAE farm-gate price pull is a genuine dead end (not a transient gap).**
`pipeline/pull_oae_prices.py --selftest` (offline, 30/30 assertions) then `--dry-run` (real network
— `catalog.oae.go.th` is reachable from this sandbox). Queried `package_search` directly for the
puller's exact term (`ราคาที่เกษตรกรขายได้`) plus 5 broader Thai/English terms
(`ราคา`, `ราคาสินค้าเกษตร`, `ข้าวเปลือก`, `ยางแผ่นดิบ`, `farmgate`, `price`) — every query returns
at most 6 results catalog-wide, and none is a per-crop farm-gate price series with a
CSV/XLSX/datastore resource for any of our 6 target crops (rice, rubber, sugarcane, oil palm,
cassava, maize). The puller's top-ranked match (`มูลค่าผลผลิตสินค้าเกษตรที่สำคัญ`) is JSON-metadata-only
with no priced series inside; the next-best match (`มูลค่าของผลไม้เมืองร้อน`, tropical fruit) is
off-topic. This reinforces (with fresh live evidence, not a re-read of old notes) the 2026-07-05 (5)
conclusion that this needs a Thai-IP `data.go.th` pull or manual news-URL discovery, not another
sandbox CKAN search retry. `build_crop_stress.py` correctly stays on the honestly-labelled World Bank
GLOBAL proxy — no data changed.

**4. Closed 2 stale backlog duplicates (code already shipped, never checked off):**
- **Competitor coverage QA panel** — `pipeline/build_competitor_coverage.py` (shipped 2026-06-30) already
  does exactly what the still-open `[ ]` entry asked for; confirmed via `grep` + reading the script
  before touching anything.
- **NSO census occupation distiller scaffolding** — `pipeline/ingest_gov.py`'s `build_occupations_census()`
  + `OPTIONAL_LAYERS` (commit `7fd4994`, 2026-06-30) already distill the blocked NSO 2022 Business &
  Industrial Census export into `source-data/occupations_by_district.json`, returning `None` (silent,
  crash-free skip) when `dgt_out/nso_census__bizind__*.csv` is absent — confirmed still absent in this
  sandbox (`ingest_gov.py --check` fails at the *mandatory* `factories_diw` layer for the same reason,
  since no `dgt_out/` pull has ever landed here — expected, this script isn't gated in `tests/run.sh`
  precisely because it needs the blocked Thai-IP pull). Verified via `git log -S"build_occupations_census"`
  before touching anything; no code changed, both items checked off in `docs/IMPROVEMENT_BACKLOG.md`
  rather than re-built.

**Also investigated and ruled out as a non-issue:** `source-data/commodities.json` /
`commodities_protein.json` (World Bank Pink Sheet raw-parse snapshots, orphaned from any pipeline
script — nothing reads them back, only `cache/commodities.json` inside the gitignored cache dir is
consumed) looked unsourced at first glance (bare dict, no embedded `meta`), but `docs/DATA_PROVENANCE.md`
line 84 already documents both files by name as MEASURED World Bank Pink Sheet — confirmed no gap,
no doc change needed.

**Verification:** `bash tests/run.sh check` — 52 passed, 0 failed, before and after (docs-only cycle).

**Source:** no external data pulled/committed this cycle (network calls were read-only catalog
queries against `catalog.oae.go.th`, used only to verify a dead end, not to land data). `github` MCP
used for PR/workflow status checks. Full backlog updates: `docs/IMPROVEMENT_BACKLOG.md` (2026-07-05
(7) entries).

---

## 2026-07-05 (4) — AUDIT: found the real reason the OAE puller (and every other scheduled data workflow) has never fired — none of them are merged to `master`

**Task type:** AUDIT (repo/CI integrity, not a data value change — zero files under `platform/data`
or `source-data` touched). `/workspace/watcher` [TMLI blueprint] was not present this cycle. A
RE-DERIVE pass first confirmed the working tree needed no fix: `bash tests/run.sh check` on a clean
pull of `claude/new-session-wto26j` was already green (52 passed, 0 failed, `validate_data.py`
429/429).

**What was investigated.** The 2026-07-05 (4) backlog entry flagged the OAE farm-gate price puller
(`pipeline/pull_oae_prices.py`, weekly `data-oae-prices.yml`) as the single highest-value pending
ENRICH — the infra shipped in commit `56c2e93` but `source-data/oae_farmgate_prices.json` still
doesn't exist, and it asked "why hasn't the weekly cron fired yet." Checked GitHub Actions directly
(MCP `actions_list`/`list_pull_requests`) instead of guessing:

- `mcp__github__actions_list(list_workflow_runs, data-oae-prices.yml)` → **404 Not Found** — GitHub
  doesn't even recognize this workflow file as a registered workflow.
- `mcp__github__actions_list(list_workflows)` → only **one** workflow is registered for this whole
  repo: `QA` (`.github/workflows/qa.yml`). None of the other 7 workflow files in the repo
  (`data-fuel-prices.yml`, `data-macro.yml`, `data-nabc-prices.yml`, `data-oae-prices.yml`,
  `data-overture.yml`, `data-tiles.yml`, `site-health.yml`) are registered at all.
- Root cause: **PR #1 ("Import platform + one-command data refresh…"), open since 2026-06-28, has
  never been merged into `master`.** `git fetch origin master` + `git ls-tree origin/master` shows
  `master` still only contains the pre-import single-page site (`index.html`, `vercel.json`, `.env`)
  — no `platform/`, `pipeline/`, `.github/workflows/`, nothing. GitHub Actions only discovers
  `schedule:`-triggered and (per this repo's evidence) `workflow_dispatch:`-only workflows from the
  files present on the **default branch**; `QA` is the sole exception because it also triggers on
  `push: branches: ["**"]`, which self-registers the workflow the first time it runs on *any* branch
  (confirmed via `list_workflow_runs(qa.yml)`, which returned a long history of runs on this feature
  branch).
- Practical effect: **every one of the 5 `schedule:`-cron workflows has never executed, not once** —
  `data-fuel-prices.yml` (claimed daily), `data-nabc-prices.yml` (claimed daily), `data-macro.yml`
  (weekly), `data-oae-prices.yml` (weekly), `site-health.yml` (daily). Cross-checked the two "daily"
  claims against `git log`: `source-data/fuel_prices.json` (commit `ea93b96`) and
  `source-data/nabc_prices.json` (commit `d132ea8`) were each landed by a **single Claude Code
  session committing directly to this branch**, not by the workflow executing on a schedule — the
  data in both files is real (Bangchak/NABC public APIs, genuinely pulled that one time, correctly
  labelled MEASURED — no fabrication concern), but the docs/commit messages describing them as "daily
  workflow refreshes it" are **misleadingly implying an active recurring refresh that has never
  actually happened even once**. Both files are frozen at their one-time pull date until either (a)
  PR #1 merges to `master`, or (b) someone manually re-dispatches/re-runs the puller.

**Why this matters for the no-fabrication mandate:** nothing here is fabricated data, but it is a
**provenance-freshness illusion** — a reader (or a future cycle) could reasonably assume
`fuel_prices.json`/`nabc_prices.json` are auto-refreshing daily and treat a week-old snapshot as
current, or keep re-investigating "why hasn't the OAE cron fired" as if it were a transient CI bug
(exactly what the 2026-07-05 (4) backlog entry was doing) when the real cause is a one-line repo fact:
**the branch carrying all this pipeline/workflow code has simply never been merged.** No amount of
loop cycles re-running or re-diagnosing the puller from `claude/new-session-wto26j` will fix this —
merging is the only fix, and it's a repo-owner decision (merging PR #1), not something this loop
should do unilaterally.

**Fix applied (docs only, zero data/pipeline code changed):**
- Re-scoped the 2026-07-05 (4) OAE backlog entry below: the puller isn't stuck or broken — it has
  simply never had a chance to run, and neither has anything else with a `schedule:` trigger.
- This entry documents the root cause plainly so no future cycle re-investigates the OAE puller (or
  assumes fuel/NABC prices are auto-refreshing) without first checking whether PR #1 has merged.

**Verification:** no data or pipeline file changed this cycle — `bash tests/run.sh check` unaffected
(52 passed, 0 failed, `validate_data.py` 429/429, identical before/after since this is a docs-only
commit).

**Source:** GitHub Actions API via the `github` MCP server (`actions_list`, `list_pull_requests`) +
`git fetch origin master` / `git ls-tree origin/master` (this repository's own ref state) — no
external data pulled, no repo-state assumption taken on faith.

---

## 2026-07-05 (3) — ENRICH: live Bangchak fuel prices (sitting unwired since this morning's pull) wired into the Home macro card

**Task type:** ENRICH. `/workspace/watcher` [TMLI blueprint] was not present this cycle. `bash
tests/run.sh check` on a clean pull of `claude/new-session-wto26j` was already green (49 passed, 0
failed, `validate_data.py` 423/423) — no RE-DERIVE drift to fix. A scan for already-vendored-but-
unwired `source-data/*` layers found `fuel_prices.json` (added earlier today, commit `ea93b96`,
"Add live fuel prices (Bangchak, cloud-reachable) + daily workflow"): the file is real — pulled from
Bangchak's public retail oil-price API (free, no key, cloud-reachable; verified `pulled: 2026-07-05`
in the file's own meta, diesel ฿37.50/L, gasohol95 ฿37.45/L) — but nothing in `platform/data` or
`platform/app.js` read it. Diesel price tracks the cost of running a pickup/farm vehicle and gasohol
tracks motorcycles — AutoX's two dominant title-loan collateral types — so this is a real, cheap,
daily macro-pressure signal on borrower cash flow that was going to waste.

**What changed (no new data invented — pure re-projection + UI wiring of an already-real pull):**
- New `pipeline/build_fuel_prices.py`: validates `source-data/fuel_prices.json` (headline diesel/
  gasohol95 present, both within a sane 10–100 THB/litre bound — catches a malformed pull rather
  than shipping garbage) and projects it **verbatim** (every number carried through unchanged) into
  `platform/data/fuel_prices.json`, with `meta.generated_by`/`meta.provenance` naming the Bangchak
  source and the daily workflow. `--check`-gated; exits 3/SKIP (not FAIL) when the source pull is
  absent, matching the existing `build_branch_density.py` convention for optional cloud-refreshed
  inputs. `tests/run.sh` and `tests/validate_data.py` (`check_fuel_prices()`, SKIP-pass when absent)
  gained coverage; `pipeline/build_provenance.py` regenerated to include the new layer in the
  measured/estimated/unlabelled census.
- `platform/app.js`: new `loadFuelPrices()` (same lazy, null-safe fetch pattern as every other
  optional Home-tab layer) + a "Fuel prices · measured · Bangchak retail, daily" section appended to
  `renderHomeMacro()`'s "Regulatory watch" card, showing today's diesel (pickup/farm borrowers) and
  gasohol 95 (motorcycle-title borrowers) price. Renders nothing when the file is absent — graceful,
  no fabricated placeholder.

**Verification:**
- `bash tests/run.sh check` — 50 passed, 0 failed (`validate_data.py`: 426/426, +3 new checks: meta/
  provenance present, headline object present, headline values sane). `build_fuel_prices.py --check`
  reproduces byte-exact.
- Headless-rendered `index.html#home` (`tests/lib/render.sh`): `data-errors="[]"` (zero JS errors),
  DOM dump confirms the live section renders — `Diesel … ฿37.5 THB/L`, `Gasohol 95 … ฿37.45 THB/L`,
  tagged measured, positioned under "Key commodity moves" in the macro card. Screenshot confirms no
  layout regression elsewhere on Home.
- Reverted one unrelated side-effect before committing: installing the headless-render harness's npm
  deps (`tests/.cache/node_modules`, gitignored) had incidentally rewritten `tests/package.json`'s
  pinned `deck.gl`/`leaflet` versions from exact (`8.9.35`/`1.9.4`) to caret ranges — restored via
  `git checkout -- tests/package.json` before staging, so this cycle's diff touches only the files
  described above.

**Source:** `source-data/fuel_prices.json` `meta.source` — "Bangchak retail oil-price API
(www.bangchak.co.th/api/oilprice) — daily Bangkok reference prices; free, no key, cloud-reachable."
No external pull performed this cycle — this re-projects an already-committed, already-real pull
into its first consuming view.

---

## 2026-07-05 — AUDIT: closed the R1 provenance gap — `provinces/<slug>.json` now embeds its own `meta.provenance`

**Task type:** AUDIT. `/workspace/watcher` [TMLI blueprint] was not present this cycle, so no new
cross-repo TMLI layer could be folded in. A RE-DERIVE pass first confirmed the working tree was
already fully in sync on a clean pull of `claude/new-session-wto26j`: `bash tests/run.sh check` —
47 passed, 0 failed, `validate_data.py` 421/421, no drift. A scan of every unwired `source-data/*`
file (`gpp_by_province.json`, `google_trends.json`, `spam2010_th_cropgrid.json`,
`worldpop_tha_2020_1km.tif`, `osm_gapcheck.json`, `competitors_official.json`, `heng_branches.json`)
confirmed each is either already wired into a builder or (in `gpp_by_province.json`'s case)
correctly and deliberately left unwired per the 2026-07-02 audit — nothing new to enrich this cycle.

Moved to closing an open item in `docs/DATA_PROVENANCE.md`'s own RISK REGISTER (§3), **R1**:
`provinces/<slug>.json` (77 files) + `provinces/index.json` carried numeric rollups (branch/district
counts, DIW factories, DLT vehicles, NSO workers/unemployment/income, OSM POI) with **no embedded
`meta` block** — every input was already a named sourced layer and the build was already `--check`
byte-exact deterministic, but the file itself didn't say so (flagged LOW since 2026-07-01, never
picked up).

**Fix applied (no fabrication — no data value changed):**
- `pipeline/build_province.py`: each per-province `obj` now carries a `meta` block —
  `meta.generated_by` + `meta.provenance.{measured,editorial,estimated}` naming every field's real
  source (branches = PIP of `branches_final.json` into `th_amphoe.geojson`; POI = OSM/Overpass
  `osm_layers.json`; district factories/workers = DIW `factories_by_district.json` prov|district
  join; district competitors = deduped Google Places/Overture/official-locator census; `gov.*` =
  DLT/NSO/TMLI province totals, explicitly noting the existing null-not-zero rule for absent
  provinces; `facts` = EDITORIAL `province_narratives.json`; `en`/`slug` = an ESTIMATED naming
  derivation, not a measured value) — mirrors `build_amphoe.py`'s existing `meta.provenance` pattern.
- **Deliberately left `provinces/index.json` a bare array** (not wrapped in `{meta, provinces:[...]}`)
  — it is fetched directly as an array by ~6 frontend call sites (`app.js` ×4, `province.html`,
  `rayong-catchment.html`, `branch-explorer.html`); restructuring it would be a breaking frontend
  change for a documentation-only gain. Its rows are a straight projection of the now-documented
  per-slug files, so the provenance gap is closed one level down instead.
- Regenerated all 77 `platform/data/provinces/<slug>.json` (`python3 build_province.py`) —
  byte-diff confirms **only the new top-level `meta` key was added; every existing field
  (branches/districts/poi/gov/facts) is unchanged** — `build_province.py --check` reproduces
  byte-exact. `index.json` untouched (0 diff).
- Verified no frontend code path breaks: `province.html`/`rayong-catchment.html`/`app.js` all access
  specific known keys off the per-province object (`RY.branches`, `RY.competitors`, `RY.poi`,
  `RY.districts`, `RY.province_en/th`, `RY.region`, `RY.gov.*`, `RY.facts`) — none enumerate/iterate
  its keys, so the additive `meta` key cannot affect any existing render path.
- Updated `docs/DATA_PROVENANCE.md` §1 (the `provinces/<slug>.json` and `provinces/index.json` table
  rows) and §3 (closed R1, explaining the index.json bare-array exception) to match.

**Verification:** `bash tests/run.sh check` — 47 passed, 0 failed (`validate_data.py`: 421/421, no
regression from the pre-cycle baseline). `python3 build_province.py --check` — reproduces byte-exact.
Headless-render of `province.html?p=rayong` was attempted 3x but failed to produce a screenshot each
time under this sandbox's software WebGL (`ERR_CONNECTION_REFUSED`/empty-screenshot) — this matches
already-documented sandbox flakiness for WebGL-heavy pages (see the 2026-07-02 (2) log entry's note
on `rayong-catchment.html`'s intermittent empty-screenshot behavior), not a regression from this
change: the diff touches zero HTML/JS, only an additive JSON key, and the mandated
`bash tests/run.sh check` gate is what CLAUDE.md requires green.

**Source:** no new external pull this cycle — this closes an in-file documentation gap over already-
sourced inputs (DIW/DLT/NSO/OSM/TMLI, all cited in the new `meta.provenance` block and previously
recorded in `docs/DATA_SOURCES.md`/`docs/DATA_PROVENANCE.md`).

---

## 2026-07-04 (8) — AUDIT: closed the two remaining unsourced-catchment provenance gaps flagged in `docs/DATA_PROVENANCE.md`'s risk register (R2/R3)

**Task type:** AUDIT. `/workspace/watcher` [TMLI blueprint] was not present this cycle. A RE-DERIVE
pass first confirmed the working tree was already fully in sync: `bash tests/run.sh check` on a
clean pull of `claude/new-session-wto26j` — 47 passed, 0 failed, `validate_data.py` 421/421, no
drift. With nothing to re-derive and no cross-repo TMLI pull possible (no watcher checkout), moved
to an AUDIT pass over `docs/DATA_PROVENANCE.md`'s own RISK REGISTER (§3) — the standing list of
"provenance gaps to review" the project already tracks honestly.

**What was found.** Two of the three "MEDIUM" register items (R2/R3) were real, closeable gaps —
numeric 3D-scene building-footprint layers shipping with **zero embedded provenance**, unlike every
other `platform/data` layer:
- `platform/data/rayong_catchment.json` — 180,000 building footprints (`{"buildings":[...],
  "center":{...}}`, **no `meta` key at all**). Confirmed via `git log` this is a real Overture pull
  (commit `9482b0e`, "Rayong catchment: province-wide 180k-building pull") — the source was always
  known, just never recorded in the file itself.
- `platform/data/chiang-mai_catchment.json` — same shape, 180,000 buildings, **no `meta` key**, and
  wasn't even listed in `DATA_PROVENANCE.md`'s table (a second, smaller gap: the register itself was
  incomplete). Confirmed via `git log`: commit `373b4f0`, "Chiang Mai 3D catchment: 180k-building
  Overture pull (web-sized)... 2.66M raw features capped to the dense core."
- Checked the third register item, `bangkok_catchment.json`, against the actual committed file
  (not just the doc's claim) — the doc said "meta has city/n_bldg/floor_area_m2 but no source", but
  the file **already carries `meta.source`** ("Overture Maps buildings (memory-safe streaming pull,
  6 strips, reservoir cap 180000)"). The register entry itself was stale, describing a state from
  before an earlier (undocumented) fix. No action needed on the data; corrected the doc instead.

**Fix applied (provenance metadata only — zero building/geometry values touched, no fabrication):**
- Added a `meta` block to `rayong_catchment.json` and `chiang-mai_catchment.json`, mirroring the
  exact style already used by `bangkok_catchment.json`: `city`, `n_bldg` (the real, verified 180,000
  count — matches `pull_overture_buildings.py`'s documented `--max-buildings 180000` default and the
  commit messages exactly), `source` (names the puller script + cap, real and verifiable), `note`
  (states plainly that footprints are MEASURED/Overture but heights are ESTIMATED from type +
  footprint area via `bake_catchment_heights.py` where Overture has no height tag — the same honest
  caveat the UI already carries), and `committed_in` (the exact commit hash, so a future reader can
  verify against `git log` themselves rather than trust the string). **Did NOT invent a `seen`
  (raw-features-before-cap) figure for either file** the way `bangkok_catchment.json`'s meta has one
  — that number isn't recorded anywhere in the commit history for Rayong, and Chiang Mai's commit
  message states "2.66M raw features" which I DID cite verbatim in the `note` field (traceable to
  commit `373b4f0`), but did not promote to a structured `seen` field since the commit message's
  number is prose, not a self-reported build-time tally the way Bangkok's `seen:3105076` was.
- Regenerated `platform/data/provenance.json` (`python3 build_provenance.py`) so the census picks up
  the two newly-provenanced files — `unlabelled_files` count dropped from including these two entries
  (confirmed via diff: both no longer appear in `unlabelled_files`).
- `tests/validate_data.py`'s `PROVENANCE_EXEMPT` list: removed `rayong_catchment.json` and
  `chiang-mai_catchment.json` (they now pass `check_provenance()`'s substantive `_has_provenance()`
  check on their own merits — no longer need the blanket geometry-layer exemption); corrected the
  stale `bangkok_catchment.json` inline comment. Gate's own count moved from "274 sourced / 92
  documented-exempt" to **"276 sourced / 90 documented-exempt"** (366 scanned, unchanged) — a real
  tightening, not just a relabelling, since two fewer files now rely on a broad exemption instead of
  carrying their own provenance string.
- `docs/DATA_PROVENANCE.md`: updated the §1 rows for all three catchment files (rayong "FIXED", the
  stale bangkok claim corrected in place, chiang-mai added to the table for the first time) and
  closed out R2/R3 in the §3 risk register (struck through, marked "Done", each pointing back to this
  entry).

**Verification.**
- `python3 pipeline/build_provenance.py --check` — reproduces byte-exact after the regen.
- `python3 pipeline/slim_catchment.py --check` — still `[ok]` for both `rayong_catchment.json` (32.6
  MB) and `bangkok_catchment.json` (28.8 MB); the new `meta` key sits after `buildings`/`center` in
  file order and `slim_payload()`'s `dict(d)` preserves arbitrary top-level keys verbatim, so adding
  `meta` doesn't disturb the slim-canonical-form invariant (confirmed, not assumed).
- `bash tests/run.sh check` — 47 passed, 0 failed (`validate_data.py` 421/421, unchanged pass count —
  this was a provenance-label change, not a new numeric check). `node --check platform/app.js` clean.
- Code-path check (no headless WebGL render run this cycle — pure metadata addition, no page JS
  touched): grepped every consumer of `<slug>_catchment.json` in `rayong-catchment.html` and
  `branch-explorer.html` — all access is via named keys (`CA.buildings`, `CA.center`, `ca.buildings`),
  never positional or `Object.keys().length`-based, so an added `meta` key cannot affect rendering.
  `rayong_catchment.json`/`chiang-mai_catchment.json` building count/order/content is byte-identical
  before/after (diffed: only the appended top-level `meta` key changed).

**Source:** `git log` on both files (commits `9482b0e`, `373b4f0`) + `pipeline/pull_overture_buildings.py`'s
own `--max-buildings 180000` default (cross-checked against the exact 180,000 buildings both files
carry) + the existing `bangkok_catchment.json` meta as the style precedent. No external pull performed
this cycle — this is a provenance-labelling fix over already-committed, already-real geometry data.

---

## 2026-07-04 (7) — AUDIT: two docs quoting the pre-refresh (stale) World Bank Pink Sheet vintage, corrected to match the already-committed 2026M06 data

**Task type:** AUDIT (provenance/documentation sweep — no `platform/data` or `source-data` value
changed). `/workspace/watcher` was not present this cycle. Started with a RE-DERIVE pass:
`bash tests/run.sh check` on a clean checkout of `claude/new-session-wto26j` → 46 passed, 0 failed
(`validate_data.py` 265/265) — the pipeline outputs are already in sync with their sources, so there
was no drift to fix. Moved to an AUDIT pass over docs that quote live data values, cross-checking each
against the actual committed `source-data`/`platform/data` files.

**What was found.** The 2026-07-03 Pink Sheet refresh (commit `adf5494`, "Refresh Pink Sheet to
2026M06") correctly regenerated `source-data/commodities.json`, `commodities_protein.json`,
`commodity_board.json` and `platform/data/meta.json` (whose `updated` field now correctly reads
`"2026M06 prices · drought 2026-06-21"`, and whose `macro` Gold tile correctly reads `+26.1%`) — but
two docs describing that same data were never updated and still asserted the **pre-refresh** numbers
as current:
- `docs/DATA_SOURCES.md` §"World Bank Pink Sheet — current read" was still titled "(Dec 2025 prices)"
  and quoted the old figures (rice −19.5%, rubber −13.5%, sugar −25.9%, palm −17.6%, gold +62.7%, …)
  and the old (2025-vintage) Pink Sheet URL hash — all superseded by the committed 2026M06 values
  (rice +17.9%, rubber +32.4%, sugar −13.5%, palm +18.2%, gold +26.1%, per `source-data/commodities.json`
  / `commodities_protein.json` verbatim).
- `docs/DATA_PROVENANCE.md`'s `meta.json` provenance-table row quoted the vintage label as
  `2025M12 prices · drought 2026-06-21` — the actual live `platform/data/meta.json.updated` value is
  `2026M06 prices · drought 2026-06-21`.

Neither doc had caused a live data-integrity problem (the app itself reads the correct, already-fresh
`platform/data`/`source-data` files directly — this was a documentation-only drift), but both would
mislead the next person or cycle relying on these docs as the current-state reference.

**Fix applied (docs only, zero data/pipeline changes, no fabrication — every replacement number was
copied verbatim from the already-committed source files, nothing new was pulled or invented):**
- `docs/DATA_SOURCES.md`: retitled the section "(2026M06 prices)"; replaced every quoted YoY figure
  with the current value from `source-data/commodities.json` / `commodities_protein.json`; added a
  one-line note to keep this block in sync with `meta.json.updated` on future refreshes; kept the
  independent OAE Dec-2025 outlook sentence as-is (flagged that it's a separate, not-re-verified
  citation, not a Pink Sheet figure) rather than guessing a replacement; noted shrimp is still
  genuinely stale (2023M10, unrefreshed) and that's *why* it's correctly excluded from
  `commodity_board.json`, not an oversight; updated the Pink Sheet URL note to describe the
  script's actual behaviour (`autox_enrich_loop.py`'s `pinksheet_url()` scrapes the current link each
  pull; quoted its real last-known-good 2026M06 fallback hash from the source code, not a guess).
- `docs/DATA_PROVENANCE.md`: corrected the `meta.json` row's quoted vintage label to the live value
  and noted when/why it had drifted, so a future audit can tell this was already checked.

**Verification:** `bash tests/run.sh check` — 46 passed, 0 failed, `validate_data.py` 265/265
(unchanged before/after — confirms this cycle touched no `platform/data`/`source-data` file, docs-only).
Diffed both edited files to confirm every new number traces to an existing committed file
(`source-data/commodities.json`, `commodities_protein.json`, `platform/data/meta.json`) — no value was
looked up externally or guessed.

**Follow-up (logged in `docs/IMPROVEMENT_BACKLOG.md`, not attempted):** the OAE "Dec-2025 outlook"
sentence in `docs/DATA_SOURCES.md` is now the oldest un-re-verified citation in that file; a future
cycle with OAE (`catalog.oae.go.th`, reachable from this sandbox) access could confirm or refresh it.

**Source:** `source-data/commodities.json`, `source-data/commodities_protein.json`,
`platform/data/meta.json` (all already-committed, already-audited MEASURED/proxy files — see their own
`meta`/commit `adf5494`). No external pull performed this cycle.

---

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
