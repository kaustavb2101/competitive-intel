# DATA SOURCES — provenance, reachability, field dictionary

## Reachability matrix (from THIS build environment — a foreign datacenter IP)

| Source | Host | Status | Notes |
|---|---|---|---|
| OpenStreetMap / Overpass | `maps.mail.ru/osm/tools/overpass/api/interpreter` | ✅ REACHABLE (fast mirror) | also `overpass.kumi.systems`. National query: `area["ISO3166-1"="TH"][admin_level=2]` |
| Google Places | (places_search tool) | ✅ | coords + reviews; best for live competitors |
| HDX (HumData) | `data.humdata.org/api/3/action/...` | ✅ | CKAN. UNFPA pop, WFP rainfall, geoBoundaries |
| OAE agriculture | `catalog.oae.go.th/api/3/action/...` | ✅ | CKAN/nginx, not Cloudflare-blocked. `www.oae.go.th`=200 |
| World Bank Pink Sheet | `thedocs.worldbank.org` | ✅ | Apache. Monthly commodity prices (xlsx) |
| NABC agriculture (live daily prices) | `agriapi.nabc.go.th/api` | ✅ | No key needed. `pull_nabc_prices.py`/`pull_nabc_agri.py` → `source-data/nabc_prices.json`/`nabc_agri.json`, preferred over the OAE/Pink-Sheet proxies in `build_crop_stress.py`/`build_branch_agri.py`/`build_macro_sensitivity.py` when present. Listed in CLAUDE.md's REACHABLE bullet; was missing from this table until this audit pass. |
| BIS Statistics (household debt-to-GDP) | `stats.bis.org/api/v2/data/dataflow/BIS` | ✅ | SDMX-JSON, `pull_macro.py` → `platform/data/macro_indicators.json` (quarterly, authoritative — paired with World Bank series in the same puller). Listed in CLAUDE.md's REACHABLE bullet; was missing from this table until this audit pass. |
| ThaiWater (rain gauges / flood/waterlevel) | `api-v3.thaiwater.net/api/v1/thaiwater30/public/...` | ✅ | `pull_thaiwater_rain.py`/`pull_thaiwater_flood.py` → `platform/data/thaiwater_rain.json`/`thaiwater_flood.json` (Overview rain/flood pulse). Was missing from this table until this audit pass. |
| ILOSTAT rplumber mirror (NSO Labour Force Survey) | `rplumber.ilo.org/data/indicator/` | ✅ | `pull_ilostat_labour.py` → `source-data/ilostat_labour.json` → `labour_context.json` (national-only; NSO's own hosts are geoblocked, see §"National labour context" below). Was missing from this table until this audit pass. |
| **data.go.th (all hosts)** | data.go.th, opend., api. | ❌ BLOCKED | Cloudflare "Access Denied" — **IP geo-block, not auth.** Token is valid but useless from here |
| **DLT (vehicles), old stat portal** | stat.dlt.go.th, web.dlt.go.th | ❌ BLOCKED | DNS-fail / 503 |
| **DLT (vehicles) / DIW (factories), own CKAN catalogs** | gdcatalog.dlt.go.th, diw-dataset.diw.go.th | ✅ REACHABLE (verified 2026-07-09) | **Different host from the blocked pair above** — the departments' own CKAN catalogs are NOT geoblocked, only the `data.go.th` aggregator + the old `stat.dlt.go.th` portal are. Refreshes from ANY cloud IP, no Thai laptop needed — see `committee/census.py` / `.github/workflows/data-gov-census.yml`. Full detail: CLAUDE.md "Hard environment constraints" + `docs/INSIGHTS.md` §3. |
| IMF / FRED / dataforthai / competitor sites (muangthaicap/sawad/tidlor/hengleasing) | various | ❌ | 403 / 503 / WAF |
| Isochrone routing (ORS / GISTDA) | `api.openrouteservice.org`, `api.sphere.gistda.or.th` | ⚠ UNTESTED | `pull_isochrone.py` exists but needs `ORS_KEY`/`GISTDA_API_KEY` (no free-tier key vendored here) — no `source-data/*_isochrone.json` has ever landed, so reachability itself is unconfirmed, distinct from the confirmed-blocked rows above. |

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

## World Bank Pink Sheet — current read (2026M06 prices)
> Refreshed 2026-07-03 (commit `adf5494`); this section previously described the stale Dec-2025
> vintage after the underlying `source-data/commodit*.json` had already moved to 2026M06 — keep this
> block in sync with `platform/data/meta.json`'s `updated` field whenever the loop re-pulls.
- **Crops mostly UP:** rice +17.9%, rubber +32.4%, palm +18.2%; sugar −13.5% (still down); maize +0.5% (flat).
- **Protein/forestry mixed:** beef +11.8%, lamb +16.7%, fishmeal +27.1%; chicken −0.6% and sawnwood
  −1.6% (flat/slightly down); logs 0.0% (flat). **Gold +26.1%** (matters to a title/gold-collateral
  lender). Shrimp still stale (2023M10, −25.0% YoY — never refreshed; excluded from the board for that reason).
- OAE Dec-2025 outlook: rice + rubber = 2026 RISK crops; cassava (Laos curbs → prices rise), palm,
  chicken, durian = firmer. *(This OAE outlook citation is independent of the Pink Sheet vintage above
  and has not been re-verified this cycle.)*
- Pink Sheet URL: the loop scrapes the current month's link off the WB landing page each pull
  (`pipeline/autox_enrich_loop.py`'s `pinksheet_url()`); last-known-good fallback hash (2026M06 vintage):
  `https://thedocs.worldbank.org/en/doc/74e8be41ceb20fa0da750cda2f6b9e4e-0050012026/related/CMO-Historical-Data-Monthly.xlsx`

## Macro (current, citable — for the Overview panel)
GDP 2026 ~1.6%; household debt 86.8% (Sep 2025); inflation ~0.3% (near-zero); tourists 2025 32.9M
(−7.2% YoY, first drop; 2026 target 35.5M); retail +2%; ฿44bn Khon La Khrueng co-payment scheme; credit contracting.

## Truck-fleet flow (`platform/data/truck_flow.json`) — logistics-SME borrower pulse
DLT land-transport-law registration-action log, `dataset_stat_1_009` (mirrored whole by
`pipeline/pull_dlt_all.py` to `source-data/dlt/raw/dataset_stat_1_009`). `pipeline/build_truck_flow.py`
sums the trailing 12 months of truck (รถบรรทุก, private + for-hire) new-registrations, transfers, and
permanent deregistrations per province, plus the same window one year earlier for a YoY read on
new-registrations. 100% MEASURED sums + plain ratios, no modelling. Surfaces on `#trend` as the
"Contracting truck fleet · province watch list". Distinct from `dataset_stat_1_008` (cars/pickups/
motorcycles — the collateral classes), which feeds `vehicle_flow_by_province.json` instead.

## National labour context (`platform/data/labour_context.json`) — the informal-borrower base
ILOSTAT rplumber mirror of Thailand's official NSO Labour Force Survey submissions
(`source-data/ilostat_labour.json`, `pipeline/pull_ilostat_labour.py`, pulled 2026-07-11 — NSO's own
hosts are geoblocked from this sandbox). `pipeline/build_labour_context.py` distills informality rate,
sector employment + trend, unemployment (total vs youth), and the agri-vs-factory hours gap.
**NATIONAL level only** — there is no cloud path to per-province LFS, so the vendored NSO SES 2566
layer (`source-data/tmli/`) remains the per-province debt/income source; this file does not claim
district or province resolution it doesn't have.

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
- `platform/data/rayong_province.json` / `rayong_catchment.json` — the rendered payloads (derived).

## Caveats to always state
- Reachable population in the catchment view = **dasymetric estimate** (floor-area × occupancy), not a
  street-network isochrone.
- Factory/POI points are **OSM** — directionally right, not a census (Map Ta Phut shows as a cluster,
  not every unit).
- `collateral_density` and the catchment vehicle layer are **proxies** until DLT vehicle data is pulled
  from the Thai IP.
