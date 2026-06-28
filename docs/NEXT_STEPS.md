# NEXT STEPS — prioritized backlog

Ordered by value × unblocked-ness. Each has a concrete first action so Claude Code can just start.

## 0. Replicate the Rayong deep-dive by province, then by region  ⟶ the standing ask
Rayong is the **pilot template**; the goal is the same deep-dive for every province, rolled up by
region. Anatomy of what a province view needs, and where each piece comes from:

| Piece | Source | Scales? |
|---|---|---|
| branches (filter master by prov) | `source-data/branches_final.json` | ✅ free, all 77 provinces |
| POI-within-province (10 layers) | `source-data/osm_layers.json` (national) | ✅ free |
| per-district rollups | **amphoe polygons** — only Rayong has one today | ⛔ need nationwide boundaries |
| competitors | hand-curated Google Places, **Rayong only** (30) | ⚠️ automate per province (Places) |
| "what impacts them" narrative | editorial, **Rayong only** | ⚠️ template by region, refine per province |
| catchment 3D buildings | OSM footprints, urban cores only | ⚠️ opportunistic (rural/factory zones have ~0) |

- ✅ **Done (prerequisite):** province/region keys normalized — 116→77 provinces, 0 `Other`
  (`fix_provinces.py` + `regionmap.canonical`). By-province/by-region rollups are now complete.
- **Next concrete step:** acquire **nationwide amphoe (district) polygons** — the one gating
  dataset. Try HDX `cod-ab-tha` (admin level 2) or GADM 4.1 Thailand; both should be reachable.
  Then generalize `rayong-province.html` + its JSON into a province-parameterized
  `build_province.py` that reproduces Rayong from national data + per-province inputs.
- **Then:** automate competitor pulls per province (Places, brand × province), and template the
  narrative by region (EEC-East, agri-Isan, tourism-South…) before refining per province.

## 1. Deploy to Vercel and verify production  ⟶ do first
- `cd platform && npx vercel --prod` (link to team "Kaustav Bagchi's projects"
  `team_pYNrbLMZobN80m4jD7WPWybD`; set Root Directory = current folder).
- Open the URL on a phone; click every nav item, rotate the 3D scenes.
- Then check production health (Claude Code or Claude with Vercel tools can read these):
  runtime errors + logs for the project. Existing projects incl. `autox-calibration`
  (`prj_IJwZXYYrdhobOSR2phIvf5uXHNap`).
- **Decision needed from Kaustav:** branch-level PD is sensitive → consider Vercel access protection
  (password / SSO) on the deployment.

## 2. Unblock the gov data from the Thai IP  ⟶ biggest data win, only possible locally
The whole reason to be in Claude Code on Kaustav's laptop.
- `cd pipeline && python3 autox_dgt_ingest.py` — should now reach data.go.th / DLT / DIW from a Thai connection.
  - Read the token from env, don't hardcode: `export DATA_GO_TH_TOKEN=...` (rotate the old one first).
- Targets:
  - **DLT vehicle registrations** by province/district → replace `collateral_density` proxy and the
    catchment "vehicle" layer with real counts (cars vs motorcycles vs pickups vs trucks — matters because
    motorcycle title ≈ 50% of the book, car/pickup ≈ 25%).
  - **DIW factories** (โรงงาน) → real factory census to replace OSM `ind10` proxy, esp. in factory zones
    (Pluak Daeng/Nikhom) where OSM has ~nothing.
- Then merge into `source-data/branches_final.json` and re-derive `platform/data/`.

## 3. True 15-minute isochrone (catchment view)
Replace the walk-radius dasymetric estimate with a real street-network reach polygon.
- Options: OpenRouteService (`api.openrouteservice.org`, free key, `/v2/isochrones/foot-walking`),
  or self-host Valhalla. Both fine to call from Kaustav's machine.
- Swap the circle layer in `rayong-catchment.html` for the returned isochrone polygon; recompute reachable
  population by summing building floor-area **inside the polygon** (same occupancy assumption, now honest geometry).
- Update the card footnote to say "street-network isochrone (foot-walking)".

## 4. Widen the catchment explorer beyond Mueang Rayong
- `pull_wide.py` for other urban boxes with OSM coverage (Ban Chang town, Klaeng town; check Chonburi/EEC if
  expanding). Where OSM buildings are absent (factory zones), keep the province district-polygon 3D view.
- Consider a province/area selector so the catchment view isn't hard-coded to Mueang.

## 5. Province-precise livestock & aquaculture
- DLD (livestock) and DOF (fisheries) data are **not** in the OAE datastore; currently regional-share only.
- This sharpens the agri-PD livestock buffer (the resilient-segment story). Look for DLD/DOF open data
  (likely via data.go.th from the Thai IP) or provincial statistical yearbooks.

## 6. Wire the enrichment loop straight into `platform/data/`  ⟶ DONE for national data
- ✅ `derive.py` projects `source-data/branches_final.json` → `platform/data/branches.json` + `meta.json`,
  deterministic + network-free, with `--check` (byte-exact verification of the committed output).
- ✅ `autox_enrich_loop.py` now reads/writes the real master in `source-data/`, calls `derive.py` each
  iteration, and has `--derive-only` (offline re-project). Refresh now reaches the app in one command.
- ⚠️ The livestock-buffered agri counts (`region.hi`, `n_agri`), white-space tables (`mws`/`cws`) and the
  editorial macro board are still **carried forward** by `derive.py` — they aren't recoverable from
  `source-data/` alone. To make them refresh too, have `autox_enrich_loop.py`'s scoring stage emit them
  into the master (or a sidecar) and extend `derive.py` to read them instead of carrying them.
- ⏳ Still to do: have `derive.py` also rebuild `rayong_*.json` from `bldg_wide.json` /
  `rayong_competitors.json` / `rayong_districts.geojson`; and surface the iteration log on the Overview
  tab (last-refreshed + per-source freshness).

## 7. Nice-to-haves
- Search-protection / role gating if this goes to a wider internal audience.
- A national 3D mode only where it performs (keep the 2D Leaflet default).
- Export buttons (CSV of leads per catchment) for the field team.

---

### Quick reference — IDs
- Vercel team: `team_pYNrbLMZobN80m4jD7WPWybD` ("Kaustav Bagchi's projects")
- Projects: autox-calibration `prj_IJwZXYYrdhobOSR2phIvf5uXHNap`,
  thailand-labor-intel `prj_VLpR8SIHOSwe5NXuqMjQaTBwwJFc` (holds `DATA_GO_TH_TOKEN`).
- Overpass mirror: `https://maps.mail.ru/osm/tools/overpass/api/interpreter`
