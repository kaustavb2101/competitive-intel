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

Audit date: 2026-06-30. Branch: `prov-guard`. Auditor scope: `platform/data/` + `source-data/`.

---

## 1. `platform/data/` — the layers the app actually serves

| Layer | Kind | Source / method | Carries meta? | Notes |
|---|---|---|---|---|
| `branches.json` | DERIVED | `pipeline/derive.py` projects `source-data/branches_final.json` (2,015-branch master). Per-branch fields: coords + segment scores (a/m/c/w/o), `k10` POI-within-10km counts (OSM, MEASURED), `dfac`/`dwork` (DIW factories), `rain` (HDX). | NO own meta (it is a bare list) | Provenance lives in the master + `meta.json`. **Exempt** in the gate as a pure derivative; see exemption list. The master itself is the root-of-truth and is audited in §2. |
| `meta.json` | DERIVED | `pipeline/derive.py`: `board` = passthrough of `commodity_board.json` (World Bank Pink Sheet); `region` rollups counted from branches; `macro`/`mws`/`cws` carried from prior vintage (editorial). `updated` = data vintage label (`2025M12 prices · drought 2026-06-21`). | NO `meta.*` (it *is* the meta sidecar) | **Exempt**: it is the provenance/rollup sidecar for branches, not an independent numeric series. Inputs are sourced. |
| `amphoe.json` | MEASURED + province-inherited | `pipeline/build_amphoe.py`. Branches & POI = point-in-polygon (branches_final + osm_layers into th_amphoe.geojson). fac/workers = DIW. veh = DLT (province-inherited). informal/formal = NSO. agri_stress inherited from crop_stress. | YES `meta.provenance` + `meta.formulas` + per-amphoe `fac_measured` flag | Strong: provenance explicitly separates measured-at-amphoe vs province-inherited vs estimated. |
| `crop_stress.json` | ESTIMATED (labelled) | `pipeline/build_crop_stress.py`. crop area = OAE (MEASURED); price_stress = World Bank Pink Sheet GLOBAL YoY (PROXY for direction); drought = HDX rainfall. Output `agri_stress` is a composite index in [0,1]. | YES `meta.provenance` + `meta.formula` + `meta.caveats` | Honest proxy. price_stress explicitly flagged as GLOBAL proxy, not Thai farmgate. |
| `opportunity_score.json` | ESTIMATED COMPOSITE (labelled) | `pipeline/build_opportunity_score.py`. Blends whitespace (amphoe, MEASURED) + competitor_gap (Google Places PIP, MEASURED) + agri_stress (crop_stress, ESTIMATED). Score 0-100 per district. | YES `meta.label` (states ESTIMATED), `meta.inputs_used`, `meta.score_formula`, `meta.generated_with` | **NB:** uses `generated_with` + `inputs_used` rather than the literal key `source`/`provenance`. The gate accepts `inputs_used`/`generated_with`/`label` as valid provenance signals so this passes honestly. |
| `competitors_national.json` | MEASURED | `pipeline/pull_competitors.py` — Google Places Text Search (real competitor locations). | YES `meta.source` + `meta.note` (coverage is a lower bound) | Honest: note states Places caps coverage; a lower bound, not a registry. |
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
| `branch_occupations.json` | MEASURED | `pipeline/build_occupations.py` — Overture places occupation rollup, index-aligned to branches. | Not committed today. When present, must carry provenance (gate-checked). |
| `amphoe_occupations.json` | MEASURED | `pipeline/build_amphoe_occupations.py` — Overture occupation mix per district. | Not committed today. Gate-checked when present. |
| `competitors_overture.json` | MEASURED | Overture places competitor census. | Not committed today. Gate-checked when present. |
| tmli layers (`ingest_tmli.py`) | — | **No `ingest_tmli.py` exists in this tree.** | No tmli data layer present. `refresh_all.sh` skips it gracefully. |

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
