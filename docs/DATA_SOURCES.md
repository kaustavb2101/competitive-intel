# DATA SOURCES — provenance, reachability, field dictionary

## Reachability matrix (from THIS build environment — a foreign datacenter IP)

| Source | Host | Status | Notes |
|---|---|---|---|
| OpenStreetMap / Overpass | `maps.mail.ru/osm/tools/overpass/api/interpreter` | ✅ REACHABLE (fast mirror) | also `overpass.kumi.systems`. National query: `area["ISO3166-1"="TH"][admin_level=2]` |
| Google Places | (places_search tool) | ✅ | coords + reviews; best for live competitors |
| HDX (HumData) | `data.humdata.org/api/3/action/...` | ✅ | CKAN. UNFPA pop, WFP rainfall, geoBoundaries |
| OAE agriculture | `catalog.oae.go.th/api/3/action/...` | ✅ | CKAN/nginx, not Cloudflare-blocked. `www.oae.go.th`=200 |
| World Bank Pink Sheet | `thedocs.worldbank.org` | ✅ | Apache. Monthly commodity prices (xlsx) |
| **data.go.th (all hosts)** | data.go.th, opend., api. | ❌ BLOCKED | Cloudflare "Access Denied" — **IP geo-block, not auth.** Token is valid but useless from here |
| **DLT (vehicles, per-province)** | stat.dlt.go.th, web.dlt.go.th, gdcatalog.dlt.go.th | ❌ BLOCKED | DNS-fail / 503. Per-province registered-vehicle stock still needs the Thai IP |
| **MOT (vehicles, national)** | `datagov.mot.go.th` | ✅ REACHABLE | CKAN; cumulative registered vehicles by type × year (national only, not province). Folded via `pull_datagoth.py --only mot_vehicles` → `build_vehicle_registry.py` → `vehicle_registry.json` |
| IMF / FRED / dataforthai / gdcatalog / competitor sites | various | ❌ | 403 / 503 / WAF |

**The single most important fact for the handoff:** the blocked sources are blocked because this
sandbox runs on a foreign (Chicago) datacenter IP. **They should work from Kaustav's Thai residential
connection.** Running `pipeline/autox_dgt_ingest.py` from his laptop is expected to unblock DLT vehicle
registrations and DIW factories.

### data.go.th token
- Lives in Vercel env var `DATA_GO_TH_TOKEN` on project **thailand-labor-intel**
  (`prj_VLpR8SIHOSwe5NXuqMjQaTBwwJFc`).
- Valid, but Cloudflare IP-blocks the sandbox regardless of token.
- **Security:** it was exposed in chat — mark Sensitive in Vercel and **rotate it**. Don't hardcode it;
  read from env (`os.environ["DATA_GO_TH_TOKEN"]`).

## World Bank Pink Sheet — current read (2026M07 prices)
> Refreshed 2026-08-21; the underlying `source-data/commodit*.json` moved 2026M06 → 2026M07 (this
> block previously drifted to a stale Dec-2025 reading after an earlier refresh) — keep this block in
> sync with `platform/data/meta.json`'s `updated` field whenever the loop re-pulls.
- **Crops mostly UP:** rice +19.1%, rubber +24.7% (cooling off its +32% peak), palm +12.8%, maize
  +11.1% (firmed from flat); sugar −8.1% (still down, but stress easing from −13.5%).
- **Protein/forestry mixed:** beef +8.8%, lamb +19.9%, fishmeal +22.2%; chicken −2.8%, sawnwood
  −1.0% and logs −2.2% (flat/slightly soft). **Gold +21.9%** (matters to a title/gold-collateral
  lender; eased from +26.1% as spot pulled back MoM). Shrimp still stale (2023M10, −25.0% YoY — never refreshed; excluded from the board for that reason).
- OAE Dec-2025 outlook: rice + rubber = 2026 RISK crops; cassava (Laos curbs → prices rise), palm,
  chicken, durian = firmer. *(This OAE outlook citation is independent of the Pink Sheet vintage above
  and has not been re-verified this cycle.)*
- Pink Sheet URL: the loop scrapes the current month's link off the WB landing page each pull
  (`pipeline/autox_enrich_loop.py`'s `pinksheet_url()`); last-known-good fallback hash (2026M07 vintage):
  `https://thedocs.worldbank.org/en/doc/74e8be41ceb20fa0da750cda2f6b9e4e-0050012026/related/CMO-Historical-Data-Monthly.xlsx`
- **Refresh cadence:** a monthly cron now keeps this current — `.github/workflows/data-pinksheet.yml`
  runs `pipeline/pull_pinksheet.py` (the standalone, self-testing roll of the four `commodit*.json`
  source files + the `meta.updated` stamp), re-derives the board-derived fan-out + a new time-dimension
  snapshot, and opens a DRAFT PR when the WB vintage advances. Before this cron (added 2026-08-23) the
  board was refreshed only by hand / opportunistically, so it aged a month between refreshes.

## Macro (current, citable — for the Overview panel)
GDP 2026 ~1.6%; household debt 86.8% (Sep 2025); inflation ~0.3% (near-zero); tourists 2025 32.9M
(−7.2% YoY, first drop; 2026 target 35.5M); retail +2%; ฿44bn Khon La Khrueng co-payment scheme; credit contracting.

## `branches_final.json` field dictionary (the master, 2,015 records)
Identity: `code, name, prov, district, subdistrict, zip, lat, lng, prec` (geocode precision),
`phone, region` (Isan/North/South/East/Central&BKK).
Demand/POI within 10km: `demand` (f10 fuel + v10 vehicle + m10 market composite), `ind10` (industrial),
`bank10, atm10, cvs10, hotel10, civic10, fmkt10` (fresh market), `rest10` (restaurant), `super10`,
`pharm10, gold10, veh10` (vehicle commerce), `sch10` (school).
Estates: `n_estate10, nearest_estate, nearest_km, worker_demand`.
Footprint: `own10` (AutoX branches within 10km — competition-with-self).
Joined context: `dist_pop, dist_workingage` (district, ~99% joined), `rain_3mo_anom` (drought %; <100 = drier than normal).
Scores: `demand_decile, comp_model, opportunity, lead_type, lead_priority`,
**`agri_pd, merchant_demand, merchant_pd, collateral_density, tourism_score`**.

### Score definitions
- **agri_pd** = province crop-price-stress × drought, urban-suppressed, **minus** a regional livestock-income
  buffer (Isan .10, Central/East .06, North .05, South .04). Region means: Isan 61, North 56, East 34,
  South 25, Central&BKK 43. ~730–791 branches elevated. *This is the score Kaustav called "far-fetched"
  for a single province — keep it national-level, don't lead Rayong with it.*
- **merchant_demand** = z-scored (fresh_market + restaurant + supermarket + working-age-pop + tourism).
  Concentrates Central/Bangkok.
- **merchant_pd** = consumption-strain proxy (household debt, near-zero inflation, tourism dip).
- **collateral_density** = z-scored (vehicle_commerce .6 + gold .4). Proxy for title/gold collateral supply
  (DLT-blocked stand-in). Bangkok Lat Phrao is the extreme.
- **tourism_score** = per-branch, from MOTS 2024 province tourism revenue (Phuket 497, Chonburi 317,
  Bangkok ~550 volume, Surat Thani 119, Chiang Mai 104, Krabi 91 ฿bn …).

## OSM layers (`osm_layers.json`) — items are `[lng, lat]`
industrial 4789, bank 1991, atm 3274, convenience 8831, hotel 6784, civic 6751, vehicle_commerce 3382,
fresh_market 1965, supermarket 2344, pharmacy 1522, gold 769, restaurant 19409, school 17160.
(Pawnbroker too sparse at 56 to use.)

## Rayong-specific data
- `rayong_districts.geojson` — 8 amphoe polygons (geoBoundaries ADM2, matched by branch containment) +
  per-district rollups (branches, working-age, factories_avg, vehicle_avg, estates).
- `rayong_competitors.json` — 30 live competitor branches (Google Places, hand-curated). Brands:
  Srisawad / Muangthai / Tidlor / Krungsri.
- `bldg_wide.json` — 3,633 raw OSM buildings for the Mueang Rayong urban box
  (lat 12.655–12.725, lng 101.155–101.310). Pulled via Overpass. **Factory zones have ~no OSM buildings.**
- `platform/data/provinces/<slug>.json` / `rayong_catchment.json` — the rendered payloads (derived).
  (The standalone `rayong_province.json` was retired 2026-09-05; the per-province deep-dive is now
  `provinces/<slug>.json` from `build_province.py`.)

## Caveats to always state
- Reachable population in the catchment view = **dasymetric estimate** (floor-area × occupancy), not a
  street-network isochrone.
- Factory/POI points are **OSM** — directionally right, not a census (Map Ta Phut shows as a cluster,
  not every unit).
- `collateral_density` and the catchment vehicle layer are **proxies** until DLT vehicle data is pulled
  from the Thai IP.
