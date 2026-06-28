# CLAUDE.md — AutoX / เงินไชโย Credit Intelligence

> This file is auto-loaded by Claude Code. Read it first. It tells you what this project is,
> what's already built, the hard environment constraints, and how to continue.

## Who this is for
**Kaustav**, Corp Strategy Director at **AutoX / บริษัท ออโต้ เอกซ์ จำกัด** (brand **เงินไชโย / Ngern Chaiyo**),
a Thai non-bank **title-loan lender** (SCBX subsidiary). Targets ~1M customers, ฿70bn loans,
3,000 branches, 25% ROE, IPO ~2027.

Kaustav works from a laptop in **Thailand** and deploys to **Vercel**. He gets overwhelmed by
complexity — so: **lead with the answer, explain simply, keep outputs concrete (not abstract indices),
prefer something that visibly works over something clever.** He values honesty about data provenance
(measured vs estimated) and acknowledging gaps.

## The two standing objectives (everything serves these)
1. **Portfolio impact / risk** — which borrower segments and collateral are getting riskier.
2. **Acquisition / where to expand** — where to open branches; white-space vs competitor density.

## What this project is
A branch-intelligence platform over all **2,015 AutoX branches**, plus deep-dives. It is a
**static site deployed to Vercel** (no build step) backed by a **Python data pipeline**.

### The deployable app — `platform/` (deploy THIS subfolder)
One Vercel app, one nav bar, multiple routes (kept as separate pages on purpose — three heavy
deck.gl/WebGL scenes in one DOM crashed on mobile; separate routes each get a fresh GL context):
- `index.html` + `app.js` — SPA with tabs: **Overview** (macro + commodity board + region signals),
  **National** (Leaflet 2D map, 2,015 branches, lens switcher: opportunity / agri-PD / merchant / collateral),
  **Acquisition** (white-space tables), **Branches** (search/sort).
- `rayong-province.html` — deck.gl **3D extruded district polygons** (8 districts), 57 branches,
  live competitors, "what impacts them" panel. Loads `data/rayong_province.json`.
- `rayong-catchment.html` — deck.gl **3D buildings** (3,631 extruded), Mueang Rayong core.
  Left = reachable-population card; right = acquisition leads + recommendations. Loads `data/rayong_catchment.json`.
- `styles.css`, `vercel.json` (static, cleanUrls). Data served from `platform/data/`.

**Map tech split (deliberate):** National view = Leaflet (light, reliable on mobile for 2,015 pts).
Rayong views = deck.gl 8.9.35 (3D). Don't merge them into one page.

### The pipeline — `pipeline/`
- `autox_enrich_loop.py` — the re-runnable enrichment loop. Source registry (13 OSM POI layers,
  OAE crops, HDX pop/rainfall, World Bank Pink Sheet), freshness-TTL caching, recomputes per-branch
  features + segment scores into `source-data/branches_final.json`, then calls `derive.py` so the
  refresh lands in the app; writes `iteration_log.json`. `--watch --interval 86400` to self-refresh;
  `--derive-only` skips all network pulls and just re-projects the master (runnable offline).
  Has DATA_GO_TH_TOKEN hooks (off by default; turn on from a Thai network — see DATA_SOURCES.md).
- `derive.py` — **projects the master into the app**: regenerates `platform/data/branches.json` +
  `meta.json` from `source-data/`, deterministic and network-free. `--check` verifies the committed
  data still reproduces exactly (byte-for-byte). Mechanical fields are derived; the livestock-buffered
  agri counts (`region.hi`, `n_agri`), white-space tables (`mws`/`cws`) and editorial macro are
  carried forward (they need the live enrich loop, not source-data alone).
- `autox_dgt_ingest.py` — ready-to-run data.go.th ingestion (DIW factories, DLT vehicles, OAE).
  **Blocked from a foreign IP; must run from Kaustav's Thai network.**
- `regionmap.py` — province→region + tier lookup (imported by other scripts).
- `save_competitors.py` — writes `rayong_competitors.json` (live Google Places pull, hand-curated list).
- `pull_buildings.py`, `pull_wide.py` — Overpass building-footprint pulls for Rayong catchments.
- `build_platform.py` — assembles the two Rayong HTML pages from head + app + loader, wires the nav.

### Master data — `source-data/`
- `branches_final.json` — **the master**, all 2,015 branches, 46 fields each (see DATA_SOURCES.md
  for the field dictionary). Everything in `platform/data/` is derived from this.
- `osm_layers.json` — 13 national OSM POI coordinate layers (~79k points; items are `[lng,lat]`).
- `estates.json` (35 industrial estates), `rayong_competitors.json` (30 live competitor branches),
  `commodity_board.json` / `commodities*.json` (Pink Sheet prices), `crop_prov_area.json` /
  `rice_prov_area.json` (province planting area), `bldg_wide.json` (3,633 Rayong buildings),
  `rayong_districts.geojson` (8 district polygons + rollups).

## How to run things
```bash
# serve the app locally (must be http, not file://, or data fetch fails)
cd platform && python3 -m http.server 8000      # open http://localhost:8000

# deploy (Kaustav's Vercel; sets root to platform/)
cd platform && npx vercel --prod                  # prints live URL

# refresh data (national features + segment scores) — now writes straight to platform/data/
cd pipeline && python3 autox_enrich_loop.py       # recompute master + derive platform/data + log iteration
cd pipeline && python3 derive.py                  # just re-project master → platform/data (no network)
cd pipeline && python3 derive.py --check          # verify committed platform/data still matches the master

# pull the BLOCKED gov data — ONLY works from a Thai/residential IP
cd pipeline && python3 autox_dgt_ingest.py        # DIW factories, DLT vehicle registrations
```
`pip install --break-system-packages shapely openlocationcode openpyxl pdfplumber` if missing.

## Hard environment constraints (read DATA_SOURCES.md for the full list)
- **REACHABLE:** Overpass (mirror `https://maps.mail.ru/osm/tools/overpass/api/interpreter`),
  Google Places, HDX, OAE (`catalog.oae.go.th`), World Bank (`thedocs.worldbank.org`).
- **BLOCKED from the sandbox's foreign IP (geo/Cloudflare):** ALL data.go.th, DLT, IMF, FRED,
  competitor corporate sites, dataforthai. **These should work from Kaustav's Thai laptop** —
  that is the single biggest reason to continue in Claude Code.
- `DATA_GO_TH_TOKEN` lives in Vercel env (project `thailand-labor-intel`). It is valid but
  useless from a foreign IP. Treat as sensitive; rotate (it was exposed in chat).

## Conventions / theme
Dark instrument-console. Fonts IBM Plex Sans Thai + IBM Plex Mono. Accent `#5B7CFA`.
Segment colors: agri/PD `#C8433B`, merchant `#1C8C7D`, collateral `#7A4FE0`, opportunity/gold `#E6B450`.
Always state whether a number is measured or estimated. Read the matching SKILL.md before generating
docx/pptx/xlsx/pdf.

## Where to go next
See `docs/NEXT_STEPS.md` (prioritized) and `docs/PROGRESS_LOG.md` (what's done + decisions).
The top three: (1) deploy and verify on Vercel, (2) run the blocked gov data from the Thai IP and
fold DLT vehicles + DIW factories into the loop, (3) replace the catchment's walk-radius estimate
with a true 15-min street-network isochrone (routing API).
