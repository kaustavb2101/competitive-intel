# CKAN_SOURCES.md — reachable Thai government open-data catalogs

The breakthrough (docs/INSIGHTS.md §3, re-verified 2026-07-09 from the cloud sandbox): the
`data.go.th` aggregator is Cloudflare-geoblocked to datacenter IPs, but several **departments' own
CKAN catalogs are not**. This is the live map of what a cloud runner / GitHub Action can actually pull,
so future sessions don't rediscover it or chase the laptop.

Probe: `GET https://<host>/api/3/action/package_search?q=&rows=0` (CKAN count endpoint).

## ✅ Reachable (HTTP 200 from the sandbox)
| Catalog | Host | Datasets | Highest-value contents |
|---|---|---|---|
| **DIW** factories | `diw-dataset.diw.go.th` | — | `factype3` (~67k category-3 factories, all 77 prov, with workers + registered capital). Used by `committee/census.py`. **MEASURED.** |
| **DLT** vehicles | `gdcatalog.dlt.go.th` | — | `dataset_1_1_04` (registered vehicles by province + type; national 44.29M — moto 23.4M / car 13.1M / pickup 6.96M). Resource URLs rotate monthly — resolve the newest CSV via the API. **MEASURED.** |
| **OAE** agriculture | `catalog.oae.go.th` | 57 | See below. **MEASURED.** |
| **NABC** live prices | `agriapi.nabc.go.th` (REST, not CKAN) | — | Daily Thai market prices — crops · livestock · fisheries. Already wired: `pull_nabc_prices.py` → `build_branch_agri.py` **and** `build_crop_stress.py` (preferred over the WB global proxy). **MEASURED.** |

### OAE (`catalog.oae.go.th`) — datasets worth pulling next
- `ai-drought-warning` — **SPEI drought index by amphoe** (per-district) — the natural measured upgrade
  for the rainfall-anomaly drought proxy in `build_crop_stress.py`. (format: HTML dashboard — needs a
  resource/scrape path.)
- `dataset66-15-03` — **net cash farm income** ฿/household (national; JSON) — objective-#1 context.
- `dataoae1104` / `dataoae1204` / `dataoae1304` / `dataoae1404` / `dataoae1504` — production quantity
  (rice / maize / cassava / rubber / oil palm), CSV/XLSX.
- `dataset-12-*` — households + planted area per crop (per-crop; mostly PDF).
- `farmer-family` — registered farmer households.

Note: OAE's CKAN is mostly **annual/national production & value** data, NOT a monthly per-crop
farm-gate PRICE series — that lives in OAE's price system. For prices, **NABC (daily, live) is already
the better source and is wired in**, so the "farm-gate price" gap is effectively closed.

## ❌ Blocked / not CKAN from the sandbox (2026-07-09)
| Catalog | Result |
|---|---|
| `data.go.th` (the aggregator) | geoblocked (Cloudflare) — the whole reason to use department catalogs |
| MOC commerce prices `data.moc.go.th` | 404 (no CKAN at this path — needs a different endpoint) |
| TMD weather `data.tmd.go.th` | 403 |
| NESDC `data.nesdc.go.th` | 502 (proxy tunnel) — GPP stays the vendored, partly-estimated file |
| DOAE `opendata.doae.go.th` | 404 |
| NSO `catalog.nso.go.th` | 418 |
| DEDE `data.dede.go.th` | SSL cert verify failed |
| LDD `catalog.ldd.go.th` | 502 |

Competitor corporate store-locators (muangthaicap / sawad / tidlor / hengleasing) are also blocked from
the datacenter IP — the national competitor census (`competitors_census.json`, 16,503 points) was
already pulled and can't refresh from CI. A real **loan-tape export** remains the only true owner-side
data unlock.

## Round-2 sweep (2026-07-09) — what else is reachable
Probed RID, MOC(alt), MOAC, DOPA, MOPH, MOTS, GISTDA, BMA, ONEP. **Only one new reachable source:**
- **ThaiWater** `api-v3.thaiwater.net` (REST, not CKAN) — reservoir / water-level / flood telemetry per
  province. Candidate upgrade for the drought/flood side of `build_crop_stress.py` (currently HDX/CHIRPS
  rainfall). Reachable; not yet wired.
All others 502 / connection-reset through the proxy (MOC, RID, MOPH, MOTS, GISTDA, BMA, ONEP, DOPA).
The reachable gov-data surface is now essentially mapped: **OAE · DIW · DLT · NABC · ThaiWater · HDX ·
World Bank · BIS · Overpass · Google Places(keyed)**.

## Round-3 deep enumeration (2026-07-09)
- **`gdcatalog.<dept>.go.th` pattern probe** — tried 13 more departments (TMD, DOA, DOAE, DIT, NSO,
  DOL, MOI, DOPA, OAE, Fisheries, DLD, MOC, OIE): **all blocked** (proxy 502). Only DLT hosts this
  reachably.
- **DLT is INTERMITTENT** — `gdcatalog.dlt.go.th` answered census.py at ~17:30 UTC, then dropped
  connections at ~19:00 (HTTP 000, "remote end closed"). The CI census job's retry loop is the right
  countermeasure; do not assume a single failed probe means blocked-forever.
- **DIW full catalog** (13 datasets): beyond `factype3` (used), the valuable ones are
  **`factype2`** (small 10–50HP factories — the small-business borrowers a title lender actually
  serves; widens the census beyond big plants), **`fac-10scurve`** (S-curve/EV-industry factories —
  feeds the EV-transition risk narrative), `fac-eec-class3`, `factype101-105-106`, `dataset_chem`.
  All pull through the same census.py CKAN path.

## Data-hunt waves (standing directive: keep finding, workaround blocks, iterate)
**Wave 1 (2026-07-09):** Wayback Machine = **403 through the proxy** (dead as a geo-block bypass);
NSO statbank blocked. **DLT window re-opened** and was exploited: 8 raw CSVs secured into
`source-data/dlt/` — first registrations BY BRAND/MODEL (BE 2565–2568) + new-registration totals →
`build_brand_trends.py` → Overview "New-vehicle market" board. Measured headlines: new-pickup
registrations collapsed (Isuzu −71%, Toyota −53% since 2022); pure-EV marques 0.2%→3.8%.
DLT also carries `dataset_stat_1_005` (driver licenses, monthly to Feb 2026) and
`dataset_stat_1_008/009` (monthly registration/tax transactions) for future pulls.

**Wave 2 (2026-07-09) — HDX deep-mine (162 Thailand datasets), verdicts:**
- Thailand **MPI** (Oxford OPHI): only national + 6 macro-regions — too coarse for the 77-province
  read. Skip (the app's NSO SES debt/income layers are finer).
- **WFP Food Prices**: 1 market (Bangkok), 4 commodities, series ENDS 2020-03 — stale; NABC live
  daily Thai prices strictly dominate. Skip.
- "Thailand – Poverty / Financial Sector / Key Indicators" = World Bank WDI national indicators —
  already covered by `pull_macro.py`. Skip.
- Still-useful HDX assets (subnational population, CHIRPS rainfall, admin boundaries) are ALREADY
  wired into the pipeline. Net: HDX adds nothing new at province granularity.

**Wave 3 (2026-07-09) — DIW deep pulls:**
- `factype2` = only **570 records nationally** — NOT the hoped small-business census. Skip.
- `fac-10scurve` = **18,091 target-industry factories** with province/workers/capital/industry-group →
  pulled + aggregated by `pull_diw_scurve.py` → `source-data/scurve_by_province.json` (55 KB, MEASURED,
  all 77 provinces). The **automotive group: 1,621 factories / 172,878 workers** = the ICE-parts
  workforce exposed to the EV transition (top: สมุทรปราการ 46.7k, ปทุมธานี 14.5k, ฉะเชิงเทรา 13.8k,
  ปราจีนบุรี, นครราชสีมา, ระยอง). Pairs with the brand-trends EV wave for the per-province risk read.
  Not yet surfaced in the app — next wave.

**Wave 4 (2026-07-09):** EV-exposure surfaced — `build_ev_exposure.py` → `platform/data/ev_exposure.json`
→ top-10 province table inside the Overview's New-vehicle market block. Gate 65/0.

**Wave 5 (2026-07-09) — ThaiWater wired:** `/public/rain_24h` = **4,460 live rain-gauge stations** with
province/amphoe/coords → `pull_thaiwater_rain.py` → `source-data/thaiwater_rain.json` (per-province
n_stations / max / p90 / %heavy / %very-heavy, Thai Met thresholds). The real-time flood/soak pulse
(live check: Songkhla 102mm max). Dam endpoints (`dam_daily` etc.) are auth-walled 403/404 — gauge
network only. Not yet surfaced in the app.

**Wave 6–7 (2026-07-09):** live rain pulse surfaced on the Overview (own #rainpulse element) +
6-hourly CI refresh workflow (data-thaiwater-rain.yml).

**Wave 8 (2026-07-09) — DLT monthly deep-pull (window re-opened):**
- `dataset_stat_1_005` driver licenses: only Bangkok-vs-regions split (67 rows) — too coarse. Skip.
- Monthly brand files: **Jan-2026 complete** (1,422 rows) → committed as
  `first_regis_brand_monthly_2569_01.csv`; Feb-2026 upstream file is a 6-row stub — skipped with a
  >500-row completeness guard in `build_brand_trends.py`. Headline: **pure-EV share 10.4% in Jan-2026**
  (vs 3.8% full-2025 — ~3× acceleration) and **BYD #4 overall, ahead of Isuzu**. Surfaced as a YTD card
  on the New-vehicle market board.

**Next-wave targets:** ~~DLT stat_1_008 monthly transaction series~~ — DONE (2026-07-10, data-
enrichment cycle): `pull_dlt_all.py`'s full-catalog mirror already secured all 50 monthly
`dataset_stat_1_008` files; `build_vehicle_flow.py` sums the trailing 12 months into
`source-data/vehicle_flow_by_province.json` (dereg_rate/transfer_rate by car/pickup/moto), joined
into `provinces/<slug>.json`'s `gov.vehicle_flow` and surfaced as a "motorcycle scrappage" impact
line on the province deep-dive. New target: `dataset_stat_1_009` (the land-transport-law sibling —
trucks/buses) is the same shape but not yet distilled; refresh the Jan-2026 monthly file set as new
months publish (manual or a future workflow).

**Wave 11 (2026-07-10) — EV penetration + NSO verdict:**
- The DLT mirror's `dataset_1_1_04` turned out to be province × vehicle type × **FUEL TYPE** (Feb-2026
  vintage) → `build_ev_penetration.py` → measured per-province BEV/electrified/diesel shares
  (national BEV stock 0.95%, Bangkok 2.20%). Joined into the Overview EV-exposure table with the
  stock-vs-flow framing (fleet 0.95% vs ~10% of new registrations).
- **NSO final verdict:** every direct host is sealed from datacenter IPs (www reachable but no open
  API; api/ittdashboard/gis/provincial 403; statbank/gdcatalog/sdg/opendata 502). Reachable mirrors:
  **ILOSTAT** (official LFS submissions, wired — wave 9), WB microdata catalog (survey METADATA only),
  UNSD SDG API (national indicators). Per-province NSO data = the vendored TMLI SES/LFS layers remain
  the finest available; a Thai-IP pull is the only refresh path.

## POI sources (Overpass / OSM)
Overpass (mirror `maps.mail.ru`) is reachable and fast. The branch feature layer is `source-data/
osm_layers.json` — **13 national layers** feeding the per-branch within-10km `k10` radar (wired through
`autox_enrich_loop.py` OSM_LAYERS → keymap → `derive.py` POI10 → app radar):
`industrial · bank · atm · convenience · hotel · civic · vehicle_commerce · fresh_market · supermarket ·
pharmacy · gold · restaurant · school`.

Candidate NEW categories (national OSM counts, 2026-07-09):
| Category | National | Verdict |
|---|---|---|
| `amenity=fuel` (fuel stations) | **5,348** | **Dense + relevant** (vehicle economy + rural reach) — the one worthwhile add. |
| `amenity=marketplace` | 706 | thin vs the existing `fresh_market` (1,965) — marginal. |
| `shop=car_repair` | 605 | overlaps `vehicle_commerce` (3,382) — marginal. |
| `shop=pawnbroker` | ~4 (Chonburi) | OSM barely tags these — the official competitor census covers pawn/title rivals far better. |
| `shop=agrarian`, rice mills | ~0–1 | OSM coverage ≈ nil in Thailand. |

Finding: the dense, high-value POI signals are **already covered** by the 13 layers, and the measured
gov census (DIW factories, DLT vehicles) **supersedes** the OSM proxies for the key collateral/industrial
signals. The single genuinely-additive layer was **fuel stations** — now SHIPPED (2026-07-09) via the
safe standalone pattern instead of the heavy enrich-loop path: `pull_fuel_stations.py` (8,706 stations,
nodes + way-centroids, top brands PT/PTT/Bangchak/Caltex/Shell) → `source-data/fuel_stations.json` →
`build_branch_fuel.py` → `platform/data/branch_fuel.json` (per-branch ≤10km count, median 11, max 214;
index-aligned + fingerprinted + gated) → one MEASURED popup line under Buildings ≤10km.
