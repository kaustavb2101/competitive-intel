# DATA_PROVENANCE.md — every committed data layer, traced to a source

> **Mandate:** no data in this platform may be hallucinatory or fabricated. Every committed data
> layer must be traceable to a real source, OR be honestly labelled as ESTIMATED-with-method, OR be
> DERIVED deterministically from named inputs that are themselves sourced.
>
> This file is the audit register. It is enforced — `tests/validate_data.py` has a provenance gate
> (`check_provenance`) that fails `bash tests/run.sh check` if any committed **numeric** layer in
> `platform/data/` ships with no `meta.source` / `meta.provenance` and is not on the documented
> exemption list at the bottom of this file.
>
> Provenance kinds used below:
> - **MEASURED** — counted/observed from a named real source (OSM, DIW, DLT, NSO, OAE, World Bank, Google Places).
> - **ESTIMATED** — a proxy / model / index, with the method stated. Honest, not measured.
> - **DERIVED** — produced deterministically by a named script from named inputs that are themselves sourced.
> - **UNKNOWN / REVIEW** — provenance could NOT be determined from the file or its generating script. **Do not ship these as fact.** Listed as RISK.

Audit date: 2026-07-01 (re-audit; supersedes 2026-06-30 `prov-guard`). Branch: `agent/provenance-ledger`.
Auditor scope: every JSON under `platform/data/` (top-level + `provinces/`) + `source-data/`.
This pass added the risk / occupation / exposure / collateral / competitor layers that shipped after the
first audit, and corrected the stale `ingest_tmli.py` / "absent today" entries. The ledger now covers
**all 34 top-level `platform/data/*.json` layers** plus the 78-file `provinces/` subtree.

---

## 1. `platform/data/` — the layers the app actually serves

| Layer | Kind | Source / method | Carries meta? | Notes |
|---|---|---|---|---|
| `branches.json` | DERIVED | `pipeline/derive.py` projects `source-data/branches_final.json` (2,015-branch master). Per-branch fields: coords + segment scores (a/m/c/w/o), `k10` POI-within-10km counts (OSM, MEASURED), `dfac`/`dwork` (DIW factories), `rain` (HDX). | NO own meta (it is a bare list) | Provenance lives in the master + `meta.json`. **Exempt** in the gate as a pure derivative; see exemption list. The master itself is the root-of-truth and is audited in §2. |
| `meta.json` | DERIVED | `pipeline/derive.py`: `board` = passthrough of `commodity_board.json` (World Bank Pink Sheet); `region` rollups counted from branches; `macro`/`mws`/`cws` carried from prior vintage (editorial). `updated` = data vintage label (currently `2026M06 prices · drought 2026-06-21`; keep in sync with the live file — this example drifted to a stale `2025M12` reading after the 2026-07-03 Pink Sheet refresh, corrected 2026-07-04). | NO `meta.*` (it *is* the meta sidecar) | **Exempt**: it is the provenance/rollup sidecar for branches, not an independent numeric series. Inputs are sourced. |
| `amphoe.json` | MEASURED + province-inherited | `pipeline/build_amphoe.py`. Branches & POI = point-in-polygon (branches_final + osm_layers into th_amphoe.geojson). fac/workers = DIW. veh = DLT (province-inherited). informal/formal = NSO. agri_stress inherited from crop_stress. | YES `meta.provenance` + `meta.formulas` + per-amphoe `fac_measured` flag | Strong: provenance explicitly separates measured-at-amphoe vs province-inherited vs estimated. |
| `crop_stress.json` | ESTIMATED (labelled) | `pipeline/build_crop_stress.py`. crop area = OAE (MEASURED); price_stress = World Bank Pink Sheet GLOBAL YoY (PROXY for direction); drought = HDX rainfall. Output `agri_stress` is a composite index in [0,1]. | YES `meta.provenance` + `meta.formula` + `meta.caveats` | Honest proxy. price_stress explicitly flagged as GLOBAL proxy, not Thai farmgate. |
| `opportunity_score.json` | ESTIMATED COMPOSITE (labelled) | `pipeline/build_opportunity_score.py`. Blends whitespace (amphoe, MEASURED) + competitor_gap (Google Places PIP, MEASURED) + agri_stress (crop_stress, ESTIMATED). Score 0-100 per district. | YES `meta.label` (states ESTIMATED), `meta.inputs_used`, `meta.score_formula`, `meta.generated_with` | **NB:** uses `generated_with` + `inputs_used` rather than the literal key `source`/`provenance`. The gate accepts `inputs_used`/`generated_with`/`label` as valid provenance signals so this passes honestly. |
| `competitors_national.json` | MEASURED | `pipeline/pull_competitors.py` — Google Places Text Search (real competitor locations). | YES `meta.source` + `meta.note` (coverage is a lower bound) | Honest: note states Places caps coverage; a lower bound, not a registry. |
| `competitors_overture.json` | MEASURED (lower bound) | `pipeline/pull_overture_national.py` — Overture Maps Places, competitor lenders matched by brand name over the national bbox. | YES `meta.source` + `meta.generated_with` + `meta.count`/`bbox` | Honest: `meta.source` states it is "a sample/lower bound, not a registry". |
| `competitor_coverage.json` | MEASURED found + ESTIMATED expected | `pipeline/build_competitor_coverage.py` — `found` = de-duplicated count across `competitors_national.json` + `competitors_overture.json` (MEASURED); `expected` = per-brand nationwide branch counts ESTIMATED-from-public-reports (company IR / annual reports, cited in `meta.expected_sources`). | YES `meta.source` + `meta.generated_by` + `meta.expected_sources` (per-brand citations; Heng left null, not invented) | Honest: found=measured vs expected=cited-public-report clearly split; a brand with no cited count is left null. |
| `branch_occupations.json` | MEASURED (lower bound) | `pipeline/build_occupations.py` — share of Overture Maps Places within ≤10km of each branch, bucketed into 14 occupation categories; index-aligned to `branches.json`. | YES `meta.source` + `meta.measured=true` + `meta.buckets`/`radius_km` | Honest: `meta.source` states Overture Places is "a sample/lower bound, not a registry". |
| `amphoe_occupations.json` | MEASURED (lower bound) | `pipeline/build_amphoe_occupations.py` — Overture Maps Places occupation mix per amphoe (point-in-polygon into `th_amphoe.geojson`), 14 buckets. | YES `meta.source` + `meta.measured=true` + `meta.buckets` | Honest: same Overture lower-bound caveat as branch_occupations. |
| `poi_relevance.json` | ESTIMATED weighting over MEASURED counts | `pipeline/build_poi_relevance.py` — MEASURED per-branch POI COUNTS (Overture/OSM, ≤10km) weighted by an ESTIMATED per-category title-loan relevance MODEL (`meta.weights` + `meta.weight_rationale`). | YES `meta.label` (states ESTIMATED weighting) + `meta.generated_by` + `meta.measured`/`estimated` split | Honest: counts measured, weights are judgement — both stated explicitly. |
| `occupation_risk.json` | ESTIMATED COMPOSITE (labelled) | `pipeline/build_occupation_risk.py` — MEASURED occupation shares (from `branch_occupations.json`) × an ESTIMATED "stressed sector" weighting (fixed factory macro lever + province crop-household stress from `crop_stress.json`). Index-aligned to `branches.json`. | YES `meta.label` (states ESTIMATED, "NOT a measured default rate") + `meta.generated_with` + `meta.measured`/`estimated` split | Honest triage flag; measured-vs-estimated split spelled out. |
| `household_risk_by_province.json` | MEASURED | `pipeline/build_household_risk.py` — per-province household debt / income and debt-to-income from NSO SES 2566 (2023 CE) via the vendored TMLI layers (`pipeline/ingest_tmli.py`; see `source-data/tmli/PROVENANCE.md`). | YES `meta.source` + `meta.provenance` (states MEASURED · NSO SES) + per-field labels | Honest: named NSO SES source; debt/income/DTI all MEASURED. |
| `branch_risk.json` | ESTIMATED COMPOSITE (labelled) | `pipeline/build_branch_risk.py` — fuses household DTI (MEASURED · NSO, province-inherited) + crop/drought stress (ESTIMATED) + occupation concentration (MEASURED mix × ESTIMATED weight) + branch segment/collateral mix into one 0-100 triage score. Index-aligned to `branches.json`. | YES `meta.label` (states ESTIMATED COMPOSITE, "NOT a measured default rate") + `meta.generated_by` + per-component `provenance` | Honest: each of the 4 components carries its own MEASURED/ESTIMATED provenance in `meta.components`. |
| `province_risk.json` | ESTIMATED COMPOSITE (rollup) | `pipeline/build_province_risk.py` — per-province rollup (mean/p90) of `branch_risk.json` over `branches.json` provinces; inherits that composite's provenance. | YES `meta.source` + `meta.provenance` (states `n_branches` MEASURED; `mean_risk`/`p90_risk` are aggregates of the ESTIMATED composite, NOT default rates) | Honest: measured count vs estimated aggregate clearly separated. |
| `segment_exposure.json` | ESTIMATED (structural) | `pipeline/build_segment_exposure.py` — portfolio concentration (dominant segment, mix, HHI) computed from the per-branch a/m/c ESTIMATED segment scores in `branches.json`. | YES `meta.label` (states ESTIMATED) + `meta.source` + `meta.method` | Honest: labelled a structural concentration read over estimated segment scores, not a measured book. |
| `collateral_outlook.json` | ESTIMATED directional (labelled) | `pipeline/build_collateral_outlook.py` — per-province directional collateral-recovery outlook. Inputs incl. gold YoY (World Bank Pink Sheet GLOBAL, applied nationally) + segment/collateral mix. | YES `meta.label` (states ESTIMATED, "NOT a measured recovery rate") + `meta.generated_by` + `meta.what_this_is` + per-field provenance | Honest: explicitly "a DIRECTIONAL read … NOT a measured loss-given-default or recovery rate, and no price is invented". |
| `peer_npl.json` | MEASURED (reported peer figures) | Hand-compiled from `docs/RESEARCH_DIGEST.md` §B — listed title-loan peers' reported NPL ratios (FY2025 / 2025 IR). | YES `meta.source` + `meta.note` ("PEER figures only — NOT an AutoX number; we have no measured AutoX NPL") | Honest: explicitly peer-reported, not an AutoX number. |
| `tiles_config.json` | CONFIG (not data) | Hand-configured CDN URL for Overture building vector tiles produced by `pipeline/build_building_tiles.py` (real Overture pull, clipped to 10km buffers). No values here; records only WHERE real tiles are served. | YES `meta.source` + `meta.provenance` + `meta.label="configuration, not measured data"` | Honest: URLs are null until tiles are hosted; scenes fall back to curated catchments — nothing invented. |
| `loan_tape_derived.json` | SYNTHETIC (labelled) | `pipeline/ingest_loan_tape.py`. **NOT real customer data.** Deterministic synthetic tape (vintage aging, ROI, HHI, PD calibration). | YES `meta.SYNTHETIC=true` + `meta.provenance` ("SYNTHETIC placeholder — NOT real customer data") | Correctly self-labelled. Will become MEASURED only when ingested with `--real` against a true export. |
| `deltas.json` | DERIVED | `pipeline/timeseries.py` — diff of two committed snapshots (`from`/`to` vintage labels). | NO own meta, but carries `from`/`to`/`baseline`/`updated_to` vintage stamps | **Exempt**: a deterministic diff of snapshots whose inputs are branches/meta (sourced). Vintage labels self-document. |
| `snapshots_index.json` | DERIVED | `pipeline/timeseries.py` — index of captured vintage snapshots (`count` + labels). | NO meta; is itself an index of vintages | **Exempt**: structural index, no independent numeric series. |
| `provinces/index.json` | DERIVED | `pipeline/build_province.py` — per-province rollups (branches, factories=DIW, vehicles=DLT, workers=NSO). | NO `meta` on the index list | **REVIEW (low):** the index is a derivative of `provinces/<slug>.json` (which are derivatives of sourced layers), but neither the index nor the per-province files carry a `meta` block. Inputs ARE sourced (DIW/DLT/NSO/OSM via build_province.py). **Exempt** as derived, but flagged so the data loop can add a `meta.provenance` stamp to build_province output. |
| `provinces/<slug>.json` (77 files) | DERIVED | `pipeline/build_province.py` — spatial join of branches_final (PIP) + th_amphoe polygons + DIW/DLT/NSO gov layers + osm_layers POI + competitor census. | NO `meta` block | **REVIEW (low):** same as index — no embedded provenance, but every input is a named sourced layer and the build is deterministic (`--check` byte-exact). **Exempt** as derived; recommend build_province.py emit a `meta.provenance` like build_amphoe does. |
| `rayong_catchment.json` | MEASURED (pulled) | `pipeline/pull_overture_buildings.py` (Overture building footprints) + `bake_catchment_heights.py` (estimated heights). | NO `meta` (only `buildings`/`center`) | **REVIEW (medium):** numeric building footprints with **no embedded source stamp**. Source is known (Overture, via the puller) but not recorded in the file. Network-pulled (not in determinism gate). **Exempt** (geometry/visual layer, not a decision metric) but flagged — add `meta.source="Overture buildings"`. |
| `bangkok_catchment.json` | MEASURED (pulled) | `pipeline/pull_overture_buildings.py` (Overture, Bangkok). | PARTIAL — `meta` has `city`/`n_bldg`/`floor_area_m2` but **no `source`** | **REVIEW (medium):** has a meta block but it names no source. Same treatment as rayong_catchment — geometry layer, exempt-with-flag; add `meta.source`. |
| `rayong_province.json` | DERIVED | `pipeline/build_rayong.py` — curated Rayong pilot deep-dive (districts/branches/competitors/poi/estates/facts/gov). | NO `meta` | **REVIEW (low):** curated pilot; inputs are the sourced layers + hand-curated competitor list. Exempt as derived/visual; flagged. |
| `rayong_landuse.json`, `rayong_roads.json`, `rayong_water.json`, `rayong_rail.json` | MEASURED (pulled) | Overpass/OSM geometry pulls (`pull_*` scripts). | NO `meta` | **Exempt**: OSM geometry/basemap layers (lines/polygons), not numeric decision series. Source is OSM. Flagged for a `meta.source` stamp. |
| `bangkok_landuse.json`, `bangkok_roads.json`, `bangkok_water.json` | MEASURED (pulled) | Overpass/OSM geometry pulls. | NO `meta` | **Exempt**: OSM geometry/basemap layers. Source is OSM. Flagged for a `meta.source` stamp. |
| `province_bbox.json` | MEASURED (derived) | `pipeline/pull_overture_buildings.py` (`write_province_bbox`) — per-province bbox `[S,W,N,E]` = union of that province's amphoe polygon extents in `source-data/th_amphoe.geojson` (GeoBoundaries THA ADM2), padded ~1.1km. Deterministic, network-free; `--bbox-check` is byte-exact. Drives the per-province Overture building pulls + frontend coverage; slugs match `provinces/index.json`. | YES `meta.source` + `meta.provenance="measured"` + `meta.generated_by` | Strong: carries an explicit measured-geometry source stamp. |

### Optional layers (absent today; SKIP-PASS in the gate when not present)
| Layer | Kind | Source / method | Notes |
|---|---|---|---|
| *(none currently absent)* | — | — | As of the 2026-07-01 re-audit, all previously-optional layers (`branch_occupations.json`, `amphoe_occupations.json`, `competitors_overture.json`) are now committed and moved into the main §1 table. The gate still SKIP-PASSes any of them if a future refresh drops them. |

> **Correction (was stale as of 2026-06-30):** the prior audit stated "No `ingest_tmli.py` exists in this
> tree." It DOES exist now — `pipeline/ingest_tmli.py` vendors the NSO SES / LFS layers under
> `source-data/tmli/` (see `source-data/tmli/PROVENANCE.md`), and `household_risk_by_province.json` is
> built from them. See §2.

---

## 2. `source-data/` — the master inputs (root of truth)

These are the upstream layers that everything in `platform/data/` derives from. They are **not** served
to the app directly, so they are outside the platform-data gate, but their provenance is recorded here
because the DERIVED platform layers inherit it.

| File | Kind | Source | Notes |
|---|---|---|---|
| `branches_final.json` | MEASURED + ESTIMATED (mixed) | The 2,015-branch master. Coords + branch list (AutoX), POI counts (OSM measured), segment scores (ESTIMATED composites). | 46 fields/branch; field dictionary in `docs/DATA_SOURCES.md`. **REVIEW:** no embedded `meta`; provenance documented externally in DATA_SOURCES.md. |
| `osm_layers.json` | MEASURED | 13 national OSM POI coordinate layers (~79k points). | OpenStreetMap via Overpass. No embedded meta; source is OSM by construction. |
| `commodity_board.json`, `commodities.json`, `commodities_protein.json` | MEASURED | World Bank Pink Sheet GLOBAL commodity prices. | Used as a **proxy** for Thai farmgate direction (see crop_stress caveat). |
| `crop_prices.json` | MEASURED | OAE / gov crop prices fold-in (`ingest_gov.py`). | Blocked from foreign IP; pulled from Thai network. |
| `crop_prov_area.json`, `rice_prov_area.json` | MEASURED | OAE planting area (rai) per crop per province. | |
| `factories_by_district.json` | MEASURED | DIW factory registry (via `ingest_gov.py`). | |
| `vehicles_by_province.json` | MEASURED | DLT vehicle registrations per province. | |
| `employment_by_province.json` | MEASURED | NSO labour-force (formal/informal). | |
| `estates.json` | MEASURED | 35 industrial estates (IEAT). | |
| `rayong_competitors.json` | MEASURED (hand-curated) | Google Places hand-curated competitor list (`save_competitors.py`). | Curated, not exhaustive. |
| `bldg_wide.json` | MEASURED | Overpass building footprints (Rayong wide pull). | |
| `th_amphoe.geojson` | MEASURED | Nationwide 928 amphoe (district) polygons (gov boundaries). | Drives all spatial joins. |
| `province_narratives.json` | EDITORIAL | Hand-written "what impacts them" narratives (Rayong curated). | **EDITORIAL, not data** — labelled as such. Not a numeric series. |
| `tmli/` (`nso-ses-debt-2566.json`, `nso-ses-income-2566.json`, `nso-lfs-provincial-summary.json`, `household-debt.js`, `provinces.js`) | MEASURED, **with one exception** | NSO SES 2566 (household debt + income) + NSO LFS provincial summary, vendored via `pipeline/ingest_tmli.py` (from `kaustavb2101/watcher`). Provenance recorded in `source-data/tmli/PROVENANCE.md`. **Exception (2026-07-04 audit):** `household-debt.js`'s `debtToIncome`/`stressIndex` (attributed to "BOT Household Debt Regional Q4/2024") cite no CKAN/BOT resource id and diverge 10-20x from the app's own computed ratio — UNVERIFIED, not consumed by any builder. Only `debtPerHousehold` from that file is MEASURED/used. | Drives `household_risk_by_province.json` (and thereby the `branch_risk`/`province_risk` composites) via `debt_per_household` + `avg_monthly_income` only. |
| `tmli/provincial-gpp.js` → `source-data/gpp_by_province.json` | **⚠ MOSTLY ESTIMATED (corrected 2026-07-02)** | Self-styled "NESDC OFFICIAL DATA" but only 1/77 rows (Mukdahan) carries `source: 'CKAN-NESDC-2566'` (independently CKAN-verified); the other 76 are round-number figures with generic `source: 'NESDC-2566'` and hand-assigned confidence — an estimated knowledge base, not a per-province pull. `ingest_tmli.py` now emits the corrected provenance + per-row `source` field. | **NOT wired into any `platform/data` layer** (caught before it reached the app). Needs a real per-province NESDC CKAN pull before use; see `docs/DATA_REFRESH_LOG.md`. |
| `snapshots/` | DERIVED | Per-vintage snapshots written by `timeseries.py`. | |

---

## 3. RISK REGISTER — provenance gaps to review (do NOT fabricate sources)

None of these are *fabricated* data, but they lack a self-contained, in-file provenance stamp. They
are kept on the gate's **exemption list** (they are derived from sourced inputs, or are geometry/visual
basemap layers, not numeric decision metrics) and are listed here so a human or the data loop can close
the gap by adding a `meta.source` / `meta.provenance` to the generating script's output.

| # | Item | Severity | Why it's a risk | Recommended fix |
|---|---|---|---|---|
| R1 | `provinces/<slug>.json` + `provinces/index.json` | LOW | 77 deep-dive files carry numeric rollups (factories/vehicles/workers) with **no embedded `meta`**. Inputs are sourced (DIW/DLT/NSO/OSM) and the build is `--check` deterministic, but the file itself doesn't say so. | Have `build_province.py` emit a `meta.provenance` block like `build_amphoe.py` does. |
| R2 | `rayong_catchment.json` | MEDIUM | ~124k building footprints, numeric, **no source stamp at all**. Source is Overture (via the puller) but a reader of the file cannot tell. | Add `meta={"source":"Overture buildings","pulled_by":"pull_overture_buildings.py"}`. |
| R3 | `bangkok_catchment.json` | MEDIUM | Has a `meta` block (city/n_bldg/floor_area) but it **names no source**. | Add `meta.source="Overture buildings"`. |
| R4 | `branches.json` / `meta.json` | LOW | The app's primary layer carries no in-file provenance; it relies on `derive.py` + the master + DATA_SOURCES.md. | Optional: stamp `meta.json` with a `provenance` summary so the served meta is self-describing. |
| R5 | `branches_final.json` (master) | LOW | The root-of-truth master has no embedded `meta`; provenance is only in `docs/DATA_SOURCES.md`. | Optional: emit a `meta` header from `autox_enrich_loop.py`. |
| R6 | `rayong_*` / `bangkok_*` OSM geometry layers | LOW | Basemap geometry with no `meta.source`. Source is OSM by construction. | Optional: stamp `meta.source="OpenStreetMap (Overpass)"`. |

**No UNKNOWN-and-unattributable layer was found.** Every numeric layer either (a) carries provenance,
(b) is a deterministic derivative of named sourced inputs, or (c) is OSM/Overture geometry. The gaps
above are missing *in-file stamps*, not missing *sources* — none required inventing a source.

**2026-07-01 re-audit note:** the risk / occupation / exposure / collateral / competitor family added since
the first audit (`branch_risk`, `province_risk`, `segment_exposure`, `collateral_outlook`, `occupation_risk`,
`poi_relevance`, `household_risk_by_province`, `branch_occupations`, `amphoe_occupations`,
`competitors_overture`, `competitor_coverage`, `peer_npl`, `tiles_config`) all ship **with** an in-file
`meta` provenance/label block (verified against each file), so they added **no new RISK-register items** —
R1–R6 are unchanged.

---

## 4. The gate (how this is enforced)

`tests/validate_data.py :: check_provenance()` runs as part of `bash tests/run.sh check`:

- For each committed numeric layer in `platform/data/` it asserts a non-empty provenance signal —
  any of `meta.source`, `meta.provenance`, `meta.sources`, `meta.generated_by`, `meta.generated_with`,
  `meta.inputs_used`, or `meta.label` (the last covers honestly-labelled ESTIMATED composites).
- Layers with no embedded provenance that ARE pure deterministic derivatives or basemap geometry are
  on an explicit **exemption list** (mirrored in §1/§3 above). A file on the exemption list passes;
  a numeric file that is **neither sourced nor exempted FAILS the gate** — making unsourced data
  un-shippable.
- The exemption list is intentionally narrow. Adding a new numeric layer with no provenance and no
  exemption entry will break the build, forcing a conscious provenance decision.
