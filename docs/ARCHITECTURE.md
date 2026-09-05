# ARCHITECTURE — how it fits together

## Repo layout
```
autox-credit-intel/                 ← repo root (open THIS in Claude Code)
├── CLAUDE.md                        ← auto-context (read first)
├── README.md                        ← short orientation
├── docs/
│   ├── PROGRESS_LOG.md              ← what's done + decisions (why)
│   ├── DATA_SOURCES.md              ← provenance, reachable/blocked, field dictionary
│   ├── ARCHITECTURE.md              ← this file
│   ├── NEXT_STEPS.md                ← prioritized backlog
│   └── SETUP_CLAUDE_CODE.md         ← first-30-minutes setup for Kaustav
├── platform/                        ← THE VERCEL APP (deploy this subfolder only)
│   ├── index.html  app.js  styles.css  vercel.json  README.md
│   └── data/  branches.json  meta.json  provinces/<slug>.json  rayong_catchment.json
├── pipeline/                        ← Python (run locally; some needs Thai IP)
│   ├── autox_enrich_loop.py  autox_dgt_ingest.py  regionmap.py
│   ├── save_competitors.py  pull_buildings.py  pull_wide.py  build_province.py
└── source-data/                     ← master inputs (rebuild platform/data from these)
    ├── branches_final.json  osm_layers.json  estates.json  rayong_competitors.json
    ├── commodity_board.json  commodities*.json  crop_prov_area.json  rice_prov_area.json
    ├── bldg_wide.json  rayong_districts.geojson
```
**Deploy boundary:** only `platform/` is the website. Keep `pipeline/` and `source-data/` out of the
deploy (set Vercel "Root Directory" = `platform`, or `cd platform && vercel --prod`). `source-data/`
may be sensitive and is large — don't publish it.

## Data flow
```
   Overpass/Places/HDX/OAE/WorldBank          (+ data.go.th/DLT/DIW from Thai IP)
            │  pipeline/autox_enrich_loop.py            │ pipeline/autox_dgt_ingest.py
            ▼                                            ▼
   source-data/branches_final.json  ◄──────── (merge new gov layers here)
            │
            │  derive / slim  (see "Regenerate" below)
            ▼
   platform/data/*.json   ──fetch()──►  platform/*.html  ──vercel──►  live app
```

## How each app route gets its data
- **Overview / Acquisition / Branches** ← `platform/data/branches.json` (slim, ~12 fields/branch) +
  `meta.json` (commodity board, macro, region rollups, white-space lists).
- **National map** ← same `branches.json`; Leaflet circleMarkers, lens switch recolors/resizes.
- **province.html?p=<slug>** ← `data/provinces/<slug>.json` (per-province districts + branches + competitors + rollups; Rayong = pilot). `rayong-province.html` is a retired redirect stub → `rayong-catchment`.
- **rayong-catchment.html** ← `data/rayong_catchment.json` (buildings + branches + competitors + poi + landmarks + meta).

## Regenerate `platform/data/` from `source-data/`
(The slimming/scoring scripts were run inline during the build; recreate them under `pipeline/` if you
need to re-derive. The logic:)
- `branches.json` = `branches_final.json` reduced to render fields
  `{x:lng,y:lat,n:name,v:prov,r:region,o:opportunity,a:agri_pd,m:merchant_demand,c:collateral_density,
   w:own10,t:tourism_score,dem:demand,fmkt:fmkt10,veh:veh10,rain:rain_3mo_anom}`.
- `meta.json` = commodity_board + macro cards + per-region aggregates + estate/merchant/collateral white-space.
- `provinces/<slug>.json` = `build_province.py` spatial join (amphoe polygons + branches PIP + gov layers +
  `competitors_census.json`) for all 77 provinces; Rayong is the pilot. (Superseded the retired standalone
  `build_rayong.py` → `rayong_province.json`, removed 2026-09-05.)
- `rayong_catchment.json` = `pull_wide.py` (buildings) → compute floor-area (footprint × levels) →
  filter branches/competitors/POI to the building bbox → emit; the page is committed static HTML.

## Why the map tech is split
- 2,015 points in 3D on a phone = crashes. National view uses **Leaflet** (2D, canvas renderer) for reliability.
- Rayong views use **deck.gl 8.9.35** for true 3D (extruded polygons / buildings), but each is its **own page**
  so only one WebGL context is alive at a time. Each page carries a shared `#nav` and a `fetch()`
  loader (with loading + error states), committed static in the page itself.

## Gotchas
- Pages must be served over **http** (Vercel or `python3 -m http.server`); `file://` blocks `fetch()`.
- OSM layer coords are `[lng, lat]` (not lat,lng) — a real bug we already hit once.
- deck.gl TileLayer basemap: `props.tile.boundingBox` = `[[w,s],[e,n]]`; no Mapbox token (CARTO raster).
- `vercel.json` uses `cleanUrls:true`; links use `.html` (Vercel redirects to clean paths — fine).
- Thai text in deck.gl TextLayer needs `fontFamily:'IBM Plex Sans Thai'` + `characterSet:'auto'`.
