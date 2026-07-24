# SERVICE AUDIT — AutoX / เงินไชโย Credit-Intelligence Platform

> Emitted by the autonomous **market & service intelligence** loop. Audits the platform *as a
> service*: data freshness per layer, provenance coverage, broken data references, and heavy-JSON
> load weight. Every number here is read from the committed tree — nothing is estimated or invented.
> Regenerate the underlying ledger with `python3 pipeline/build_provenance.py`.

_Audit run: 2026-07-24 · latest ship: the freshly-surfaced district-drought layer's dropped freshness stamp recovered in the Data-room card (§1) · against `platform/data/provenance.json` (104 layers · 409 files)._

## Headline

The data room is healthy. **No broken data references, no missing fetches; provenance intact
(52 measured · 51 estimated · the single standing catchment family).** The one concrete gap this
run **fixed**: `drought_district.json` — the MODELLED OAE-SPEI district-drought layer surfaced on
Overview only days ago (#141) — stamps its real freshness date under the key `snapshot`
(`= 2026-06`, the SPEI reference month), which `build_provenance.py::_vintage_of()` did not scan, so
its vintage showed **blank** in the exec-facing Data-room card. Exactly the same class of bug as the
2026-07-17 (6 keys) and 2026-07-19 (3 keys) §1 fixes; a full re-scan of every committed layer's
`meta` this run found `snapshot` to be the **only** remaining unscanned date-shaped freshness key,
carried by this **one** layer — so the extractor now scans it and the drought vintage surfaces like
the rest.

_Tree grew 96 → 104 layers since the last audit (drought_district, crop_drought, the two thaiwater
live-pulse layers, set/valuation and credit-anchor market layers, …). Re-verified this run: the
ledger reports 104 layers (52 measured · 51 estimated · 1 unlabelled = the standing 3D building-
catchment family, 77 files under one `family:true` row — structurally meta-less, an accepted standing
state, not a regression); every analytical layer is wired into a live `fetch()` or is a pipeline
input; and no `data/*.json` path referenced in `platform/*.html` + `app.js` fails to resolve._

## 1. Freshness per layer (the fix this run shipped)

**2026-07-24 (this run):** a full re-scan of all 104 layers' `meta` blocks for date-shaped freshness
fields *not* in the extractor's key list found **one** layer still dropping a real vintage from the
Data-room card:

| Layer | Freshness key (was dropped) | Value now surfaced | Class |
|---|---|---|---|
| `drought_district.json` | `snapshot` | 2026-06 | MODELLED OAE-SPEI per-amphoe drought (freshly surfaced, #141) |

`_vintage_of()` now also scans `snapshot`, placed among the data-vintage keys (after `price_vintage`,
ahead of any pull timestamp — `snapshot` is the SPEI reference month, a data vintage, not a pull
time; the layer's own `retrieved: 2026-07-20` pull date is intentionally **not** surfaced as the
freshness cell, matching how `observed_to` / `price_vintage` prefer the observation window over the
pull stamp). Verified the change touches **only this one** vintage cell (`'' → 2026-06`); a diff of
the regenerated ledger confirms every other field — counts, labels, sources, the files block — is
byte-identical, and `build_provenance.py --check` passes on the recommitted ledger. No date is
invented — `2026-06` is read from the layer's own committed `meta.snapshot`.

---

**2026-07-19 (prior run):** a full re-scan of all 96 layers' `meta` blocks for date-shaped freshness
fields *not* in the extractor's key list found **three** layers still dropping a real vintage from
the Data-room card:

| Layer | Freshness key (was dropped) | Value now surfaced | Class |
|---|---|---|---|
| `rival_pulse.json` | `promos_pulled_at` | 2026-07-19 | live rival promo/sentiment watch (freshest) |
| `pico_competitors.json` | `pico_vintage` | 2026-05-22 | FPO PICO-finance licence registry |
| `occupation_income_individual.json` | `vintage_individual` | 2025 | NSO LFS individual-income |

`_vintage_of()` now also scans `pico_vintage, vintage_individual, promos_pulled_at`. Verified the
change touches **only these three** vintage cells (`build_provenance.py --check` byte-exact; a diff
of the regenerated ledger confirms counts/labels/sources unchanged). No date is invented — each is
read from the layer's own committed `meta`. `rival_reputation.json` / `rival_threat.json` carry an
explicit `vintage: null` and correctly stay blank (no rating vintage was captured).

---

**2026-07-17 (prior run):** `_vintage_of()` previously scanned only `updated / vintage / as_of /
updated_to`. Six layers stamp their freshness under **other** real keys and were therefore showing
blank in the Data-room card despite carrying a date:

| Layer | Freshness key (was dropped) | Value now surfaced |
|---|---|---|
| `thaiwater_flood.json` | `observed_to` | 2026-07-11 08:40 |
| `thaiwater_rain.json` | `observed_to` | 2026-07-10 02:00 |
| `search_demand.json` | `pulled_at_utc` | 2026-07-04T00:45Z |
| `fuel_prices.json` | `pulled` | 2026-07-05 |
| `macro_indicators.json` | `pulled` | 2026-07-05 |
| `macro_sensitivity.json` | `price_vintage` | 2026M06 |

Extraction now scans (in priority order): `updated, vintage, as_of, updated_to, observed_to,
price_vintage, pico_vintage, vintage_individual, pulled_at_utc, pulled, promos_pulled_at`. A note
field that merely mentions a year
(`brand_trends.json::note_be_to_ce = "พ.ศ. − 543 = ค.ศ. …"`) is correctly **not** treated as a
vintage — the extractor keys off known freshness fields, not any date-shaped string.

Result: **23 of 96** layers now carry a captured vintage (was 20 before this run's three-key fix;
11 of 78 after the 2026-07-17 fix). The remaining 73 are derived/geometry layers whose freshness is
inherited from their inputs (no independent vintage); their vintage-blank state is honest, not a bug.

**Freshest reachable inputs today** (all measured except the rival watch, all recent): rival-pulse
promo pull 2026-07-19, credit anchor 2026-07-18, fuel prices 2026-07-17, thaiwater flood 2026-07-11,
thaiwater rain 2026-07-10, search demand 2026-07-04. No stale live-input layer detected.

## 2. Provenance coverage

- **83 layers · 314 files.** 41 measured · 42 estimated · **0 unlabelled** — the shame board is **clear**.
- **Update 2026-07-17 (a), intelligence loop:** the board was **cut 6 → 2**. Four structural layers
  gained an honest self-declared `meta` stamp at the generator so they stay `--check`-reproducible:
  `meta.json` (`derive.py::build_meta` — MIXED, classifies ESTIMATED), `deltas.json` +
  `snapshots_index.json` (`timeseries.py::targets`), and the orphaned curated pilot aggregate
  `rayong_province.json` (hand-stamped — verified **no live `fetch()`**).
- **Update 2026-07-17 (b), intelligence loop — the sidecar mechanism (this run):** the last **2**
  unlabelled files — `branches.json` and `provinces/index.json` — are **top-level JSON arrays** that
  structurally cannot carry an inline `meta` block. `build_provenance.py` now consults a hand-authored
  **sidecar manifest** (`platform/data/provenance_sidecar.json`, keyed by relpath) for exactly those
  array-shaped layers, supplying the same `label/source/provenance` an inline block would. `branches.json`
  → **ESTIMATED** (MIXED: measured location/context + derived segment scores), inheriting meta.json's
  live vintage via a `vintage_from` key; `provinces/index.json` → **MEASURED** (a directory/index with
  measured rollups). The sidecar carries **provenance text only — zero data, zero numbers**; a file is
  upgraded only when an honest committed entry names it. **Shame board 2 → 0.** Honest by mechanism, not
  by fabrication — the board reports 314/314 labelled.

## 3. Broken data references — NONE

Cross-checked every `data/*.json` path referenced in `platform/*.html` + `app.js` (66 distinct)
against the committed tree. The only two that don't resolve —`perimeter_counts.json`,
`rayong_trees.json` — appear **exclusively in code comments** (describing a source path and an
optional scenery layer), never in a live `fetch()`. No functional break. The optional per-city
scenery layers (trees/rail/isochrone) are already allowlist-gated (`SCENERY_CITIES`, empty today)
so they issue no 404s — see PROGRESS_LOG 2026-07-12 (ux-loop).

## 4. Heavy-JSON load weight

Total `platform/data` = **242 MB across 309 files**, dominated by the 3D building catchments:

| File | Size | Load path |
|---|---|---|
| `chiang-mai_catchment.json` | 40.5 MB | lazy — only on `rayong-catchment.html?city=chiang-mai` |
| `rayong_catchment.json` | 34.2 MB | lazy — only on the Rayong 3D scene |
| `bangkok_catchment.json` | 30.2 MB | lazy — only on the Bangkok 3D scene |
| `bangkok_places.json` | 7.3 MB | lazy — per-province places |
| `occupation_leads.json` | 6.8 MB | lazy — occupation-leads block |

None load on the SPA's default routes — each is fetched only when its own heavy WebGL scene opens
(the deliberate one-route-per-GL-context split, CLAUDE.md). The command-center / overview / map
routes stay light. **Not a regression**; flagged as the standing weight to watch if a future change
ever eager-loads a catchment. A precision-trim of the 30–40 MB catchments (round coordinates /
drop sub-visible buildings) is the biggest available payload win but belongs to the 3D/UX loop.

## Next service task (recommended)

**Done 2026-07-17 (b)** — the sidecar mechanism shipped (see §2): `build_provenance.py` now reads
`provenance_sidecar.json` for the two array-shaped layers, taking the board **2 → 0 / 314 files
100 % labelled**. Provenance coverage is now complete and self-sustaining (any future array-shaped
layer just adds a sidecar entry).

The next standing service target is **§4 heavy-JSON load weight**: the 30–40 MB Overture building
catchments (`chiang-mai` 40.5 MB, `rayong` 34.2 MB, `bangkok` 30.2 MB) are the biggest available
payload win. All three are lazy (fetched only when their own WebGL scene opens), so this is **not a
regression** — but a precision-trim (round coordinates to ~6 dp, drop sub-visible buildings) would
cut the 3D-scene cold-load. That belongs to the **3D/UX loop** (it changes what a scene renders), not
this intelligence loop. For the service pillar, the data room is healthy with no open gap.
