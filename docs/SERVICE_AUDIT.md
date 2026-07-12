# SERVICE AUDIT — AutoX / เงินไชโย Credit-Intelligence Platform

> Emitted by the autonomous **market & service intelligence** loop. Audits the platform *as a
> service*: data freshness per layer, provenance coverage, broken data references, and heavy-JSON
> load weight. Every number here is read from the committed tree — nothing is estimated or invented.
> Regenerate the underlying ledger with `python3 pipeline/build_provenance.py`.

_Audit run: 2026-07-12 · commit at time of run: `c163b56` · against `platform/data/provenance.json`._

## Headline

The data room is healthy. **No broken data references, no missing fetches.** The one concrete
gap this run **fixed**: the provenance ledger's freshness column was silently dropping 6 layers'
real vintage stamps because `build_provenance.py` only scanned 4 vintage keys — it now scans the
4 additional freshness fields those layers actually carry.

## 1. Freshness per layer (the fix this run shipped)

`build_provenance.py::_vintage_of()` reads a layer's data vintage from its own `meta` block. It
previously scanned only `updated / vintage / as_of / updated_to`. Six layers stamp their freshness
under **other** real keys and were therefore showing blank in the Data-room card despite carrying a
date:

| Layer | Freshness key (was dropped) | Value now surfaced |
|---|---|---|
| `thaiwater_flood.json` | `observed_to` | 2026-07-11 08:40 |
| `thaiwater_rain.json` | `observed_to` | 2026-07-10 02:00 |
| `search_demand.json` | `pulled_at_utc` | 2026-07-04T00:45Z |
| `fuel_prices.json` | `pulled` | 2026-07-05 |
| `macro_indicators.json` | `pulled` | 2026-07-05 |
| `macro_sensitivity.json` | `price_vintage` | 2026M06 |

Extraction now scans (in priority order): `updated, vintage, as_of, updated_to, observed_to,
price_vintage, pulled_at_utc, pulled`. A note field that merely mentions a year
(`brand_trends.json::note_be_to_ce = "พ.ศ. − 543 = ค.ศ. …"`) is correctly **not** treated as a
vintage — the extractor keys off known freshness fields, not any date-shaped string.

Result: layers carrying a captured vintage rose from **5 → 11** of 78. The remaining 67 are
derived/geometry layers whose freshness is inherited from their inputs (no independent vintage);
their vintage-blank state is honest, not a bug.

**Freshest reachable inputs today** (all measured, all recent): thaiwater flood 2026-07-11,
thaiwater rain 2026-07-10, fuel & macro pulls 2026-07-05, search demand 2026-07-04. No stale
live-input layer detected.

## 2. Provenance coverage

- **78 layers · 309 files.** 33 measured · 39 estimated · **6 unlabelled** (the "shame board").
- The 6 unlabelled files are all **structural, not numeric-intelligence** layers:
  `branches.json`, `deltas.json`, `meta.json`, `provinces/index.json`, `rayong_province.json`,
  `snapshots_index.json`. They carry no self-declared `meta.label/source/provenance/generated_by`
  stamp. Low priority — none ships an un-sourced risk/market number — but adding a one-line meta
  stamp to each would clear the board. **Logged, not fixed this run** (scope: one change per run).

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

Clear the 6-file provenance shame board by stamping a one-line `meta` block on each structural
layer (`branches.json`, `meta.json`, …) so the Data-room census reaches 100 % labelled — a small,
deterministic, gate-safe change for a future run.
