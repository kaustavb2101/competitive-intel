# NEXT STEPS — prioritized backlog

Ordered by value × unblocked-ness. Each has a concrete first action so Claude Code can just start.

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

## 6. Wire the enrichment loop straight into `platform/data/`
- Have `autox_enrich_loop.py` (or a small `derive.py`) write `branches.json` + `meta.json` +
  `rayong_*.json` directly, so "refresh + redeploy" is one command.
- Add the iteration log to the Overview tab (last-refreshed, source freshness).

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
